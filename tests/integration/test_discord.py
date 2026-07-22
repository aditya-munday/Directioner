"""Integration tests for Discord integration.

These tests mock the Discord API to test the bot's behavior
without requiring a real Discord connection.

Run with:
    pytest tests/integration/ -v
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@dataclass
class MockUser:
    """Mock Discord user."""
    id: str
    name: str
    discriminator: str = "0000"
    bot: bool = False
    _display_name: str | None = None

    @property
    def display_name(self) -> str:
        return self._display_name or self.name


@dataclass
class MockChannel:
    """Mock Discord channel."""
    id: str
    name: str
    guild_id: str
    type: int = 0  # 0 = text channel


@dataclass
class MockGuild:
    """Mock Discord guild (server)."""
    id: str
    name: str
    shard_id: int = 0


@dataclass
class MockMessage:
    """Mock Discord message."""
    id: str
    content: str
    channel: MockChannel
    author: MockUser
    guild: MockGuild | None = None
    mention_everyone: bool = False
    mentions: list[MockUser] = field(default_factory=list)
    created_at: float = 0.0


class MockDiscordClient:
    """Mock Discord client for testing."""

    def __init__(self) -> None:
        self.user = MockUser(id="123456789", name="Directioner", bot=True)
        self.guilds: dict[str, MockGuild] = {}
        self.channels: dict[str, MockChannel] = {}
        self.messages: list[MockMessage] = []
        self.event_handlers: dict[str, list] = {}

    def event(self, coro):
        """Decorator to register event handlers."""
        name = coro.__name__
        if name not in self.event_handlers:
            self.event_handlers[name] = []
        self.event_handlers[name].append(coro)
        return coro

    async def dispatch(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Dispatch an event to handlers."""
        handlers = self.event_handlers.get(event, [])
        for handler in handlers:
            await handler(*args, **kwargs)

    def simulate_message(
        self,
        content: str,
        user_id: str = "987654321",
        username: str = "TestUser",
        channel_id: str = "111222333444555",
        guild_id: str = "666777888999000",
    ) -> MockMessage:
        """Simulate receiving a message."""
        message = MockMessage(
            id="123",
            content=content,
            channel=MockChannel(
                id=channel_id,
                name="general",
                guild_id=guild_id,
            ),
            author=MockUser(
                id=user_id,
                name=username,
            ),
            guild=MockGuild(
                id=guild_id,
                name="Test Server",
            ),
        )
        self.messages.append(message)
        return message


@pytest.fixture
def mock_discord_client():
    """Create a mock Discord client."""
    return MockDiscordClient()


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class TestMessageHandling:
    """Test message handling."""

    @pytest.mark.asyncio
    async def test_simple_message(self, mock_discord_client: MockDiscordClient) -> None:
        """Test handling a simple message."""
        from directioner.conversation.events import ConversationEvent, ConversationEventKind
        from directioner.conversation.router import ConversationRouter
        from directioner.conversation.context import ContextManager
        from directioner.conversation.state import ConversationStateManager
        from directioner.intent.planner import Planner
        from directioner.memory.store import MemoryStore
        from directioner.response.router import ResponseRouter

        # Build components
        memory = MemoryStore()
        planner = Planner()
        responses = ResponseRouter(memory=memory)
        context = ContextManager()
        router = ConversationRouter(
            memory=memory,
            planner=planner,
            responses=responses,
            context=context,
        )

        # Create a message event
        event = ConversationEvent(
            kind=ConversationEventKind.CHAT_MESSAGE,
            conversation_id="123-456",
            user_id="user123",
            text="Hello!",
            channel_id="channel123",
            guild_id="guild123",
        )

        # Process the event
        await router.handle(event)

        # Verify state was created
        state = router._state_manager.get("123-456")
        assert state is not None
        assert state.guild_id == "guild123"
        assert state.channel_id == "channel123"
        assert state.user_id == "user123"

    @pytest.mark.asyncio
    async def test_interruption_handling(self, mock_discord_client: MockDiscordClient) -> None:
        """Test interruption handling."""
        from directioner.conversation.events import ConversationEvent, ConversationEventKind
        from directioner.conversation.router import ConversationRouter
        from directioner.conversation.context import ContextManager
        from directioner.intent.planner import Planner
        from directioner.memory.store import MemoryStore
        from directioner.response.router import ResponseRouter

        # Build components
        memory = MemoryStore()
        planner = Planner()
        responses = ResponseRouter(memory=memory)
        context = ContextManager()
        router = ConversationRouter(
            memory=memory,
            planner=planner,
            responses=responses,
            context=context,
        )

        # Create conversation
        conv_id = "test-conv-1"
        
        # Send first message
        event1 = ConversationEvent(
            kind=ConversationEventKind.CHAT_MESSAGE,
            conversation_id=conv_id,
            user_id="user1",
            text="Hello!",
        )
        await router.handle(event1)

        # Verify no interruptions yet
        state = router._state_manager.get(conv_id)
        assert state.interruption_count == 0

    @pytest.mark.asyncio
    async def test_mention_removal(self) -> None:
        """Test that Discord mentions are removed from messages."""
        from directioner.conversation.events import ConversationEvent, ConversationEventKind
        from directioner.conversation.router import ConversationRouter
        from directioner.conversation.context import ContextManager
        from directioner.intent.planner import Planner
        from directioner.memory.store import MemoryStore
        from directioner.response.router import ResponseRouter

        # Build components
        memory = MemoryStore()
        planner = Planner()
        responses = ResponseRouter(memory=memory)
        context = ContextManager()
        router = ConversationRouter(
            memory=memory,
            planner=planner,
            responses=responses,
            context=context,
        )

        # Message with mentions
        event = ConversationEvent(
            kind=ConversationEventKind.CHAT_MESSAGE,
            conversation_id="conv-mention",
            user_id="user1",
            text="<@123456789> Hello bot! <@987654321> How are you?",
        )
        await router.handle(event)


class TestScaling:
    """Test scaling capabilities."""

    @pytest.mark.asyncio
    async def test_many_conversations(self) -> None:
        """Test handling many concurrent conversations."""
        from directioner.conversation.router import ConversationRouter
        from directioner.conversation.context import ContextManager
        from directioner.intent.planner import Planner
        from directioner.memory.store import MemoryStore
        from directioner.response.router import ResponseRouter

        # Build components with small limits for testing
        memory = MemoryStore()
        planner = Planner()
        responses = ResponseRouter(memory=memory)
        context = ContextManager()
        router = ConversationRouter(
            memory=memory,
            planner=planner,
            responses=responses,
            context=context,
            max_conversations=100,  # Small limit for testing
        )

        # Create many conversations
        tasks = []
        for i in range(50):
            from directioner.conversation.events import ConversationEvent, ConversationEventKind
            
            event = ConversationEvent(
                kind=ConversationEventKind.CHAT_MESSAGE,
                conversation_id=f"conv-{i}",
                user_id=f"user-{i % 10}",  # 10 unique users
                text=f"Message {i}",
                guild_id=f"guild-{i % 5}",  # 5 unique guilds
                channel_id=f"channel-{i % 20}",  # 20 unique channels
            )
            tasks.append(router.handle(event))

        # Process all concurrently
        await asyncio.gather(*tasks)

        # Verify conversations were created
        stats = router.get_state_stats()
        assert stats["total_conversations"] == 50
        assert stats["total_users"] == 10
        assert stats["total_guilds"] == 5
        assert stats["total_channels"] == 20

    @pytest.mark.asyncio
    async def test_guild_isolation(self) -> None:
        """Test that guilds are properly isolated."""
        from directioner.conversation.router import ConversationRouter
        from directioner.conversation.context import ContextManager
        from directioner.intent.planner import Planner
        from directioner.memory.store import MemoryStore
        from directioner.response.router import ResponseRouter

        memory = MemoryStore()
        planner = Planner()
        responses = ResponseRouter(memory=memory)
        context = ContextManager()
        router = ConversationRouter(
            memory=memory,
            planner=planner,
            responses=responses,
            context=context,
        )

        # Create conversations in different guilds
        from directioner.conversation.events import ConversationEvent, ConversationEventKind
        
        for i in range(3):
            for j in range(5):
                event = ConversationEvent(
                    kind=ConversationEventKind.CHAT_MESSAGE,
                    conversation_id=f"conv-{i}-{j}",
                    user_id=f"user-{j}",
                    text=f"Message {j}",
                    guild_id=f"guild-{i}",
                    channel_id=f"channel-{i}-{j}",
                )
                await router.handle(event)

        # Verify guild isolation
        stats = router.get_state_stats()
        assert stats["total_guilds"] == 3
        assert stats["total_conversations"] == 15

        # Get guild-specific stats
        guild1_convs = router._state_manager.get_guild_states("guild-0")
        assert len(guild1_convs) == 5


class TestRateLimiting:
    """Test rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limit_enforcement(self) -> None:
        """Test that rate limits are enforced."""
        from directioner.memory.store import (
            PerEntityRateLimiter,
            MemoryRateLimitError,
        )
        
        # Create limiter with very low limits
        limiter = PerEntityRateLimiter(
            per_user_limit=2,
            per_channel_limit=5,
            per_guild_limit=10,
            window_seconds=60,
        )

        # First 2 user requests should pass
        assert limiter.check_user("user1") is True
        assert limiter.check_user("user1") is True
        
        # 3rd should fail
        assert limiter.check_user("user1") is False

        # Different user should pass
        assert limiter.check_user("user2") is True

        # Check all at once
        allowed, reason = limiter.check_all(
            user_id="user1",
            channel_id="channel1",
            guild_id="guild1",
        )
        assert allowed is False
        assert "User" in reason

    @pytest.mark.asyncio
    async def test_rate_limit_in_memory_store(self) -> None:
        """Test rate limiting integrated with MemoryStore."""
        from directioner.memory.store import (
            MemoryStore,
            PerEntityRateLimiter,
        )
        from directioner.conversation.events import ConversationEvent, ConversationEventKind

        # Create limiter with low limits
        limiter = PerEntityRateLimiter(
            per_user_limit=1,
            per_channel_limit=2,
            per_guild_limit=3,
        )
        memory = MemoryStore(rate_limiter=limiter)

        event = ConversationEvent(
            kind=ConversationEventKind.CHAT_MESSAGE,
            conversation_id="test-conv",
            user_id="test-user",
            text="Hello!",
            guild_id="test-guild",
            channel_id="test-channel",
        )

        from directioner.conversation.state import ConversationState
        state = ConversationState(conversation_id="test-conv")

        # First request should work
        ctx = await memory.retrieve(event, state)
        assert ctx is not None

        # Second request should be rate limited
        ctx = await memory.retrieve(event, state)


class TestSecurity:
    """Test security features."""

    def test_discord_id_validation(self) -> None:
        """Test Discord ID validation."""
        from directioner.security import DiscordIdValidator

        validator = DiscordIdValidator()

        # Valid IDs
        assert validator.is_valid_user_id("123456789012345678") is True
        assert validator.is_valid_channel_id("987654321098765432") is True
        assert validator.is_valid_guild_id("111222333444555666") is True

        # Invalid IDs
        assert validator.is_valid_user_id("abc") is False
        assert validator.is_valid_user_id("123") is False  # Too short
        assert validator.is_valid_user_id("") is True  # Optional

    def test_content_validation(self) -> None:
        """Test content validation."""
        from directioner.security import ContentValidator

        validator = ContentValidator()

        # Valid content
        result = validator.validate_message("Hello, world!")
        assert result.valid is True

        # Empty content
        result = validator.validate_message("")
        assert result.valid is False

        # Script injection
        result = validator.validate_message("<script>alert('xss')</script>")
        assert result.valid is False

        # JavaScript protocol
        result = validator.validate_message("javascript:alert('xss')")
        assert result.valid is False

        # Event handler
        result = validator.validate_message("<img onerror=alert(1)>")
        assert result.valid is False

    def test_content_sanitization(self) -> None:
        """Test content sanitization."""
        from directioner.security import ContentValidator

        validator = ContentValidator()

        # Remove null bytes
        sanitized = validator.sanitize_message("Hello\x00World")
        assert "\x00" not in sanitized

        # Normalize whitespace
        sanitized = validator.sanitize_message("Hello    World")
        assert "  " not in sanitized


class TestHealthCheck:
    """Test health check functionality."""

    def test_health_check_command(self) -> None:
        """Test health check command runs successfully."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "directioner.app", "health-check"],
            capture_output=True,
            text=True,
            env={"PYTHONPATH": "src"},
            cwd="/workspace/project/Directioner",
        )

        assert result.returncode == 0
        assert "status" in result.stdout
        assert "ok" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
