"""Unit tests for Discord action tools."""

from __future__ import annotations

import pytest

from directioner.tools.discord_actions import (
    discord_add_reaction_tool,
    discord_kick_from_voice_tool,
    discord_move_voice_tool,
    discord_send_message_tool,
)

pytestmark = pytest.mark.asyncio


class FakeChatSender:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send(self, channel_id: int, content: str) -> None:
        self.sent.append((channel_id, content))


class FakeRuntime:
    def __init__(self) -> None:
        self.reactions: list[tuple] = []
        self.moves: list[tuple] = []
        self.kicks: list[tuple] = []

    async def add_reaction(self, channel_id, message_id, emoji):
        self.reactions.append((channel_id, message_id, emoji))

    async def move_member_voice(self, guild_id, user_id, channel_id):
        self.moves.append((guild_id, user_id, channel_id))

    async def disconnect_member_voice(self, guild_id, user_id):
        self.kicks.append((guild_id, user_id))


async def test_send_message_tool() -> None:
    sender = FakeChatSender()
    tool = discord_send_message_tool(sender)
    result = await tool.handler({"channel_id": "111", "content": "hello"})
    assert result["ok"] is True
    assert sender.sent == [(111, "hello")]


async def test_send_message_tool_missing_args() -> None:
    sender = FakeChatSender()
    tool = discord_send_message_tool(sender)
    with pytest.raises(ValueError):
        await tool.handler({"channel_id": "111"})


async def test_add_reaction_tool() -> None:
    runtime = FakeRuntime()
    tool = discord_add_reaction_tool(runtime)
    result = await tool.handler({"channel_id": "1", "message_id": "2", "emoji": "🎉"})
    assert result["ok"] is True
    assert runtime.reactions == [(1, 2, "🎉")]


async def test_move_voice_tool() -> None:
    runtime = FakeRuntime()
    tool = discord_move_voice_tool(runtime)
    result = await tool.handler({"guild_id": "10", "user_id": "20", "channel_id": "30"})
    assert result["ok"] is True
    assert runtime.moves == [(10, 20, 30)]


async def test_kick_from_voice_tool() -> None:
    runtime = FakeRuntime()
    tool = discord_kick_from_voice_tool(runtime)
    result = await tool.handler({"guild_id": "10", "user_id": "20"})
    assert result["ok"] is True
    assert runtime.kicks == [(10, 20)]


async def test_kick_from_voice_missing_args() -> None:
    runtime = FakeRuntime()
    tool = discord_kick_from_voice_tool(runtime)
    with pytest.raises(ValueError):
        await tool.handler({"guild_id": "10"})
