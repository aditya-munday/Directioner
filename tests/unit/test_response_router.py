from __future__ import annotations

import pytest

from directioner.conversation.events import ConversationEvent, ConversationEventKind
from directioner.conversation.state import ConversationState
from directioner.intent.planner import Plan, PlanKind
from directioner.llm.client import LlmResponse, LlmToolCall
from directioner.memory.store import MemorySettings, MemoryStore
from directioner.response.router import ResponseRouter


pytestmark = pytest.mark.asyncio


class FakeChatSender:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, str | None]] = []

    async def send(self, channel_id: int, content: str, reply_to: str | None = None) -> None:
        self.sent.append((channel_id, content, reply_to))


async def test_response_router_sends_chat_response() -> None:
    sender = FakeChatSender()
    router = ResponseRouter(
        chat_sender=sender,
        chat_responder=lambda event, state, plan: _respond("pong"),
    )

    await router.respond(
        ConversationEvent(
            kind=ConversationEventKind.CHAT_MESSAGE,
            conversation_id="2",
            user_id="4",
            channel_id="2",
            text="ping",
        ),
        ConversationState(conversation_id="2"),
        Plan(kind=PlanKind.CHAT, prompt="ping"),
    )

    assert sender.sent == [(2, "pong", None)]


async def test_response_router_streaming_sends_accumulated_message() -> None:
    sender = FakeChatSender()

    class FakeStreamingClient:
        async def complete(self, request):
            raise AssertionError("streaming test should not call complete")

        async def stream(self, request):
            yield "hello"
            yield " world"

    router = ResponseRouter(chat_sender=sender, llm_client=FakeStreamingClient())
    state = ConversationState(conversation_id="2")

    await router.respond_streaming(
        ConversationEvent(
            kind=ConversationEventKind.CHAT_MESSAGE,
            conversation_id="2",
            user_id="4",
            channel_id="2",
            text="ping",
        ),
        state,
        Plan(kind=PlanKind.CHAT, prompt="ping"),
    )

    assert sender.sent == [(2, "hello world", None)]



async def test_response_router_streams_chat_incrementally() -> None:
    sender = FakeChatSender()

    class FakeStreamingClient:
        async def complete(self, request):
            raise AssertionError("streaming test should not call complete")

        async def stream(self, request):
            yield "This is the first sentence. "
            yield "And here is the second sentence that stays buffered"

    from directioner.config.settings import LlmSettings

    router = ResponseRouter(
        chat_sender=sender,
        llm_client=FakeStreamingClient(),
        llm_settings=LlmSettings(
            provider="groq",
            api_key="test-key",
            stream_flush_chars=10,
        ),
    )
    state = ConversationState(conversation_id="2")

    event = ConversationEvent(
        kind=ConversationEventKind.CHAT_MESSAGE,
        conversation_id="2",
        user_id="4",
        channel_id="2",
        text="ping",
    )

    await router.respond(event, state, Plan(kind=PlanKind.CHAT, prompt="ping"))

    # The first sentence is flushed before the whole stream completes.
    assert sender.sent[0] == (2, "This is the first sentence.", None)
    assert len(sender.sent) >= 2
    joined = " ".join(content for _, content, _ in sender.sent)
    assert "second sentence" in joined
    assert state.context_records[-1].role == "assistant"


async def test_response_router_uses_single_message_for_mock_provider() -> None:
    sender = FakeChatSender()

    class FakeStreamingClient:
        async def complete(self, request):
            return LlmResponse(content="one clean reply", provider="mock", model="m1")

        async def stream(self, request):
            yield "part "
            yield "two"

    from directioner.config.settings import LlmSettings

    router = ResponseRouter(
        chat_sender=sender,
        llm_client=FakeStreamingClient(),
        llm_settings=LlmSettings(provider="mock", stream_chat=True),
    )
    state = ConversationState(conversation_id="2")

    await router.respond(
        ConversationEvent(
            kind=ConversationEventKind.CHAT_MESSAGE,
            conversation_id="2",
            user_id="4",
            channel_id="2",
            text="ping",
        ),
        state,
        Plan(kind=PlanKind.CHAT, prompt="ping"),
    )

    assert sender.sent == [(2, "one clean reply", None)]
    sender = FakeChatSender()
    router = ResponseRouter(chat_sender=sender)
    state = ConversationState(conversation_id="2")

    await router.respond(
        ConversationEvent(
            kind=ConversationEventKind.CHAT_MESSAGE,
            conversation_id="2",
            user_id="4",
            channel_id="2",
            text="ping",
        ),
        state,
        Plan(kind=PlanKind.CHAT, prompt="ping"),
    )

    assert len(sender.sent) == 1
    assert sender.sent[0][0] == 2
    assert "mock mode" in sender.sent[0][1].lower() or "directioner" in sender.sent[0][1].lower()
    assert state.context_records[-1].role == "assistant"
    assert state.context_records[-1].source == "llm_response"
    assert state.context_records[-1].metadata["provider"] == "mock"


async def test_response_router_records_tool_results_in_context_and_memory() -> None:
    sender = FakeChatSender()

    class FakeToolLlmClient:
        async def complete(self, request):
            if not request.messages:
                return LlmResponse(
                    content="",
                    provider="mock",
                    model="mock-model",
                    tool_calls=(
                        LlmToolCall(
                            id="tool-1",
                            name="calculator",
                            arguments={"expression": "2 + 2"},
                        ),
                    ),
                )
            return LlmResponse(
                content="Done.",
                provider="mock",
                model="mock-model",
            )

        async def stream(self, request):
            yield "Done."

    memory = MemoryStore(MemorySettings())
    router = ResponseRouter(chat_sender=sender, llm_client=FakeToolLlmClient(), memory=memory)
    state = ConversationState(conversation_id="2")
    event = ConversationEvent(
        kind=ConversationEventKind.CHAT_MESSAGE,
        conversation_id="2",
        user_id="4",
        channel_id="2",
        text="calculate 2 + 2",
    )

    await router.respond(event, state, Plan(kind=PlanKind.TOOL, prompt="calculate 2 + 2"))

    assert sender.sent[-1] == (2, "Done.", None)
    assert any(record.role == "tool" and "calculator:" in record.content for record in state.context_records)
    ctx = await memory.retrieve(event, state)
    assert any(turn.startswith("tool: calculator:") for turn in ctx.conversation)


async def test_response_router_uses_pipecat_for_multistep_plan() -> None:
    sender = FakeChatSender()
    seen_prompts: list[str] = []

    class FakeStreamingClient:
        async def complete(self, request):
            seen_prompts.append(request.plan.prompt)
            return LlmResponse(content="ok", provider="mock", model="m1")

        async def stream(self, request):
            yield "ok"

    router = ResponseRouter(chat_sender=sender, llm_client=FakeStreamingClient(), stream_chat=False)
    state = ConversationState(conversation_id="2")
    event = ConversationEvent(
        kind=ConversationEventKind.CHAT_MESSAGE,
        conversation_id="2",
        user_id="4",
        channel_id="2",
        text="think through this step by step about rust ownership",
    )

    await router.respond(
        event,
        state,
        Plan(kind=PlanKind.MULTI_STEP, prompt=event.text),
    )

    assert sender.sent[-1] == (2, "ok", None)
    assert seen_prompts


async def _respond(text: str) -> str:
    return text
