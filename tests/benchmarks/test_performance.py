"""Performance benchmarks for Directioner.

Run with: pytest tests/benchmarks/ -v --tb=short
"""

import time
import pytest
import tempfile
import os

# Test the performance utilities
from directioner.monitoring.performance import (
    LRUCache,
    LatencyTracker,
    fast_hash,
)


class TestLRUCachePerformance:
    """Benchmarks for LRU Cache."""

    def test_cache_get_put_performance(self) -> None:
        """Benchmark: 100k cache get/put operations."""
        cache = LRUCache(max_size=10_000)
        
        # Warm up
        for i in range(100):
            cache.set(f"key_{i}", f"value_{i}")
        
        # Benchmark
        start = time.perf_counter()
        for i in range(100_000):
            cache.set(f"key_{i % 1000}", f"value_{i}")
            cache.get(f"key_{i % 1000}")
        elapsed = time.perf_counter() - start
        
        print(f"\n  100k get/put operations: {elapsed*1000:.2f}ms")
        assert elapsed < 1.0, f"Cache operations too slow: {elapsed:.2f}s"

    def test_cache_hit_rate(self) -> None:
        """Benchmark: Cache hit rate with different access patterns."""
        cache = LRUCache(max_size=1000)
        
        # Zipfian access pattern (realistic)
        for i in range(10_000):
            key = f"key_{i % 100}"  # Hot keys
            cache.set(key, f"value_{i}")
        
        # Benchmark hits
        start = time.perf_counter()
        for i in range(50_000):
            key = f"key_{i % 100}"  # Only hot keys
            cache.get(key)
        elapsed = time.perf_counter() - start
        
        stats = cache.get_stats()
        print(f"\n  50k cache lookups: {elapsed*1000:.2f}ms")
        print(f"  Hit rate: {stats['hit_rate']:.2%}")
        assert elapsed < 0.5, f"Cache lookups too slow: {elapsed:.2f}s"


class TestLatencyTrackerPerformance:
    """Benchmarks for Latency Tracker."""

    def test_tracking_overhead(self) -> None:
        """Benchmark: Latency tracking overhead."""
        tracker = LatencyTracker()
        
        start = time.perf_counter()
        for i in range(100_000):
            handle = tracker.start("test_operation")
            tracker.end(handle)
        elapsed = time.perf_counter() - start
        
        print(f"\n  100k track operations: {elapsed*1000:.2f}ms")
        print(f"  Per-operation overhead: {elapsed*1000000/100000:.2f}μs")
        assert elapsed < 2.0, f"Tracking too slow: {elapsed:.2f}s"

    def test_stats_computation(self) -> None:
        """Benchmark: Stats computation."""
        tracker = LatencyTracker()
        
        # Add some measurements
        for i in range(10_000):
            handle = tracker.start("test")
            tracker.end(handle)
        
        # Benchmark stats
        start = time.perf_counter()
        for _ in range(1000):
            tracker.get_stats()
        elapsed = time.perf_counter() - start
        
        print(f"\n  1k stats computations: {elapsed*1000:.2f}ms")
        assert elapsed < 1.0, f"Stats computation too slow: {elapsed:.2f}s"


class TestMemoryStorePerformance:
    """Benchmarks for Memory Store."""

    def test_conversation_memory_throughput(self) -> None:
        """Benchmark: Conversation memory record/retrieve."""
        from directioner.memory.store import ConversationMemory, MemoryTurn
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl') as f:
            persist_path = f.name
        
        try:
            memory = ConversationMemory(
                max_turns_per_conversation=1000,
                persist_path=persist_path,
            )
            
            # Benchmark writes
            start = time.perf_counter()
            for i in range(5000):
                turn = MemoryTurn(
                    conversation_id="test_conv",
                    role="user",
                    content=f"Message {i}" * 10,
                )
                memory.record(turn)
            write_time = time.perf_counter() - start
            
            # Benchmark reads
            start = time.perf_counter()
            for _ in range(1000):
                memory.recent("test_conv", limit=10)
            read_time = time.perf_counter() - start
            
            print(f"\n  5k conversation writes: {write_time*1000:.2f}ms")
            print(f"  1k conversation reads: {read_time*1000:.2f}ms")
            assert write_time < 5.0, f"Conversation writes too slow: {write_time:.2f}s"
            assert read_time < 1.0, f"Conversation reads too slow: {read_time:.2f}s"
        finally:
            os.unlink(persist_path)

    def test_semantic_search_throughput(self) -> None:
        """Benchmark: Semantic memory search."""
        from directioner.memory.store import SemanticMemory
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            persist_path = f.name
        
        try:
            memory = SemanticMemory(persist_path=persist_path)
            
            # Add entries
            for i in range(1000):
                memory.record("conv_1", f"This is test message number {i} with some content")
            
            # Benchmark searches
            start = time.perf_counter()
            for i in range(1000):
                memory.search("conv_1", "test message", limit=5)
            elapsed = time.perf_counter() - start
            
            print(f"\n  1k semantic searches (1k entries): {elapsed*1000:.2f}ms")
            print(f"  Per-search: {elapsed*1000:.2f}ms")
            assert elapsed < 5.0, f"Semantic search too slow: {elapsed:.2f}s"
        finally:
            os.unlink(persist_path)


class TestFastHash:
    """Benchmarks for hash functions."""

    def test_fast_hash_performance(self) -> None:
        """Benchmark: Fast hash generation."""
        test_data = [
            ("user_123", "channel_456"),
            ("large", "data", "set", "with", "many", "items"),
            123,
            {"nested": "data", "with": ["lists", "and", "more"]},
        ]
        
        start = time.perf_counter()
        for _ in range(100_000):
            for data in test_data:
                fast_hash(data)
        elapsed = time.perf_counter() - start
        
        print(f"\n  100k fast_hash calls: {elapsed*1000:.2f}ms")
        assert elapsed < 2.0, f"Hash too slow: {elapsed:.2f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
