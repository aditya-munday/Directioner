"""Route generated responses to Discord chat or voice output."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Protocol

from directioner.config.settings import LlmSettings
from directioner.conversation.context import ContextSnapshot
from directioner.conversation.events import ConversationEvent, ConversationEventKind
from directioner.conversation.state import ConversationState
from directioner.intent.planner import Plan, PlanKind
from directioner.llm.client import LlmClient, LlmRequest, LlmMessage, build_llm_client
from directioner.memory.store import MemoryStore
from directioner.monitoring import event_fields, get_logger
from directioner.orchestrator.pipecat_pipeline import PipecatPipeline
from directioner.response.streaming import ChatStreamBuffer
from directioner.tools import build_default_registry, ToolRegistry, set_user_preference_tool, delete_user_preference_tool


class ChatSender(Protocol):
    async def send(self, channel_id: int, content: str) -> None: ...


class VoiceOutputSink(Protocol):
    def write_pcm_s16le_stereo_48khz(self, pcm: bytes) -> bool: ...


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
        pipecat_pipeline: PipecatPipeline | None = None,
        voice_output: VoiceOutputSink | None = None,
        tts=None,
        voice_output_pipeline=None,
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
        self._pipecat = pipecat_pipeline or PipecatPipeline()
        self._voice_output = voice_output
        self._tts = tts
        self._voice_output_pipeline = voice_output_pipeline
        self._cancel_events: dict[str, asyncio.Event] = {}
        # per-conversation barge-in cancel events for voice synthesis
        self._voice_cancel_events: dict[str, asyncio.Event] = {}

    def _should_stream_chat(self) -> bool:
        if not self._stream_chat:
            return False
        provider = self._llm_settings.provider.strip().lower()
        return provider not in {"", "mock", "local-mock"}

    async def respond(
        self,
        event: ConversationEvent,
        state: ConversationState,
        plan: Plan,
        context: ContextSnapshot | None = None,
    ) -> None:
        if event.kind in {ConversationEventKind.VOICE_FINAL, ConversationEventKind.VOICE_PARTIAL}:
            await self._respond_voice(plan, event=event, state=state, context=context)
        elif self._should_stream_chat():
            await self._respond_chat_streaming(event, state, plan, context)
        else:
            await self._respond_chat(event, state, plan, context)

    async def respond_streaming(
        self,
        event: ConversationEvent,
        state: ConversationState,
        plan: Plan,
        context: ContextSnapshot | None = None,
    ) -> None:
        """Streaming variant for chat responses.

        Chat replies are streamed from the LLM and flushed to the chat gateway in
        coalesced segments (see :class:`ChatStreamBuffer`) as soon as a natural
        boundary or size threshold is reached, so partial output appears quickly.
        """
        if event.kind in {ConversationEventKind.VOICE_FINAL, ConversationEventKind.VOICE_PARTIAL}:
            await self._respond_voice(plan, event=event, state=state, context=context)
        else:
            await self._respond_chat_streaming(event, state, plan, context)

    async def cancel_active_response(self, state: ConversationState) -> None:
        state.active_task = None
        cancel_event = self._cancel_events.get(state.conversation_id)
        if cancel_event is not None:
            cancel_event.set()
        # Also cancel any in-progress voice synthesis
        voice_cancel = self._voice_cancel_events.get(state.conversation_id)
        if voice_cancel is not None:
            voice_cancel.set()

    async def _respond_voice(
        self,
        plan: Plan,
        event: ConversationEvent | None = None,
        state: ConversationState | None = None,
        context=None,
    ) -> None:
        # Get LLM text for voice response
        text = plan.prompt.strip()
        if not text:
            return

        # If we have a real LLM client, generate the response first
        if state is not None and event is not None:
            request = await self._build_llm_request(event, plan, context, state)
            try:
                response = await self._llm_client.complete(request)
                text = response.content.strip() or text
                if text and state is not None:
                    state.context_records.append(
                        _assistant_context_record(response.content, response.provider, response.model)
                    )
                    if self._memory is not None:
                        self._memory.record_assistant_turn(event.conversation_id, text)
            except Exception:
                LOGGER.exception("voice.llm_error conversation=%s", plan.prompt[:40])

        if not text:
            return

        # Use VoiceOutputPipeline if available (preferred path)
        if self._voice_output_pipeline is not None:
            conv_id = event.conversation_id if event else "voice"
            cancel_event = self._voice_cancel_events.setdefault(conv_id, asyncio.Event())
            if cancel_event.is_set():
                cancel_event = asyncio.Event()
                self._voice_cancel_events[conv_id] = cancel_event
            stats = await self._voice_output_pipeline.speak(text, cancel_event=cancel_event)
            LOGGER.info(
                "voice.output %s",
                event_fields(
                    chunks=stats.chunks_synthesized,
                    frames=stats.pcm_frames_written,
                    cancelled=stats.cancelled,
                ),
            )
            return

        # Fallback: direct TTS → writer
        if self._tts is not None and self._voice_output is not None:
            from directioner.response.processing import ResponseProcessor
            processor = ResponseProcessor()
            for chunk in processor.chunk_for_tts(text):
                async for pcm_view in self._tts.synthesize(chunk):
                    self._voice_output.write_pcm_s16le_stereo_48khz(bytes(pcm_view))

    async def _respond_chat(
        self,
        event: ConversationEvent,
        state: ConversationState,
        plan: Plan,
        context: ContextSnapshot | None,
    ) -> None:
        if self._chat_sender is None or event.channel_id is None:
            return
        plan = await self._preprocess_plan(event.conversation_id, plan)
        LOGGER.info(
            "response.chat %s",
            event_fields(conversation_id=event.conversation_id, plan_kind=plan.kind.value),
        )
        reply_to = event.metadata.get("reply_to_message_id") or event.metadata.get("message_id")

        if self._chat_responder is not None:
            content = await self._chat_responder(event, state, plan)
        elif plan.kind != PlanKind.TOOL:
            request = await self._build_llm_request(event, plan, context, state)
            response = await self._llm_client.complete(request)
            content = response.content
            provider = response.provider
            model = response.model
            if content:
                state.context_records.append(
                    _assistant_context_record(content, provider, model)
                )
                if self._memory is not None:
                    self._memory.record_assistant_turn(event.conversation_id, content)
        else:
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
                        result_str = json.dumps({"error": str(exc)}, ensure_ascii=False)
                    intermediate_messages.append(
                        LlmMessage(
                            role="tool",
                            content=result_str,
                            tool_call_id=tool_call.id,
                            name=tool_call.name,
                        )
                    )
                    state.context_records.append(
                        _tool_context_record(tool_call.name, result_str)
                    )
                    if self._memory is not None:
                        self._memory.record_tool_result(
                            event.conversation_id,
                            tool_call.name,
                            result_str,
                        )

            if final_response is not None:
                content = final_response.content
                provider = final_response.provider
                model = final_response.model
            else:
                content = ""
                provider = self._llm_settings.provider
                model = self._llm_settings.model

            if content:
                state.context_records.append(
                    _assistant_context_record(content, provider, model)
                )
                if self._memory is not None:
                    self._memory.record_assistant_turn(event.conversation_id, content)

        if content:
            LOGGER.info(
                "response.chat_send %s",
                event_fields(
                    conversation_id=event.conversation_id,
                    chars=len(content),
                    preview=content[:80],
                ),
            )
            await self._chat_sender.send(int(event.channel_id), content, reply_to)

    async def _respond_chat_streaming(
        self,
        event: ConversationEvent,
        state: ConversationState,
        plan: Plan,
        context: ContextSnapshot | None,
    ) -> None:
        if self._chat_sender is None or event.channel_id is None:
            return
        plan = await self._preprocess_plan(event.conversation_id, plan)
        LOGGER.info(
            "response.chat_streaming %s",
            event_fields(conversation_id=event.conversation_id, plan_kind=plan.kind.value),
        )

        reply_to_s = event.metadata.get("reply_to_message_id") or event.metadata.get("message_id")

        if self._chat_responder is not None:
            content = await self._chat_responder(event, state, plan)
            if content:
                await self._chat_sender.send(int(event.channel_id), content, reply_to_s)
            return

        from directioner.intent.planner import PlanKind

        if plan.kind != PlanKind.TOOL:
            # Direct streaming bypasses complete() loop entirely
            request = await self._build_llm_request(event, plan, context, state)
            channel_id = int(event.channel_id)
            buffer = ChatStreamBuffer(
                flush_threshold=self._llm_settings.stream_flush_chars,
                hard_limit=self._llm_settings.max_output_chars,
            )
            collected: list[str] = []
            first_segment = True

            async for chunk in self._llm_client.stream(request):
                if not chunk:
                    continue
                collected.append(chunk)
                for segment in buffer.add(chunk):
                    await self._chat_sender.send(channel_id, segment, reply_to_s if first_segment else None)
                    first_segment = False

            for segment in buffer.drain():
                await self._chat_sender.send(channel_id, segment, reply_to_s if first_segment else None)
                first_segment = False

            content = "".join(collected).strip()
            if content:
                state.context_records.append(
                    _assistant_context_record(
                        content,
                        self._llm_settings.provider,
                        self._llm_settings.model,
                    )
                )
                if self._memory is not None:
                    self._memory.record_assistant_turn(event.conversation_id, content)
            return

        registry = ToolRegistry()
        for t in self._tools.list():
            registry.register(t)
        if self._memory is not None:
            registry.register(set_user_preference_tool(self._memory, event.user_id))
            registry.register(delete_user_preference_tool(self._memory, event.user_id))

        intermediate_messages: list[LlmMessage] = []
        final_response_content = ""

        for _ in range(5):
            request = await self._build_llm_request(event, plan, context, state)
            request = replace(request,
                messages=tuple(intermediate_messages),
                tools=registry.list()
            )
            response = await self._llm_client.complete(request)
            if not response.tool_calls:
                final_response_content = response.content
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
                    result_str = json.dumps({"error": str(exc)}, ensure_ascii=False)
                intermediate_messages.append(
                    LlmMessage(
                        role="tool",
                        content=result_str,
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    )
                )
                state.context_records.append(
                    _tool_context_record(tool_call.name, result_str)
                )
                if self._memory is not None:
                    self._memory.record_tool_result(
                        event.conversation_id,
                        tool_call.name,
                        result_str,
                    )

        channel_id = int(event.channel_id)
        buffer = ChatStreamBuffer(
            flush_threshold=self._llm_settings.stream_flush_chars,
            hard_limit=self._llm_settings.max_output_chars,
        )
        collected: list[str] = []

        final_request = LlmRequest(
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

        async for chunk in self._llm_client.stream(final_request):
            if not chunk:
                continue
            collected.append(chunk)
            for segment in buffer.add(chunk):
                await self._chat_sender.send(channel_id, segment)

        for segment in buffer.drain():
            await self._chat_sender.send(channel_id, segment, reply_to_s if first_segment else None)
            first_segment = False

        content = "".join(collected).strip()
        if not content and final_response_content:
            content = final_response_content.strip()
            if content:
                await self._chat_sender.send(channel_id, content, reply_to_s)

        if content:
            state.context_records.append(
                _assistant_context_record(
                    content,
                    self._llm_settings.provider,
                    self._llm_settings.model,
                )
            )
            if self._memory is not None:
                self._memory.record_assistant_turn(event.conversation_id, content)

    async def _preprocess_plan(self, conversation_id: str, plan: Plan) -> Plan:
        if plan.kind != PlanKind.MULTI_STEP:
            return plan

        cancel_event = self._cancel_events.setdefault(conversation_id, asyncio.Event())
        if cancel_event.is_set():
            cancel_event = asyncio.Event()
            self._cancel_events[conversation_id] = cancel_event

        orchestrated_prompt, run = await self._pipecat.run_to_text(
            plan,
            cancel_event=cancel_event,
        )
        metadata = dict(plan.metadata)
        metadata["pipecat"] = {
            "cancelled": run.cancelled,
            "emitted_chunks": run.emitted_chunks,
        }
        return Plan(
            kind=PlanKind.CHAT,
            prompt=orchestrated_prompt or plan.prompt,
            tool_names=plan.tool_names,
            metadata=metadata,
        )

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
                # If retrieving memory fails, just use what we had
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
