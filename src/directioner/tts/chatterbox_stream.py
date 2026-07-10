"""Chatterbox streaming TTS adapter."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import numpy as np

from directioner.response.processing import ResponseChunk

logger = logging.getLogger(__name__)

# Discord voice expects 48 kHz stereo S16LE
_DISCORD_SAMPLE_RATE = 48_000
_DISCORD_CHANNELS = 2


class ChatterboxStreamingTts:
    """Wraps the Chatterbox TTS model.

    Lazy-loads on first synthesize call.  Converts Chatterbox output (typically
    24 kHz mono float32) to 48 kHz stereo S16LE for the Discord voice output ring.
    """

    def __init__(
        self,
        device: str = "cuda",
        exaggeration: float = 0.5,
        cfg_weight: float = 0.5,
    ) -> None:
        self._device = device
        self._exaggeration = exaggeration
        self._cfg_weight = cfg_weight
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        logger.info("tts.load chatterbox device=%s", self._device)
        from chatterbox.tts import ChatterboxTTS  # type: ignore[import-untyped]

        self._model = ChatterboxTTS.from_pretrained(device=self._device)

    def _to_discord_pcm(self, audio: np.ndarray, source_rate: int) -> bytes:
        """Resample to 48 kHz, duplicate to stereo, convert to S16LE bytes."""
        # Upsample with linear interpolation if needed
        if source_rate != _DISCORD_SAMPLE_RATE:
            ratio = _DISCORD_SAMPLE_RATE / source_rate
            new_len = int(len(audio) * ratio)
            audio = np.interp(
                np.linspace(0, len(audio) - 1, new_len),
                np.arange(len(audio)),
                audio,
            )
        # Stereo interleave
        stereo = np.stack([audio, audio], axis=1).reshape(-1)
        s16 = (stereo * 32767).clip(-32768, 32767).astype(np.int16)
        return s16.tobytes()

    async def synthesize(self, chunk: ResponseChunk) -> AsyncIterator[memoryview]:
        """Synthesize text and yield 48 kHz stereo S16LE PCM chunks."""
        text = chunk.text.strip()
        if not text:
            return

        self._load()

        try:
            from directioner.monitoring.pipeline_metrics import track_tts, record_first_audio
            import time as _time
            t0 = _time.perf_counter()
            first_audio_recorded = False
            with track_tts():
                wav = self._model.generate(  # type: ignore[union-attr]
                    text,
                    exaggeration=self._exaggeration,
                    cfg_weight=self._cfg_weight,
                )
        except Exception:
            logger.exception("tts.synthesize_error text_preview=%s", text[:60])
            return

        # wav is a torch.Tensor or numpy array; normalise to float32 numpy
        try:
            audio: np.ndarray = wav.squeeze().cpu().numpy()  # type: ignore[union-attr]
        except AttributeError:
            audio = np.asarray(wav, dtype=np.float32).squeeze()

        source_rate: int = getattr(self._model, "sr", 24_000)
        pcm = self._to_discord_pcm(audio.astype(np.float32), source_rate)

        chunk_size = _DISCORD_SAMPLE_RATE * _DISCORD_CHANNELS * 2 * 20 // 1000
        first_chunk = True
        for offset in range(0, len(pcm), chunk_size):
            if first_chunk:
                from directioner.monitoring.pipeline_metrics import record_first_audio
                import time as _time
                record_first_audio(_time.perf_counter() - t0)
                first_chunk = False
            yield memoryview(pcm[offset : offset + chunk_size])
