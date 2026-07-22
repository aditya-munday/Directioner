"""Route generated responses to Discord chat with error handling."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Protocol

from directioner.config.settings import LlmSettings
from directioner.conversation.context import ContextSnapshot
from directioner.conversation.events import ConversationEvent
from directioner.conversation.state import ConversationState
from directioner.intent.planner import Plan, PlanKind
from directioner.llm.client import (
    LlmClient,
    LlmError,
    LlmRateLimitError,
    LlmRequest,
    LlmMessage,
    build_llm_client,
)
from directioner.memory.store import MemoryStore
from directioner.monitoring import event_fields, get_logger
from directioner.tools import build_default_registry, ToolRegistry, set_user_preference_tool, delete_user_preference_tool

# Content limits
MAX_MESSAGE_LENGTH = 2000


class ChatSender(Protocol):
    async def send(self, channel_id: int, content: str) -> None: ...


ChatResponder = Callable[[ConversationEvent, ConversationState, Plan], Awaitable[str]]
LOGGER = get_logger(__name__)


async def default_chat_responder(
    event: ConversationEvent,
    state: ConversationState,
    plan: Plan,
) -> str:
    _ = event, state
    if plan.prompt.strip():
        return "I received the message. The LLM layer is ready to be wired into this slot."
    return "I am online."


class ResponseRouter:
    def __init__(
        self,
        chat_sender: ChatSender | None = None,
        chat_responder: ChatResponder | None = None,
        llm_client: LlmClient | None = None,
        llm_settings: LlmSettings | None = None,
        stream_chat: bool | None = None,
        memory: MemoryStore | None = None,
        tools: ToolRegistry | None = None,
    ) -> None:
        self._chat_sender = chat_sender
        self._chat_responder = chat_responder
        self._llm_settings = llm_settings or LlmSettings()
        self._llm_client = llm_client or build_llm_client(self._llm_settings)
        self._stream_chat = (
            self._llm_settings.stream_chat if stream_chat is None else stream_chat
        )
        self._memory = memory
        self._tools = tools or build_default_registry()
        self._cancel_events: dict[str, asyncio.Event] = {}

    def _should_stream_chat(self) -> bool:
        if not self._stream_chat:
            return False
        provider = self._llm_settings.provider.strip().lower()
        return provider not in {"", "mock", "local-mock"}

    def _truncate_content(self, content: str) -> str:
        """Truncate content to Discord message limit with ellipsis."""
        if len(content) <= MAX_MESSAGE_LENGTH:
            return content
        truncated = content[: MAX_MESSAGE_LENGTH - 3]
        for sep in ("\n", ". ", "! ", "? ", ", "):
            last_sep = truncated.rfind(sep)
            if last_sep > MAX_MESSAGE_LENGTH // 2:
                return truncated[: last_sep + 1].strip()
        return truncated.strip() + "..."

    async def respond(
        self,
        event: ConversationEvent,
        state: ConversationState,
        plan: Plan,
        context: ContextSnapshot | None = None,
    ) -> None:
        try:
            if self._should_stream_chat():
                await self._respond_chat_streaming(event, state, plan, context)
            else:
                await self._respond_chat(event, state, plan, context)
        except LlmRateLimitError:
            LOGGER.warning("LLM rate limited for conversation %s", event.conversation_id)
            if self._chat_sender and event.channel_id:
                await self._chat_sender.send(
                    int(event.channel_id),
                    "I'm receiving too many requests right now. Please try again in a moment.",
                )
        except LlmError as exc:
            LOGGER.error("LLM error for conversation %s: %s", event.conversation_id, exc)
            if self._chat_sender and event.channel_id:
                await self._chat_sender.send(
                    int(event.channel_id),
                    "I encountered an error processing your request. Please try again.",
                )
        except Exception:
            LOGGER.exception("Unexpected error in respond for conversation %s", event.conversation_id)

    async def cancel_active_response(self, state: ConversationState) -> None:
        state.active_task = None
        cancel_event = self._cancel_events.get(state.conversation_id)
        if cancel_event is not None:
            cancel_event.set()

    async def _respond_chat(
        self,
        event: ConversationEvent,
        state: ConversationState,
        plan: Plan,
        context: ContextSnapshot | None,
    ) -> None:
        if self._chat_sender is None or event.channel_id is None:
            return
        LOGGER.info(
            "response.chat %s",
            event_fields(conversation_id=event.conversation_id, plan_kind=plan.kind.value),
        )

        if self._chat_responder is not None:
            content = await self._chat_responder(event, state, plan)
        elif plan.kind == PlanKind.TOOL:
            content = await self._handle_tool_call(event, plan, context, state)
        else:
            request = await self._build_llm_request(event, plan, context, state)
            response = await self._llm_client.complete(request)
            content = response.content
            if content:
                state.context_records.append(
                    _assistant_context_record(content, response.provider, response.model)
                )
                if self._memory is not None:
                    self._memory.record_assistant_turn(event.conversation_id, content)

        if content:
            content = self._truncate_content(content)
            await self._chat_sender.send(int(event.channel_id), content)

    async def _respond_chat_streaming(
        self,
        event: ConversationEvent,
        state: ConversationState,
        plan: Plan,
        context: ContextSnapshot | None,
    ) -> None:
        if self._chat_sender is None or event.channel_id is None:
            return
        LOGGER.info(
            "response.chat_streaming %s",
            event_fields(conversation_id=event.conversation_id),
        )

        channel_id = int(event.channel_id)
        registry = ToolRegistry()
        for t in self._tools.list():
            registry.register(t)
        if self._memory is not None:
            registry.register(set_user_preference_tool(self._memory, event.user_id))
            registry.register(delete_user_preference_tool(self._memory, event.user_id))

        intermediate_messages: list[LlmMessage] = []
        final_response = None

        for _ in range(5):
            request = LlmRequest(
                system_prompt=self._llm_settings.system_prompt,
                plan=plan,
                context=context,
                memory=plan.metadata.get("memory"),
                messages=tuple(intermediate_messages),
                tools=registry.list(),
                metadata={
                    "conversation_id": event.conversation_id,
                    "channel_id": event.channel_id or "",
                    "guild_id": event.guild_id or "",
                },
            )
            response = await self._llm_client.complete(request)
            if not response.tool_calls:
                final_response = response
                break

            intermediate_messages.append(
                LlmMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )
            for tool_call in response.tool_calls:
                try:
                    tool = registry.get(tool_call.name)
                    result = await tool.handler(tool_call.arguments)
                    result_str = json.dumps(result, ensure_ascii=False)
                except Exception as exc:
                    LOGGER.warning("Tool %s failed: %s", tool_call.name, exc)
                    result_str = json.dumps({"error": str(exc)}, ensure_ascii=False)
                intermediate_messages.append(
                    LlmMessage(
                        role="tool",
                        content=result_str,
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    )
                )
                state.context_records.append(_tool_context_record(tool_call.name, result_str))
                if self._memory is not None:
                    self._memory.record_tool_result(event.conversation_id, tool_call.name, result_str)

        if final_response is not None:
            content = self._truncate_content(final_response.content)
            await self._chat_sender.send(channel_id, content)
            if final_response.content:
                state.context_records.append(
                    _assistant_context_record(final_response.content, final_response.provider, final_response.model)
                )
                if self._memory is not None:
                    self._memory.record_assistant_turn(event.conversation_id, final_response.content)
    
    async def _handle_tool_call(
        self,
        event: ConversationEvent,
        plan: Plan,
        context: ContextSnapshot | None,
        state: ConversationState,
    ) -> str:
        registry = ToolRegistry()
        for t in self._tools.list():
            registry.register(t)
        if self._memory is not None:
            registry.register(set_user_preference_tool(self._memory, event.user_id))
            registry.register(delete_user_preference_tool(self._memory, event.user_id))

        request = LlmRequest(
            system_prompt=self._llm_settings.system_prompt,
            plan=plan,
            context=context,
            tools=registry.list(),
            metadata={
                "conversation_id": event.conversation_id,
                "channel_id": event.channel_id or "",
                "guild_id": event.guild_id or "",
            },
        )
        response = await self._llm_client.complete(request)
        return response.content

    async def _build_llm_request(
        self,
        event: ConversationEvent,
        plan: Plan,
        context: ContextSnapshot | None,
        state: ConversationState | None,
    ) -> LlmRequest:
        memory = plan.metadata.get("memory")
        if self._memory is not None and state is not None and memory is None:
            try:
                memory = await self._memory.retrieve(event, state)
            except Exception:
                pass
        return LlmRequest(
            system_prompt=self._llm_settings.system_prompt,
            plan=plan,
            context=context,
            memory=memory,
            metadata={
                "conversation_id": event.conversation_id,
                "channel_id": event.channel_id or "",
                "guild_id": event.guild_id or "",
            },
        )


def _assistant_context_record(content: str, provider: str, model: str):
    from directioner.conversation.context import ContextManager, ContextRecord

    return ContextRecord(
        role="assistant",
        content=content,
        source="llm_response",
        token_estimate=ContextManager.estimate_tokens(content),
        metadata={"provider": provider, "model": model},
    )


def _tool_context_record(tool_name: str, result: str):
    from directioner.conversation.context import ContextManager, ContextRecord

    content = f"{tool_name}: {result}"
    return ContextRecord(
        role="tool",
        content=content,
        source="tool_result",
        token_estimate=ContextManager.estimate_tokens(content),
        metadata={"tool_name": tool_name},
    )
