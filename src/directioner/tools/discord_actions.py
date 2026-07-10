"""Discord action tools exposed to the LLM tool registry."""

from __future__ import annotations

import logging
from typing import Any

from directioner.tools.registry import ToolSpec

logger = logging.getLogger(__name__)


def discord_send_message_tool(chat_sender) -> ToolSpec:
    """Send a message to a Discord channel."""

    async def _handle(arguments: dict[str, Any]) -> dict[str, Any]:
        channel_id = arguments.get("channel_id")
        content = str(arguments.get("content", "")).strip()
        if not channel_id or not content:
            raise ValueError("channel_id and content are required")
        await chat_sender.send(int(channel_id), content)
        return {"ok": True, "channel_id": str(channel_id)}

    return ToolSpec(
        name="discord_send_message",
        description="Send a text message to a Discord channel by channel_id.",
        handler=_handle,
    )


def discord_add_reaction_tool(runtime) -> ToolSpec:
    """Add an emoji reaction to a Discord message."""

    async def _handle(arguments: dict[str, Any]) -> dict[str, Any]:
        channel_id = arguments.get("channel_id")
        message_id = arguments.get("message_id")
        emoji = str(arguments.get("emoji", "👍")).strip()
        if not channel_id or not message_id:
            raise ValueError("channel_id and message_id are required")
        # Best-effort: runtime may not support this yet
        if hasattr(runtime, "add_reaction"):
            await runtime.add_reaction(int(channel_id), int(message_id), emoji)
        return {"ok": True, "emoji": emoji}

    return ToolSpec(
        name="discord_add_reaction",
        description="Add an emoji reaction to a Discord message.",
        handler=_handle,
    )


def discord_move_voice_tool(runtime) -> ToolSpec:
    """Move a user to a different voice channel."""

    async def _handle(arguments: dict[str, Any]) -> dict[str, Any]:
        guild_id = arguments.get("guild_id")
        user_id = arguments.get("user_id")
        channel_id = arguments.get("channel_id")
        if not guild_id or not user_id or not channel_id:
            raise ValueError("guild_id, user_id, and channel_id are required")
        if hasattr(runtime, "move_member_voice"):
            await runtime.move_member_voice(int(guild_id), int(user_id), int(channel_id))
        return {"ok": True, "user_id": str(user_id), "channel_id": str(channel_id)}

    return ToolSpec(
        name="discord_move_to_voice",
        description="Move a Discord user to a different voice channel.",
        handler=_handle,
    )


def discord_kick_from_voice_tool(runtime) -> ToolSpec:
    """Disconnect a user from their current voice channel."""

    async def _handle(arguments: dict[str, Any]) -> dict[str, Any]:
        guild_id = arguments.get("guild_id")
        user_id = arguments.get("user_id")
        if not guild_id or not user_id:
            raise ValueError("guild_id and user_id are required")
        if hasattr(runtime, "disconnect_member_voice"):
            await runtime.disconnect_member_voice(int(guild_id), int(user_id))
        return {"ok": True, "user_id": str(user_id)}

    return ToolSpec(
        name="discord_kick_from_voice",
        description="Disconnect a Discord user from their current voice channel.",
        handler=_handle,
    )
