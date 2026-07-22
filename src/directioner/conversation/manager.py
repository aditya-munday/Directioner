"""Conversation manager composition root."""

from __future__ import annotations

from directioner.config.settings import ConversationSettings, MemorySettings
from directioner.conversation.context import ContextManager
from directioner.conversation.router import ConversationRouter
from directioner.intent.planner import Planner
from directioner.memory.store import MemoryStore
from directioner.response.router import ResponseRouter


def build_conversation_router(
    responses: ResponseRouter | None = None,
    settings: ConversationSettings | None = None,
    memory_settings: MemorySettings | None = None,
) -> ConversationRouter:
    memory = MemoryStore(memory_settings)
    planner = Planner()

    if responses is None:
        responses = ResponseRouter(memory=memory)

    if responses._memory is None:
        responses._memory = memory

    context = ContextManager(
        token_budget=settings.context_window_tokens if settings else 32_000,
    )
    return ConversationRouter(
        memory=memory,
        planner=planner,
        responses=responses,
        context=context,
    )
