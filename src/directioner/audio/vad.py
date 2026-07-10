"""Silero VAD adapter for speech/silence gating."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import torch

from directioner.audio.frames import PcmFormat, PcmFrame

logger = logging.getLogger(__name__)

_SILERO_REPO = "snakers4/silero-vad"
_SILERO_MODEL = "silero_vad"

# Silero expects 16 kHz mono int16 or float32, 512-sample chunks (32 ms at 16 kHz)
_SILERO_SAMPLE_RATE = 16_000
_SILERO_CHUNK_SAMPLES = 512


@dataclass
class VadResult:
    is_speech: bool
    probability: float
    frame: PcmFrame


@dataclass
class _Resampler:
    """Minimal integer-ratio downsampler (48 kHz stereo → 16 kHz mono)."""

    in_rate: int
    out_rate: int
    channels: int

    def convert(self, pcm_s16le: bytes) -> np.ndarray:
        samples = np.frombuffer(pcm_s16le, dtype=np.int16)
        if self.channels > 1:
            samples = samples.reshape(-1, self.channels).mean(axis=1).astype(np.int16)
        ratio = self.in_rate // self.out_rate
        if ratio > 1:
            samples = samples[::ratio]
        return samples


class SileroVad:
    """Wraps the Silero VAD model.

    Lazy-loads on first call so import is cheap.  Thread-safe for single-threaded
    asyncio use; do not share across threads without a lock.
    """

    def __init__(self, threshold: float = 0.5) -> None:
        self._threshold = threshold
        self._model: torch.nn.Module | None = None
        self._utils: tuple | None = None
        self._buffer: list[np.ndarray] = []
        self._buffer_samples = 0

    def _load(self) -> None:
        if self._model is not None:
            return
        logger.info("vad.load silero")
        model, utils = torch.hub.load(
            repo_or_dir=_SILERO_REPO,
            model=_SILERO_MODEL,
            force_reload=False,
            trust_repo=True,
        )
        model.eval()
        self._model = model
        self._utils = utils

    def process(self, frame: PcmFrame) -> VadResult:
        """Run VAD on a single PcmFrame.  Returns speech probability and gate."""
        self._load()

        resampler = _Resampler(
            in_rate=frame.sample_rate_hz,
            out_rate=_SILERO_SAMPLE_RATE,
            channels=frame.channels,
        )
        pcm_bytes = bytes(frame.payload)
        if frame.sample_format == PcmFormat.F32LE:
            f32 = np.frombuffer(pcm_bytes, dtype=np.float32)
            if frame.channels > 1:
                f32 = f32.reshape(-1, frame.channels).mean(axis=1)
            ratio = frame.sample_rate_hz // _SILERO_SAMPLE_RATE
            if ratio > 1:
                f32 = f32[::ratio]
            mono16 = (f32 * 32767).clip(-32768, 32767).astype(np.int16)
        else:
            mono16 = resampler.convert(pcm_bytes)

        self._buffer.append(mono16)
        self._buffer_samples += len(mono16)

        if self._buffer_samples < _SILERO_CHUNK_SAMPLES:
            return VadResult(is_speech=False, probability=0.0, frame=frame)

        chunk = np.concatenate(self._buffer)[:_SILERO_CHUNK_SAMPLES]
        leftover = np.concatenate(self._buffer)[_SILERO_CHUNK_SAMPLES:]
        self._buffer = [leftover] if len(leftover) else []
        self._buffer_samples = len(leftover)

        tensor = torch.from_numpy(chunk.astype(np.float32) / 32768.0).unsqueeze(0)
        with torch.no_grad():
            prob: float = float(self._model(tensor, _SILERO_SAMPLE_RATE).item())  # type: ignore[operator]

        return VadResult(is_speech=prob >= self._threshold, probability=prob, frame=frame)

    def reset(self) -> None:
        if self._model is not None:
            self._model.reset_states()  # type: ignore[operator]
        self._buffer = []
        self._buffer_samples = 0
