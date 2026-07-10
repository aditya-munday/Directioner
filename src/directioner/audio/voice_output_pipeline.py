"""Voice output pipeline: LLM text → TTS → shared-memory PCM ring."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from directioner.audio.voice_output import VoiceOutputWriter
from directioner.response.processing import ResponseProcessor

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VoiceOutputStats:
    chunks_synthesized: int = 0
    pcm_frames_written: int = 0
    cancelled: bool = False


class VoiceOutputPipeline:
    """Streams LLM response text through TTS and writes PCM to the output ring.

    Accepts a ``cancel_event`` so barge-in from the voice input pipeline can
    abort synthesis mid-stream.  Pass ``voice_input_pipeline`` to automatically
    signal output_active so the input pipeline can detect barge-in.
    """

    def __init__(
        self,
        writer: VoiceOutputWriter,
        tts,
        processor: ResponseProcessor | None = None,
        voice_input_pipeline=None,
    ) -> None:
        self._writer = writer
        self._tts = tts
        self._processor = processor or ResponseProcessor()
        self._voice_input = voice_input_pipeline

    async def speak(
        self,
        text: str,
        cancel_event: asyncio.Event | None = None,
    ) -> VoiceOutputStats:
        """Synthesize ``text`` and stream PCM to the output ring."""
        chunks = self._processor.chunk_for_tts(text)
        if not chunks:
            return VoiceOutputStats()

        if self._voice_input is not None:
            self._voice_input.set_output_active(True)

        synthesized = 0
        written = 0

        try:
            for chunk in chunks:
                if cancel_event is not None and cancel_event.is_set():
                    logger.debug("voice_output.cancelled_before_chunk text_preview=%s", chunk.text[:40])
                    return VoiceOutputStats(
                        chunks_synthesized=synthesized,
                        pcm_frames_written=written,
                        cancelled=True,
                    )

                logger.debug("voice_output.synthesize chunk=%s", chunk.text[:60])
                try:
                    async for pcm_view in self._tts.synthesize(chunk):
                        if cancel_event is not None and cancel_event.is_set():
                            logger.debug("voice_output.cancelled_mid_chunk")
                            return VoiceOutputStats(
                                chunks_synthesized=synthesized,
                                pcm_frames_written=written,
                                cancelled=True,
                            )
                        self._writer.write_pcm_s16le_stereo_48khz(bytes(pcm_view))
                        written += 1
                except Exception:
                    logger.exception("voice_output.tts_error chunk=%s", chunk.text[:60])
                    continue

                synthesized += 1

                if chunk.pause_after_ms > 0:
                    await asyncio.sleep(chunk.pause_after_ms / 1000.0)
                else:
                    await asyncio.sleep(0)

            return VoiceOutputStats(
                chunks_synthesized=synthesized,
                pcm_frames_written=written,
                cancelled=False,
            )
        finally:
            if self._voice_input is not None:
                self._voice_input.set_output_active(False)
