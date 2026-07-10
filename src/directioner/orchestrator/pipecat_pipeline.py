"""Pipecat orchestration boundary."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from directioner.intent.planner import Plan


@dataclass(slots=True)
class PipelineRun:
    cancelled: bool = False
    emitted_chunks: int = 0


class PipecatPipeline:
    async def run(
        self,
        plan: Plan,
        *,
        cancel_event: asyncio.Event | None = None,
        chunk_chars: int = 120,
    ) -> AsyncIterator[str]:
        prompt = plan.prompt.strip()
        if not prompt:
            return

        if chunk_chars <= 0:
            chunk_chars = 120

        words = prompt.split()
        if not words:
            return

        chunk = ""
        for word in words:
            if cancel_event is not None and cancel_event.is_set():
                return
            candidate = (chunk + " " + word).strip()
            if len(candidate) > chunk_chars and chunk:
                yield chunk + " "
                await asyncio.sleep(0)
                chunk = word
            else:
                chunk = candidate
        if chunk:
            yield chunk

    async def run_to_text(
        self,
        plan: Plan,
        *,
        cancel_event: asyncio.Event | None = None,
        chunk_chars: int = 120,
    ) -> tuple[str, PipelineRun]:
        parts: list[str] = []
        run = PipelineRun()
        async for chunk in self.run(plan, cancel_event=cancel_event, chunk_chars=chunk_chars):
            if cancel_event is not None and cancel_event.is_set():
                run.cancelled = True
                break
            parts.append(chunk)
            run.emitted_chunks += 1
        if cancel_event is not None and cancel_event.is_set():
            run.cancelled = True
        return "".join(parts).strip(), run

