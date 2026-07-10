"""NVIDIA Parakeet TDT 0.6B v2 streaming STT adapter.

Production-grade implementation using:
- Silero VAD for voice activity detection
- NVIDIA Parakeet ONNX for speech recognition

Supports both:
1. Real-time streaming from shared memory (async push interface)
2. Direct microphone input (blocking interface)
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

import numpy as np
import torch

from directioner.diarization.service import SpeakerSegment

if TYPE_CHECKING:
    import onnx_asr

logger = logging.getLogger(__name__)

# Model configuration
_PARAKEET_SAMPLE_RATE = 16_000
_SILERO_SAMPLE_RATE = 16_000
_SILERO_CHUNK_SIZE = 512  # Silero VAD expects 512-sample chunks at 16kHz
_SILENCE_CHUNKS_TO_END = 20  # ~0.6s of silence ends an utterance
_MIN_AUDIO_DURATION = 0.3  # seconds - ignore tiny audio blips

# Environment for HF transfer optimization
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")


@dataclass(frozen=True, slots=True)
class TranscriptEvent:
    speaker_id: str
    text: str
    is_final: bool
    confidence: float
    start_time_ms: int | None = None
    end_time_ms: int | None = None


class ParakeetStreamingStt:
    """Production-grade Parakeet STT with Silero VAD.

    Features:
    - Silero VAD for accurate voice activity detection
    - Automatic utterance boundary detection (silence-based)
    - Per-speaker audio buffering
    - ONNX runtime for fast inference
    - Configurable model path
    """

    def __init__(
        self,
        model_name: str = "nemo-parakeet-tdt-0.6b-v2",
        model_path: str | None = None,
        vad_threshold: float = 0.5,
        silence_chunks: int = _SILENCE_CHUNKS_TO_END,
    ) -> None:
        self._model_name = model_name
        self._model_path = model_path
        self._vad_threshold = vad_threshold
        self._silence_chunks = silence_chunks

        # Lazy-loaded models
        self._vad_model = None
        self._asr_model: "onnx_asr.Model | None" = None

        # Per-speaker state: audio buffers and VAD state
        self._buffers: dict[str, list[np.ndarray]] = {}
        self._silence_counts: dict[str, int] = {}
        self._is_speaking: dict[str, bool] = {}

    def _load_vad(self) -> None:
        """Load Silero VAD model."""
        if self._vad_model is not None:
            return
        logger.info("stt.vad.load Loading Silero VAD...")
        from silero_vad import load_silero_vad

        self._vad_model = load_silero_vad()
        logger.info("stt.vad.loaded Silero VAD ready")

    def _load_asr(self) -> None:
        """Load Parakeet ONNX model."""
        if self._asr_model is not None:
            return
        logger.info("stt.parakeet.load Loading Parakeet ONNX model=%s", self._model_name)

        try:
            import onnx_asr

            if self._model_path:
                self._asr_model = onnx_asr.load_model(self._model_name, path=self._model_path)
            else:
                self._asr_model = onnx_asr.load_model(self._model_name)
            logger.info("stt.parakeet.loaded Parakeet ONNX ready")
        except ImportError:
            logger.warning("onnx_asr not installed, falling back to NeMo")
            self._load_nemo()

    def _load_nemo(self) -> None:
        """Fallback to NeMo Parakeet if ONNX not available."""
        logger.info("stt.parakeet.load_fallback Loading NeMo Parakeet...")
        import nemo.collections.asr as nemo_asr

        self._asr_model = nemo_asr.models.ASRModel.from_pretrained(model_name=self._model_name)
        self._asr_model.eval()

    def _vad_predict(self, audio: np.ndarray) -> float:
        """Run VAD on audio chunk, return speech probability."""
        self._load_vad()
        chunk_tensor = torch.from_numpy(audio).float()
        return self._vad_model(chunk_tensor, _SILERO_SAMPLE_RATE).item()

    def _transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio using Parakeet."""
        self._load_asr()

        if hasattr(self._asr_model, "recognize"):
            # ONNX model
            return self._asr_model.recognize(audio, sample_rate=_PARAKEET_SAMPLE_RATE)
        else:
            # NeMo model
            results = self._asr_model.transcribe([audio], batch_size=1)
            return results[0] if results else ""

    def _to_16k_mono_f32(self, segment: SpeakerSegment) -> np.ndarray:
        """Convert speaker segment to 16kHz mono float32."""
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
        """Process audio segment with VAD and accumulate for transcription.

        Returns TranscriptEvent when an utterance is complete (silence detected).
        Returns None while still collecting audio.
        """
        from directioner.monitoring.pipeline_metrics import track_stt

        audio = self._to_16k_mono_f32(segment)
        speaker = segment.speaker_id

        # Initialize speaker state
        buf = self._buffers.setdefault(speaker, [])
        silence_count = self._silence_counts.setdefault(speaker, 0)
        is_speaking = self._is_speaking.setdefault(speaker, False)

        # VAD check
        speech_prob = self._vad_predict(audio)

        if speech_prob > self._vad_threshold:
            is_speaking = True
            self._is_speaking[speaker] = True
            silence_count = 0
            self._silence_counts[speaker] = 0
            buf.append(audio)
        elif is_speaking:
            # Trailing silence - keep collecting briefly
            silence_count += 1
            self._silence_counts[speaker] = silence_count
            buf.append(audio)

            if silence_count > self._silence_chunks:
                # Utterance finished - transcribe
                self._is_speaking[speaker] = False

                full_audio = np.concatenate(buf)
                self._buffers[speaker] = []
                buf = []

                # Skip tiny audio blips
                duration_s = len(full_audio) / _PARAKEET_SAMPLE_RATE
                if duration_s < _MIN_AUDIO_DURATION:
                    return None

                try:
                    with track_stt():
                        text = self._transcribe(full_audio)

                    if text.strip():
                        duration_ms = int(duration_s * 1000)
                        return TranscriptEvent(
                            speaker_id=speaker,
                            text=text.strip(),
                            is_final=True,
                            confidence=1.0,
                            start_time_ms=0,
                            end_time_ms=duration_ms,
                        )
                except Exception:
                    logger.exception("stt.transcribe_error speaker=%s", speaker)

        return None

    def reset(self, speaker_id: str | None = None) -> None:
        """Reset buffers for a speaker or all speakers."""
        if speaker_id is not None:
            self._buffers.pop(speaker_id, None)
            self._silence_counts.pop(speaker_id, None)
            self._is_speaking.pop(speaker_id, None)
        else:
            self._buffers.clear()
            self._silence_counts.clear()
            self._is_speaking.clear()

    @property
    def loaded(self) -> bool:
        """Check if models are loaded."""
        return self._vad_model is not None and self._asr_model is not None


class MicrophoneTranscriber:
    """Direct microphone input transcriber for testing/debugging.

    Usage:
        async def on_transcript(text: str):
            print(f"You said: {text}")

        transcriber = MicrophoneTranscriber(on_transcript)
        await transcriber.start()  # Runs until KeyboardInterrupt
    """

    def __init__(
        self,
        on_transcript: Callable[[str], None],
        sample_rate: int = _PARAKEET_SAMPLE_RATE,
        chunk_size: int = _SILERO_CHUNK_SIZE,
        vad_threshold: float = 0.5,
        silence_chunks: int = _SILENCE_CHUNKS_TO_END,
    ) -> None:
        self._on_transcript = on_transcript
        self._sample_rate = sample_rate
        self._chunk_size = chunk_size
        self._vad_threshold = vad_threshold
        self._silence_chunks = silence_chunks

        self._audio_buffer: list[np.ndarray] = []
        self._silence_count = 0
        self._is_speaking = False
        self._running = False

        # Lazy-loaded
        self._vad = None
        self._asr = None

    def _load_models(self) -> None:
        """Load VAD and ASR models."""
        logger.info("Loading models...")
        from silero_vad import load_silero_vad

        self._vad = load_silero_vad()

        try:
            import onnx_asr

            self._asr = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v2")
            logger.info("Models loaded (ONNX)")
        except ImportError:
            import nemo.collections.asr as nemo_asr

            self._asr = nemo_asr.models.ASRModel.from_pretrained(
                model_name="nvidia/parakeet-tdt-0.6b-v2"
            )
            self._asr.eval()
            logger.info("Models loaded (NeMo)")

    def _process_chunk(self, chunk: np.ndarray) -> None:
        """Process a single audio chunk through VAD and ASR."""
        if self._vad is None:
            self._load_models()

        # VAD
        chunk_tensor = torch.from_numpy(chunk).float()
        speech_prob = self._vad(chunk_tensor, self._sample_rate).item()

        if speech_prob > self._vad_threshold:
            self._is_speaking = True
            self._silence_count = 0
            self._audio_buffer.append(chunk)
        elif self._is_speaking:
            self._silence_count += 1
            self._audio_buffer.append(chunk)

            if self._silence_count > self._silence_chunks:
                self._transcribe_and_reset()
        else:
            self._silence_count = 0

    def _transcribe_and_reset(self) -> None:
        """Transcribe accumulated audio and reset state."""
        self._is_speaking = False
        self._silence_count = 0

        full_audio = np.concatenate(self._audio_buffer)
        self._audio_buffer = []

        # Skip tiny blips
        if len(full_audio) / self._sample_rate < _MIN_AUDIO_DURATION:
            return

        # Transcribe
        if hasattr(self._asr, "recognize"):
            text = self._asr.recognize(full_audio, sample_rate=self._sample_rate)
        else:
            results = self._asr.transcribe([full_audio], batch_size=1)
            text = results[0] if results else ""

        if text.strip():
            self._on_transcript(text.strip())

    async def start(self) -> None:
        """Start listening from microphone. Runs until KeyboardInterrupt."""
        import sounddevice as sd

        self._running = True
        logger.info(
            "Microphone transcriber started. Speak into mic (Ctrl+C to stop)..."
        )

        try:
            with sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="float32",
                blocksize=self._chunk_size,
                callback=lambda indata, *_: self._process_chunk(indata[:, 0].copy()),
            ):
                while self._running:
                    await asyncio.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Microphone transcriber stopped.")

