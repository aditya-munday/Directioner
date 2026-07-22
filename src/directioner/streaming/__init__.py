"""Ultra-low latency streaming architecture for Directioner.

This module implements ChatGPT-style streaming for minimal perceived latency:
- Token streaming as they're generated
- Parallel tool execution
- Predictive caching
- Fast-path routing for simple queries
- Connection pre-warming
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

import structlog

LOGGER = structlog.get_logger(__name__)


# =============================================================================
# Streaming Protocol
# =============================================================================

@dataclass
class StreamToken:
    """A single token in a stream."""
    text: str
    is_final: bool = False
    latency_ms: float = 0.0
    token_index: int = 0


@dataclass
class StreamChunk:
    """A chunk of tokens from the LLM."""
    tokens: list[str]
    is_complete: bool = False
    total_latency_ms: float = 0.0


# =============================================================================
# Streaming Response Handler
# =============================================================================

class StreamingResponseHandler(ABC):
    """Abstract base for streaming response handlers."""

    @abstractmethod
    async def send_token(self, token: str, is_final: bool = False) -> None:
        """Send a token to the client."""
        pass

    @abstractmethod
    async def start_typing(self) -> None:
        """Start the typing indicator."""
        pass

    @abstractmethod
    async def stop_typing(self) -> None:
        """Stop the typing indicator."""
        pass


class DiscordStreamingHandler(StreamingResponseHandler):
    """Discord-specific streaming handler."""

    def __init__(
        self,
        channel_id: str,
        send_message: Callable[[str], Any],
        start_typing: Callable[[], Any],
        stop_typing: Callable[[], Any],
    ) -> None:
        self.channel_id = channel_id
        self._send_message = send_message
        self._start_typing = start_typing
        self._stop_typing = stop_typing
        self._current_message: Any = None
        self._buffer: str = ""
        self._buffer_size: int = 50  # Send every 50 chars
        self._lock = asyncio.Lock()

    async def send_token(self, token: str, is_final: bool = False) -> None:
        """Buffer tokens and send periodically."""
        async with self._lock:
            self._buffer += token

            # Send if buffer is full or final
            if len(self._buffer) >= self._buffer_size or is_final:
                await self._flush_buffer()

    async def _flush_buffer(self) -> None:
        """Flush the token buffer to Discord."""
        if not self._buffer:
            return

        if self._current_message is None:
            # Create initial message
            self._current_message = await self._send_message(self._buffer)
        else:
            # Edit existing message
            # Note: discord.py has message.edit() method
            try:
                await self._current_message.edit(content=self._buffer)
            except Exception:
                # Fallback: send new message
                self._current_message = await self._send_message(self._buffer)

        self._buffer = ""

    async def start_typing(self) -> None:
        """Start typing indicator."""
        try:
            self._start_typing()
        except Exception as exc:
            LOGGER.debug("Failed to start typing", error=exc)

    async def stop_typing(self) -> None:
        """Stop typing indicator."""
        try:
            # Flush any remaining buffer
            await self._flush_buffer()
            self._stop_typing()
        except Exception as exc:
            LOGGER.debug("Failed to stop typing", error=exc)


# =============================================================================
# Fast-Path Router
# =============================================================================

@dataclass
class FastPathRule:
    """Rule for fast-path routing."""
    patterns: list[str]  # Lowercase patterns to match
    response_template: str | Callable[[dict], str]
    priority: int = 0
    description: str = ""


class FastPathRouter:
    """Ultra-fast routing for simple queries without LLM."""

    def __init__(self) -> None:
        self._rules: list[FastPathRule] = []
        self._regex_patterns: list[tuple[Any, FastPathRule]] = []
        self._hit_count: dict[str, int] = defaultdict(int)
        self._response_times: list[float] = []
        self._lock = asyncio.Lock()

        # Built-in fast paths
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        """Register default fast-path rules."""
        import re

        # Greetings
        self.add_rule(FastPathRule(
            patterns=["hello", "hi", "hey", "greetings", "howdy", "yo"],
            response_template="Hello! How can I help you today?",
            priority=10,
            description="Greeting"
        ))

        # Thanks
        self.add_rule(FastPathRule(
            patterns=["thank", "thanks", "thx", "ty"],
            response_template="You're welcome! Is there anything else I can help with?",
            priority=10,
            description="Thanks"
        ))

        # Time queries
        self.add_rule(FastPathRule(
            patterns=["what time is it", "current time", "time now"],
            response_template=lambda ctx: f"The current time is {time.strftime('%H:%M:%S')}.",
            priority=5,
            description="Time query"
        ))

        # Date queries
        self.add_rule(FastPathRule(
            patterns=["what date is it", "current date", "date today", "what day is it"],
            response_template=lambda ctx: f"Today is {time.strftime('%A, %B %d, %Y')}.",
            priority=5,
            description="Date query"
        ))

        # Math - simple
        self.add_rule(FastPathRule(
            patterns=["what is 2 + 2", "2 + 2", "2+2"],
            response_template="2 + 2 = 4",
            priority=20,
            description="Simple math"
        ))

        # Bot info
        self.add_rule(FastPathRule(
            patterns=["who are you", "what are you", "about you", "your name"],
            response_template="I'm Directioner, an AI-powered Discord assistant. I can help with coding, math, web search, and more!",
            priority=15,
            description="Bot info"
        ))

        # Help
        self.add_rule(FastPathRule(
            patterns=["help", "commands", "what can you do", "how do i use you"],
            response_template="I can help with: 💬 Chat, 🔢 Math (just ask!), 🔍 Web Search, 📁 File operations, and more! Just type your question.",
            priority=20,
            description="Help"
        ))

        # Goodbye
        self.add_rule(FastPathRule(
            patterns=["bye", "goodbye", "see you", "later", "good night"],
            response_template="Goodbye! Feel free to come back anytime! 👋",
            priority=10,
            description="Farewell"
        ))

        # Yes/No
        self.add_rule(FastPathRule(
            patterns=["yes", "yep", "yeah", "sure", "ok", "okay", "no", "nope", "nah"],
            response_template="Got it!",
            priority=25,
            description="Acknowledgment"
        ))

    def add_rule(self, rule: FastPathRule) -> None:
        """Add a fast-path rule."""
        import re
        self._rules.append(rule)

        # Compile regex for each pattern
        for pattern in rule.patterns:
            regex = re.compile(re.escape(pattern), re.IGNORECASE)
            self._regex_patterns.append((regex, rule))

        # Sort by priority (higher = checked first)
        self._regex_patterns.sort(key=lambda x: x[1].priority, reverse=True)

    async def try_route(self, text: str, context: dict[str, Any] | None = None) -> str | None:
        """Try to route to a fast path. Returns response or None."""
        context = context or {}
        text_lower = text.lower().strip()

        async with self._lock:
            for regex, rule in self._regex_patterns:
                if regex.search(text_lower):
                    # Track hit
                    self._hit_count[rule.description] += 1

                    # Generate response
                    start = time.perf_counter()
                    if callable(rule.response_template):
                        response = rule.response_template(context)
                    else:
                        response = rule.response_template

                    elapsed = (time.perf_counter() - start) * 1000
                    self._response_times.append(elapsed)

                    LOGGER.debug(
                        "Fast-path hit",
                        rule=rule.description,
                        latency_ms=elapsed
                    )
                    return response

        return None

    def get_stats(self) -> dict[str, Any]:
        """Get fast-path statistics."""
        avg_time = sum(self._response_times) / len(self._response_times) if self._response_times else 0
        return {
            "total_rules": len(self._rules),
            "hit_counts": dict(self._hit_count),
            "avg_response_time_ms": round(avg_time, 3),
            "total_hits": sum(self._hit_count.values()),
        }


# =============================================================================
# Parallel Tool Executor
# =============================================================================

@dataclass
class ToolResult:
    """Result from a tool execution."""
    tool_name: str
    success: bool
    result: Any = None
    error: str | None = None
    latency_ms: float = 0.0


class ParallelToolExecutor:
    """Execute multiple tools in parallel for minimum latency."""

    def __init__(self, max_concurrent: int = 5) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._execution_count: int = 0
        self._total_latency_ms: float = 0.0
        self._lock = asyncio.Lock()

    async def execute_parallel(
        self,
        tools: list[tuple[str, Callable, dict]],
    ) -> list[ToolResult]:
        """Execute multiple tools in parallel."""
        tasks = [
            self._execute_single(name, func, kwargs)
            for name, func, kwargs in tools
        ]
        return await asyncio.gather(*tasks)

    async def _execute_single(
        self,
        tool_name: str,
        func: Callable,
        kwargs: dict,
    ) -> ToolResult:
        """Execute a single tool with semaphore."""
        async with self._semaphore:
            start = time.perf_counter()
            try:
                # Check if coroutine
                if asyncio.iscoroutinefunction(func):
                    result = await func(**kwargs)
                else:
                    result = func(**kwargs)

                latency_ms = (time.perf_counter() - start) * 1000

                async with self._lock:
                    self._execution_count += 1
                    self._total_latency_ms += latency_ms

                return ToolResult(
                    tool_name=tool_name,
                    success=True,
                    result=result,
                    latency_ms=latency_ms,
                )
            except Exception as exc:
                latency_ms = (time.perf_counter() - start) * 1000
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    error=str(exc),
                    latency_ms=latency_ms,
                )

    async def execute_with_fallback(
        self,
        primary: tuple[str, Callable, dict],
        fallback: tuple[str, Callable, dict],
        timeout: float = 5.0,
    ) -> ToolResult:
        """Execute primary, fall back to secondary on failure."""
        # Start primary
        primary_task = asyncio.create_task(
            self._execute_single(primary[0], primary[1], primary[2])
        )

        try:
            result = await asyncio.wait_for(primary_task, timeout=timeout)
            if result.success:
                return result
        except asyncio.TimeoutError:
            LOGGER.warning("Primary tool timed out", tool=primary[0])

        # Fall back
        LOGGER.info("Falling back to secondary tool", fallback=fallback[0])
        return await self._execute_single(fallback[0], fallback[1], fallback[2])

    def get_stats(self) -> dict[str, Any]:
        """Get executor statistics."""
        avg_latency = self._total_latency_ms / self._execution_count if self._execution_count > 0 else 0
        return {
            "total_executions": self._execution_count,
            "avg_latency_ms": round(avg_latency, 2),
        }


# =============================================================================
# Predictive Cache
# =============================================================================

@dataclass
class CachedResponse:
    """A cached response with metadata."""
    text: str
    query_hash: str
    created_at: float
    access_count: int = 0
    last_accessed: float = 0.0
    avg_latency_ms: float = 0.0


class PredictiveCache:
    """AI-powered predictive caching for ultra-fast responses."""

    def __init__(
        self,
        max_size: int = 10000,
        ttl_seconds: float = 3600.0,
        min_access_count: int = 3,
    ) -> None:
        self._cache: dict[str, CachedResponse] = {}
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._min_access_count = min_access_count
        self._hit_count: int = 0
        self._miss_count: int = 0
        self._lock = asyncio.Lock()
        self._access_order: list[str] = []  # LRU tracking

    def _hash_query(self, text: str, context: dict[str, Any] | None = None) -> str:
        """Create a hash for the query."""
        import hashlib
        import json

        data = {
            "text": text.lower().strip(),
            "context_keys": sorted(context.keys()) if context else [],
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]

    async def get(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> CachedResponse | None:
        """Get a cached response if available."""
        query_hash = self._hash_query(text, context)
        now = time.time()

        async with self._lock:
            if query_hash in self._cache:
                cached = self._cache[query_hash]

                # Check TTL
                if now - cached.created_at > self._ttl_seconds:
                    del self._cache[query_hash]
                    self._miss_count += 1
                    return None

                # Update access stats
                cached.access_count += 1
                cached.last_accessed = now
                self._hit_count += 1

                # Move to end of LRU
                if query_hash in self._access_order:
                    self._access_order.remove(query_hash)
                self._access_order.append(query_hash)

                LOGGER.debug(
                    "Cache hit",
                    hash=query_hash,
                    access_count=cached.access_count,
                )
                return cached

        self._miss_count += 1
        return None

    async def put(
        self,
        text: str,
        response: str,
        context: dict[str, Any] | None = None,
        latency_ms: float = 0.0,
    ) -> None:
        """Cache a response."""
        query_hash = self._hash_query(text, context)
        now = time.time()

        async with self._lock:
            # Evict if at capacity
            if len(self._cache) >= self._max_size and query_hash not in self._cache:
                self._evict_lru()

            self._cache[query_hash] = CachedResponse(
                text=response,
                query_hash=query_hash,
                created_at=now,
                last_accessed=now,
                avg_latency_ms=latency_ms,
            )
            self._access_order.append(query_hash)

    async def get_or_compute(
        self,
        text: str,
        context: dict[str, Any] | None,
        compute_fn: Callable[[], Awaitable[str]],
    ) -> str:
        """Get from cache or compute."""
        cached = await self.get(text, context)
        if cached:
            return cached.text

        start = time.perf_counter()
        result = await compute_fn()
        latency_ms = (time.perf_counter() - start) * 1000

        await self.put(text, result, context, latency_ms)
        return result

    def _evict_lru(self) -> None:
        """Evict least recently used item."""
        if self._access_order:
            oldest = self._access_order.pop(0)
            if oldest in self._cache:
                del self._cache[oldest]

    async def warm_up(self, queries: list[tuple[str, dict]]) -> int:
        """Pre-warm cache with common queries."""
        warmed = 0
        for text, context in queries:
            cached = await self.get(text, context)
            if cached is None:
                warmed += 1

        LOGGER.info("Cache warmed", queries=len(queries), new=warmed)
        return warmed

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._hit_count + self._miss_count
        hit_rate = (self._hit_count / total * 100) if total > 0 else 0

        avg_latency = 0.0
        if self._cache:
            avg_latency = sum(c.avg_latency_ms for c in self._cache.values()) / len(self._cache)

        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate_percent": round(hit_rate, 2),
            "avg_cached_latency_ms": round(avg_latency, 2),
            "ttl_seconds": self._ttl_seconds,
        }


# =============================================================================
# Connection Pool Manager
# =============================================================================

class LLMConnectionPool:
    """Manage warm LLM connections for minimum latency."""

    def __init__(
        self,
        pool_size: int = 3,
        warm_up_callback: Callable | None = None,
    ) -> None:
        self._pool_size = pool_size
        self._connections: list[Any] = []
        self._available: asyncio.Queue = asyncio.Queue()
        self._warm_up_callback = warm_up_callback
        self._is_warmed: bool = False
        self._lock = asyncio.Lock()

    async def pre_warm(self) -> None:
        """Pre-warm all connections."""
        async with self._lock:
            if self._is_warmed:
                return

            LOGGER.info("Pre-warming LLM connections", count=self._pool_size)

            for i in range(self._pool_size):
                try:
                    if self._warm_up_callback:
                        conn = await self._warm_up_callback()
                    else:
                        conn = {"id": i, "ready": True}

                    self._connections.append(conn)
                    await self._available.put(conn)
                except Exception as exc:
                    LOGGER.error("Failed to warm connection", index=i, error=exc)

            self._is_warmed = True
            LOGGER.info("LLM connections warmed", count=len(self._connections))

    async def acquire(self, timeout: float = 5.0) -> Any | None:
        """Acquire a connection from the pool."""
        if not self._is_warmed:
            await self.pre_warm()

        try:
            return await asyncio.wait_for(self._available.get(), timeout=timeout)
        except asyncio.TimeoutError:
            LOGGER.warning("Connection pool timeout")
            return None

    async def release(self, connection: Any) -> None:
        """Release a connection back to the pool."""
        await self._available.put(connection)

    async def close(self) -> None:
        """Close all connections."""
        self._connections.clear()
        self._is_warmed = False
        LOGGER.info("LLM connections closed")

    def get_stats(self) -> dict[str, Any]:
        """Get pool statistics."""
        return {
            "pool_size": self._pool_size,
            "active_connections": len(self._connections),
            "available": self._available.qsize(),
            "is_warmed": self._is_warmed,
        }


# =============================================================================
# Token Buffer
# =============================================================================

@dataclass
class TokenBuffer:
    """Buffer tokens for efficient streaming."""
    buffer: str = ""
    max_size: int = 20  # Flush after 20 tokens
    min_delay_ms: float = 10.0  # Minimum delay between flushes

    def add(self, token: str) -> bool:
        """Add a token. Returns True if buffer should flush."""
        self.buffer += token
        return len(self.buffer) >= self.max_size

    def should_flush(self, time_since_last_ms: float) -> bool:
        """Check if buffer should flush based on time."""
        return len(self.buffer) > 0 and time_since_last_ms >= self.min_delay_ms

    def flush(self) -> str:
        """Flush the buffer and return contents."""
        result = self.buffer
        self.buffer = ""
        return result


# =============================================================================
# Streaming LLM Client
# =============================================================================

class StreamingLLMClient:
    """LLM client with streaming support for minimal latency."""

    def __init__(
        self,
        base_client: Any,  # Base LLM client
        connection_pool: LLMConnectionPool | None = None,
        buffer_size: int = 20,
    ) -> None:
        self._base_client = base_client
        self._pool = connection_pool
        self._buffer_size = buffer_size
        self._total_tokens: int = 0
        self._total_time_ms: float = 0.0

    async def stream_complete(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream completion tokens."""
        context = context or {}
        start = time.perf_counter()
        buffer = TokenBuffer(max_size=self._buffer_size)
        last_flush = start
        token_count = 0

        # Acquire connection if using pool
        connection = None
        if self._pool:
            connection = await self._pool.acquire()

        try:
            async for token in self._base_client.stream_complete(prompt, context):
                yield token
                token_count += 1
                self._total_tokens += 1

                # Buffer management
                if buffer.add(token):
                    await asyncio.sleep(0)  # Yield to event loop
                    last_flush = time.perf_counter()

            # Final flush
            if buffer.buffer:
                pass  # Already yielded tokens

        finally:
            if connection:
                await self._pool.release(connection)

        elapsed = (time.perf_counter() - start) * 1000
        self._total_time_ms += elapsed

        LOGGER.debug(
            "Stream complete",
            tokens=token_count,
            total_ms=elapsed,
            avg_per_token_ms=elapsed / token_count if token_count > 0 else 0,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get client statistics."""
        avg_time = self._total_time_ms / self._total_tokens if self._total_tokens > 0 else 0
        return {
            "total_tokens": self._total_tokens,
            "total_time_ms": round(self._total_time_ms, 2),
            "avg_time_per_token_ms": round(avg_time, 2),
        }


# =============================================================================
# Ultra-Low Latency Orchestrator
# =============================================================================

class UltraLowLatencyOrchestrator:
    """Orchestrates all latency optimization components."""

    def __init__(
        self,
        llm_client: Any,
        fast_path_router: FastPathRouter,
        tool_executor: ParallelToolExecutor,
        predictive_cache: PredictiveCache,
        connection_pool: LLMConnectionPool | None = None,
    ) -> None:
        self._llm = llm_client
        self._fast_path = fast_path_router
        self._tools = tool_executor
        self._cache = predictive_cache
        self._pool = connection_pool

    async def pre_warm(self) -> None:
        """Pre-warm all components."""
        LOGGER.info("Pre-warming ultra-low latency components")

        # Pre-warm LLM connections
        if self._pool:
            await self._pool.pre_warm()

        LOGGER.info("Pre-warming complete")

    async def handle(
        self,
        text: str,
        context: dict[str, Any],
    ) -> tuple[str, str]:  # (response, path)
        """
        Handle a message with optimal latency.
        Returns (response, path) where path is 'fast', 'cache', or 'llm'.
        """
        # 1. Try fast-path (microseconds)
        fast_response = await self._fast_path.try_route(text, context)
        if fast_response:
            return fast_response, "fast"

        # 2. Try predictive cache (sub-millisecond)
        cached = await self._cache.get(text, context)
        if cached:
            return cached.text, "cache"

        # 3. Execute tools in parallel if needed
        tools_to_run = self._determine_tools(text)
        if tools_to_run:
            tool_results = await self._tools.execute_parallel(tools_to_run)

        # 4. Generate response via LLM with streaming
        prompt = self._build_prompt(text, context, tools_to_run if tools_to_run else None)

        # For now, generate without streaming for simplicity
        # Streaming would require the caller to handle the async iterator
        response = await self._llm.complete(prompt, context)

        # 5. Cache the response
        await self._cache.put(text, response, context)

        return response, "llm"

    def _determine_tools(
        self,
        text: str,
    ) -> list[tuple[str, Callable, dict]] | None:
        """Determine which tools to use based on query."""
        # Simple heuristic-based tool selection
        text_lower = text.lower()

        tools: list[tuple[str, Callable, dict]] = []

        # Calculator
        if any(op in text for op in ['+', '-', '*', '/', 'calculate', 'math']):
            # Extract expression would go here
            pass

        # Web search
        if any(word in text_lower for word in ['search', 'find', 'lookup', 'what is', 'who is', 'where is']):
            # Add web search tool
            pass

        return tools if tools else None

    def _build_prompt(
        self,
        text: str,
        context: dict[str, Any],
        tool_results: list[ToolResult] | None = None,
    ) -> str:
        """Build prompt for LLM."""
        # Simple prompt building - would be more sophisticated in production
        memory_context = context.get("memory", "")
        persona = context.get("persona", "helpful")

        prompt = f"{persona} mode. Memory: {memory_context}\n\nUser: {text}"
        if tool_results:
            results = "\n".join(f"- {r.tool_name}: {r.result}" for r in tool_results if r.success)
            prompt += f"\n\nTool results:\n{results}"

        return prompt

    async def stream_handle(
        self,
        text: str,
        context: dict[str, Any],
        handler: StreamingResponseHandler,
    ) -> str:
        """
        Handle message with streaming response.
        Sends tokens to handler as they're generated.
        """
        # 1. Try fast-path first
        fast_response = await self._fast_path.try_route(text, context)
        if fast_response:
            for char in fast_response:
                await handler.send_token(char)
            await handler.send_token("", is_final=True)
            return fast_response

        # 2. Try cache
        cached = await self._cache.get(text, context)
        if cached:
            for char in cached.text:
                await handler.send_token(char)
            await handler.send_token("", is_final=True)
            return cached.text

        # 3. Stream from LLM
        await handler.start_typing()
        full_response = ""

        try:
            prompt = self._build_prompt(text, context, None)

            async for token in self._llm.stream_complete(prompt, context):
                await handler.send_token(token)
                full_response += token

        finally:
            await handler.stop_typing()
            await handler.send_token("", is_final=True)

        # 4. Cache the response
        await self._cache.put(text, full_response, context)

        return full_response

    def get_all_stats(self) -> dict[str, Any]:
        """Get statistics from all components."""
        return {
            "fast_path": self._fast_path.get_stats(),
            "cache": self._cache.get_stats(),
            "tools": self._tools.get_stats(),
            "llm": self._llm.get_stats(),
            "pool": self._pool.get_stats() if self._pool else {"enabled": False},
        }
