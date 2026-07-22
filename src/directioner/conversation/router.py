"""Single routing entry point for text interactions with scaling support."""

from __future__ import annotations

from directioner.conversation.context import ContextManager
from directioner.conversation.events import ConversationEvent, ConversationEventKind
from directioner.conversation.identity import IdentityMapper
from directioner.conversation.state import ConversationState, ConversationStateManager
from directioner.conversation.summarizer import ContextSummarizer
from directioner.intent.planner import Planner
from directioner.memory.store import MemoryStore
from directioner.monitoring import event_fields, get_logger
from directioner.response.router import ResponseRouter
from directioner.text.cleanup import strip_discord_mentions

LOGGER = get_logger(__name__)


class ConversationRouter:
    def __init__(
        self,
        memory: MemoryStore,
        planner: Planner,
        responses: ResponseRouter,
        context: ContextManager | None = None,
        summarizer: ContextSummarizer | None = None,
        identity: IdentityMapper | None = None,
        state_manager: ConversationStateManager | None = None,
        max_conversations: int = 100_000,
    ) -> None:
        self._memory = memory
        self._planner = planner
        self._responses = responses
        self._context = context or ContextManager()
        self._summarizer = summarizer or ContextSummarizer()
        self._identity = identity or IdentityMapper()
        # Use the new state manager for scalable state management
        self._state_manager = state_manager or ConversationStateManager(
            max_states=max_conversations,
        )

    async def handle(self, event: ConversationEvent) -> None:
        state = self._state_manager.get_or_create(
            conversation_id=event.conversation_id,
            guild_id=event.guild_id,
            channel_id=event.channel_id,
            user_id=event.user_id,
        )

        # Resolve identity
        if event.user_id:
            self._identity.get_or_create_discord(event.user_id)

        # Handle interruption
        if event.kind is ConversationEventKind.INTERRUPTION:
            state.interruption_count += 1
            LOGGER.info(
                "conversation.interruption %s",
                event_fields(conversation_id=event.conversation_id, count=state.interruption_count),
            )
            await self._responses.cancel_active_response(state)
            return

        # Text cleanup
        cleaned_text = strip_discord_mentions(event.text)
        if not cleaned_text:
            return
        if cleaned_text != event.text:
            event = ConversationEvent(
                kind=event.kind,
                conversation_id=event.conversation_id,
                user_id=event.user_id,
                text=cleaned_text,
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
                source="chat",
            ),
        )
        await self._responses.respond(event, state, plan, self._context.snapshot(state))

    def get_state_stats(self) -> dict:
        """Get statistics about the router's state management."""
        return self._state_manager.get_stats()
