"""OpenWakeWord adapter for wake-word detection."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from directioner.audio.vad import VadResult

logger = logging.getLogger(__name__)

# OWW expects 16 kHz mono float32, 1280-sample (80 ms) chunks
_OWW_SAMPLE_RATE = 16_000
_OWW_CHUNK_SAMPLES = 1280


@dataclass(frozen=True, slots=True)
class WakeWordEvent:
    model_name: str
    score: float


class OpenWakeWordDetector:
    """Wraps openwakeword.Model.

    Lazy-loads on first call.  Pass ``model_paths`` to load custom .tflite/.onnx
    models; leave empty to use the bundled pre-trained models.
    """

    def __init__(
        self,
        model_paths: list[str] | None = None,
        threshold: float = 0.5,
        inference_framework: str = "onnx",
    ) -> None:
        self._model_paths = model_paths or []
        self._threshold = threshold
        self._inference_framework = inference_framework
        self._model = None
        self._buffer: list[np.ndarray] = []
        self._buffer_samples = 0

    def _load(self) -> None:
        if self._model is not None:
            return
        import openwakeword  # type: ignore[import-untyped]
        from openwakeword.model import Model  # type: ignore[import-untyped]

        logger.info("wakeword.load openwakeword models=%s", self._model_paths or "builtin")
        openwakeword.utils.download_models()
        kwargs: dict = {"inference_framework": self._inference_framework}
        if self._model_paths:
            kwargs["wakeword_models"] = self._model_paths
        self._model = Model(**kwargs)

    def process(self, vad_result: VadResult) -> WakeWordEvent | None:
        """Feed a VAD result into OWW.  Returns a WakeWordEvent if triggered."""
        if not vad_result.is_speech:
            return None

        self._load()

        # Resample from frame rate to 16 kHz mono if needed
        frame = vad_result.frame
        pcm_bytes = bytes(frame.payload)
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        if frame.channels > 1:
            samples = samples.reshape(-1, frame.channels).mean(axis=1).astype(np.int16)
        ratio = frame.sample_rate_hz // _OWW_SAMPLE_RATE
        if ratio > 1:
            samples = samples[::ratio]

        self._buffer.append(samples)
        self._buffer_samples += len(samples)

        if self._buffer_samples < _OWW_CHUNK_SAMPLES:
            return None

        chunk = np.concatenate(self._buffer)[:_OWW_CHUNK_SAMPLES].astype(np.float32) / 32768.0
        leftover = np.concatenate(self._buffer)[_OWW_CHUNK_SAMPLES:]
        self._buffer = [leftover.astype(np.int16)] if len(leftover) else []
        self._buffer_samples = len(leftover)

        predictions: dict[str, list[float]] = self._model.predict(chunk)  # type: ignore[union-attr]
        for model_name, scores in predictions.items():
            score = float(scores[-1]) if scores else 0.0
            if score >= self._threshold:
                logger.debug("wakeword.detected model=%s score=%.3f", model_name, score)
                return WakeWordEvent(model_name=model_name, score=score)

        return None

    def reset(self) -> None:
        self._buffer = []
        self._buffer_samples = 0
