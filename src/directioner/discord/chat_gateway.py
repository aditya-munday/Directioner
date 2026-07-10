"""Discord text channel integration — full chat input pipeline.

Stages:
  raw Discord message
    → bot filter
    → mention detection
    → slash command detection
    → thread / reply detection
    → attachment processor
    → markdown / formatting strip
    → Chat Context Builder
    → ConversationRouter
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from directioner.conversation.events import ConversationEvent, ConversationEventKind
from directioner.conversation.router import ConversationRouter
from directioner.discord.slash_commands import SlashCommandHandler, get_slash_command_handler

logger = logging.getLogger(__name__)

_MENTION_RE = re.compile(r"<@!?(\d+)>")
_CHANNEL_MENTION_RE = re.compile(r"<#\d+>")
_ROLE_MENTION_RE = re.compile(r"<@&\d+>")
_SLASH_CMD_RE = re.compile(r"^/(\w+)")
_URL_RE = re.compile(r"https?://\S+")


@dataclass(frozen=True, slots=True)
class DiscordAttachment:
    filename: str
    url: str
    content_type: str = ""
    size_bytes: int = 0


@dataclass(frozen=True, slots=True)
class DiscordMessage:
    guild_id: str
    channel_id: str
    author_id: str
    content: str
    message_id: str
    thread_id: str | None = None
    reply_to_message_id: str | None = None
    bot_id: str | None = None                          # the bot's own Discord ID
    attachments: tuple[DiscordAttachment, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParsedChatMessage:
    """Normalised view of an incoming Discord message."""
    raw: DiscordMessage
    is_mention: bool
    is_slash_command: bool
    slash_command: str | None
    clean_text: str                    # mentions/markup stripped
    attachment_summary: str            # human-readable attachment list for LLM
    conversation_id: str               # channel or thread id
    reply_to_message_id: str | None


class ChatGateway:
    """Full Discord chat input pipeline.

    Handles:
    - Bot self-message filtering
    - Mention detection (responds only when mentioned or in DM)
    - Slash command routing
    - Thread / reply context
    - Attachment summarisation for LLM context
    - Typing indicator signalling
    """

    def __init__(
        self,
        router: ConversationRouter,
        bot_id: str | None = None,
        require_mention: bool = True,
        typing_sender=None,           # optional: object with send_typing(channel_id)
        slash_handler: SlashCommandHandler | None = None,
    ) -> None:
        self._router = router
        self._bot_id = bot_id
        self._require_mention = require_mention
        self._typing_sender = typing_sender
        self._slash_handler = slash_handler or get_slash_command_handler()
    
    async def _handle_slash_command(
        self,
        command: str,
        channel_id: str,
        sender: Any,
    ) -> bool:
        """Handle a slash command directly. Returns True if handled."""
        result = await self._slash_handler.execute(command, {})
        if result is None:
            return False
        
        message, _ = result
        try:
            await sender.send(int(channel_id), message)
        except Exception:
            logger.exception("chat.slash_command.send_failed channel=%s", channel_id)
        return True

    async def handle_message(self, message: DiscordMessage, sender=None) -> None:
        parsed = self._parse(message)
        if parsed is None:
            return

        logger.debug(
            "chat.handle channel=%s user=%s mention=%s slash=%s",
            message.channel_id, message.author_id,
            parsed.is_mention, parsed.is_slash_command,
        )

        # Handle persona/system slash commands directly without LLM
        if parsed.is_slash_command and parsed.slash_command:
            # Try to handle as a built-in slash command first
            if sender is not None:
                handled = await self._handle_slash_command(
                    parsed.slash_command,
                    message.channel_id,
                    sender,
                )
                if handled:
                    return
            
            # If not handled by built-in, route to LLM for custom commands
            kind = ConversationEventKind.SLASH_COMMAND
        else:
            kind = ConversationEventKind.CHAT_MESSAGE

        # Send typing indicator before routing (fire-and-forget)
        if self._typing_sender is not None:
            try:
                await self._typing_sender.send_typing(int(message.channel_id))
            except Exception:
                pass

        text = parsed.clean_text
        if parsed.attachment_summary:
            text = f"{text}\n[Attachments: {parsed.attachment_summary}]".strip()

        event = ConversationEvent(
            kind=kind,
            conversation_id=parsed.conversation_id,
            user_id=message.author_id,
            text=text,
            channel_id=message.channel_id,
            guild_id=message.guild_id,
            metadata={
                "message_id": message.message_id,
                "reply_to_message_id": parsed.reply_to_message_id,
                "slash_command": parsed.slash_command,
                "source": "chat_gateway",
                **message.metadata,
            },
        )
        await self._router.handle(event)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _parse(self, message: DiscordMessage) -> ParsedChatMessage | None:
        content = message.content or ""

        # Detect mention
        mentioned_ids = _MENTION_RE.findall(content)
        is_mention = self._bot_id in mentioned_ids if self._bot_id else bool(mentioned_ids)

        # Detect slash command
        slash_match = _SLASH_CMD_RE.match(content.strip())
        is_slash = slash_match is not None
        slash_command = slash_match.group(1) if slash_match else None

        # Require mention unless it's a slash command or DM (no guild)
        if self._require_mention and not is_mention and not is_slash and message.guild_id:
            return None

        # Strip all mention markup and clean up
        clean = _MENTION_RE.sub("", content)
        clean = _CHANNEL_MENTION_RE.sub("", clean)
        clean = _ROLE_MENTION_RE.sub("", clean)
        clean = " ".join(clean.split())

        # Attachment summary
        attachment_summary = self._summarise_attachments(message.attachments)

        # Conversation ID: prefer thread, then channel
        conversation_id = message.thread_id or message.channel_id

        return ParsedChatMessage(
            raw=message,
            is_mention=is_mention,
            is_slash_command=is_slash,
            slash_command=slash_command,
            clean_text=clean,
            attachment_summary=attachment_summary,
            conversation_id=conversation_id,
            reply_to_message_id=message.reply_to_message_id,
        )

    @staticmethod
    def _summarise_attachments(attachments: tuple[DiscordAttachment, ...]) -> str:
        if not attachments:
            return ""
        parts: list[str] = []
        for att in attachments:
            ct = att.content_type or "file"
            parts.append(f"{att.filename} ({ct})")
        return ", ".join(parts)
