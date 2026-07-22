"""Latency tracking and optimization for Directioner.

This module provides comprehensive latency tracking and optimization:
- Per-operation latency tracking
- Bottleneck identification
- Automatic optimization suggestions
- SLA monitoring
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from contextlib import asynccontextmanager

import structlog

LOGGER = structlog.get_logger(__name__)


# =============================================================================
# Latency Targets (in milliseconds)
# =============================================================================

LATENCY_TARGETS = {
    "fast_path": 5.0,       # Fast-path response target
    "cache_hit": 10.0,     # Cache hit target
    "tool_execution": 100.0,  # Single tool execution target
    "parallel_tools": 150.0,   # Parallel tools target
    "llm_first_token": 500.0,  # First LLM token target
    "llm_stream": 50.0,       # Per-token streaming target
    "total_response": 2000.0,  # Total response target
}


@dataclass
class LatencyRecord:
    """A recorded latency measurement."""
    operation: str
    latency_ms: float
    timestamp: float
    success: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LatencyStats:
    """Statistics for a latency distribution."""
    count: int = 0
    sum_ms: float = 0.0
    min_ms: float = float('inf')
    max_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0

    @property
    def avg_ms(self) -> float:
        return self.sum_ms / self.count if self.count > 0 else 0.0


class LatencyTracker:
    """Track and analyze latency for all operations."""

    def __init__(
        self,
        window_size: int = 1000,  # Keep last N records per operation
        auto_optimize: bool = True,
    ) -> None:
        self._records: dict[str, list[LatencyRecord]] = defaultdict(list)
        self._stats: dict[str, LatencyStats] = defaultdict(LatencyStats)
        self._window_size = window_size
        self._lock = asyncio.Lock()
        self._auto_optimize = auto_optimize
        self._sla_violations: list[dict[str, Any]] = []

    async def record(
        self,
        operation: str,
        latency_ms: float,
        success: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a latency measurement."""
        record = LatencyRecord(
            operation=operation,
            latency_ms=latency_ms,
            timestamp=time.time(),
            success=success,
            metadata=metadata or {},
        )

        async with self._lock:
            # Add record
            self._records[operation].append(record)

            # Trim to window size
            if len(self._records[operation]) > self._window_size:
                self._records[operation] = self._records[operation][-self._window_size:]

            # Update stats
            self._update_stats(operation)

            # Check SLA
            if operation in LATENCY_TARGETS:
                target = LATENCY_TARGETS[operation]
                if latency_ms > target:
                    self._sla_violations.append({
                        "operation": operation,
                        "latency_ms": latency_ms,
                        "target_ms": target,
                        "timestamp": record.timestamp,
                        "violation_percent": ((latency_ms - target) / target * 100),
                    })
                    # Keep only recent violations
                    self._sla_violations = self._sla_violations[-100:]

    def _update_stats(self, operation: str) -> None:
        """Update statistics for an operation."""
        records = self._records[operation]
        if not records:
            return

        latencies = [r.latency_ms for r in records if r.success]
        if not latencies:
            return

        stats = LatencyStats(
            count=len(latencies),
            sum_ms=sum(latencies),
            min_ms=min(latencies),
            max_ms=max(latencies),
        )

        # Calculate percentiles
        sorted_latencies = sorted(latencies)
        stats.p50_ms = self._percentile(sorted_latencies, 0.50)
        stats.p95_ms = self._percentile(sorted_latencies, 0.95)
        stats.p99_ms = self._percentile(sorted_latencies, 0.99)

        self._stats[operation] = stats

    def _percentile(self, sorted_values: list[float], percentile: float) -> float:
        """Calculate percentile from sorted values."""
        if not sorted_values:
            return 0.0
        index = int(len(sorted_values) * percentile)
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]

    @asynccontextmanager
    async def track(self, operation: str, metadata: dict[str, Any] | None = None):
        """Context manager to track operation latency."""
        start = time.perf_counter()
        success = True
        try:
            yield
        except Exception:
            success = False
            raise
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            await self.record(operation, latency_ms, success, metadata)

    def get_stats(self, operation: str | None = None) -> dict[str, Any]:
        """Get statistics for an operation or all operations."""
        if operation:
            if operation not in self._stats:
                return {}
            return self._format_stats(operation, self._stats[operation])

        return {
            op: self._format_stats(op, stats)
            for op, stats in self._stats.items()
        }

    def _format_stats(self, operation: str, stats: LatencyStats) -> dict[str, Any]:
        """Format stats with SLA information."""
        target = LATENCY_TARGETS.get(operation)
        p50_vs_target = (stats.p50_ms / target * 100) if target else None
        p95_vs_target = (stats.p95_ms / target * 100) if target else None

        return {
            "count": stats.count,
            "avg_ms": round(stats.avg_ms, 2),
            "min_ms": round(stats.min_ms, 2),
            "max_ms": round(stats.max_ms, 2),
            "p50_ms": round(stats.p50_ms, 2),
            "p95_ms": round(stats.p95_ms, 2),
            "p99_ms": round(stats.p99_ms, 2),
            "target_ms": target,
            "p50_vs_target_percent": round(p50_vs_target, 1) if p50_vs_target else None,
            "p95_vs_target_percent": round(p95_vs_target, 1) if p95_vs_target else None,
            "sla_met": target is None or stats.p95_ms <= target,
        }

    def get_sla_violations(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent SLA violations."""
        return self._sla_violations[-limit:]

    def get_sla_summary(self) -> dict[str, Any]:
        """Get SLA compliance summary."""
        operations_with_targets = [
            op for op in self._stats.keys()
            if op in LATENCY_TARGETS
        ]

        if not operations_with_targets:
            return {"total_operations": len(self._stats)}

        sla_met = 0
        sla_violated = 0

        for op in operations_with_targets:
            stats = self._stats[op]
            target = LATENCY_TARGETS[op]
            if stats.p95_ms <= target:
                sla_met += 1
            else:
                sla_violated += 1

        return {
            "total_operations": len(self._stats),
            "with_sla_targets": len(operations_with_targets),
            "sla_met": sla_met,
            "sla_violated": sla_violated,
            "compliance_percent": round(sla_met / len(operations_with_targets) * 100, 1),
        }

    def get_bottlenecks(self, limit: int = 5) -> list[dict[str, Any]]:
        """Identify latency bottlenecks."""
        bottlenecks = []

        for op, stats in self._stats.items():
            target = LATENCY_TARGETS.get(op)
            if target and stats.p95_ms > target:
                violation = ((stats.p95_ms - target) / target) * 100
                bottlenecks.append({
                    "operation": op,
                    "p95_ms": round(stats.p95_ms, 2),
                    "target_ms": target,
                    "violation_percent": round(violation, 1),
                    "suggestion": self._get_optimization_suggestion(op, stats, target),
                })

        return sorted(bottlenecks, key=lambda x: x["violation_percent"], reverse=True)[:limit]

    def _get_optimization_suggestion(
        self,
        operation: str,
        stats: LatencyStats,
        target: float,
    ) -> str:
        """Get optimization suggestion for an operation."""
        suggestions = {
            "fast_path": "Consider adding more fast-path rules or expanding existing patterns.",
            "cache_hit": "Increase cache size or extend TTL. Check for cache invalidation issues.",
            "tool_execution": "Optimize tool implementation or add caching for tool results.",
            "parallel_tools": "Increase max_concurrent tools or optimize individual tools.",
            "llm_first_token": "Use a faster model or pre-warm connections. Consider streaming.",
            "llm_stream": "Reduce buffer size or use a faster model.",
            "total_response": "Profile individual components to find the bottleneck.",
        }
        return suggestions.get(operation, "Review and optimize this operation.")


# =============================================================================
# Adaptive Latency Optimizer
# =============================================================================

class AdaptiveLatencyOptimizer:
    """Automatically optimize latency based on observed patterns."""

    def __init__(
        self,
        tracker: LatencyTracker,
        cache: Any,  # PredictiveCache
        fast_path: Any,  # FastPathRouter
    ) -> None:
        self._tracker = tracker
        self._cache = cache
        self._fast_path = fast_path
        self._optimizations: list[dict[str, Any]] = []

    async def analyze_and_optimize(self) -> list[dict[str, Any]]:
        """Analyze latency patterns and apply optimizations."""
        applied = []

        # Check cache hit rate
        cache_stats = self._cache.get_stats()
        if cache_stats["hit_rate_percent"] < 30:
            # Increase cache size
            LOGGER.info("Optimizing cache size", current=cache_stats["size"])
            applied.append({
                "type": "cache_size_increase",
                "reason": "Low cache hit rate",
                "action": "Cache hit rate is low - consider warming with common queries",
            })

        # Check for slow operations
        bottlenecks = self._tracker.get_bottlenecks()
        for bottleneck in bottlenecks:
            if bottleneck["violation_percent"] > 50:
                optimization = self._suggest_optimization(bottleneck)
                if optimization:
                    applied.append(optimization)

        self._optimizations.extend(applied)
        return applied

    def _suggest_optimization(self, bottleneck: dict[str, Any]) -> dict[str, Any] | None:
        """Suggest an optimization for a bottleneck."""
        op = bottleneck["operation"]

        suggestions = {
            "llm_first_token": {
                "type": "llm_optimization",
                "action": "Enable connection pre-warming or use faster model",
                "priority": "high",
            },
            "total_response": {
                "type": "parallel_processing",
                "action": "Execute independent operations in parallel",
                "priority": "medium",
            },
        }

        return suggestions.get(op)


# =============================================================================
# Global latency tracker
# =============================================================================

latency_tracker = LatencyTracker()


def track_latency(operation: str):
    """Decorator to track function latency."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            async with latency_tracker.track(operation):
                return await func(*args, **kwargs)
        return wrapper
    return decorator
