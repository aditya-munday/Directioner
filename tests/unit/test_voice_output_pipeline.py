"""Unit tests for VoiceOutputPipeline."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from directioner.audio.voice_output_pipeline import VoiceOutputPipeline
from directioner.response.processing import ResponseChunk, ResponseProcessor

pytestmark = pytest.mark.asyncio


class FakeWriter:
    def __init__(self) -> None:
        self.written: list[bytes] = []

    def write_pcm_s16le_stereo_48khz(self, pcm: bytes) -> bool:
        self.written.append(pcm)
        return True


class FakeTts:
    def __init__(self, chunks_per_call: int = 2) -> None:
        self._chunks = chunks_per_call
        self.calls: list[str] = []

    async def synthesize(self, chunk: ResponseChunk) -> AsyncIterator[memoryview]:
        self.calls.append(chunk.text)
        for i in range(self._chunks):
            yield memoryview(bytes([i, i + 1, i + 2, i + 3]))


async def test_speak_writes_pcm() -> None:
    writer = FakeWriter()
    tts = FakeTts(chunks_per_call=2)
    pipeline = VoiceOutputPipeline(writer=writer, tts=tts)

    stats = await pipeline.speak("Hello world. How are you?")

    assert stats.cancelled is False
    assert stats.chunks_synthesized >= 1
    assert stats.pcm_frames_written >= 2
    assert len(writer.written) >= 2


async def test_speak_empty_text_returns_zero_stats() -> None:
    writer = FakeWriter()
    tts = FakeTts()
    pipeline = VoiceOutputPipeline(writer=writer, tts=tts)

    stats = await pipeline.speak("   ")

    assert stats.chunks_synthesized == 0
    assert stats.pcm_frames_written == 0
    assert stats.cancelled is False
    assert writer.written == []


async def test_speak_cancelled_before_start() -> None:
    writer = FakeWriter()
    tts = FakeTts()
    pipeline = VoiceOutputPipeline(writer=writer, tts=tts)

    cancel = asyncio.Event()
    cancel.set()  # already cancelled

    stats = await pipeline.speak("Hello world.", cancel_event=cancel)

    assert stats.cancelled is True
    assert stats.pcm_frames_written == 0


async def test_speak_cancelled_mid_stream() -> None:
    """Cancel fires after the first PCM chunk is written."""
    writer = FakeWriter()
    cancel = asyncio.Event()

    class CancelAfterFirstTts:
        async def synthesize(self, chunk: ResponseChunk) -> AsyncIterator[memoryview]:
            yield memoryview(b"\x00\x01\x02\x03")
            cancel.set()  # trigger barge-in after first frame
            yield memoryview(b"\x04\x05\x06\x07")

    pipeline = VoiceOutputPipeline(writer=writer, tts=CancelAfterFirstTts())
    stats = await pipeline.speak(
        "Hello world. This is a second sentence.", cancel_event=cancel
    )

    assert stats.cancelled is True
    # At least the first frame was written before cancellation
    assert stats.pcm_frames_written >= 1


async def test_response_processor_splits_sentences() -> None:
    processor = ResponseProcessor()
    chunks = processor.chunk_for_tts(
        "Hello there. How are you doing today? I hope you are well."
    )
    assert len(chunks) == 3
    assert all(c.text for c in chunks)


async def test_response_processor_strips_markdown() -> None:
    processor = ResponseProcessor()
    chunks = processor.chunk_for_tts("**Bold text** and `code` and a https://example.com link.")
    assert chunks
    text = chunks[0].text
    assert "**" not in text
    assert "`" not in text
    assert "https" not in text
    assert "a link" in text


async def test_response_processor_empty_returns_empty() -> None:
    processor = ResponseProcessor()
    assert processor.chunk_for_tts("") == ()
    assert processor.chunk_for_tts("   ") == ()
