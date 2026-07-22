"""Conversation context-window management."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Any

from directioner.conversation.events import ConversationEvent
from directioner.conversation.state import ConversationState


@dataclass(frozen=True, slots=True)
class ContextRecord:
    role: str
    content: str
    source: str
    token_estimate: int
    user_id: str | None = None
    channel_id: str | None = None
    guild_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    records: tuple[ContextRecord, ...]
    token_budget: int
    token_estimate: int
    dropped_records: int

    @property
    def text_items(self) -> tuple[str, ...]:
        return tuple(record.content for record in self.records)


class ContextManager:
    """Maintains a bounded context window for one conversation state."""

    def __init__(self, token_budget: int = 32_000, max_records: int = 512) -> None:
        if token_budget <= 0:
            raise ValueError("token_budget must be positive")
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        self._token_budget = token_budget
        self._max_records = max_records

    @property
    def token_budget(self) -> int:
        return self._token_budget

    def remember_event(self, state: ConversationState, event: ConversationEvent) -> None:
        content = event.text.strip()
        if not content:
            return

        record = ContextRecord(
            role="user",
            content=content,
            source=event.kind.value,
            token_estimate=self.estimate_tokens(content),
            user_id=event.user_id,
            channel_id=event.channel_id,
            guild_id=event.guild_id,
            metadata=dict(event.metadata),
        )
        state.context_records.append(record)
        state.remember_text(content)
        self._trim_record_count(state)

    def remember_assistant_text(
        self,
        state: ConversationState,
        text: str,
        *,
        source: str = "assistant",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        content = text.strip()
        if not content:
            return
        state.context_records.append(
            ContextRecord(
                role="assistant",
                content=content,
                source=source,
                token_estimate=self.estimate_tokens(content),
                metadata=metadata or {},
            )
        )
        self._trim_record_count(state)

    def snapshot(self, state: ConversationState) -> ContextSnapshot:
        selected: list[ContextRecord] = []
        used_tokens = 0

        for record in reversed(state.context_records):
            if selected and used_tokens + record.token_estimate > self._token_budget:
                break
            if not selected and record.token_estimate > self._token_budget:
                selected.append(record)
                used_tokens = record.token_estimate
                break
            selected.append(record)
            used_tokens += record.token_estimate

        selected.reverse()
        return ContextSnapshot(
            records=tuple(selected),
            token_budget=self._token_budget,
            token_estimate=used_tokens,
            dropped_records=max(0, len(state.context_records) - len(selected)),
        )

    @staticmethod
    def estimate_tokens(text: str) -> int:
        stripped = text.strip()
        if not stripped:
            return 0
        return max(1, ceil(len(stripped) / 4))

    def _trim_record_count(self, state: ConversationState) -> None:
        overflow = len(state.context_records) - self._max_records
        if overflow > 0:
            del state.context_records[:overflow]

