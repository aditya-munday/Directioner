"""Python control layer for the native DPP Discord runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from directioner.config.settings import DiscordSettings

from directioner.native import require_native


@dataclass(frozen=True, slots=True)
class NativeDiscordTextEvent:
    guild_id: int
    channel_id: int
    message_id: int
    author_id: int
    content: str
    author_is_bot: bool


class DppDiscordRuntime:
    """Owns the native DPP bot object and presents a Python-friendly API."""

    def __init__(self, settings: "DiscordSettings") -> None:
        self._settings = settings
        native = require_native()
        self._native = native
        self._runtime = native.DppDiscordRuntime()

    def construct_smoke(self) -> str:
        return str(self._native.dpp_construct_smoke(self._build_config()))

    def start(self) -> None:
        if not self._settings.bot_token:
            raise RuntimeError("DISCORD_BOT_TOKEN is required to start the DPP runtime")
        self._runtime.start(self._build_config())

    def _build_config(self) -> object:
        config = self._native.DiscordBotConfig()
        config.token = self._settings.bot_token
        config.shard_count = self._settings.shard_count
        config.cluster_id = self._settings.cluster_id
        config.cluster_count = self._settings.cluster_count
        config.compressed = self._settings.compressed
        config.use_etf = self._settings.use_etf
        config.register_global_commands = self._settings.register_global_commands
        return config

    def stop(self) -> None:
        self._runtime.stop()

    def running(self) -> bool:
        return bool(self._runtime.running())

    def send_text_message(self, channel_id: int, content: str) -> bool:
        return bool(self._runtime.send_text_message(channel_id, content))

    def poll_text_event(self) -> NativeDiscordTextEvent | None:
        event = self._runtime.pop_text_event()
        if event is None:
            return None
        return NativeDiscordTextEvent(
            guild_id=int(event.guild_id),
            channel_id=int(event.channel_id),
            message_id=int(event.message_id),
            author_id=int(event.author_id),
            content=str(event.content),
            author_is_bot=bool(event.author_is_bot),
        )
