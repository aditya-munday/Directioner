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
    voice_output_pipeline=None,
    tts=None,
    voice_output=None,
) -> ConversationRouter:
    memory = MemoryStore(memory_settings)
    planner = Planner()

    if responses is None:
        responses = ResponseRouter(
            memory=memory,
            voice_output_pipeline=voice_output_pipeline,
            tts=tts,
            voice_output=voice_output,
        )
    else:
        # Inject voice components into an already-constructed ResponseRouter
        if voice_output_pipeline is not None and responses._voice_output_pipeline is None:
            responses._voice_output_pipeline = voice_output_pipeline
        if tts is not None and responses._tts is None:
            responses._tts = tts
        if voice_output is not None and responses._voice_output is None:
            responses._voice_output = voice_output

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
