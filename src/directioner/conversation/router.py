"""Single routing entry point for voice and text interactions."""

from __future__ import annotations

from directioner.conversation.context import ContextManager
from directioner.conversation.events import ConversationEvent, ConversationEventKind
from directioner.conversation.identity import IdentityMapper
from directioner.conversation.state import ConversationState
from directioner.conversation.summarizer import ContextSummarizer
from directioner.intent.planner import Planner
from directioner.memory.store import MemoryStore
from directioner.monitoring import event_fields, get_logger
from directioner.response.router import ResponseRouter
from directioner.text.cleanup import strip_discord_mentions

LOGGER = get_logger(__name__)


def _voice_conversation_id(event: ConversationEvent) -> str:
    """Voice events get a separate conversation namespace so they never
    share state with the chat channel."""
    return f"voice:{event.conversation_id}"


class ConversationRouter:
    def __init__(
        self,
        memory: MemoryStore,
        planner: Planner,
        responses: ResponseRouter,
        context: ContextManager | None = None,
        summarizer: ContextSummarizer | None = None,
        identity: IdentityMapper | None = None,
    ) -> None:
        self._memory = memory
        self._planner = planner
        self._responses = responses
        self._context = context or ContextManager()
        self._summarizer = summarizer or ContextSummarizer()
        self._identity = identity or IdentityMapper()
        self._states: dict[str, ConversationState] = {}

    async def handle(self, event: ConversationEvent) -> None:
        is_voice = event.kind in {
            ConversationEventKind.VOICE_FINAL,
            ConversationEventKind.VOICE_PARTIAL,
            ConversationEventKind.BARGE_IN,
        }

        if is_voice:
            conv_id = _voice_conversation_id(event)
            event = ConversationEvent(
                kind=event.kind,
                conversation_id=conv_id,
                user_id=event.user_id,
                text=event.text,
                speaker_id=event.speaker_id,
                channel_id=event.channel_id,
                guild_id=event.guild_id,
                metadata=event.metadata,
            )

        state = self._states.setdefault(
            event.conversation_id,
            ConversationState(conversation_id=event.conversation_id),
        )

        # Resolve identity: map speaker label to a display name
        if is_voice and event.speaker_id:
            profile = self._identity.get_or_create_speaker(event.speaker_id)
            # If the event carries a discord_id hint, link them
            discord_hint = event.metadata.get("discord_id")
            if discord_hint:
                self._identity.link_speaker_to_discord(event.speaker_id, str(discord_hint))
        elif not is_voice and event.user_id:
            self._identity.get_or_create_discord(event.user_id)

        # BARGE_IN: cancel active voice synthesis immediately
        if event.kind is ConversationEventKind.BARGE_IN:
            state.interruption_count += 1
            LOGGER.info(
                "conversation.barge_in %s",
                event_fields(conversation_id=event.conversation_id, count=state.interruption_count),
            )
            await self._responses.cancel_active_response(state)
            return

        if event.kind is ConversationEventKind.INTERRUPTION:
            state.interruption_count += 1
            LOGGER.info(
                "conversation.interruption %s",
                event_fields(conversation_id=event.conversation_id, count=state.interruption_count),
            )
            await self._responses.cancel_active_response(state)
            return

        # Text cleanup
        if is_voice:
            cleaned_text = event.text
        else:
            cleaned_text = strip_discord_mentions(event.text)
            if not cleaned_text:
                return
            if cleaned_text != event.text:
                event = ConversationEvent(
                    kind=event.kind,
                    conversation_id=event.conversation_id,
                    user_id=event.user_id,
                    text=cleaned_text,
                    speaker_id=event.speaker_id,
                    channel_id=event.channel_id,
                    guild_id=event.guild_id,
                    metadata=event.metadata,
                )

        if not event.text.strip():
            return

        # Summarize context if over budget before adding new record
        await self._summarizer.maybe_summarize(state, self._context)

        self._context.remember_event(state, event)
        memory_context = await self._memory.retrieve(event, state)
        self._memory.record_event(event)
        plan = await self._planner.plan(event, state, memory_context)
        LOGGER.info(
            "conversation.plan %s",
            event_fields(
                conversation_id=event.conversation_id,
                kind=plan.kind.value,
                channel_id=event.channel_id,
                source="voice" if is_voice else "chat",
            ),
        )
        await self._responses.respond(event, state, plan, self._context.snapshot(state))
