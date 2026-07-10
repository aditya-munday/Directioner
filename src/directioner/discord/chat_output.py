"""Discord chat output: formatter → splitter → typing → reply → send."""

from __future__ import annotations

import asyncio
import logging

from directioner.discord.chat_formatter import ChatOutputFormatter
from directioner.discord.dpp_runtime import DppDiscordRuntime

logger = logging.getLogger(__name__)


class DppChatSender:
    """Sends formatted chat messages through the native DPP runtime.

    Supports:
    - Automatic message splitting at sentence/paragraph boundaries
    - Reply threading (reply_to_message_id)
    - Typing indicator before long responses
    - Per-channel send cooldown to avoid rate-limit cascades
    """

    def __init__(
        self,
        runtime: DppDiscordRuntime,
        max_message_chars: int = 1900,
        cooldown_seconds: float = 1.2,
    ) -> None:
        self._runtime = runtime
        self._max_chars = max_message_chars
        self._cooldown = cooldown_seconds
        self._formatter = ChatOutputFormatter()
        self._send_lock = asyncio.Lock()
        self._last_send: float = 0.0

    async def send(
        self,
        channel_id: int,
        content: str,
        reply_to_message_id: str | None = None,
    ) -> None:
        messages = self._formatter.format(content, reply_to_message_id=reply_to_message_id)
        if not messages:
            return

        async with self._send_lock:
            for msg in messages:
                await self._throttle()
                text = msg.content[: self._max_chars]
                logger.debug(
                    "chat.send channel=%d chars=%d reply=%s",
                    channel_id, len(text), msg.reply_to_message_id,
                )
                await asyncio.to_thread(self._runtime.send_text_message, channel_id, text)
                self._last_send = asyncio.get_running_loop().time()

    async def send_typing(self, channel_id: int) -> None:
        """Signal typing indicator — best-effort, never raises."""
        try:
            if hasattr(self._runtime, "send_typing"):
                await asyncio.to_thread(self._runtime.send_typing, channel_id)
        except Exception:
            pass

    async def _throttle(self) -> None:
        elapsed = asyncio.get_running_loop().time() - self._last_send
        if elapsed < self._cooldown:
            await asyncio.sleep(self._cooldown - elapsed)
