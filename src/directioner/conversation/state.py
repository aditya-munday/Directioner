"""Conversation state containers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from directioner.conversation.context import ContextRecord


@dataclass(slots=True)
class ActiveTask:
    task_id: str
    cancellable: bool = True
    output_destination: str = "chat"


@dataclass(slots=True)
class ConversationState:
    conversation_id: str
    active_speakers: dict[str, str] = field(default_factory=dict)
    active_task: ActiveTask | None = None
    context_items: list[str] = field(default_factory=list)
    context_records: list["ContextRecord"] = field(default_factory=list)
    interruption_count: int = 0

    def remember_text(self, text: str) -> None:
        if text:
            self.context_items.append(text)
