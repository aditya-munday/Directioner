"""Voice input pipeline: shared-memory PCM → VAD → wakeword → STT → conversation."""

from __future__ import annotations

from dataclasses import dataclass

from directioner.audio.frames import PcmFrameFlags
from directioner.audio.vad import SileroVad, VadResult
from directioner.audio.voice_input import VoiceInputReader
from directioner.audio.wakeword import OpenWakeWordDetector
from directioner.conversation.events import ConversationEvent, ConversationEventKind
from directioner.conversation.router import ConversationRouter
from directioner.diarization.service import DiarizationService
from directioner.stt.parakeet_stream import ParakeetStreamingStt, TranscriptEvent
from directioner.text.cleanup import TextCleanup


@dataclass(frozen=True, slots=True)
class VoicePipelineStats:
    frames_read: int = 0
    frames_speech: int = 0
    wakeword_triggers: int = 0
    transcript_events: int = 0
    routed_events: int = 0
    barge_in_events: int = 0


class VoiceInputPipeline:
    """Drain PCM frames from shared memory through the full voice AI stack.

    Flow per frame:
      VoiceInputReader → SileroVad → [barge-in check] → OpenWakeWordDetector
        → DiarizationService → ParakeetStreamingStt → TextCleanup → ConversationRouter
    """

    def __init__(
        self,
        reader: VoiceInputReader,
        diarization: DiarizationService,
        stt: ParakeetStreamingStt,
        cleanup: TextCleanup,
        router: ConversationRouter,
        conversation_id: str,
        vad: SileroVad | None = None,
        wakeword: OpenWakeWordDetector | None = None,
        require_wakeword: bool = False,
        allow_barge_in: bool = True,
    ) -> None:
        self._reader = reader
        self._diarization = diarization
        self._stt = stt
        self._cleanup = cleanup
        self._router = router
        self._conversation_id = conversation_id
        self._vad = vad
        self._wakeword = wakeword
        self._require_wakeword = require_wakeword
        self._allow_barge_in = allow_barge_in
        # Once a wake word fires, stay active until silence resets the gate
        self._wakeword_active = not require_wakeword
        # Set to True by the output pipeline while TTS is playing
        self._output_active = False

        self._frames_read = 0
        self._frames_speech = 0
        self._wakeword_triggers = 0
        self._transcript_events = 0
        self._routed_events = 0
        self._barge_in_events = 0

    @property
    def stats(self) -> VoicePipelineStats:
        return VoicePipelineStats(
            frames_read=self._frames_read,
            frames_speech=self._frames_speech,
            wakeword_triggers=self._wakeword_triggers,
            transcript_events=self._transcript_events,
            routed_events=self._routed_events,
            barge_in_events=self._barge_in_events,
        )

    def set_output_active(self, active: bool) -> None:
        """Called by the output pipeline to signal whether TTS is currently playing."""
        self._output_active = active

    async def drain_once(self, max_frames: int = 32) -> int:
        routed = 0
        for _ in range(max_frames):
            frame = self._reader.read()
            if frame is None:
                break

            self._frames_read += 1

            # --- VAD gate ---
            if self._vad is not None:
                vad_result = self._vad.process(frame)
                if not vad_result.is_speech:
                    if self._require_wakeword:
                        self._wakeword_active = False
                    continue
                self._frames_speech += 1
                # Barge-in: speech detected while TTS output is playing
                if self._allow_barge_in and self._output_active:
                    await self._emit_barge_in()
            else:
                vad_result = VadResult(is_speech=True, probability=1.0, frame=frame)
                self._frames_speech += 1

            # --- Wake-word gate ---
            if self._wakeword is not None and self._require_wakeword:
                if not self._wakeword_active:
                    ww_event = self._wakeword.process(vad_result)
                    if ww_event is not None:
                        self._wakeword_triggers += 1
                        self._wakeword_active = True
                    else:
                        continue

            # --- Diarization → STT ---
            segment = await self._diarization.identify(frame)
            transcript = await self._stt.push(segment)
            if transcript is None:
                continue

            self._transcript_events += 1
            await self._route_transcript(transcript)
            routed += 1

        return routed

    async def _emit_barge_in(self) -> None:
        self._barge_in_events += 1
        event = ConversationEvent(
            kind=ConversationEventKind.BARGE_IN,
            conversation_id=self._conversation_id,
            user_id="voice",
            metadata={"source": "vad_barge_in"},
        )
        await self._router.handle(event)

    async def _route_transcript(self, transcript: TranscriptEvent) -> None:
        text = self._cleanup.normalize(transcript.text)
        if not text:
            return

        event = ConversationEvent(
            kind=(
                ConversationEventKind.VOICE_FINAL
                if transcript.is_final
                else ConversationEventKind.VOICE_PARTIAL
            ),
            conversation_id=self._conversation_id,
            user_id=transcript.speaker_id,
            speaker_id=transcript.speaker_id,
            text=text,
            metadata={
                "confidence": transcript.confidence,
                "start_time_ms": transcript.start_time_ms,
                "end_time_ms": transcript.end_time_ms,
                "source": "voice_pcm_in",
            },
        )
        await self._router.handle(event)
        self._routed_events += 1
