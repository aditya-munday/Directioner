"""Discord chat integration adapters (text-only mode)."""

from directioner.discord.dpp_runtime import (
    DppDiscordRuntime,
    NativeDiscordTextEvent,
)

__all__ = [
    "DppDiscordRuntime",
    "NativeDiscordTextEvent",
]
