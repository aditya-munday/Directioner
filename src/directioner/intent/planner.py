"""Intent and planning facade."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TYPE_CHECKING

from directioner.conversation.events import ConversationEvent
from directioner.conversation.state import ConversationState

if TYPE_CHECKING:
    from directioner.memory.store import MemoryContext


class PlanKind(StrEnum):
    CHAT = "chat"
    TOOL = "tool"
    SEARCH = "search"
    COMMAND = "command"
    MULTI_STEP = "multi_step"


@dataclass(frozen=True, slots=True)
class Plan:
    kind: PlanKind
    prompt: str
    tool_names: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class Planner:
    def __init__(
        self,
        *,
        max_prompt_chars: int = 4_000,
        blocked_patterns: tuple[str, ...] = (
            r"ignore\s+previous\s+instructions",
            r"reveal\s+system\s+prompt",
            r"developer\s+message",
        ),
    ) -> None:
        self._max_prompt_chars = max_prompt_chars
        self._blocked_patterns = tuple(
            re.compile(pattern, flags=re.IGNORECASE) for pattern in blocked_patterns
        )

    async def plan(
        self,
        event: ConversationEvent,
        state: ConversationState,
        memory: MemoryContext,
    ) -> Plan:
        _ = state
        prompt = event.text.strip()
        metadata: dict[str, Any] = {"memory": memory}

        if not prompt:
            return Plan(kind=PlanKind.CHAT, prompt="", metadata=metadata)

        safety_flags: list[str] = []
        for pattern in self._blocked_patterns:
            if pattern.search(prompt):
                safety_flags.append(pattern.pattern)
        if len(prompt) > self._max_prompt_chars:
            prompt = prompt[: self._max_prompt_chars]
            safety_flags.append("prompt_truncated")
        if safety_flags:
            metadata["safety_flags"] = tuple(safety_flags)

        lowered = prompt.lower()
        if self._should_use_calculator(lowered):
            return Plan(
                kind=PlanKind.TOOL,
                prompt=prompt,
                tool_names=("calculator",),
                metadata=metadata,
            )
        if self._should_use_web_search(lowered):
            return Plan(
                kind=PlanKind.TOOL,
                prompt=prompt,
                tool_names=("web_search",),
                metadata=metadata,
            )
        if self._should_set_preference(lowered):
            return Plan(
                kind=PlanKind.TOOL,
                prompt=prompt,
                tool_names=("set_user_preference",),
                metadata=metadata,
            )
        if self._should_use_multi_step(lowered):
            return Plan(kind=PlanKind.MULTI_STEP, prompt=prompt, metadata=metadata)

        return Plan(
            kind=PlanKind.CHAT,
            prompt=prompt,
            metadata=metadata,
        )

    @staticmethod
    def _should_use_calculator(lowered_prompt: str) -> bool:
        return any(word in lowered_prompt for word in ("calculate", "calc", "compute"))

    @staticmethod
    def _should_use_web_search(lowered_prompt: str) -> bool:
        return any(
            phrase in lowered_prompt
            for phrase in ("search ", "look up", "lookup ", "find on web", "web search")
        )

    @staticmethod
    def _should_set_preference(lowered_prompt: str) -> bool:
        return "remember " in lowered_prompt or "my preference" in lowered_prompt

    @staticmethod
    def _should_use_multi_step(lowered_prompt: str) -> bool:
        return any(
            phrase in lowered_prompt
            for phrase in (
                "step by step",
                "multi step",
                "plan this",
                "think through",
            )
        )

