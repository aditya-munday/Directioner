from __future__ import annotations

import pytest

from directioner.audio.frames import PcmFormat, PcmFrame, PcmFrameFlags
from directioner.audio.vad import VadResult
from directioner.audio.voice_pipeline import VoiceInputPipeline
from directioner.audio.wakeword import WakeWordEvent
from directioner.conversation.events import ConversationEvent, ConversationEventKind
from directioner.diarization.service import SpeakerSegment
from directioner.stt.parakeet_stream import TranscriptEvent
from directioner.text.cleanup import TextCleanup

pytestmark = pytest.mark.asyncio


def _make_frame(flags: PcmFrameFlags = PcmFrameFlags.NONE) -> PcmFrame:
    return PcmFrame(
        stream_id=1, sequence=1, capture_time_ns=1,
        sample_rate_hz=48_000, channels=2,
        sample_format=PcmFormat.S16LE, frame_samples=1,
        payload=memoryview(b"\x00\x00\x00\x00"),
        flags=flags,
    )


class FakeReader:
    def __init__(self, frames: list[PcmFrame]) -> None:
        self._frames = list(frames)

    def read(self) -> PcmFrame | None:
        return self._frames.pop(0) if self._frames else None


class FakeDiarization:
    async def identify(self, frame: PcmFrame) -> SpeakerSegment:
        return SpeakerSegment(speaker_id="speaker-1", frame=frame, confidence=0.9)


class FakeStt:
    async def push(self, segment: SpeakerSegment) -> TranscriptEvent:
        return TranscriptEvent(
            speaker_id=segment.speaker_id,
            text=" hello   world ",
            is_final=True,
            confidence=0.8,
        )


class FakeRouter:
    def __init__(self) -> None:
        self.events: list[ConversationEvent] = []

    async def handle(self, event: ConversationEvent) -> None:
        self.events.append(event)


class FakeVad:
    def __init__(self, speech: bool) -> None:
        self._speech = speech

    def process(self, frame: PcmFrame) -> VadResult:
        return VadResult(is_speech=self._speech, probability=0.9 if self._speech else 0.0, frame=frame)

    def reset(self) -> None:
        pass


class FakeWakeWord:
    def __init__(self, trigger: bool) -> None:
        self._trigger = trigger

    def process(self, vad_result: VadResult) -> WakeWordEvent | None:
        return WakeWordEvent(model_name="hey_directioner", score=0.9) if self._trigger else None

    def reset(self) -> None:
        pass


def _pipeline(reader, vad=None, wakeword=None, require_wakeword=False) -> tuple[VoiceInputPipeline, FakeRouter]:
    router = FakeRouter()
    pipeline = VoiceInputPipeline(
        reader=reader,
        diarization=FakeDiarization(),
        stt=FakeStt(),
        cleanup=TextCleanup(),
        router=router,
        conversation_id="voice:guild:channel",
        vad=vad,
        wakeword=wakeword,
        require_wakeword=require_wakeword,
    )
    return pipeline, router


async def test_voice_pipeline_routes_final_transcript() -> None:
    p, router = _pipeline(FakeReader([_make_frame()]))
    routed = await p.drain_once()
    assert routed == 1
    assert router.events[0].kind is ConversationEventKind.VOICE_FINAL
    assert router.events[0].text == "hello world"
    assert router.events[0].speaker_id == "speaker-1"


async def test_vad_gates_silence() -> None:
    """Frames classified as silence by VAD must not reach STT."""
    p, router = _pipeline(FakeReader([_make_frame()]), vad=FakeVad(speech=False))
    routed = await p.drain_once()
    assert routed == 0
    assert router.events == []


async def test_vad_passes_speech() -> None:
    p, router = _pipeline(FakeReader([_make_frame()]), vad=FakeVad(speech=True))
    routed = await p.drain_once()
    assert routed == 1


async def test_wakeword_gates_without_trigger() -> None:
    """With require_wakeword=True and no trigger, nothing should be routed."""
    p, router = _pipeline(
        FakeReader([_make_frame()]),
        vad=FakeVad(speech=True),
        wakeword=FakeWakeWord(trigger=False),
        require_wakeword=True,
    )
    routed = await p.drain_once()
    assert routed == 0


async def test_wakeword_activates_on_trigger() -> None:
    """Wakeword fires on frame 1, gate opens; both frames continue to STT."""
    p, router = _pipeline(
        FakeReader([_make_frame(), _make_frame()]),
        vad=FakeVad(speech=True),
        wakeword=FakeWakeWord(trigger=True),
        require_wakeword=True,
    )
    routed = await p.drain_once()
    # Frame 1: wakeword fires, gate opens, frame proceeds to STT
    # Frame 2: gate already open, proceeds to STT
    assert routed == 2


async def test_stats_accumulate() -> None:
    p, _ = _pipeline(FakeReader([_make_frame(), _make_frame()]), vad=FakeVad(speech=True))
    await p.drain_once()
    assert p.stats.frames_read == 2
    assert p.stats.frames_speech == 2
    assert p.stats.routed_events == 2
