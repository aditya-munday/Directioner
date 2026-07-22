"""Provider-neutral LLM facade with retry logic and error handling."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from directioner.config.settings import LlmSettings
from directioner.conversation.context import ContextRecord, ContextSnapshot
from directioner.intent.planner import Plan
from directioner.memory.store import MemoryContext
from directioner.tools.registry import ToolSpec

LOGGER = logging.getLogger(__name__)

# Retry configuration
_MAX_RETRIES = 3
_INITIAL_BACKOFF = 0.5
_MAX_BACKOFF = 8.0
_BACKOFF_MULTIPLIER = 2.0

# Circuit breaker configuration
_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
_CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 30.0

# LLM Response Cache configuration
_LLM_CACHE_MAX_SIZE = 1000
_LLM_CACHE_TTL = 60  # 1 minute cache for LLM responses


class LlmError(Exception):
    """Base exception for LLM-related errors."""
    pass


class LlmRateLimitError(LlmError):
    """Raised when rate limit is hit."""
    pass


class LlmTimeoutError(LlmError):
    """Raised when request times out."""
    pass


class CircuitBreaker:
    """Circuit breaker for fault tolerance."""

    def __init__(
        self,
        failure_threshold: int = _CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout: float = _CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._state = "closed"  # closed, open, half_open

    @property
    def state(self) -> str:
        if self._state == "open":
            if (
                self._last_failure_time
                and time.monotonic() - self._last_failure_time >= self._recovery_timeout
            ):
                self._state = "half_open"
        return self._state

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self._failure_threshold:
            self._state = "open"
            LOGGER.warning(
                "LLM circuit breaker opened after %d failures",
                self._failure_count,
            )

    def can_attempt(self) -> bool:
        return self.state != "open"


async def with_retry(
    coro,
    max_retries: int = _MAX_RETRIES,
    operation_name: str = "LLM request",
):
    """Execute coroutine with exponential backoff retry."""
    last_exception: Exception | None = None
    backoff = _INITIAL_BACKOFF

    for attempt in range(max_retries + 1):
        try:
            return await coro
        except Exception as exc:
            last_exception = exc
            error_type = type(exc).__name__

            # Don't retry on configuration errors
            if isinstance(exc, (ValueError, RuntimeError)):
                if "requires" in str(exc) or "configured" in str(exc):
                    raise

            # Check for rate limit
            if "429" in str(exc) or "rate limit" in str(exc).lower():
                LOGGER.warning(
                    "LLM rate limited, attempt %d/%d",
                    attempt + 1,
                    max_retries + 1,
                )
                if attempt < max_retries:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * _BACKOFF_MULTIPLIER, _MAX_BACKOFF)
                    continue
                raise LlmRateLimitError(f"Rate limited after {max_retries} retries") from exc

            # Check for timeout
            if "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
                LOGGER.warning(
                    "%s timed out, attempt %d/%d",
                    operation_name,
                    attempt + 1,
                    max_retries + 1,
                )
                if attempt < max_retries:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * _BACKOFF_MULTIPLIER, _MAX_BACKOFF)
                    continue
                raise LlmTimeoutError(f"Timed out after {max_retries} retries") from exc

            # Log and retry other errors
            if attempt < max_retries:
                LOGGER.warning(
                    "%s failed (%s), attempt %d/%d, retrying in %.1fs",
                    operation_name,
                    error_type,
                    attempt + 1,
                    max_retries + 1,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * _BACKOFF_MULTIPLIER, _MAX_BACKOFF)
            else:
                LOGGER.error(
                    "%s failed after %d attempts: %s",
                    operation_name,
                    max_retries + 1,
                    exc,
                )

    raise LlmError(f"{operation_name} failed after {max_retries + 1} attempts") from last_exception


@dataclass(frozen=True, slots=True)
class LlmToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LlmMessage:
    role: str
    content: str
    tool_calls: tuple[LlmToolCall, ...] = ()
    tool_call_id: str | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class LlmRequest:
    system_prompt: str
    plan: Plan
    context: ContextSnapshot | None = None
    messages: tuple[LlmMessage, ...] = ()
    memory: MemoryContext | None = None
    tools: tuple[ToolSpec, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LlmResponse:
    content: str
    provider: str
    model: str
    tool_calls: tuple[LlmToolCall, ...] = ()


class LlmClient(Protocol):
    async def complete(self, request: LlmRequest) -> LlmResponse: ...

    async def stream(self, request: LlmRequest) -> AsyncIterator[str]: ...


class MockLlmClient:
    """Deterministic local model substitute used until a real provider is selected."""

    def __init__(self, settings: LlmSettings) -> None:
        self._settings = settings

    async def complete(self, request: LlmRequest) -> LlmResponse:
        prompt = request.plan.prompt.strip()
        if not prompt:
            return LlmResponse(
                content="I am online.",
                provider="mock",
                model=self._settings.model,
            )

        if request.messages and request.messages[-1].role == "tool":
            last_tool_msg = request.messages[-1]
            try:
                import json
                res_data = json.loads(last_tool_msg.content)
                if last_tool_msg.name == "calculator":
                    content = f"The calculator result is {res_data.get('result')}."
                elif last_tool_msg.name == "set_user_preference":
                    content = f"I have saved that: {res_data.get('key')} = {res_data.get('value')}."
                else:
                    content = f"Tool output: {last_tool_msg.content}"
            except Exception:
                content = "Tool output was processed."
            return LlmResponse(
                content=content,
                provider="mock",
                model=self._settings.model,
            )

        tool_calls = []
        if "calculate" in prompt.lower():
            expr = prompt.lower().split("calculate")[-1].strip()
            tool_calls.append(
                LlmToolCall(
                    id="mock-tc-1",
                    name="calculator",
                    arguments={"expression": expr or "2 + 2"},
                )
            )
        elif "remember" in prompt.lower() or "preference" in prompt.lower():
            key, val = "name", "Adi"
            if "remember" in prompt.lower():
                parts = prompt.lower().split("remember")[-1].strip().split(" as ")
                if len(parts) == 2:
                    key, val = parts[0].strip(), parts[1].strip()
            tool_calls.append(
                LlmToolCall(
                    id="mock-tc-2",
                    name="set_user_preference",
                    arguments={"key": key, "value": val},
                )
            )

        if tool_calls:
            return LlmResponse(
                content="",
                provider="mock",
                model=self._settings.model,
                tool_calls=tuple(tool_calls),
            )

        content = self._build_mock_reply(prompt, request)
        return LlmResponse(
            content=content[: self._settings.max_output_chars],
            provider="mock",
            model=self._settings.model,
        )

    async def stream(self, request: LlmRequest) -> AsyncIterator[str]:
        response = await self.complete(request)
        for token in _iter_stream_tokens(response.content):
            yield token

    def _build_mock_reply(self, prompt: str, request: LlmRequest) -> str:
        _ = request
        lowered = prompt.lower()
        if lowered in {"hi", "hello", "hey", "yo"}:
            return (
                "Hey! I'm Directioner and I'm online. "
                "Add `GROQ_API_KEY` to your `.env` for full AI responses."
            )
        return (
            f"You said: {prompt}\n\n"
            "I'm running in mock mode until an LLM API key is configured."
        )


class OpenAiCompatibleClient:
    """Placeholder boundary for OpenAI-compatible chat-completions providers."""

    def __init__(self, settings: LlmSettings) -> None:
        self._settings = settings

    async def complete(self, request: LlmRequest) -> LlmResponse:
        _ = request
        raise RuntimeError(
            "DIRECTIONER_LLM_PROVIDER=openai-compatible is configured, but the HTTP client "
            "adapter is not installed yet. Choose the provider/model and API package next."
        )

    async def stream(self, request: LlmRequest) -> AsyncIterator[str]:
        response = await self.complete(request)
        yield response.content


class GroqLlmClient:
    """Groq chat-completions adapter with retry logic, circuit breaker, and caching."""

    # Class-level LRU cache shared across instances
    _response_cache: dict[str, tuple[LlmResponse, float]] = {}
    _cache_lock = asyncio.Lock()
    _cache_max_size = _LLM_CACHE_MAX_SIZE

    def __init__(self, settings: LlmSettings) -> None:
        self._settings = settings
        try:
            from groq import Groq
        except ImportError as exc:
            raise RuntimeError(
                "DIRECTIONER_LLM_PROVIDER=groq requires the `groq` Python package. "
                "Install it with: pip install groq"
            ) from exc

        kwargs: dict[str, str] = {}
        if settings.api_key:
            kwargs["api_key"] = settings.api_key
        if settings.base_url:
            kwargs["base_url"] = settings.base_url
        self._client = Groq(**kwargs)
        self._circuit_breaker = CircuitBreaker()

    def _make_cache_key(self, request: LlmRequest) -> str:
        """Create a cache key for the request."""
        # Hash the prompt and system prompt for cache key
        data = f"{request.system_prompt}:{request.plan.prompt}:{request.plan.kind.value}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    async def _get_cached_response(self, cache_key: str) -> LlmResponse | None:
        """Get cached response if available and not expired."""
        async with self._cache_lock:
            if cache_key in self._response_cache:
                response, expiry = self._response_cache[cache_key]
                if time.time() < expiry:
                    LOGGER.debug("llm.cache.hit", key=cache_key[:8])
                    return response
                del self._response_cache[cache_key]
        return None

    async def _cache_response(self, cache_key: str, response: LlmResponse) -> None:
        """Cache a response with TTL."""
        async with self._cache_lock:
            # Evict oldest if at capacity
            if len(self._response_cache) >= self._cache_max_size:
                # Remove expired entries first
                now = time.time()
                expired = [k for k, (_, exp) in self._response_cache.items() if exp <= now]
                for k in expired:
                    del self._response_cache[k]

                # If still at capacity, remove oldest
                if len(self._response_cache) >= self._cache_max_size:
                    oldest_key = min(self._response_cache.keys(), key=lambda k: self._response_cache[k][1])
                    del self._response_cache[oldest_key]

            self._response_cache[cache_key] = (response, time.time() + _LLM_CACHE_TTL)
            LOGGER.debug("llm.cache.set", key=cache_key[:8])

    async def complete(self, request: LlmRequest) -> LlmResponse:
        if not self._circuit_breaker.can_attempt():
            raise LlmError("LLM circuit breaker is open. Service temporarily unavailable.")

        # Check cache first (for non-streaming requests without tools)
        if not request.tools and not request.messages:
            cache_key = self._make_cache_key(request)
            cached = await self._get_cached_response(cache_key)
            if cached:
                return cached

        last_exception: Exception | None = None
        backoff = _INITIAL_BACKOFF

        for attempt in range(_MAX_RETRIES + 1):
            try:
                result = await asyncio.to_thread(self._run_complete_sync, request)
                self._circuit_breaker.record_success()
                
                # Build response
                response = LlmResponse(
                    content=result.content[: self._settings.max_output_chars],
                    provider="groq",
                    model=self._settings.model,
                    tool_calls=result.tool_calls,
                )
                
                # Cache the response if applicable
                if not request.tools and not request.messages:
                    await self._cache_response(cache_key, response)
                
                return response
            except Exception as exc:
                last_exception = exc
                error_type = type(exc).__name__

                # Don't retry on configuration errors
                if isinstance(exc, (ValueError, RuntimeError)):
                    if "requires" in str(exc) or "configured" in str(exc):
                        self._circuit_breaker.record_failure()
                        raise

                # Check for rate limit
                if "429" in str(exc) or "rate limit" in str(exc).lower():
                    LOGGER.warning("Groq rate limited, attempt %d/%d", attempt + 1, _MAX_RETRIES + 1)
                    if attempt < _MAX_RETRIES:
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * _BACKOFF_MULTIPLIER, _MAX_BACKOFF)
                        continue
                    self._circuit_breaker.record_failure()
                    raise LlmRateLimitError(f"Rate limited after {_MAX_RETRIES} retries") from exc

                # Check for timeout
                if "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
                    LOGGER.warning("Groq timed out, attempt %d/%d", attempt + 1, _MAX_RETRIES + 1)
                    if attempt < _MAX_RETRIES:
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * _BACKOFF_MULTIPLIER, _MAX_BACKOFF)
                        continue
                    self._circuit_breaker.record_failure()
                    raise LlmTimeoutError(f"Timed out after {_MAX_RETRIES} retries") from exc

                # Log and retry other errors
                if attempt < _MAX_RETRIES:
                    LOGGER.warning(
                        "Groq failed (%s), attempt %d/%d, retrying in %.1fs",
                        error_type,
                        attempt + 1,
                        _MAX_RETRIES + 1,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * _BACKOFF_MULTIPLIER, _MAX_BACKOFF)
                else:
                    LOGGER.error("Groq failed after %d attempts: %s", _MAX_RETRIES + 1, exc)
                    self._circuit_breaker.record_failure()

        raise LlmError(f"Groq complete failed after {_MAX_RETRIES + 1} attempts") from last_exception

    def _groq_create_kwargs(self, request: LlmRequest, *, stream: bool) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._settings.model,
            "messages": _groq_messages(request),
            "temperature": self._settings.temperature,
            "max_completion_tokens": min(self._settings.max_completion_tokens, 1024),
            "top_p": self._settings.top_p,
            "stream": stream,
            "stop": None,
        }
        if request.tools:
            tools_def = [tool_spec_to_openai_tool(t) for t in request.tools]
            kwargs["tools"] = tools_def
            kwargs["tool_choice"] = "auto"
        return kwargs

    def _run_complete_sync(self, request: LlmRequest) -> LlmResponse:
        import json

        completion = self._client.chat.completions.create(
            **self._groq_create_kwargs(request, stream=False)
        )
        choice = completion.choices[0]
        content = choice.message.content or ""
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}
                tool_calls.append(
                    LlmToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args,
                    )
                )
        return LlmResponse(
            content=content[: self._settings.max_output_chars],
            provider="groq",
            model=self._settings.model,
            tool_calls=tuple(tool_calls),
        )

    async def stream(self, request: LlmRequest) -> AsyncIterator[str]:
        if not self._circuit_breaker.can_attempt():
            yield "Service temporarily unavailable. Please try again later."
            return

        queue: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        stream_error: str | None = None

        def run_stream() -> None:
            nonlocal stream_error
            try:
                completion = self._client.chat.completions.create(
                    **self._groq_create_kwargs(request, stream=True)
                )
                for chunk in completion:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        loop.call_soon_threadsafe(queue.put_nowait, content)
            except Exception as exc:
                LOGGER.warning("Groq stream failed: %s", exc)
                stream_error = str(exc)
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    "Sorry, I hit an LLM error. Please try again in a moment.",
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        task = asyncio.create_task(asyncio.to_thread(run_stream))
        try:
            while True:
                item = await asyncio.wait_for(queue.get(), timeout=60.0)
                if item is None:
                    break
                yield item
            if stream_error:
                self._circuit_breaker.record_failure()
            else:
                self._circuit_breaker.record_success()
        except asyncio.TimeoutError:
            task.cancel()
            self._circuit_breaker.record_failure()
            yield "Request timed out. Please try again."
        finally:
            await task


def build_llm_client(settings: LlmSettings) -> LlmClient:
    provider = settings.provider.strip().lower()
    if provider in {"", "mock", "local-mock"}:
        return MockLlmClient(settings)
    if provider == "groq":
        if not (settings.api_key or os.getenv("GROQ_API_KEY")):
            LOGGER.warning(
                "Groq provider configured but no API key found; falling back to mock LLM. "
                "Set GROQ_API_KEY or DIRECTIONER_LLM_API_KEY in .env."
            )
            return MockLlmClient(settings)
        return GroqLlmClient(settings)
    if provider in {"openai-compatible", "openai_compatible"}:
        if not settings.api_key:
            LOGGER.warning(
                "OpenAI-compatible provider configured but no API key found; "
                "falling back to mock LLM."
            )
            return MockLlmClient(settings)
        return OpenAiCompatibleClient(settings)
    raise ValueError(f"Unsupported LLM provider: {settings.provider}")


def _iter_stream_tokens(content: str) -> tuple[str, ...]:
    """Split ``content`` into word-with-trailing-space tokens for streaming."""

    if not content:
        return ()
    tokens: list[str] = []
    current = ""
    for char in content:
        current += char
        if char.isspace():
            tokens.append(current)
            current = ""
    if current:
        tokens.append(current)
    return tuple(tokens)


def tool_spec_to_openai_tool(spec: ToolSpec) -> dict[str, Any]:
    if spec.name == "calculator":
        return {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": spec.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "The arithmetic expression to evaluate (e.g. '2 + 2')."
                        }
                    },
                    "required": ["expression"]
                }
            }
        }
    if spec.name == "set_user_preference":
        return {
            "type": "function",
            "function": {
                "name": "set_user_preference",
                "description": spec.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "The key of the preference to set (e.g. 'name', 'favorite_color')."
                        },
                        "value": {
                            "type": "string",
                            "description": "The value of the preference."
                        }
                    },
                    "required": ["key", "value"]
                }
            }
        }
    if spec.name == "delete_user_preference":
        return {
            "type": "function",
            "function": {
                "name": "delete_user_preference",
                "description": spec.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "The key of the preference to delete (e.g. 'name', 'favorite_color')."
                        }
                    },
                    "required": ["key"]
                }
            }
        }
    if spec.name == "web_search":
        return {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": spec.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to run on the public web.",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Optional result cap between 1 and 8.",
                        },
                    },
                    "required": ["query"],
                },
            },
        }
    if spec.name in {"read_file", "list_directory"}:
        return {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path relative to the configured tool base directory.",
                        }
                    },
                    "required": [],
                },
            },
        }
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }


_GROQ_MAX_MESSAGES = 6
_GROQ_MAX_MESSAGE_CHARS = 400
_GROQ_MAX_SYSTEM_CHARS = 800
_GROQ_MAX_CONTEXT_RECORDS = 3


def _format_system_prompt_with_memory(system_prompt: str, memory: MemoryContext | None) -> str:
    if not memory:
        return system_prompt[:_GROQ_MAX_SYSTEM_CHARS]
    parts = [system_prompt]
    if memory.user_preferences:
        prefs = "\n".join(f"- {k}: {v}" for k, v in memory.user_preferences.items())
        parts.append(f"USER PREFERENCES:\n{prefs}")
    if memory.semantic:
        sems = "\n".join(f"- {s[:200]}" for s in memory.semantic[:3])
        parts.append(f"RELEVANT HISTORICAL CONTEXT:\n{sems}")
    combined = "\n\n".join(parts)
    return combined[:_GROQ_MAX_SYSTEM_CHARS]


def _clip_groq_content(text: str) -> str:
    cleaned = text.strip()
    if len(cleaned) <= _GROQ_MAX_MESSAGE_CHARS:
        return cleaned
    return cleaned[: _GROQ_MAX_MESSAGE_CHARS - 3] + "..."


def _append_groq_message(
    messages: list[dict[str, Any]],
    *,
    role: str,
    content: str,
) -> None:
    clipped = _clip_groq_content(content)
    if not clipped:
        return
    if messages and messages[-1].get("role") == role and messages[-1].get("content") == clipped:
        return
    messages.append({"role": role, "content": clipped})


def _groq_messages(request: LlmRequest) -> list[dict[str, Any]]:
    import json
    messages: list[dict[str, Any]] = []

    system_prompt = request.system_prompt.strip()
    if request.memory:
        system_prompt = _format_system_prompt_with_memory(system_prompt, request.memory)
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt[:_GROQ_MAX_SYSTEM_CHARS]})

    prompt = request.plan.prompt.strip()
    for record in _context_records(request.context)[-_GROQ_MAX_CONTEXT_RECORDS:]:
        if record.role == "tool":
            continue
        if record.role == "user" and record.content.strip() == prompt:
            continue
        role = "assistant" if record.role == "assistant" else "user"
        _append_groq_message(messages, role=role, content=record.content)

    for msg in request.messages:
        if msg.role == "assistant" and msg.tool_calls:
            messages.append({
                "role": "assistant",
                "content": msg.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                        }
                    }
                    for tc in msg.tool_calls
                ]
            })
        elif msg.role == "tool":
            messages.append({
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "name": msg.name,
                "content": msg.content
            })
        else:
            content = msg.content.strip()
            if content:
                messages.append({"role": msg.role, "content": content})

    prompt = request.plan.prompt.strip()
    if prompt:
        already_present = False
        if messages and messages[-1].get("role") == "user" and messages[-1].get("content") == prompt:
            already_present = True
        if not already_present:
            _append_groq_message(messages, role="user", content=prompt)

    if not messages:
        messages.append({"role": "user", "content": ""})
    return messages[-_GROQ_MAX_MESSAGES:]


def _context_records(context: ContextSnapshot | None) -> tuple[ContextRecord, ...]:
    if context is None:
        return ()
    kept: list[ContextRecord] = []
    for record in context.records[-12:]:
        if record.role == "user" or record.role == "tool":
            kept.append(record)
            continue
        if _is_usable_assistant_context(record.content):
            kept.append(record)
    return tuple(kept)


def _is_usable_assistant_context(content: str) -> bool:
    lowered = content.lower()
    blocked = (
        "python llm facade",
        "mock mode",
        "groq_api_key",
        "i retrieved relevant memories",
    )
    return bool(content.strip()) and not any(phrase in lowered for phrase in blocked)


def _recent_user_lines(context: ContextSnapshot | None) -> tuple[str, ...]:
    if context is None:
        return ()

    lines: list[str] = []
    for record in context.records[-5:]:
        lines.append(_record_text(record))
    return tuple(line for line in lines if line)


def _record_text(record: ContextRecord) -> str:
    text = record.content.strip()
    if not text:
        return ""
    return f"{record.role}: {text}"
