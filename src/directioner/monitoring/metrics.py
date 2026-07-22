"""Prometheus metrics for Directioner.

This module provides comprehensive metrics collection for monitoring
the bot's performance in production environments.

Usage:
    from directioner.monitoring.metrics import metrics
    
    # Record a request
    metrics.record_request(guild_id="123", channel_id="456")
    
    # Record latency
    metrics.record_latency("chat", 150.5)
    
    # Get current values
    metrics.get_active_conversations()
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

try:
    from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

import structlog

LOGGER = structlog.get_logger(__name__)


# =============================================================================
# Legacy Metrics Classes (for backwards compatibility)
# =============================================================================

@dataclass(frozen=True, slots=True)
class MetricSample:
    name: str
    value: float
    tags: tuple[tuple[str, str], ...] = ()


class MetricsSink:
    def __init__(self) -> None:
        self._latest: dict[str, float] = defaultdict(float)

    def record(self, sample: MetricSample) -> None:
        self._latest[sample.name] = sample.value

    def latest(self, name: str) -> float:
        return self._latest[name]


# =============================================================================
# Prometheus Metrics Collector
# =============================================================================

class MetricsCollector:
    """Collects and exposes Prometheus metrics."""

    def __init__(self) -> None:
        if not PROMETHEUS_AVAILABLE:
            LOGGER.warning("prometheus_client not installed, metrics disabled")
            self._enabled = False
            return
        
        self._enabled = True
        
        # Request counters
        self.requests_total = Counter(
            "directioner_requests_total",
            "Total number of requests processed",
            ["guild_id", "channel_id", "kind"],
        )
        
        self.messages_received = Counter(
            "directioner_messages_received_total",
            "Total messages received",
            ["guild_id", "channel_id"],
        )
        
        self.messages_processed = Counter(
            "directioner_messages_processed_total",
            "Total messages successfully processed",
            ["guild_id", "channel_id"],
        )
        
        self.messages_failed = Counter(
            "directioner_messages_failed_total",
            "Total messages that failed processing",
            ["guild_id", "channel_id", "error_type"],
        )
        
        # Latency histograms
        self.request_latency = Histogram(
            "directioner_request_latency_seconds",
            "Request processing latency in seconds",
            ["operation"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )
        
        self.llm_latency = Histogram(
            "directioner_llm_latency_seconds",
            "LLM API call latency in seconds",
            ["provider", "model"],
            buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
        )
        
        self.memory_latency = Histogram(
            "directioner_memory_latency_seconds",
            "Memory store operation latency in seconds",
            ["operation"],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
        )
        
        # Gauges
        self.active_conversations = Gauge(
            "directioner_active_conversations",
            "Number of currently active conversations",
            ["guild_id"],
        )
        
        self.total_conversations = Gauge(
            "directioner_total_conversations",
            "Total number of conversations since startup",
        )
        
        self.memory_usage_bytes = Gauge(
            "directioner_memory_usage_bytes",
            "Memory store memory usage in bytes",
            ["store_type"],
        )
        
        self.cache_size = Gauge(
            "directioner_cache_size",
            "Current size of response cache",
        )
        
        self.rate_limit_hits = Counter(
            "directioner_rate_limit_hits_total",
            "Total rate limit hits",
            ["entity_type", "guild_id"],
        )
        
        # LLM specific
        self.llm_tokens_used = Counter(
            "directioner_llm_tokens_used_total",
            "Total LLM tokens used",
            ["provider", "model", "token_type"],
        )
        
        self.llm_errors = Counter(
            "directioner_llm_errors_total",
            "Total LLM errors",
            ["provider", "error_type"],
        )
        
        self.cache_hits = Counter(
            "directioner_cache_hits_total",
            "Total cache hits",
        )
        
        self.cache_misses = Counter(
            "directioner_cache_misses_total",
            "Total cache misses",
        )
        
        # Tool usage
        self.tool_usage = Counter(
            "directioner_tool_usage_total",
            "Total tool usage",
            ["tool_name", "guild_id"],
        )
        
        # System info
        self.system_info = Info(
            "directioner_system",
            "Directioner system information",
        )
        self.system_info.info({
            "version": "1.0.0",
            "app_name": "directioner",
        })

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record_request(
        self,
        guild_id: str | None = None,
        channel_id: str | None = None,
        kind: str = "message",
    ) -> None:
        """Record a received request."""
        if not self._enabled:
            return
        self.requests_total.labels(
            guild_id=guild_id or "unknown",
            channel_id=channel_id or "unknown",
            kind=kind,
        ).inc()

    def record_message_received(
        self,
        guild_id: str | None = None,
        channel_id: str | None = None,
    ) -> None:
        """Record a message received."""
        if not self._enabled:
            return
        self.messages_received.labels(
            guild_id=guild_id or "unknown",
            channel_id=channel_id or "unknown",
        ).inc()

    def record_message_processed(
        self,
        guild_id: str | None = None,
        channel_id: str | None = None,
    ) -> None:
        """Record a message successfully processed."""
        if not self._enabled:
            return
        self.messages_processed.labels(
            guild_id=guild_id or "unknown",
            channel_id=channel_id or "unknown",
        ).inc()

    def record_message_failed(
        self,
        guild_id: str | None = None,
        channel_id: str | None = None,
        error_type: str = "unknown",
    ) -> None:
        """Record a message that failed processing."""
        if not self._enabled:
            return
        self.messages_failed.labels(
            guild_id=guild_id or "unknown",
            channel_id=channel_id or "unknown",
            error_type=error_type,
        ).inc()

    def record_latency(self, operation: str, latency_seconds: float) -> None:
        """Record operation latency."""
        if not self._enabled:
            return
        self.request_latency.labels(operation=operation).observe(latency_seconds)

    def record_llm_latency(
        self,
        provider: str,
        model: str,
        latency_seconds: float,
    ) -> None:
        """Record LLM API call latency."""
        if not self._enabled:
            return
        self.llm_latency.labels(provider=provider, model=model).observe(latency_seconds)

    def record_memory_latency(self, operation: str, latency_seconds: float) -> None:
        """Record memory store operation latency."""
        if not self._enabled:
            return
        self.memory_latency.labels(operation=operation).observe(latency_seconds)

    def set_active_conversations(
        self,
        guild_id: str | None = None,
        count: int = 0,
    ) -> None:
        """Set the number of active conversations."""
        if not self._enabled:
            return
        self.active_conversations.labels(guild_id=guild_id or "unknown").set(count)

    def set_total_conversations(self, count: int) -> None:
        """Set the total number of conversations."""
        if not self._enabled:
            return
        self.total_conversations.set(count)

    def set_memory_usage(self, store_type: str, bytes_used: int) -> None:
        """Set memory store usage."""
        if not self._enabled:
            return
        self.memory_usage_bytes.labels(store_type=store_type).set(bytes_used)

    def set_cache_size(self, size: int) -> None:
        """Set the response cache size."""
        if not self._enabled:
            return
        self.cache_size.set(size)

    def record_rate_limit_hit(
        self,
        entity_type: str,
        guild_id: str | None = None,
    ) -> None:
        """Record a rate limit hit."""
        if not self._enabled:
            return
        self.rate_limit_hits.labels(
            entity_type=entity_type,
            guild_id=guild_id or "unknown",
        ).inc()

    def record_tokens_used(
        self,
        provider: str,
        model: str,
        token_type: str,
        count: int,
    ) -> None:
        """Record LLM token usage."""
        if not self._enabled:
            return
        self.llm_tokens_used.labels(
            provider=provider,
            model=model,
            token_type=token_type,
        ).inc(count)

    def record_llm_error(
        self,
        provider: str,
        error_type: str = "unknown",
    ) -> None:
        """Record an LLM error."""
        if not self._enabled:
            return
        self.llm_errors.labels(provider=provider, error_type=error_type).inc()

    def record_cache_hit(self) -> None:
        """Record a cache hit."""
        if not self._enabled:
            return
        self.cache_hits.inc()

    def record_cache_miss(self) -> None:
        """Record a cache miss."""
        if not self._enabled:
            return
        self.cache_misses.inc()

    def record_tool_usage(
        self,
        tool_name: str,
        guild_id: str | None = None,
    ) -> None:
        """Record tool usage."""
        if not self._enabled:
            return
        self.tool_usage.labels(
            tool_name=tool_name,
            guild_id=guild_id or "unknown",
        ).inc()

    def generate_metrics(self) -> tuple[bytes, str]:
        """Generate Prometheus metrics output."""
        if not self._enabled:
            return b"# Metrics disabled", "text/plain"
        return generate_latest(), CONTENT_TYPE_LATEST

    def get_stats(self) -> dict[str, Any]:
        """Get current metrics as a dictionary."""
        if not self._enabled:
            return {"enabled": False}
        
        return {
            "enabled": True,
            "metrics_types": {
                "counters": [
                    "requests_total",
                    "messages_received_total",
                    "messages_processed_total",
                    "messages_failed_total",
                    "rate_limit_hits_total",
                    "llm_tokens_used_total",
                    "llm_errors_total",
                    "cache_hits_total",
                    "cache_misses_total",
                    "tool_usage_total",
                ],
                "histograms": [
                    "request_latency_seconds",
                    "llm_latency_seconds",
                    "memory_latency_seconds",
                ],
                "gauges": [
                    "active_conversations",
                    "total_conversations",
                    "memory_usage_bytes",
                    "cache_size",
                ],
            },
        }


# Global metrics instance
metrics = MetricsCollector()


# Decorator for automatic latency tracking
def track_latency(operation: str):
    """Decorator to automatically track function latency."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                latency = time.perf_counter() - start
                metrics.record_latency(operation, latency)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                latency = time.perf_counter() - start
                metrics.record_latency(operation, latency)
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator
