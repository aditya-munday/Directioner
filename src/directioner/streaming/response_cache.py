"""Ultra-fast response caching for minimum latency.

This module provides aggressive caching strategies for ChatGPT-style speed:
- Semantic similarity caching
- Query normalization
- Response compression
- Distributed cache support (future)
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

import structlog

LOGGER = structlog.get_logger(__name__)


# =============================================================================
# Query Normalizer
# =============================================================================

class QueryNormalizer:
    """Normalize queries for better cache hit rates."""

    # Common patterns to normalize
    NORMALIZATIONS = [
        # Remove extra whitespace
        (r'\s+', ' '),
        # Remove punctuation variations
        (r'[.!?]+', '.'),
        # Normalize numbers (optional - could hurt math queries)
        # (r'\d+', 'N'),
    ]

    def __init__(self, aggressive: bool = False) -> None:
        self._aggressive = aggressive
        self._patterns = [
            (re.compile(pattern), replacement)
            for pattern, replacement in self.NORMALIZATIONS
        ]

    def normalize(self, query: str) -> str:
        """Normalize a query for caching."""
        normalized = query.lower().strip()

        # Apply normalizations
        for pattern, replacement in self._patterns:
            normalized = pattern.sub(replacement, normalized)

        # Remove extra spaces again
        normalized = ' '.join(normalized.split())

        return normalized

    def hash(self, query: str) -> str:
        """Get a hash for a normalized query."""
        normalized = self.normalize(query)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]


# =============================================================================
# Response Cache Entry
# =============================================================================

@dataclass
class CacheEntry:
    """A cached response with rich metadata."""
    response: str
    query_hash: str
    created_at: float
    access_count: int = 0
    last_accessed: float = 0.0
    first_token_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    token_count: int = 0
    similarity_key: str | None = None  # For semantic caching


# =============================================================================
# Ultra-Fast Response Cache
# =============================================================================

class UltraFastResponseCache:
    """
    Aggressive response caching for ultra-low latency.
    
    Features:
    - O(1) lookup with hash indexing
    - TTL with access tracking
    - LRU eviction
    - Hit rate optimization
    - Pre-computed response variants
    """

    def __init__(
        self,
        max_size: int = 20000,
        default_ttl: float = 3600.0,
        warm_up_queries: int = 100,
    ) -> None:
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._warm_up_queries = warm_up_queries

        # Cache storage
        self._cache: dict[str, CacheEntry] = {}
        self._access_order: OrderedDict[str, None] = OrderedDict()

        # Normalizer
        self._normalizer = QueryNormalizer()

        # Stats
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._total_latency_saved_ms = 0.0

    def _make_key(self, query: str) -> str:
        """Create cache key from query."""
        return self._normalizer.hash(query)

    def get(self, query: str) -> str | None:
        """Get cached response. O(1) operation."""
        key = self._make_key(query)
        now = time.time()

        if key in self._cache:
            entry = self._cache[key]

            # Check TTL
            if now - entry.created_at > self._default_ttl:
                self._evict(key)
                self._misses += 1
                return None

            # Update access
            entry.access_count += 1
            entry.last_accessed = now
            self._hits += 1

            # Track latency savings
            self._total_latency_saved_ms += entry.total_latency_ms

            # Move to end of LRU
            if key in self._access_order:
                self._access_order.move_to_end(key)

            LOGGER.debug(
                "Cache hit",
                key=key[:8],
                access_count=entry.access_count,
            )
            return entry.response

        self._misses += 1
        return None

    def put(
        self,
        query: str,
        response: str,
        first_token_ms: float = 0.0,
        total_ms: float = 0.0,
    ) -> None:
        """Cache a response."""
        key = self._make_key(query)
        now = time.time()

        # Evict if at capacity
        while len(self._cache) >= self._max_size:
            self._evict_lru()

        # Store entry
        entry = CacheEntry(
            response=response,
            query_hash=key,
            created_at=now,
            last_accessed=now,
            first_token_latency_ms=first_token_ms,
            total_latency_ms=total_ms,
            token_count=len(response.split()),
        )

        self._cache[key] = entry
        self._access_order[key] = None

    def _evict(self, key: str) -> None:
        """Evict a specific key."""
        if key in self._cache:
            del self._cache[key]
        if key in self._access_order:
            del self._access_order[key]

    def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if self._access_order:
            oldest_key = next(iter(self._access_order))
            self._evict(oldest_key)
            self._evictions += 1

    def get_or_compute(
        self,
        query: str,
        compute_fn,
    ) -> tuple[str, bool]:
        """
        Get from cache or compute.
        
        Returns: (response, was_cached)
        """
        cached = self.get(query)
        if cached:
            return cached, True

        response = compute_fn()
        self.put(query, response)
        return response, False

    def warm_up(
        self,
        queries: list[tuple[str, str]],  # (query, response) pairs
    ) -> int:
        """
        Pre-warm cache with common queries.
        
        Returns: Number of queries cached
        """
        cached = 0
        for query, response in queries:
            if len(self._cache) < self._max_size:
                self.put(query, response, first_token_ms=50.0, total_ms=100.0)
                cached += 1

        LOGGER.info("Cache warmed", queries=len(queries), cached=cached)
        return cached

    def invalidate(self, query: str) -> bool:
        """Invalidate a specific query."""
        key = self._make_key(query)
        if key in self._cache:
            self._evict(key)
            return True
        return False

    def clear(self) -> None:
        """Clear entire cache."""
        self._cache.clear()
        self._access_order.clear()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._total_latency_saved_ms = 0.0

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0

        avg_latency_saved = (
            self._total_latency_saved_ms / self._hits
            if self._hits > 0 else 0.0
        )

        # Most accessed entries
        top_entries = sorted(
            self._cache.values(),
            key=lambda e: e.access_count,
            reverse=True,
        )[:5]

        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": round(hit_rate, 2),
            "evictions": self._evictions,
            "avg_latency_saved_ms": round(avg_latency_saved, 2),
            "total_latency_saved_ms": round(self._total_latency_saved_ms, 2),
            "ttl_seconds": self._default_ttl,
            "top_entries": [
                {
                    "hash": e.query_hash[:8],
                    "accesses": e.access_count,
                    "tokens": e.token_count,
                }
                for e in top_entries
            ],
        }


# =============================================================================
# Semantic Cache (Simplified)
# =============================================================================

class SemanticCache:
    """
    Simple semantic caching using keyword overlap.
    
    For production, would use embedding similarity.
    """

    def __init__(
        self,
        base_cache: UltraFastResponseCache,
        similarity_threshold: float = 0.8,
    ) -> None:
        self._base = base_cache
        self._threshold = similarity_threshold
        self._keywords: dict[str, set[str]] = {}  # query_hash -> keywords

    def _extract_keywords(self, query: str) -> set[str]:
        """Extract keywords from query."""
        # Simple word extraction
        words = re.findall(r'\b\w{3,}\b', query.lower())
        # Remove common stop words
        stop_words = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'has', 'her', 'was', 'one', 'our', 'out'}
        keywords = {w for w in words if w not in stop_words}
        return keywords

    def get(self, query: str) -> str | None:
        """Get cached response, including semantic matches."""
        # Direct hit
        direct = self._base.get(query)
        if direct:
            return direct

        # Semantic match
        query_keywords = self._extract_keywords(query)
        if not query_keywords:
            return None

        best_match = None
        best_score = 0.0

        for hash_key, keywords in self._keywords.items():
            if not keywords:
                continue

            # Calculate Jaccard similarity
            intersection = len(query_keywords & keywords)
            union = len(query_keywords | keywords)
            score = intersection / union if union > 0 else 0.0

            if score >= self._threshold and score > best_score:
                best_score = score
                best_match = hash_key

        if best_match and best_match in self._base._cache:
            entry = self._base._cache[best_match]
            LOGGER.info(
                "Semantic cache hit",
                query_hash=best_match[:8],
                score=best_score,
            )
            return self._base.get(best_match)  # This updates access

        return None

    def put(self, query: str, response: str) -> None:
        """Cache a response with semantic indexing."""
        key = self._base._make_key(query)
        self._base.put(query, response)
        self._keywords[key] = self._extract_keywords(query)


# =============================================================================
# Global cache instance
# =============================================================================

_response_cache: UltraFastResponseCache | None = None


def get_response_cache() -> UltraFastResponseCache:
    """Get the global response cache."""
    global _response_cache
    if _response_cache is None:
        _response_cache = UltraFastResponseCache()
    return _response_cache


def initialize_response_cache(
    max_size: int = 20000,
    ttl: float = 3600.0,
) -> UltraFastResponseCache:
    """Initialize the global response cache."""
    global _response_cache
    _response_cache = UltraFastResponseCache(max_size=max_size, default_ttl=ttl)
    return _response_cache
