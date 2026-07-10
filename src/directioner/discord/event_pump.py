"""Poll native DPP events and feed Directioner's Python conversation router."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from directioner.conversation.events import ConversationEvent, ConversationEventKind
from directioner.conversation.router import ConversationRouter
from directioner.discord.dpp_runtime import DppDiscordRuntime
from directioner.monitoring import event_fields, get_logger

LOGGER = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EventPumpStats:
    text_events_routed: int = 0
    bot_messages_ignored: int = 0
    permission_events_blocked: int = 0
    moderated_events_blocked: int = 0
    voice_frames_polled: int = 0


class DppEventPump:
    def __init__(
        self,
        runtime: DppDiscordRuntime,
        router: ConversationRouter,
        poll_interval_seconds: float = 0.02,
        blocked_terms: tuple[str, ...] | None = None,
        allowed_guild_ids: tuple[str, ...] | None = None,
        allowed_channel_ids: tuple[str, ...] | None = None,
        allowed_user_ids: tuple[str, ...] | None = None,
    ) -> None:
        self._runtime = runtime
        self._router = router
        self._poll_interval_seconds = poll_interval_seconds
        configured_terms = blocked_terms
        if configured_terms is None:
            configured_terms = tuple(
                term.strip().lower()
                for term in os.getenv("DIRECTIONER_BLOCKED_TERMS", "").split(",")
                if term.strip()
            )
        self._blocked_terms = configured_terms
        self._allowed_guild_ids = _load_allowed_ids(
            allowed_guild_ids,
            env_name="DIRECTIONER_ALLOWED_GUILD_IDS",
        )
        self._allowed_channel_ids = _load_allowed_ids(
            allowed_channel_ids,
            env_name="DIRECTIONER_ALLOWED_CHANNEL_IDS",
        )
        self._allowed_user_ids = _load_allowed_ids(
            allowed_user_ids,
            env_name="DIRECTIONER_ALLOWED_USER_IDS",
        )
        self._text_events_routed = 0
        self._bot_messages_ignored = 0
        self._permission_events_blocked = 0
        self._moderated_events_blocked = 0
        self._voice_frames_polled = 0
        self._seen_message_ids: set[str] = set()

    @property
    def stats(self) -> EventPumpStats:
        return EventPumpStats(
            text_events_routed=self._text_events_routed,
            bot_messages_ignored=self._bot_messages_ignored,
            permission_events_blocked=self._permission_events_blocked,
            moderated_events_blocked=self._moderated_events_blocked,
            voice_frames_polled=self._voice_frames_polled,
        )

    async def run_forever(self) -> None:
        while self._runtime.running():
            routed = await self.drain_once()
            if routed == 0:
                await asyncio.sleep(self._poll_interval_seconds)

    async def drain_once(self) -> int:
        routed = 0
        while await self._drain_text_once():
            routed += 1

        while self._runtime.poll_voice_frame() is not None:
            self._voice_frames_polled += 1
            routed += 1

        return routed

    async def _drain_text_once(self) -> bool:
        event = self._runtime.poll_text_event()
        if event is None:
            return False
        if event.author_is_bot:
            self._bot_messages_ignored += 1
            LOGGER.debug("discord.event.ignored_bot %s", event_fields(message_id=event.message_id))
            return True
        if not self._passes_permission_policy(event):
            self._permission_events_blocked += 1
            LOGGER.info(
                "discord.event.blocked_permission %s",
                event_fields(
                    guild_id=event.guild_id,
                    channel_id=event.channel_id,
                    user_id=event.author_id,
                ),
            )
            return True
        if self._should_block_content(event.content):
            self._moderated_events_blocked += 1
            LOGGER.info(
                "discord.event.blocked_moderation %s",
                event_fields(message_id=event.message_id),
            )
            return True

        message_id = str(event.message_id)
        if message_id in self._seen_message_ids:
            return True
        self._seen_message_ids.add(message_id)

        conversation_event = ConversationEvent(
            kind=ConversationEventKind.CHAT_MESSAGE,
            conversation_id=str(event.channel_id),
            user_id=str(event.author_id),
            text=event.content,
            channel_id=str(event.channel_id),
            guild_id=str(event.guild_id),
            metadata={"message_id": str(event.message_id), "source": "dpp"},
        )
        await self._router.handle(conversation_event)
        self._text_events_routed += 1
        return True

    def _should_block_content(self, content: str) -> bool:
        lowered = content.lower()
        return any(term in lowered for term in self._blocked_terms)

    def _passes_permission_policy(self, event) -> bool:  # noqa: ANN001
        guild_id = str(event.guild_id)
        channel_id = str(event.channel_id)
        user_id = str(event.author_id)
        if self._allowed_guild_ids and guild_id not in self._allowed_guild_ids:
            return False
        if self._allowed_channel_ids and channel_id not in self._allowed_channel_ids:
            return False
        if self._allowed_user_ids and user_id not in self._allowed_user_ids:
            return False
        return True


def _load_allowed_ids(
    configured: tuple[str, ...] | None,
    *,
    env_name: str,
) -> frozenset[str]:
    if configured is not None:
        return frozenset(str(value).strip() for value in configured if str(value).strip())
    values = [
        value.strip()
        for value in os.getenv(env_name, "").split(",")
        if value.strip()
    ]
    return frozenset(values)

