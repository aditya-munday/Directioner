from __future__ import annotations

from dataclasses import dataclass

import pytest

from directioner.conversation.events import ConversationEvent
from directioner.discord.dpp_runtime import NativeDiscordTextEvent
from directioner.discord.event_pump import DppEventPump


@dataclass
class FakeRuntime:
    text_events: list[NativeDiscordTextEvent]

    def running(self) -> bool:
        return False

    def poll_text_event(self) -> NativeDiscordTextEvent | None:
        if not self.text_events:
            return None
        return self.text_events.pop(0)

    def poll_voice_frame(self) -> None:
        return None


class FakeRouter:
    def __init__(self) -> None:
        self.events: list[ConversationEvent] = []

    async def handle(self, event: ConversationEvent) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_event_pump_routes_native_text_event() -> None:
    runtime = FakeRuntime(
        text_events=[
            NativeDiscordTextEvent(
                guild_id=1,
                channel_id=2,
                message_id=3,
                author_id=4,
                content="hello",
                author_is_bot=False,
            )
        ]
    )
    router = FakeRouter()
    pump = DppEventPump(runtime, router)  # type: ignore[arg-type]

    routed = await pump.drain_once()

    assert routed == 1
    assert router.events[0].text == "hello"
    assert router.events[0].channel_id == "2"


@pytest.mark.asyncio
async def test_event_pump_ignores_bot_messages() -> None:
    runtime = FakeRuntime(
        text_events=[
            NativeDiscordTextEvent(
                guild_id=1,
                channel_id=2,
                message_id=3,
                author_id=4,
                content="bot",
                author_is_bot=True,
            )
        ]
    )
    router = FakeRouter()
    pump = DppEventPump(runtime, router)  # type: ignore[arg-type]

    routed = await pump.drain_once()

    assert routed == 1
    assert router.events == []
    assert pump.stats.bot_messages_ignored == 1


@pytest.mark.asyncio
async def test_event_pump_blocks_configured_moderation_terms() -> None:
    runtime = FakeRuntime(
        text_events=[
            NativeDiscordTextEvent(
                guild_id=1,
                channel_id=2,
                message_id=3,
                author_id=4,
                content="this contains spoiler",
                author_is_bot=False,
            )
        ]
    )
    router = FakeRouter()
    pump = DppEventPump(runtime, router, blocked_terms=("spoiler",))  # type: ignore[arg-type]

    routed = await pump.drain_once()

    assert routed == 1
    assert router.events == []
    assert pump.stats.moderated_events_blocked == 1


@pytest.mark.asyncio
async def test_event_pump_blocks_events_outside_permission_policy() -> None:
    runtime = FakeRuntime(
        text_events=[
            NativeDiscordTextEvent(
                guild_id=9,
                channel_id=2,
                message_id=3,
                author_id=4,
                content="hello",
                author_is_bot=False,
            )
        ]
    )
    router = FakeRouter()
    pump = DppEventPump(
        runtime,
        router,
        allowed_guild_ids=("1",),
        allowed_channel_ids=("2",),
        allowed_user_ids=("4",),
    )  # type: ignore[arg-type]

    routed = await pump.drain_once()

    assert routed == 1
    assert router.events == []
    assert pump.stats.permission_events_blocked == 1

