
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

try:
    from supabase import create_client, Client
    from supabase.lib.client_options import ClientOptions
except ImportError:
    Client = None
    create_client = None
    ClientOptions = None

import structlog

LOGGER = structlog.get_logger(__name__)

# ============================================================================
# Configuration
# ============================================================================

SUPABASE_MAX_RETRIES = 3
SUPABASE_INITIAL_BACKOFF = 0.1
SUPABASE_MAX_BACKOFF = 2.0
SUPABASE_BACKOFF_MULTIPLIER = 2.0

SUPABASE_CONNECTION_TIMEOUT = 10.0
SUPABASE_REQUEST_TIMEOUT = 30.0

# Batch operation settings
BATCH_INSERT_SIZE = 100
BATCH_FLUSH_INTERVAL = 1.0  # seconds

# Circuit breaker settings
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 10
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 60.0
CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS = 3


# ============================================================================
# Exceptions
# ============================================================================

class SupabaseError(Exception):
    """Base exception for Supabase operations."""
    pass


class SupabaseConnectionError(SupabaseError):
    """Raised when connection to Supabase fails."""
    pass


class SupabaseQueryError(SupabaseError):
    """Raised when a query fails."""
    pass


class SupabaseRateLimitError(SupabaseError):
    """Raised when rate limited."""
    pass


class SupabaseCircuitOpenError(SupabaseError):
    """Raised when circuit breaker is open."""
    pass


# ============================================================================
# Circuit Breaker
# ============================================================================

class CircuitBreakerState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class SupabaseCircuitBreaker:
    """Circuit breaker for Supabase operations.
    
    Prevents cascading failures when Supabase is unavailable.
    """

    def __init__(
        self,
        failure_threshold: int = CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout: float = CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
        half_open_max_calls: int = CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._state = CircuitBreakerState.CLOSED
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        if self._state == CircuitBreakerState.OPEN:
            if (
                self._last_failure_time
                and time.monotonic() - self._last_failure_time >= self._recovery_timeout
            ):
                return CircuitBreakerState.HALF_OPEN
        return self._state

    async def can_attempt(self) -> bool:
        """Check if a request can be attempted."""
        async with self._lock:
            current_state = self.state
            
            if current_state == CircuitBreakerState.CLOSED:
                return True
            
            if current_state == CircuitBreakerState.HALF_OPEN:
                if self._half_open_calls < self._half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            
            # OPEN state
            return False

    async def record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            self._failure_count = 0
            self._success_count += 1
            self._half_open_calls = 0
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._state = CircuitBreakerState.CLOSED
                LOGGER.info("Supabase circuit breaker closed after successful recovery")

    async def record_failure(self, error: Exception | None = None) -> None:
        """Record a failed call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            self._half_open_calls = 0
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._state = CircuitBreakerState.OPEN
                LOGGER.warning("Supabase circuit breaker reopened after failure")
            elif self._failure_count >= self._failure_threshold:
                self._state = CircuitBreakerState.OPEN
                LOGGER.warning(
                    "Supabase circuit breaker opened after %d failures",
                    self._failure_count,
                )

    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "state": self.state,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self._failure_threshold,
            "recovery_timeout": self._recovery_timeout,
        }


# ============================================================================
# Connection Pool Manager
# ============================================================================

@dataclass
class ConnectionStats:
    """Statistics for a Supabase connection."""
    created_at: float = 0.0
    last_used: float = 0.0
    requests: int = 0
    errors: int = 0
    avg_latency_ms: float = 0.0
    total_latency_ms: float = 0.0

    def record_request(self, latency_ms: float) -> None:
        """Record a request latency."""
        self.requests += 1
        self.total_latency_ms += latency_ms
        self.avg_latency_ms = self.total_latency_ms / self.requests if self.requests > 0 else 0.0


class SupabasePool:
    """Connection pool for Supabase with health monitoring.
    
    Manages multiple Supabase client connections for better performance
    and fault tolerance.
    """

    def __init__(
        self,
        url: str,
        key: str,
        pool_size: int = 3,
        health_check_interval: float = 30.0,
    ) -> None:
        self._url = url
        self._key = key
        self._pool_size = pool_size
        self._health_check_interval = health_check_interval
        
        self._clients: list[Client] = []
        self._available: asyncio.Queue[Client] = asyncio.Queue()
        self._stats: list[ConnectionStats] = []
        self._circuit_breaker = SupabaseCircuitBreaker()
        
        self._initialized = False
        self._closed = False
        self._lock = asyncio.Lock()
        self._health_check_task: asyncio.Task | None = None
        
        self._total_requests = 0
        self._total_errors = 0
        self._avg_latency_ms = 0.0

    async def initialize(self) -> None:
        """Initialize the connection pool."""
        if self._initialized:
            return
            
        async with self._lock:
            if self._initialized:
                return
                
            LOGGER.info("Initializing Supabase connection pool", pool_size=self._pool_size)
            
            # Create initial connections
            for i in range(self._pool_size):
                try:
                    client = self._create_client()
                    self._clients.append(client)
                    await self._available.put(client)
                    self._stats.append(ConnectionStats(
                        created_at=time.time(),
                        last_used=time.time(),
                    ))
                    LOGGER.info("Created Supabase connection %d", i)
                except Exception as exc:
                    LOGGER.error("Failed to create Supabase connection %d: %s", i, exc)
            
            if not self._clients:
                raise SupabaseConnectionError("Failed to create any Supabase connections")
            
            # Start health check task
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            self._initialized = True
            LOGGER.info("Supabase connection pool initialized", connections=len(self._clients))

    def _create_client(self) -> Client:
        """Create a new Supabase client."""
        if create_client is None:
            raise SupabaseConnectionError("Supabase client library not installed")
        
        return create_client(self._url, self._key)

    async def acquire(self) -> Client:
        """Acquire a connection from the pool."""
        if not self._initialized:
            await self.initialize()
        
        if self._closed:
            raise SupabaseConnectionError("Connection pool is closed")
        
        # Check circuit breaker
        if not await self._circuit_breaker.can_attempt():
            raise SupabaseCircuitOpenError("Circuit breaker is open, Supabase is unavailable")
        
        # Get client from pool (with timeout)
        try:
            client = await asyncio.wait_for(
                self._available.get(),
                timeout=SUPABASE_CONNECTION_TIMEOUT,
            )
            return client
        except asyncio.TimeoutError:
            raise SupabaseConnectionError("Timeout waiting for available connection")

    async def release(self, client: Client) -> None:
        """Release a connection back to the pool."""
        if self._closed:
            return
            
        try:
            self._available.put_nowait(client)
        except asyncio.QueueFull:
            LOGGER.warning("Connection pool full, closing excess connection")

    async def execute_with_retry(
        self,
        operation: str,
        query_func: callable,
    ) -> Any:
        """Execute a query with retry logic and circuit breaker."""
        if not await self._circuit_breaker.can_attempt():
            raise SupabaseCircuitOpenError("Circuit breaker is open")
        
        last_error: Exception | None = None
        backoff = SUPABASE_INITIAL_BACKOFF
        
        for attempt in range(SUPABASE_MAX_RETRIES + 1):
            start_time = time.perf_counter()
            client = None
            
            try:
                client = await self.acquire()
                
                # Execute the query
                result = query_func(client)
                
                # Record success
                latency_ms = (time.perf_counter() - start_time) * 1000
                await self._circuit_breaker.record_success()
                self._total_requests += 1
                self._avg_latency_ms = (
                    (self._avg_latency_ms * (self._total_requests - 1) + latency_ms)
                    / self._total_requests
                )
                
                LOGGER.debug(
                    "Supabase operation succeeded",
                    operation=operation,
                    latency_ms=latency_ms,
                    attempt=attempt + 1,
                )
                
                return result
                
            except SupabaseCircuitOpenError:
                raise
            except Exception as exc:
                last_error = exc
                error_str = str(exc).lower()
                
                # Record failure
                await self._circuit_breaker.record_failure(exc)
                self._total_errors += 1
                
                # Check for rate limit
                if "429" in error_str or "rate limit" in error_str:
                    if attempt < SUPABASE_MAX_RETRIES:
                        LOGGER.warning(
                            "Supabase rate limited, attempt %d/%d, backing off %.2fs",
                            attempt + 1,
                            SUPABASE_MAX_RETRIES + 1,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * SUPABASE_BACKOFF_MULTIPLIER, SUPABASE_MAX_BACKOFF)
                        continue
                    raise SupabaseRateLimitError(f"Rate limited after {SUPABASE_MAX_RETRIES} retries") from exc
                
                # Check for connection error
                if any(x in error_str for x in ["connection", "timeout", "network", "refused"]):
                    if attempt < SUPABASE_MAX_RETRIES:
                        LOGGER.warning(
                            "Supabase connection error, attempt %d/%d, backing off %.2fs: %s",
                            attempt + 1,
                            SUPABASE_MAX_RETRIES + 1,
                            backoff,
                            exc,
                        )
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * SUPABASE_BACKOFF_MULTIPLIER, SUPABASE_MAX_BACKOFF)
                        continue
                    raise SupabaseConnectionError(f"Connection failed after {SUPABASE_MAX_RETRIES} retries") from exc
                
                # Other errors - don't retry
                LOGGER.error("Supabase operation failed: %s", exc)
                raise SupabaseQueryError(f"Query failed: {exc}") from exc
                
            finally:
                if client is not None:
                    await self.release(client)
        
        raise SupabaseError(f"Operation failed after {SUPABASE_MAX_RETRIES + 1} attempts") from last_error

    async def health_check(self) -> bool:
        """Perform a health check on all connections."""
        LOGGER.debug("Running Supabase health check")
        
        healthy_count = 0
        for i, (client, stats) in enumerate(zip(self._clients, self._stats)):
            try:
                # Simple health check - query system info
                start = time.perf_counter()
                client.table("conversation_memory").select("id").limit(1).execute()
                latency = (time.perf_counter() - start) * 1000
                stats.record_request(latency)
                stats.last_used = time.time()
                healthy_count += 1
                LOGGER.debug("Connection %d healthy", i, latency_ms=latency)
            except Exception as exc:
                stats.errors += 1
                LOGGER.warning("Connection %d unhealthy: %s", i, exc)
        
        is_healthy = healthy_count > 0
        LOGGER.info(
            "Supabase health check complete",
            healthy=healthy_count,
            total=len(self._clients),
            healthy_pct=round(healthy_count / len(self._clients) * 100, 1) if self._clients else 0,
        )
        return is_healthy

    async def _health_check_loop(self) -> None:
        """Background health check loop."""
        while not self._closed:
            try:
                await asyncio.sleep(self._health_check_interval)
                if not self._closed:
                    await self.health_check()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                LOGGER.error("Health check loop error: %s", exc)

    async def close(self) -> None:
        """Close all connections in the pool."""
        self._closed = True
        
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Drain the queue
        while not self._available.empty():
            try:
                self._available.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        LOGGER.info("Supabase connection pool closed")

    def get_stats(self) -> dict[str, Any]:
        """Get connection pool statistics."""
        return {
            "initialized": self._initialized,
            "closed": self._closed,
            "pool_size": self._pool_size,
            "available": self._available.qsize(),
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "avg_latency_ms": round(self._avg_latency_ms, 2),
            "circuit_breaker": self._circuit_breaker.get_stats(),
            "connections": [
                {
                    "created_at": s.created_at,
                    "last_used": s.last_used,
                    "requests": s.requests,
                    "errors": s.errors,
                    "avg_latency_ms": round(s.avg_latency_ms, 2),
                }
                for s in self._stats
            ],
        }


# ============================================================================
# Batch Operations
# ============================================================================

class BatchOperation:
    """Represents a pending batch operation."""
    
    def __init__(self, table: str, data: list[dict]) -> None:
        self.table = table
        self.data = data
        self.created_at = time.time()


class BatchProcessor:
    """Batches multiple operations for efficient bulk execution.
    
    Accumulates inserts and flushes them in batches for better performance.
    """

    def __init__(
        self,
        pool: SupabasePool,
        batch_size: int = BATCH_INSERT_SIZE,
        flush_interval: float = BATCH_FLUSH_INTERVAL,
    ) -> None:
        self._pool = pool
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._pending: dict[str, list[dict]] = {}
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None
        self._closed = False
        
        self._total_batches = 0
        self._total_items = 0
        self._errors = 0

    async def initialize(self) -> None:
        """Initialize the batch processor."""
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def add_insert(self, table: str, data: dict) -> None:
        """Add an insert to the batch queue."""
        async with self._lock:
            if table not in self._pending:
                self._pending[table] = []
            self._pending[table].append(data)
            
            # Flush if batch size reached
            if len(self._pending[table]) >= self._batch_size:
                await self._flush_table(table)

    async def _flush_table(self, table: str) -> None:
        """Flush pending inserts for a specific table."""
        if table not in self._pending or not self._pending[table]:
            return
        
        data = self._pending.pop(table)
        
        try:
            await self._pool.execute_with_retry(
                f"batch_insert_{table}",
                lambda client: client.table(table).insert(data).execute(),
            )
            self._total_batches += 1
            self._total_items += len(data)
            LOGGER.debug(
                "Batch insert completed",
                table=table,
                count=len(data),
            )
        except Exception as exc:
            self._errors += 1
            LOGGER.error("Batch insert failed for %s: %s", table, exc)
            # Re-queue failed items
            if table not in self._pending:
                self._pending[table] = []
            self._pending[table].extend(data)

    async def flush(self) -> None:
        """Flush all pending operations."""
        async with self._lock:
            tables = list(self._pending.keys())
        
        for table in tables:
            await self._flush_table(table)

    async def _flush_loop(self) -> None:
        """Background flush loop."""
        while not self._closed:
            try:
                await asyncio.sleep(self._flush_interval)
                if not self._closed:
                    await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                LOGGER.error("Flush loop error: %s", exc)

    async def close(self) -> None:
        """Close the batch processor and flush remaining items."""
        self._closed = True
        
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        # Final flush
        await self.flush()
        
        LOGGER.info(
            "Batch processor closed",
            total_batches=self._total_batches,
            total_items=self._total_items,
            errors=self._errors,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get batch processor statistics."""
        return {
            "pending_tables": list(self._pending.keys()),
            "pending_items": sum(len(v) for v in self._pending.values()),
            "total_batches": self._total_batches,
            "total_items": self._total_items,
            "errors": self._errors,
        }


# ============================================================================
# Query Optimizer
# ============================================================================

class QueryOptimizer:
    """Optimizes queries for better performance.
    
    Features:
    - Query pagination
    - Index hints
    - Query caching
    """

    def __init__(self, cache_size: int = 1000, cache_ttl: float = 60.0) -> None:
        self._cache: dict[str, tuple[Any, float]] = {}
        self._cache_size = cache_size
        self._cache_ttl = cache_ttl
        self._lock = asyncio.Lock()

    async def get_cached(
        self,
        cache_key: str,
    ) -> Any | None:
        """Get cached query result."""
        async with self._lock:
            if cache_key in self._cache:
                result, expiry = self._cache[cache_key]
                if time.time() < expiry:
                    return result
                del self._cache[cache_key]
        return None

    async def set_cached(self, cache_key: str, result: Any) -> None:
        """Cache a query result."""
        async with self._lock:
            # Evict if full
            if len(self._cache) >= self._cache_size:
                # Remove expired first
                now = time.time()
                expired = [k for k, (_, exp) in self._cache.items() if exp <= now]
                for k in expired:
                    del self._cache[k]
                
                # Still full? Remove oldest
                if len(self._cache) >= self._cache_size:
                    oldest_key = min(self._cache.keys())
                    del self._cache[oldest_key]
            
            self._cache[cache_key] = (result, time.time() + self._cache_ttl)

    def paginate_query(
        self,
        total_items: int,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """Calculate pagination parameters."""
        total_pages = (total_items + page_size - 1) // page_size if page_size > 0 else 1
        offset = page * page_size
        
        return {
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "offset": offset,
            "has_next": page < total_pages - 1,
            "has_prev": page > 0,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get query optimizer statistics."""
        return {
            "cache_size": len(self._cache),
            "cache_max_size": self._cache_size,
        }


# ============================================================================
# Global Pool Instance
# ============================================================================

_supabase_pool: SupabasePool | None = None
_batch_processor: BatchProcessor | None = None
_query_optimizer: QueryOptimizer | None = None


async def get_supabase_pool(
    url: str | None = None,
    key: str | None = None,
    pool_size: int = 3,
) -> SupabasePool:
    """Get or create the global Supabase connection pool."""
    global _supabase_pool
    
    if _supabase_pool is None:
        if url is None or key is None:
            raise SupabaseError("Supabase URL and key are required")
        
        _supabase_pool = SupabasePool(url, key, pool_size)
        await _supabase_pool.initialize()
    
    return _supabase_pool


async def get_batch_processor() -> BatchProcessor | None:
    """Get the global batch processor."""
    global _batch_processor
    return _batch_processor


async def get_query_optimizer() -> QueryOptimizer | None:
    """Get the global query optimizer."""
    global _query_optimizer
    
    if _query_optimizer is None:
        _query_optimizer = QueryOptimizer()
    
    return _query_optimizer


async def initialize_supabase(
    url: str,
    key: str,
    pool_size: int = 3,
    enable_batching: bool = True,
) -> dict[str, Any]:
    """Initialize the Supabase integration."""
    global _supabase_pool, _batch_processor, _query_optimizer
    
    LOGGER.info("Initializing Supabase integration", url=url, pool_size=pool_size)
    
    # Create connection pool
    _supabase_pool = SupabasePool(url, key, pool_size)
    await _supabase_pool.initialize()
    
    # Create batch processor
    if enable_batching:
        _batch_processor = BatchProcessor(_supabase_pool)
        await _batch_processor.initialize()
    
    # Create query optimizer
    _query_optimizer = QueryOptimizer()
    
    LOGGER.info("Supabase integration initialized")
    
    return {
        "pool": _supabase_pool.get_stats(),
        "batching": enable_batching,
    }


async def close_supabase() -> None:
    """Close the Supabase integration."""
    global _supabase_pool, _batch_processor, _query_optimizer
    
    if _batch_processor:
        await _batch_processor.close()
        _batch_processor = None
    
    if _supabase_pool:
        await _supabase_pool.close()
        _supabase_pool = None
    
    _query_optimizer = None
    
    LOGGER.info("Supabase integration closed")


def get_supabase_stats() -> dict[str, Any]:
    """Get comprehensive Supabase statistics."""
    global _supabase_pool, _batch_processor, _query_optimizer
    
    stats: dict[str, Any] = {}
    
    if _supabase_pool:
        stats["pool"] = _supabase_pool.get_stats()
    
    if _batch_processor:
        stats["batching"] = _batch_processor.get_stats()
    
    if _query_optimizer:
        stats["optimizer"] = _query_optimizer.get_stats()
    
    return stats
