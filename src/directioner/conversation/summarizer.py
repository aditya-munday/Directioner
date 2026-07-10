"""Context summarization for conversation overflow."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from directioner.conversation.context import ContextManager, ContextRecord, ContextSnapshot
from directioner.conversation.state import ConversationState

logger = logging.getLogger(__name__)

_SUMMARY_ROLE = "summary"
_SUMMARY_SOURCE = "context_summarizer"
_MIN_RECORDS_TO_SUMMARIZE = 6  # don't summarize tiny windows


@dataclass(frozen=True, slots=True)
class SummarizationResult:
    records_replaced: int
    summary_tokens: int
    skipped: bool = False


class ContextSummarizer:
    """Summarizes the oldest half of context records when the token budget is
    exceeded, replacing them with a single compact summary record.

    Uses the LLM client if available; falls back to a simple extractive
    summary (first sentence of each record) when no LLM is configured.
    """

    def __init__(self, llm_client=None, max_summary_chars: int = 600) -> None:
        self._llm = llm_client
        self._max_summary_chars = max_summary_chars

    async def maybe_summarize(
        self,
        state: ConversationState,
        context_manager: ContextManager,
    ) -> SummarizationResult:
        """Summarize oldest records if the context window is over budget."""
        snapshot = context_manager.snapshot(state)
        if snapshot.token_estimate <= context_manager.token_budget * 0.9:
            return SummarizationResult(records_replaced=0, summary_tokens=0, skipped=True)

        records = list(state.context_records)
        if len(records) < _MIN_RECORDS_TO_SUMMARIZE:
            return SummarizationResult(records_replaced=0, summary_tokens=0, skipped=True)

        # Summarize the oldest half
        split = len(records) // 2
        to_summarize = records[:split]
        keep = records[split:]

        summary_text = await self._summarize(to_summarize)
        if not summary_text:
            return SummarizationResult(records_replaced=0, summary_tokens=0, skipped=True)

        summary_record = ContextRecord(
            role=_SUMMARY_ROLE,
            content=summary_text,
            source=_SUMMARY_SOURCE,
            token_estimate=ContextManager.estimate_tokens(summary_text),
        )

        state.context_records.clear()
        state.context_records.append(summary_record)
        state.context_records.extend(keep)

        logger.info(
            "context.summarized replaced=%d summary_tokens=%d",
            split,
            summary_record.token_estimate,
        )
        return SummarizationResult(
            records_replaced=split,
            summary_tokens=summary_record.token_estimate,
        )

    async def _summarize(self, records: list[ContextRecord]) -> str:
        text_parts = [r.content for r in records if r.content.strip()]
        if not text_parts:
            return ""

        if self._llm is not None:
            try:
                from directioner.intent.planner import Plan, PlanKind
                from directioner.llm.client import LlmRequest

                combined = "\n".join(text_parts)
                prompt = (
                    f"Summarize the following conversation excerpt in at most "
                    f"{self._max_summary_chars} characters, preserving key facts:\n\n{combined}"
                )
                request = LlmRequest(
                    system_prompt="You are a concise summarizer. Output only the summary.",
                    plan=Plan(kind=PlanKind.CHAT, prompt=prompt),
                )
                response = await self._llm.complete(request)
                return response.content.strip()[: self._max_summary_chars]
            except Exception as exc:
                logger.debug("context.summarize_llm_error err=%s", exc)

        # Extractive fallback: first sentence of each record
        sentences: list[str] = []
        for part in text_parts:
            first = part.split(".")[0].strip()
            if first:
                sentences.append(first)
        return ". ".join(sentences)[: self._max_summary_chars]
