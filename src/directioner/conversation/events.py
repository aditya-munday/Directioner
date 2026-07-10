"""Internal event model used for both voice and text turns."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ConversationEventKind(StrEnum):
    VOICE_PARTIAL = "voice_partial"
    VOICE_FINAL = "voice_final"
    CHAT_MESSAGE = "chat_message"
    SLASH_COMMAND = "slash_command"
    TOOL_RESULT = "tool_result"
    INTERRUPTION = "interruption"
    BARGE_IN = "barge_in"


@dataclass(frozen=True, slots=True)
class ConversationEvent:
    kind: ConversationEventKind
    conversation_id: str
    user_id: str
    text: str = ""
    speaker_id: str | None = None
    channel_id: str | None = None
    guild_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

