"""Tests for scaling and rate limiting features."""

import time
import pytest
from directioner.conversation.state import ConversationState, ConversationStateManager
from directioner.memory.store import (
    RateLimiter,
    PerEntityRateLimiter,
    MemoryRateLimitError,
)


class TestConversationStateManager:
    """Tests for ConversationStateManager."""

    def test_create_and_get_state(self) -> None:
        """Test basic state creation and retrieval."""
        manager = ConversationStateManager(max_states=100)
        
        state1 = manager.get_or_create(
            conversation_id="conv1",
            guild_id="guild1",
            channel_id="channel1",
            user_id="user1",
        )
        
        assert state1.conversation_id == "conv1"
        assert state1.guild_id == "guild1"
        assert state1.channel_id == "channel1"
        assert state1.user_id == "user1"
        
        # Get same state
        state2 = manager.get_or_create(conversation_id="conv1")
        assert state1 is state2

    def test_guild_isolation(self) -> None:
        """Test that guilds are isolated."""
        manager = ConversationStateManager(max_states=100)
        
        manager.get_or_create("conv1", guild_id="guild1")
        manager.get_or_create("conv2", guild_id="guild1")
        manager.get_or_create("conv3", guild_id="guild2")
        
        guild1_states = manager.get_guild_states("guild1")
        guild2_states = manager.get_guild_states("guild2")
        
        assert len(guild1_states) == 2
        assert len(guild2_states) == 1

    def test_channel_isolation(self) -> None:
        """Test that channels are isolated."""
        manager = ConversationStateManager(max_states=100)
        
        manager.get_or_create("conv1", channel_id="channel1")
        manager.get_or_create("conv2", channel_id="channel1")
        manager.get_or_create("conv3", channel_id="channel2")
        
        channel1_states = manager.get_channel_states("channel1")
        channel2_states = manager.get_channel_states("channel2")
        
        assert len(channel1_states) == 2
        assert len(channel2_states) == 1

    def test_user_isolation(self) -> None:
        """Test that users are isolated."""
        manager = ConversationStateManager(max_states=100)
        
        manager.get_or_create("conv1", user_id="user1")
        manager.get_or_create("conv2", user_id="user1")
        manager.get_or_create("conv3", user_id="user2")
        
        user1_states = manager.get_user_states("user1")
        user2_states = manager.get_user_states("user2")
        
        assert len(user1_states) == 2
        assert len(user2_states) == 1

    def test_max_states_eviction(self) -> None:
        """Test that oldest states are evicted when limit is reached."""
        manager = ConversationStateManager(max_states=3)
        
        # Create states with different activity times
        state1 = manager.get_or_create("conv1")
        time.sleep(0.01)
        state2 = manager.get_or_create("conv2")
        time.sleep(0.01)
        state3 = manager.get_or_create("conv3")
        time.sleep(0.01)
        
        # Access state1 to update its activity
        manager.get_or_create("conv1")
        
        # Create a new state - should evict the oldest
        state4 = manager.get_or_create("conv4")
        
        # state1 should still exist (recently accessed)
        assert manager.get("conv1") is not None
        
        # One of state2 or state3 should be evicted
        remaining = [manager.get("conv2"), manager.get("conv3")]
        assert any(r is not None for r in remaining)

    def test_idle_cleanup(self) -> None:
        """Test that idle states are cleaned up."""
        manager = ConversationStateManager(
            max_states=100,
            idle_timeout=0.1,  # 100ms
            cleanup_interval=0.05,
        )
        
        manager.get_or_create("conv1")
        manager.get_or_create("conv2")
        
        # Wait for idle timeout
        time.sleep(0.15)
        
        # Trigger cleanup
        evicted = manager.cleanup_idle()
        
        assert evicted == 2
        assert manager.get("conv1") is None
        assert manager.get("conv2") is None

    def test_remove_state(self) -> None:
        """Test state removal."""
        manager = ConversationStateManager(max_states=100)
        
        manager.get_or_create("conv1", guild_id="guild1", channel_id="channel1")
        assert manager.remove("conv1") is True
        assert manager.get("conv1") is None
        
        # Guild and channel should be cleaned up
        assert len(manager.get_guild_states("guild1")) == 0
        assert len(manager.get_channel_states("channel1")) == 0

    def test_stats(self) -> None:
        """Test statistics tracking."""
        manager = ConversationStateManager(max_states=100)
        
        manager.get_or_create("conv1", guild_id="guild1", channel_id="channel1")
        manager.get_or_create("conv2", guild_id="guild1", channel_id="channel2")
        manager.get_or_create("conv3", user_id="user1")
        
        stats = manager.get_stats()
        
        assert stats["total_conversations"] == 3
        assert stats["total_guilds"] == 1
        assert stats["total_channels"] == 2
        assert stats["total_users"] == 1
        assert stats["total_requests"] >= 3


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_basic_rate_limiting(self) -> None:
        """Test basic rate limiting functionality."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        
        # First 3 requests should pass
        assert limiter.check("entity1") is True
        assert limiter.check("entity1") is True
        assert limiter.check("entity1") is True
        
        # 4th request should fail
        assert limiter.check("entity1") is False
        
        # Different entity should pass
        assert limiter.check("entity2") is True

    def test_window_reset(self) -> None:
        """Test that rate limit resets after window."""
        limiter = RateLimiter(max_requests=2, window_seconds=0.05)
        
        assert limiter.check("entity1") is True
        assert limiter.check("entity1") is True
        assert limiter.check("entity1") is False
        
        # Wait for window to reset
        time.sleep(0.06)
        
        # Should be allowed again
        assert limiter.check("entity1") is True

    def test_try_acquire(self) -> None:
        """Test try_acquire raises on limit."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        
        limiter.try_acquire("entity1")
        limiter.try_acquire("entity1")
        
        with pytest.raises(MemoryRateLimitError):
            limiter.try_acquire("entity1")

    def test_get_remaining(self) -> None:
        """Test get_remaining."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        
        assert limiter.get_remaining("entity1") == 5
        limiter.check("entity1")
        assert limiter.get_remaining("entity1") == 4


class TestPerEntityRateLimiter:
    """Tests for PerEntityRateLimiter."""

    def test_user_rate_limit(self) -> None:
        """Test per-user rate limiting."""
        limiter = PerEntityRateLimiter(
            per_user_limit=2,
            per_channel_limit=100,
            per_guild_limit=1000,
        )
        
        # First 2 user requests pass
        assert limiter.check_user("user1") is True
        assert limiter.check_user("user1") is True
        
        # 3rd fails
        assert limiter.check_user("user1") is False
        
        # Different user passes
        assert limiter.check_user("user2") is True

    def test_channel_rate_limit(self) -> None:
        """Test per-channel rate limiting."""
        limiter = PerEntityRateLimiter(
            per_user_limit=100,
            per_channel_limit=2,
            per_guild_limit=1000,
        )
        
        assert limiter.check_channel("channel1") is True
        assert limiter.check_channel("channel1") is True
        assert limiter.check_channel("channel1") is False

    def test_guild_rate_limit(self) -> None:
        """Test per-guild rate limiting."""
        limiter = PerEntityRateLimiter(
            per_user_limit=100,
            per_channel_limit=100,
            per_guild_limit=2,
        )
        
        assert limiter.check_guild("guild1") is True
        assert limiter.check_guild("guild1") is True
        assert limiter.check_guild("guild1") is False

    def test_check_all(self) -> None:
        """Test check_all checks all limits."""
        limiter = PerEntityRateLimiter(
            per_user_limit=2,
            per_channel_limit=2,
            per_guild_limit=2,
        )
        
        # Exhaust user limit
        limiter.check_user("user1")
        limiter.check_user("user1")
        
        allowed, reason = limiter.check_all(
            user_id="user1",
            channel_id="channel1",
            guild_id="guild1",
        )
        
        assert allowed is False
        assert "User rate limit" in reason

    def test_try_acquire_all(self) -> None:
        """Test try_acquire_all raises if any limit exceeded."""
        limiter = PerEntityRateLimiter(
            per_user_limit=2,
            per_channel_limit=2,
            per_guild_limit=2,
        )
        
        # Exhaust channel limit
        limiter.check_channel("channel1")
        limiter.check_channel("channel1")
        
        with pytest.raises(MemoryRateLimitError):
            limiter.try_acquire_all(
                user_id="user1",
                channel_id="channel1",
                guild_id="guild1",
            )

    def test_stats(self) -> None:
        """Test stats include all limiters."""
        limiter = PerEntityRateLimiter(
            per_user_limit=60,
            per_channel_limit=300,
            per_guild_limit=1000,
        )
        
        limiter.check_user("user1")
        limiter.check_channel("channel1")
        limiter.check_guild("guild1")
        
        stats = limiter.get_stats()
        
        assert "user" in stats
        assert "channel" in stats
        assert "guild" in stats
        
        assert stats["user"]["max_requests"] == 60
        assert stats["channel"]["max_requests"] == 300
        assert stats["guild"]["max_requests"] == 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
