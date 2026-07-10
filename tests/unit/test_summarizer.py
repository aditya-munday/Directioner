"""Unit tests for ContextSummarizer."""

from __future__ import annotations

import pytest

from directioner.conversation.context import ContextManager, ContextRecord
from directioner.conversation.state import ConversationState
from directioner.conversation.summarizer import ContextSummarizer

pytestmark = pytest.mark.asyncio


def _state_with_records(n: int) -> ConversationState:
    state = ConversationState(conversation_id="test")
    for i in range(n):
        state.context_records.append(
            ContextRecord(
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message number {i} with some content to fill tokens.",
                source="test",
                token_estimate=20,
            )
        )
    return state


async def test_summarizer_skips_when_under_budget() -> None:
    ctx = ContextManager(token_budget=10_000)
    state = _state_with_records(4)
    summarizer = ContextSummarizer()
    result = await summarizer.maybe_summarize(state, ctx)
    assert result.skipped is True
    assert len(state.context_records) == 4


async def test_summarizer_replaces_oldest_half_when_over_budget() -> None:
    # Small budget so 10 records of 20 tokens each (200 total) exceeds 90% of 100
    ctx = ContextManager(token_budget=100)
    state = _state_with_records(10)
    summarizer = ContextSummarizer()
    result = await summarizer.maybe_summarize(state, ctx)
    assert result.skipped is False
    assert result.records_replaced == 5
    # Should now have 1 summary + 5 kept records
    assert len(state.context_records) == 6
    assert state.context_records[0].source == "context_summarizer"


async def test_summarizer_too_few_records_skips() -> None:
    ctx = ContextManager(token_budget=1)  # tiny budget
    state = _state_with_records(3)
    summarizer = ContextSummarizer()
    result = await summarizer.maybe_summarize(state, ctx)
    assert result.skipped is True


async def test_summarizer_uses_llm_when_provided() -> None:
    from directioner.llm.client import LlmResponse

    class FakeLlm:
        async def complete(self, request):
            return LlmResponse(content="Summary text.", provider="mock", model="mock")

        async def stream(self, request):
            yield "Summary text."

    ctx = ContextManager(token_budget=100)
    state = _state_with_records(10)
    summarizer = ContextSummarizer(llm_client=FakeLlm())
    result = await summarizer.maybe_summarize(state, ctx)
    assert result.skipped is False
    assert state.context_records[0].content == "Summary text."
