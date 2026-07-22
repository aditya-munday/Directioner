"""Ultra-performance module with latency optimization and caching.

This module provides:
- LRU cache with TTL for hot paths
- Request coalescing to prevent duplicate work
- Latency tracking and metrics
- Connection pooling helpers
- Performance decorators
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

import structlog

LOGGER = structlog.get_logger(__name__)

T = TypeVar("T")

# Performance constants
MAX_LRU_CACHE_SIZE = 10_000
DEFAULT_TTL = 300  # 5 minutes
CLEANUP_INTERVAL = 60  # seconds


# ============================================================================
# LRU Cache with TTL
# ============================================================================

class LRUCache:
    """Thread-safe LRU cache with TTL expiration.
    
    Optimized for minimum latency with O(1) get/put operations.
    """

    def __init__(
        self,
        max_size: int = MAX_LRU_CACHE_SIZE,
        default_ttl: int = DEFAULT_TTL,
    ) -> None:
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def _make_key(self, *args: Any, **kwargs: Any) -> str:
        """Create a cache key from arguments."""
        key_data = str(args) + str(sorted(kwargs.items()))
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]

    def get(self, key: str) -> Any | None:
        """Get value from cache if not expired. O(1) operation."""
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, expiry = self._cache[key]
            if time.monotonic() > expiry:
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set value in cache with TTL. O(1) operation."""
        with self._lock:
            expiry = time.monotonic() + (ttl or self._default_ttl)

            # If key exists, update and move to end
            if key in self._cache:
                self._cache.move_to_end(key)

            # Evict oldest if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            self._cache[key] = (value, expiry)

    def delete(self, key: str) -> bool:
        """Delete a key from cache. O(1) operation."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear the entire cache."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
            }


# ============================================================================
# Async LRU Cache
# ============================================================================

class AsyncLRUCache:
    """Async-safe LRU cache with TTL for use in async contexts."""

    def __init__(
        self,
        max_size: int = MAX_LRU_CACHE_SIZE,
        default_ttl: int = DEFAULT_TTL,
    ) -> None:
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock: asyncio.Lock | None = None
        self._hits = 0
        self._misses = 0

    async def _get_lock(self) -> asyncio.Lock:
        """Lazy initialization of asyncio lock."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def get(self, key: str) -> Any | None:
        """Get value from cache if not expired."""
        lock = await self._get_lock()
        async with lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, expiry = self._cache[key]
            if time.monotonic() > expiry:
                del self._cache[key]
                self._misses += 1
                return None

            self._cache.move_to_end(key)
            self._hits += 1
            return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set value in cache with TTL."""
        lock = await self._get_lock()
        async with lock:
            expiry = time.monotonic() + (ttl or self._default_ttl)

            if key in self._cache:
                self._cache.move_to_end(key)

            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            self._cache[key] = (value, expiry)

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        lock = await self._get_lock()
        async with lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear the entire cache."""
        lock = await self._get_lock()
        async with lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
        }


# ============================================================================
# Request Coalescing
# ============================================================================

class RequestCoalescer:
    """Coalesce duplicate requests to prevent redundant work.
    
    When multiple requests with the same key arrive simultaneously,
    only one request is executed and all waiters share the result.
    """

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def execute(
        self,
        key: str,
        coro_factory: Callable[[], Any],
    ) -> Any:
        """Execute request with coalescing."""
        # Check if already pending
        async with self._lock:
            if key in self._pending:
                future = self._pending[key]
            else:
                future = asyncio.get_event_loop().create_future()
                self._pending[key] = future

        # If we created the future, execute the request
        if not future.done():
            try:
                result = await coro_factory()
                future.set_result(result)
            except Exception as exc:
                future.set_exception(exc)
            finally:
                # Clean up after completion
                async with self._lock:
                    self._pending.pop(key, None)

        return await future


# ============================================================================
# Latency Tracker
# ============================================================================

@dataclass
class LatencyBucket:
    """Histogram bucket for latency tracking."""
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0

    def record(self, ms: float) -> None:
        """Record a latency measurement."""
        self.count += 1
        self.total_ms += ms
        self.min_ms = min(self.min_ms, ms)
        self.max_ms = max(self.max_ms, ms)

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count > 0 else 0.0


class LatencyTracker:
    """Track latency metrics with histogram buckets.
    
    Provides p50, p95, p99 latency tracking for performance monitoring.
    """

    def __init__(self, num_buckets: int = 1000) -> None:
        self._num_buckets = num_buckets
        self._measurements: list[float] = []
        self._lock = threading.Lock()
        self._total = LatencyBucket()
        self._by_operation: dict[str, LatencyBucket] = {}
        self._start_times: dict[str, float] = {}

    def start(self, operation: str) -> str:
        """Start timing an operation. Returns a handle for end()."""
        key = f"{operation}:{time.monotonic()}"
        self._start_times[key] = time.perf_counter()
        return key

    def end(self, handle: str) -> float:
        """End timing and record latency. Returns latency in milliseconds."""
        start_time = self._start_times.pop(handle, None)
        if start_time is None:
            return 0.0

        latency_ms = (time.perf_counter() - start_time) * 1000

        # Extract operation name
        operation = handle.split(":")[0]

        # Record global
        with self._lock:
            self._total.record(latency_ms)
            self._measurements.append(latency_ms)
            if len(self._measurements) > self._num_buckets:
                self._measurements = self._measurements[-self._num_buckets:]

            # Record by operation
            if operation not in self._by_operation:
                self._by_operation[operation] = LatencyBucket()
            self._by_operation[operation].record(latency_ms)

        return latency_ms

    def get_percentile(self, percentile: float) -> float:
        """Get latency percentile (0-100)."""
        with self._lock:
            if not self._measurements:
                return 0.0
            sorted_ms = sorted(self._measurements)
            idx = int(len(sorted_ms) * percentile / 100)
            return sorted_ms[min(idx, len(sorted_ms) - 1)]

    def _compute_percentile(self, measurements: list[float], percentile: float) -> float:
        """Compute percentile without acquiring lock (caller must hold lock)."""
        if not measurements:
            return 0.0
        sorted_ms = sorted(measurements)
        idx = int(len(sorted_ms) * percentile / 100)
        return sorted_ms[min(idx, len(sorted_ms) - 1)]

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive statistics."""
        with self._lock:
            op_stats = {}
            for op, bucket in self._by_operation.items():
                if bucket.count > 0:
                    op_stats[op] = {
                        "count": bucket.count,
                        "avg_ms": round(bucket.avg_ms, 2),
                        "min_ms": round(bucket.min_ms, 2),
                        "max_ms": round(bucket.max_ms, 2),
                        "p50": round(self._compute_percentile(self._measurements, 50), 2),
                        "p95": round(self._compute_percentile(self._measurements, 95), 2),
                        "p99": round(self._compute_percentile(self._measurements, 99), 2),
                    }

            return {
                "total": {
                    "count": self._total.count,
                    "avg_ms": round(self._total.avg_ms, 2),
                    "min_ms": round(self._total.min_ms, 2) if self._total.min_ms < float("inf") else 0,
                    "max_ms": round(self._total.max_ms, 2),
                    "p50": round(self._compute_percentile(self._measurements, 50), 2),
                    "p95": round(self._compute_percentile(self._measurements, 95), 2),
                    "p99": round(self._compute_percentile(self._measurements, 99), 2),
                },
                "by_operation": op_stats,
            }

    def clear(self) -> None:
        """Clear all measurements."""
        with self._lock:
            self._measurements.clear()
            self._total = LatencyBucket()
            self._by_operation.clear()
            self._start_times.clear()


# ============================================================================
# Performance Decorators
# ============================================================================

def cached(
    cache: LRUCache | AsyncLRUCache,
    key_func: Callable[..., str] | None = None,
    ttl: int | None = None,
) -> Callable:
    """Decorator to cache function results."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            # Build cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = cache._make_key(*args, **kwargs)

            # Check cache
            result = cache.get(cache_key)
            if result is not None:
                LOGGER.debug("cache.hit", function=func.__name__, key=cache_key[:8])
                return result

            # Execute and cache
            LOGGER.debug("cache.miss", function=func.__name__, key=cache_key[:8])
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            # Build cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # For async, use a simpler key
                cache_key = hashlib.md5(f"{func.__name__}:{str(args)}:{str(kwargs)}".encode()).hexdigest()[:32]

            # Check cache
            if isinstance(cache, AsyncLRUCache):
                result = await cache.get(cache_key)
            else:
                result = cache.get(cache_key)

            if result is not None:
                LOGGER.debug("cache.hit", function=func.__name__, key=cache_key[:8])
                return result

            # Execute and cache
            LOGGER.debug("cache.miss", function=func.__name__, key=cache_key[:8])
            result = await func(*args, **kwargs)

            if isinstance(cache, AsyncLRUCache):
                await cache.set(cache_key, result, ttl)
            else:
                cache.set(cache_key, result, ttl)

            return result

        # Return appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def timed(tracker: LatencyTracker) -> Callable:
    """Decorator to track function execution time."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            handle = tracker.start(func.__name__)
            try:
                return func(*args, **kwargs)
            finally:
                tracker.end(handle)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            handle = tracker.start(func.__name__)
            try:
                return await func(*args, **kwargs)
            finally:
                tracker.end(handle)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ============================================================================
# Global Performance Instance
# ============================================================================

# Global latency tracker for application-wide use
global_latency_tracker = LatencyTracker()

# Global LLM response cache
llm_response_cache = LRUCache(max_size=1000, default_ttl=60)

# Global tool result cache
tool_result_cache = LRUCache(max_size=500, default_ttl=300)

# Global request coalescer
request_coalescer = RequestCoalescer()


# ============================================================================
# Performance Utilities
# ============================================================================

async def parallel_execute(
    *coros: Any,
    max_concurrent: int = 5,
) -> tuple[Any, ...]:
    """Execute multiple coroutines in parallel with a concurrency limit.

    Args:
        *coros: Coroutines to execute
        max_concurrent: Maximum concurrent executions

    Returns:
        Tuple of results
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def with_semaphore(coro: Any) -> Any:
        async with semaphore:
            return await coro

    wrapped = [with_semaphore(c) for c in coros]
    return await asyncio.gather(*wrapped)


def fast_hash(*args: Any) -> str:
    """Fast string hash for cache keys."""
    data = str(args).encode()
    return hashlib.sha256(data).hexdigest()[:16]
