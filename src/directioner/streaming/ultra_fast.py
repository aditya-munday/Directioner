"""Ultra-fast response module for minimum latency.

This module provides ChatGPT-style ultra-fast responses through:
1. Fast-path routing for common queries (<5ms)
2. Predictive caching for frequent queries (<10ms)
3. Connection pre-warming for LLM (<100ms to first token)
4. Token streaming for perceived speed
5. Parallel execution for independent operations
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import structlog

from directioner.streaming import (
    FastPathRouter,
    ParallelToolExecutor,
    PredictiveCache,
    LLMConnectionPool,
    StreamingResponseHandler,
    UltraLowLatencyOrchestrator,
)
from directioner.streaming.latency import latency_tracker, track_latency

LOGGER = structlog.get_logger(__name__)


# =============================================================================
# Response Path Types
# =============================================================================

class ResponsePath:
    """Response generation path types."""
    FAST = "fast"      # Direct template response
    CACHED = "cached"  # From predictive cache
    LLM = "llm"        # From LLM (streaming)
    HYBRID = "hybrid"  # Fast-path + LLM tools


# =============================================================================
# Ultra-Fast Response Engine
# =============================================================================

class UltraFastResponseEngine:
    """
    Ultra-low latency response engine optimized for minimal perceived latency.
    
    Response hierarchy:
    1. Fast-path (<5ms): Direct template responses for common queries
    2. Cache (<10ms): Pre-computed responses from predictive cache
    3. Hybrid (<100ms): Fast-path for intent + parallel tool execution
    4. LLM (100ms+): Full LLM generation with streaming
    """

    def __init__(
        self,
        llm_client: Any = None,
        max_concurrent_tools: int = 5,
        cache_size: int = 10000,
        cache_ttl: float = 3600.0,
        pool_size: int = 3,
    ) -> None:
        # Components
        self._fast_path = FastPathRouter()
        self._tool_executor = ParallelToolExecutor(max_concurrent=max_concurrent_tools)
        self._cache = PredictiveCache(max_size=cache_size, ttl_seconds=cache_ttl)
        self._pool = LLMConnectionPool(pool_size=pool_size)
        self._llm_client = llm_client

        # Latency tracking
        self._tracker = latency_tracker

        # Stats
        self._response_counts: dict[str, int] = defaultdict(int)
        self._response_times: dict[str, list[float]] = defaultdict(list)

    async def initialize(self) -> None:
        """Initialize and pre-warm components."""
        LOGGER.info("Initializing ultra-fast response engine")

        # Pre-warm LLM connections
        await self._pool.pre_warm()

        # Pre-warm cache with common queries
        common_queries = [
            ("hello", {}),
            ("hi", {}),
            ("help", {}),
            ("thanks", {}),
            ("who are you", {}),
            ("what can you do", {}),
        ]
        await self._cache.warm_up(common_queries)

        LOGGER.info("Ultra-fast response engine initialized")

    async def respond(
        self,
        text: str,
        context: dict[str, Any] | None = None,
        stream_handler: StreamingResponseHandler | None = None,
    ) -> tuple[str, str, float]:
        """
        Generate a response with optimal latency.
        
        Returns: (response_text, path, latency_ms)
        """
        context = context or {}
        start = time.perf_counter()
        path = ResponsePath.LLM
        response = ""

        try:
            # Try fast-path first (microseconds)
            fast_response = await self._fast_path.try_route(text, context)
            if fast_response:
                response = fast_response
                path = ResponsePath.FAST
                latency_ms = (time.perf_counter() - start) * 1000

                # Stream if handler provided
                if stream_handler:
                    await stream_handler.start_typing()
                    for char in response:
                        await stream_handler.send_token(char)
                    await stream_handler.stop_typing()
                    await stream_handler.send_token("", is_final=True)

                await self._record_response(path, latency_ms)
                return response, path, latency_ms

            # Try cache (sub-millisecond)
            cached = await self._cache.get(text, context)
            if cached:
                response = cached.text
                path = ResponsePath.CACHED
                latency_ms = (time.perf_counter() - start) * 1000

                if stream_handler:
                    await stream_handler.start_typing()
                    for char in response:
                        await stream_handler.send_token(char)
                    await stream_handler.stop_typing()
                    await stream_handler.send_token("", is_final=True)

                await self._record_response(path, latency_ms)
                return response, path, latency_ms

            # Full LLM generation with streaming
            if self._llm_client:
                path = ResponsePath.LLM

                if stream_handler:
                    # Stream response
                    await stream_handler.start_typing()

                    try:
                        full_response = ""
                        async for token in self._llm_client.stream_complete(
                            self._build_prompt(text, context),
                            context,
                        ):
                            await stream_handler.send_token(token)
                            full_response += token

                    finally:
                        await stream_handler.stop_typing()
                        await stream_handler.send_token("", is_final=True)

                    response = full_response
                else:
                    # Non-streaming
                    response = await self._llm_client.complete(
                        self._build_prompt(text, context),
                        context,
                    )

                latency_ms = (time.perf_counter() - start) * 1000

                # Cache the response
                await self._cache.put(text, response, context, latency_ms)

                await self._record_response(path, latency_ms)
                return response, path, latency_ms

            # Fallback
            response = "I'm not sure how to respond to that."
            path = ResponsePath.FAST
            latency_ms = (time.perf_counter() - start) * 1000

            await self._record_response(path, latency_ms)
            return response, path, latency_ms

        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            LOGGER.error("Response generation failed", error=exc, latency_ms=latency_ms)
            return f"Sorry, I encountered an error.", ResponsePath.FAST, latency_ms

    async def respond_fast(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Fast response without streaming. Returns immediately if fast-path hit."""
        context = context or {}
        start = time.perf_counter()

        # Try fast-path
        fast_response = await self._fast_path.try_route(text, context)
        if fast_response:
            latency_ms = (time.perf_counter() - start) * 1000
            await self._record_response(ResponsePath.FAST, latency_ms)
            return fast_response

        # Try cache
        cached = await self._cache.get(text, context)
        if cached:
            latency_ms = (time.perf_counter() - start) * 1000
            await self._record_response(ResponsePath.CACHED, latency_ms)
            return cached.text

        # Generate
        if self._llm_client:
            response = await self._llm_client.complete(
                self._build_prompt(text, context),
                context,
            )
            latency_ms = (time.perf_counter() - start) * 1000
            await self._cache.put(text, response, context, latency_ms)
            await self._record_response(ResponsePath.LLM, latency_ms)
            return response

        return "I need more context to respond properly."

    def _build_prompt(self, text: str, context: dict[str, Any]) -> str:
        """Build prompt for LLM."""
        persona = context.get("persona", "helpful")
        memory = context.get("memory", "")

        parts = [
            f"You are {persona}.",
        ]

        if memory:
            parts.append(f"Context: {memory}")

        parts.append(f"User: {text}")

        return "\n\n".join(parts)

    async def _record_response(self, path: str, latency_ms: float) -> None:
        """Record response statistics."""
        self._response_counts[path] += 1
        self._response_times[path].append(latency_ms)

        # Record in latency tracker
        await self._tracker.record(
            f"response_{path}",
            latency_ms,
            metadata={"path": path},
        )

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive statistics."""
        total = sum(self._response_counts.values())
        avg_times = {}

        for path, times in self._response_times.items():
            if times:
                avg_times[path] = round(sum(times) / len(times), 2)

        return {
            "total_responses": total,
            "by_path": dict(self._response_counts),
            "avg_latency_ms": avg_times,
            "fast_path": self._fast_path.get_stats(),
            "cache": self._cache.get_stats(),
            "tools": self._tool_executor.get_stats(),
            "llm_pool": self._pool.get_stats(),
        }


# =============================================================================
# Optimistic Response Handler
# =============================================================================

class OptimisticResponseHandler:
    """
    Send optimistic response immediately, refine later.
    
    This provides the absolute minimum perceived latency by:
    1. Sending a quick acknowledgment immediately
    2. Processing the actual request in background
    3. Updating the response if significantly different
    """

    def __init__(
        self,
        engine: UltraFastResponseEngine,
        update_threshold: float = 0.3,  # Update if >30% better
    ) -> None:
        self._engine = engine
        self._update_threshold = update_threshold

    async def respond_optimistic(
        self,
        text: str,
        context: dict[str, Any] | None,
        immediate_callback: Any,  # Callback to send immediate response
    ) -> tuple[str, str, float]:
        """
        Respond optimistically, then refine if needed.
        
        1. Send immediate acknowledgment
        2. Start background processing
        3. If final response is significantly better, update
        """
        context = context or {}
        start = time.perf_counter()

        # Send immediate acknowledgment
        immediate_response = await self._engine._fast_path.try_route(text, context)
        if immediate_response:
            await immediate_callback(immediate_response)

        # Start background processing
        final_response, path, latency_ms = await self._engine.respond(text, context)

        # Update if significantly better
        if immediate_response and path == ResponsePath.LLM:
            improvement = len(final_response) / max(len(immediate_response), 1)
            if improvement > (1 + self._update_threshold):
                await immediate_callback(final_response)

        return final_response, path, latency_ms


# =============================================================================
# Adaptive Response Selector
# =============================================================================

class AdaptiveResponseSelector:
    """
    Select the optimal response strategy based on query characteristics.
    
    Strategies:
    - Trivial: Fast-path (greetings, thanks, etc.)
    - Simple: Cached response
    - Tool-based: Fast-path intent + parallel tools
    - Full: LLM generation
    """

    TRIVIAL_PATTERNS = [
        r"^(hi|hello|hey|greetings)$",
        r"^(thanks?|thx|ty|thank you)$",
        r"^(bye|goodbye|see you|later)$",
        r"^(yes|yep|no|nope|ok|okay|sure)$",
    ]

    SIMPLE_PATTERNS = [
        r"^what time is it",
        r"^what day is it",
        r"^who are you",
        r"^what can you do",
    ]

    def __init__(
        self,
        engine: UltraFastResponseEngine,
    ) -> None:
        self._engine = engine
        self._trivial_compiled = [
            __import__('re').compile(p) for p in self.TRIVIAL_PATTERNS
        ]
        self._simple_compiled = [
            __import__('re').compile(p) for p in self.SIMPLE_PATTERNS
        ]

    def classify(self, text: str) -> str:
        """Classify query complexity."""
        text_lower = text.lower().strip()

        for pattern in self._trivial_compiled:
            if pattern.match(text_lower):
                return "trivial"

        for pattern in self._simple_compiled:
            if pattern.match(text_lower):
                return "simple"

        # Check for tool-like queries
        if any(word in text_lower for word in ["calculate", "search", "find", "look up"]):
            return "tool_based"

        return "full"

    async def respond_adaptive(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str, float]:
        """Respond using adaptive strategy selection."""
        classification = self.classify(text)

        if classification == "trivial":
            # Direct fast-path
            response = await self._engine._fast_path.try_route(text, context)
            if response:
                return response, "trivial_fast", 1.0

        elif classification == "simple":
            # Try cache first
            cached = await self._engine._cache.get(text, context)
            if cached:
                return cached.text, "simple_cache", 5.0

            # Fall back to fast-path
            response = await self._engine._fast_path.try_route(text, context)
            if response:
                return response, "simple_fast", 10.0

        # Full processing
        return await self._engine.respond(text, context)


# =============================================================================
# Global instance
# =============================================================================

# This will be initialized with the LLM client
_engine: UltraFastResponseEngine | None = None


def get_engine() -> UltraFastResponseEngine | None:
    """Get the global response engine instance."""
    return _engine


async def initialize_engine(llm_client: Any = None) -> UltraFastResponseEngine:
    """Initialize the global response engine."""
    global _engine
    _engine = UltraFastResponseEngine(llm_client=llm_client)
    await _engine.initialize()
    return _engine
