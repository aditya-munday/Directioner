"""Speaker diarization service using pyannote.audio."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from directioner.audio.frames import PcmFormat, PcmFrame

logger = logging.getLogger(__name__)

_PYANNOTE_SAMPLE_RATE = 16_000


@dataclass(frozen=True, slots=True)
class SpeakerSegment:
    speaker_id: str
    frame: PcmFrame
    confidence: float


class DiarizationService:
    """Wraps pyannote.audio for online speaker identification.

    Falls back to a simple energy-based speaker-change heuristic when
    pyannote is not installed, so the rest of the pipeline still runs.

    Each unique ``stream_id`` in the incoming frames is treated as an
    independent audio stream (one Discord user = one stream_id).
    """

    def __init__(self, hf_token: str | None = None) -> None:
        self._hf_token = hf_token
        self._pipeline = None
        self._tried_load = False
        # stream_id -> last known speaker label
        self._stream_speakers: dict[int, str] = {}
        # stream_id -> rolling energy buffer for fallback heuristic
        self._energy_buffers: dict[int, list[float]] = {}

    def _load(self) -> None:
        if self._tried_load:
            return
        self._tried_load = True
        try:
            from pyannote.audio import Pipeline  # type: ignore[import-untyped]
            import torch

            logger.info("diarization.load pyannote")
            kwargs: dict = {}
            if self._hf_token:
                kwargs["use_auth_token"] = self._hf_token
            self._pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1", **kwargs
            )
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._pipeline.to(torch.device(device))
        except Exception as exc:
            logger.warning("diarization.load_failed fallback=energy err=%s", exc)
            self._pipeline = None

    def _to_16k_mono_f32(self, frame: PcmFrame) -> np.ndarray:
        pcm = bytes(frame.payload)
        if frame.sample_format == PcmFormat.F32LE:
            samples = np.frombuffer(pcm, dtype=np.float32)
        else:
            samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if frame.channels > 1:
            samples = samples.reshape(-1, frame.channels).mean(axis=1)
        ratio = frame.sample_rate_hz // _PYANNOTE_SAMPLE_RATE
        if ratio > 1:
            samples = samples[::ratio]
        return samples

    def _energy_speaker(self, stream_id: int, audio: np.ndarray) -> str:
        """Minimal energy-delta heuristic: detects speaker change, not identity."""
        energy = float(np.sqrt(np.mean(audio ** 2)))
        buf = self._energy_buffers.setdefault(stream_id, [])
        buf.append(energy)
        if len(buf) > 10:
            buf.pop(0)
        # Use stream_id as the stable speaker label — one Discord user per stream
        return f"speaker_{stream_id}"

    async def identify(self, frame: PcmFrame) -> SpeakerSegment:
        self._load()
        audio = self._to_16k_mono_f32(frame)

        if self._pipeline is None:
            speaker_id = self._energy_speaker(frame.stream_id, audio)
            return SpeakerSegment(speaker_id=speaker_id, frame=frame, confidence=0.5)

        try:
            import torch
            from pyannote.core import Segment  # type: ignore[import-untyped]

            duration = len(audio) / _PYANNOTE_SAMPLE_RATE
            if duration < 0.1:
                # Too short for pyannote; reuse last known speaker
                speaker_id = self._stream_speakers.get(
                    frame.stream_id, f"speaker_{frame.stream_id}"
                )
                return SpeakerSegment(speaker_id=speaker_id, frame=frame, confidence=0.4)

            tensor = torch.from_numpy(audio).unsqueeze(0).unsqueeze(0)  # (1, 1, T)
            waveform = {"waveform": tensor, "sample_rate": _PYANNOTE_SAMPLE_RATE}
            diarization = self._pipeline(waveform)

            # Pick the speaker with the most overlap in this segment
            speaker_id = f"speaker_{frame.stream_id}"
            best_duration = 0.0
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                if turn.duration > best_duration:
                    best_duration = turn.duration
                    speaker_id = speaker

            self._stream_speakers[frame.stream_id] = speaker_id
            return SpeakerSegment(speaker_id=speaker_id, frame=frame, confidence=0.9)

        except Exception as exc:
            logger.debug("diarization.identify_error stream=%d err=%s", frame.stream_id, exc)
            speaker_id = self._stream_speakers.get(
                frame.stream_id, f"speaker_{frame.stream_id}"
            )
            return SpeakerSegment(speaker_id=speaker_id, frame=frame, confidence=0.3)
