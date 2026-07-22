"""Conversation state containers with guild/channel isolation for scaling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
import time
import threading

if TYPE_CHECKING:
    from directioner.conversation.context import ContextRecord


@dataclass(slots=True)
class ActiveTask:
    task_id: str
    cancellable: bool = True
    output_destination: str = "chat"


@dataclass(slots=True)
class ConversationState:
    conversation_id: str
    guild_id: str | None = None
    channel_id: str | None = None
    user_id: str | None = None
    active_speakers: dict[str, str] = field(default_factory=dict)
    active_task: ActiveTask | None = None
    context_items: list[str] = field(default_factory=list)
    context_records: list["ContextRecord"] = field(default_factory=list)
    interruption_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    request_count: int = 0

    def remember_text(self, text: str) -> None:
        if text:
            self.context_items.append(text)
            self.last_activity = time.time()

    def update_activity(self) -> None:
        """Update last activity timestamp and request count."""
        self.last_activity = time.time()
        self.request_count += 1

    def is_idle(self, idle_seconds: float = 3600) -> bool:
        """Check if conversation has been idle for given seconds."""
        return (time.time() - self.last_activity) > idle_seconds


class ConversationStateManager:
    """Thread-safe conversation state manager with automatic cleanup.
    
    Designed for high-scale deployments with per-guild, per-channel isolation.
    """

    def __init__(
        self,
        max_states: int = 100_000,
        max_per_guild: int = 10_000,
        max_per_channel: int = 1_000,
        idle_timeout: float = 3600.0,  # 1 hour default
        cleanup_interval: float = 300.0,  # 5 minutes
    ) -> None:
        self._states: dict[str, ConversationState] = {}
        self._guild_states: dict[str, set[str]] = {}  # guild_id -> conversation_ids
        self._channel_states: dict[str, set[str]] = {}  # channel_id -> conversation_ids
        self._user_states: dict[str, set[str]] = {}  # user_id -> conversation_ids
        
        self._lock = threading.RLock()
        self._max_states = max_states
        self._max_per_guild = max_per_guild
        self._max_per_channel = max_per_channel
        self._idle_timeout = idle_timeout
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()
        
        # Stats
        self._total_requests = 0
        self._total_evictions = 0

    def get_or_create(
        self,
        conversation_id: str,
        guild_id: str | None = None,
        channel_id: str | None = None,
        user_id: str | None = None,
    ) -> ConversationState:
        """Get or create a conversation state with proper isolation."""
        with self._lock:
            self._total_requests += 1
            
            # Check if exists
            if conversation_id in self._states:
                state = self._states[conversation_id]
                state.update_activity()
                return state
            
            # Auto-cleanup if needed
            self._maybe_cleanup_unlocked()
            
            # Check limits
            if len(self._states) >= self._max_states:
                self._evict_oldest_unlocked()
            
            # Check per-guild limit
            if guild_id and guild_id in self._guild_states:
                if len(self._guild_states[guild_id]) >= self._max_per_guild:
                    # Evict oldest from this guild
                    self._evict_oldest_from_guild_unlocked(guild_id)
            
            # Check per-channel limit
            if channel_id and channel_id in self._channel_states:
                if len(self._channel_states[channel_id]) >= self._max_per_channel:
                    # Evict oldest from this channel
                    self._evict_oldest_from_channel_unlocked(channel_id)
            
            # Create new state
            state = ConversationState(
                conversation_id=conversation_id,
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=user_id,
            )
            self._states[conversation_id] = state
            
            # Update index structures
            if guild_id:
                if guild_id not in self._guild_states:
                    self._guild_states[guild_id] = set()
                self._guild_states[guild_id].add(conversation_id)
            
            if channel_id:
                if channel_id not in self._channel_states:
                    self._channel_states[channel_id] = set()
                self._channel_states[channel_id].add(conversation_id)
            
            if user_id:
                if user_id not in self._user_states:
                    self._user_states[user_id] = set()
                self._user_states[user_id].add(conversation_id)
            
            return state

    def get(self, conversation_id: str) -> ConversationState | None:
        """Get a conversation state if it exists."""
        with self._lock:
            state = self._states.get(conversation_id)
            if state:
                state.update_activity()
            return state

    def remove(self, conversation_id: str) -> bool:
        """Remove a conversation state."""
        with self._lock:
            if conversation_id not in self._states:
                return False
            
            state = self._states.pop(conversation_id)
            
            # Remove from indexes
            if state.guild_id and state.guild_id in self._guild_states:
                self._guild_states[state.guild_id].discard(conversation_id)
                if not self._guild_states[state.guild_id]:
                    del self._guild_states[state.guild_id]
            
            if state.channel_id and state.channel_id in self._channel_states:
                self._channel_states[state.channel_id].discard(conversation_id)
                if not self._channel_states[state.channel_id]:
                    del self._channel_states[state.channel_id]
            
            if state.user_id and state.user_id in self._user_states:
                self._user_states[state.user_id].discard(conversation_id)
                if not self._user_states[state.user_id]:
                    del self._user_states[state.user_id]
            
            return True

    def get_guild_states(self, guild_id: str) -> list[ConversationState]:
        """Get all conversation states for a guild."""
        with self._lock:
            conv_ids = self._guild_states.get(guild_id, set())
            return [self._states[c] for c in conv_ids if c in self._states]

    def get_channel_states(self, channel_id: str) -> list[ConversationState]:
        """Get all conversation states for a channel."""
        with self._lock:
            conv_ids = self._channel_states.get(channel_id, set())
            return [self._states[c] for c in conv_ids if c in self._states]

    def get_user_states(self, user_id: str) -> list[ConversationState]:
        """Get all conversation states involving a user."""
        with self._lock:
            conv_ids = self._user_states.get(user_id, set())
            return [self._states[c] for c in conv_ids if c in self._states]

    def _maybe_cleanup_unlocked(self) -> None:
        """Cleanup idle states if interval has passed."""
        if time.time() - self._last_cleanup < self._cleanup_interval:
            return
        
        self._last_cleanup = time.time()
        idle_ids = [
            conv_id for conv_id, state in self._states.items()
            if state.is_idle(self._idle_timeout)
        ]
        
        for conv_id in idle_ids:
            self._states.pop(conv_id, None)
            self._total_evictions += 1
        
        # Rebuild indexes
        self._rebuild_indexes_unlocked()

    def _evict_oldest_unlocked(self) -> None:
        """Evict the oldest conversation by last activity."""
        if not self._states:
            return
        
        oldest_id = min(
            self._states.keys(),
            key=lambda k: self._states[k].last_activity
        )
        self.remove(oldest_id)
        self._total_evictions += 1

    def _evict_oldest_from_guild_unlocked(self, guild_id: str) -> None:
        """Evict oldest conversation from a specific guild."""
        conv_ids = self._guild_states.get(guild_id, set())
        if not conv_ids:
            return
        
        oldest_id = min(
            conv_ids,
            key=lambda k: self._states[k].last_activity if k in self._states else float('inf')
        )
        self.remove(oldest_id)
        self._total_evictions += 1

    def _evict_oldest_from_channel_unlocked(self, channel_id: str) -> None:
        """Evict oldest conversation from a specific channel."""
        conv_ids = self._channel_states.get(channel_id, set())
        if not conv_ids:
            return
        
        oldest_id = min(
            conv_ids,
            key=lambda k: self._states[k].last_activity if k in self._states else float('inf')
        )
        self.remove(oldest_id)
        self._total_evictions += 1

    def _rebuild_indexes_unlocked(self) -> None:
        """Rebuild index structures after cleanup."""
        self._guild_states.clear()
        self._channel_states.clear()
        self._user_states.clear()
        
        for conv_id, state in self._states.items():
            if state.guild_id:
                if state.guild_id not in self._guild_states:
                    self._guild_states[state.guild_id] = set()
                self._guild_states[state.guild_id].add(conv_id)
            
            if state.channel_id:
                if state.channel_id not in self._channel_states:
                    self._channel_states[state.channel_id] = set()
                self._channel_states[state.channel_id].add(conv_id)
            
            if state.user_id:
                if state.user_id not in self._user_states:
                    self._user_states[state.user_id] = set()
                self._user_states[state.user_id].add(conv_id)

    def cleanup_idle(self) -> int:
        """Manually trigger cleanup of idle states. Returns count evicted."""
        with self._lock:
            idle_ids = [
                conv_id for conv_id, state in self._states.items()
                if state.is_idle(self._idle_timeout)
            ]
            
            for conv_id in idle_ids:
                self.remove(conv_id)
            
            self._total_evictions += len(idle_ids)
            return len(idle_ids)

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the state manager."""
        with self._lock:
            return {
                "total_conversations": len(self._states),
                "total_guilds": len(self._guild_states),
                "total_channels": len(self._channel_states),
                "total_users": len(self._user_states),
                "max_conversations": self._max_states,
                "total_requests": self._total_requests,
                "total_evictions": self._total_evictions,
            }
