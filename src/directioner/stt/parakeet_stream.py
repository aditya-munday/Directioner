"""NVIDIA Parakeet TDT 0.6B v2 streaming STT adapter."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from directioner.diarization.service import SpeakerSegment

logger = logging.getLogger(__name__)

_MODEL_NAME = "nvidia/parakeet-tdt-0.6b-v2"
# Parakeet expects 16 kHz mono float32
_PARAKEET_SAMPLE_RATE = 16_000


@dataclass(frozen=True, slots=True)
class TranscriptEvent:
    speaker_id: str
    text: str
    is_final: bool
    confidence: float
    start_time_ms: int | None = None
    end_time_ms: int | None = None


class ParakeetStreamingStt:
    """Wraps NeMo Parakeet TDT 0.6B v2.

    Lazy-loads the model on first push.  Accumulates audio per speaker and
    transcribes when a final (end-of-utterance) segment arrives.
    """

    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        self._model_name = model_name
        self._asr = None
        # per-speaker audio accumulator: speaker_id -> list[np.ndarray]
        self._buffers: dict[str, list[np.ndarray]] = {}

    def _load(self) -> None:
        if self._asr is not None:
            return
        logger.info("stt.load parakeet model=%s", self._model_name)
        import nemo.collections.asr as nemo_asr  # type: ignore[import-untyped]

        self._asr = nemo_asr.models.ASRModel.from_pretrained(model_name=self._model_name)
        self._asr.eval()  # type: ignore[union-attr]

    def _to_16k_mono_f32(self, segment: SpeakerSegment) -> np.ndarray:
        frame = segment.frame
        pcm_bytes = bytes(frame.payload)
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if frame.channels > 1:
            samples = samples.reshape(-1, frame.channels).mean(axis=1)
        ratio = frame.sample_rate_hz // _PARAKEET_SAMPLE_RATE
        if ratio > 1:
            samples = samples[::ratio]
        return samples

    async def push(self, segment: SpeakerSegment) -> TranscriptEvent | None:
        """Accumulate audio; transcribe and return a TranscriptEvent on final segment."""
        from directioner.audio.frames import PcmFrameFlags
        from directioner.monitoring.pipeline_metrics import track_stt

        audio = self._to_16k_mono_f32(segment)
        buf = self._buffers.setdefault(segment.speaker_id, [])
        buf.append(audio)

        is_final = bool(segment.frame.flags & PcmFrameFlags.FINAL)
        if not is_final:
            return None

        self._load()
        full_audio = np.concatenate(buf)
        self._buffers[segment.speaker_id] = []

        try:
            with track_stt():
                results = self._asr.transcribe([full_audio], batch_size=1)  # type: ignore[union-attr]
            text: str = results[0] if results else ""
        except Exception:
            logger.exception("stt.transcribe_error speaker=%s", segment.speaker_id)
            return None

        if not text.strip():
            return None

        duration_ms = int(len(full_audio) / _PARAKEET_SAMPLE_RATE * 1000)
        return TranscriptEvent(
            speaker_id=segment.speaker_id,
            text=text.strip(),
            is_final=True,
            confidence=1.0,
            start_time_ms=0,
            end_time_ms=duration_ms,
        )

    def reset(self, speaker_id: str | None = None) -> None:
        if speaker_id is not None:
            self._buffers.pop(speaker_id, None)
        else:
            self._buffers.clear()
