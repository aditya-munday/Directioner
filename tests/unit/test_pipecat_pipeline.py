from __future__ import annotations

import asyncio

import pytest

from directioner.intent.planner import Plan, PlanKind
from directioner.orchestrator.pipecat_pipeline import PipecatPipeline


@pytest.mark.asyncio
async def test_pipecat_pipeline_chunks_text() -> None:
    pipeline = PipecatPipeline()
    plan = Plan(kind=PlanKind.MULTI_STEP, prompt="one two three four five six seven")
    chunks = [chunk async for chunk in pipeline.run(plan, chunk_chars=10)]
    assert len(chunks) >= 2
    assert "".join(chunks).replace("  ", " ").strip() == plan.prompt


@pytest.mark.asyncio
async def test_pipecat_pipeline_honors_cancellation() -> None:
    pipeline = PipecatPipeline()
    cancel_event = asyncio.Event()
    cancel_event.set()
    plan = Plan(kind=PlanKind.MULTI_STEP, prompt="a b c d e f g")
    text, run = await pipeline.run_to_text(plan, cancel_event=cancel_event, chunk_chars=4)
    assert text == ""
    assert run.cancelled
