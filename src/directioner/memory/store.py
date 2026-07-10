"""Memory facade used by the conversation router.

The store keeps a durable, per-conversation log of user turns so the assistant
can recall what was said earlier in a channel even across restarts. Turns are
held in a bounded in-memory deque per conversation and, when a persistence path
or Supabase is configured, preserved long-term.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from directioner.config.settings import MemorySettings
from directioner.conversation.events import ConversationEvent
from directioner.conversation.state import ConversationState
from directioner.text.cleanup import strip_discord_mentions

try:
    from supabase import create_client, Client
except ImportError:
    Client = None
    create_client = None


@dataclass(frozen=True, slots=True)
class MemoryTurn:
    conversation_id: str
    role: str
    content: str
    user_id: str | None = None
    timestamp: float = 0.0

    def to_json(self) -> str:
        return json.dumps(
            {
                "conversation_id": self.conversation_id,
                "role": self.role,
                "content": self.content,
                "user_id": self.user_id,
                "timestamp": self.timestamp,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_mapping(cls, data: dict) -> "MemoryTurn":
        return cls(
            conversation_id=str(data.get("conversation_id", "")),
            role=str(data.get("role", "user")),
            content=str(data.get("content", "")),
            user_id=(str(data["user_id"]) if data.get("user_id") is not None else None),
            timestamp=float(data.get("timestamp", 0.0)),
        )


@dataclass(frozen=True, slots=True)
class MemoryContext:
    working: tuple[str, ...] = ()
    conversation: tuple[str, ...] = ()
    semantic: tuple[str, ...] = ()
    user_preferences: dict[str, str] = field(default_factory=dict)


class ConversationMemory:
    """Durable, bounded per-conversation turn log with optional persistence."""

    def __init__(
        self,
        max_turns_per_conversation: int = 200,
        persist_path: str | Path | None = None,
    ) -> None:
        if max_turns_per_conversation <= 0:
            raise ValueError("max_turns_per_conversation must be positive")
        self._max_turns = max_turns_per_conversation
        self._persist_path = Path(persist_path) if persist_path else None
        self._turns: dict[str, deque[MemoryTurn]] = defaultdict(
            lambda: deque(maxlen=self._max_turns)
        )
        if self._persist_path is not None:
            self._load()

    def record(self, turn: MemoryTurn) -> None:
        if not turn.content.strip():
            return
        self._turns[turn.conversation_id].append(turn)
        self._append_persist(turn)

    def recent(self, conversation_id: str, limit: int) -> tuple[MemoryTurn, ...]:
        if limit <= 0:
            return ()
        turns = self._turns.get(conversation_id)
        if not turns:
            return ()
        return tuple(turns)[-limit:]

    def clear_conversation(self, conversation_id: str) -> None:
        """Clear all memory for a specific conversation.
        
        Note: Persistent file isn't cleared automatically to avoid accidental data loss.
        """
        if conversation_id in self._turns:
            self._turns[conversation_id].clear()

    def _append_persist(self, turn: MemoryTurn) -> None:
        if self._persist_path is None:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        with self._persist_path.open("a", encoding="utf-8") as handle:
            handle.write(turn.to_json() + "\n")

    def _load(self) -> None:
        assert self._persist_path is not None
        if not self._persist_path.exists():
            return
        with self._persist_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                turn = MemoryTurn.from_mapping(data)
                if turn.conversation_id and turn.content:
                    self._turns[turn.conversation_id].append(turn)


def _normalize_memory_text(text: str) -> str:
    return strip_discord_mentions(text.strip())


def _should_index_semantic(text: str) -> bool:
    lowered = text.lower()
    if not lowered:
        return False
    blocked_phrases = (
        "python llm facade",
        "mock mode",
        "groq_api_key",
        "you said:",
    )
    return not any(phrase in lowered for phrase in blocked_phrases)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _cosine_similarity(text1: str, text2: str) -> float:
    words1 = _tokenize(text1)
    words2 = _tokenize(text2)
    if not words1 or not words2:
        return 0.0
    c1 = Counter(words1)
    c2 = Counter(words2)
    intersection = set(c1.keys()) & set(c2.keys())
    numerator = sum(c1[x] * c2[x] for x in intersection)
    sum1 = sum(c1[x] ** 2 for x in c1.keys())
    sum2 = sum(c2[x] ** 2 for x in c2.keys())
    denominator = math.sqrt(sum1) * math.sqrt(sum2)
    if not denominator:
        return 0.0
    return numerator / denominator


@dataclass(frozen=True, slots=True)
class SemanticEntry:
    conversation_id: str
    text: str
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "conversation_id": self.conversation_id,
            "text": self.text,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SemanticEntry:
        return cls(
            conversation_id=str(data.get("conversation_id", "")),
            text=str(data.get("text", "")),
            timestamp=float(data.get("timestamp", 0.0)),
        )


class SemanticMemory:
    """Local JSON-persisted semantic memory store using cosine similarity of word counts."""

    def __init__(self, persist_path: str | Path | None = None) -> None:
        self._persist_path = Path(persist_path) if persist_path else None
        self._entries: list[SemanticEntry] = []
        if self._persist_path:
            self._load()

    def record(self, conversation_id: str, text: str) -> None:
        cleaned = _normalize_memory_text(text)
        if not cleaned or not _should_index_semantic(cleaned):
            return
        if any(e.conversation_id == conversation_id and e.text == cleaned for e in self._entries[-10:]):
            return
        self._entries.append(SemanticEntry(conversation_id, cleaned, time.time()))
        self._save()

    def search(self, conversation_id: str, query: str, limit: int = 3) -> tuple[str, ...]:
        cleaned_query = _normalize_memory_text(query)
        if not cleaned_query:
            return ()
        candidates = [
            e
            for e in self._entries
            if e.conversation_id == conversation_id and _should_index_semantic(e.text)
        ]
        if not candidates:
            return ()
        scored = []
        for entry in candidates:
            score = _cosine_similarity(entry.text, cleaned_query)
            if score > 0.1:
                scored.append((score, entry.text))
        scored.sort(key=lambda item: item[0], reverse=True)
        return tuple(text for _, text in scored[:limit])

    def clear_conversation(self, conversation_id: str) -> None:
        """Clear all semantic memory for a specific conversation."""
        self._entries = [e for e in self._entries if e.conversation_id != conversation_id]
        self._save()

    def _save(self) -> None:
        if not self._persist_path:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with self._persist_path.open("w", encoding="utf-8") as handle:
                json.dump([e.to_dict() for e in self._entries], handle, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load(self) -> None:
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            with self._persist_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                if isinstance(data, list):
                    self._entries = [SemanticEntry.from_dict(item) for item in data]
        except Exception:
            pass


class UserPreferenceMemory:
    """Manages per-user key-value preferences with optional persistence."""

    def __init__(self, persist_path: str | Path | None = None) -> None:
        self._persist_path = Path(persist_path) if persist_path else None
        self._preferences: dict[str, dict[str, str]] = defaultdict(dict)
        if self._persist_path:
            self._load()

    def set_preference(self, user_id: str, key: str, value: str) -> None:
        if not user_id or not key:
            return
        self._preferences[user_id][key] = value
        self._save()

    def delete_preference(self, user_id: str, key: str) -> None:
        if not user_id or not key:
            return
        if user_id in self._preferences and key in self._preferences[user_id]:
            del self._preferences[user_id][key]
            self._save()

    def get_preferences(self, user_id: str) -> dict[str, str]:
        return dict(self._preferences.get(user_id, {}))

    def _save(self) -> None:
        if not self._persist_path:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with self._persist_path.open("w", encoding="utf-8") as handle:
                json.dump(self._preferences, handle, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load(self) -> None:
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            with self._persist_path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
                if isinstance(loaded, dict):
                    for uid, prefs in loaded.items():
                        if isinstance(prefs, dict):
                            self._preferences[uid] = {str(k): str(v) for k, v in prefs.items()}
        except Exception:
            pass


# Supabase-backed memory implementations
class SupabaseConversationMemory:
    """Supabase-backed conversation memory."""

    def __init__(self, client: Client, max_turns_per_conversation: int = 200):
        if not Client:
            raise RuntimeError("Supabase not installed. Install with 'pip install supabase'.")
        self._client = client
        self._max_turns = max_turns_per_conversation
        self._in_memory_turns: dict[str, deque[MemoryTurn]] = defaultdict(
            lambda: deque(maxlen=self._max_turns)
        )

    def record(self, turn: MemoryTurn) -> None:
        if not turn.content.strip():
            return
        self._in_memory_turns[turn.conversation_id].append(turn)
        try:
            self._client.table("conversation_turns").insert({
                "conversation_id": turn.conversation_id,
                "role": turn.role,
                "content": turn.content,
                "user_id": turn.user_id,
                "timestamp": turn.timestamp,
            }).execute()
        except Exception:
            pass

    def recent(self, conversation_id: str, limit: int) -> tuple[MemoryTurn, ...]:
        if limit <= 0:
            return ()
        # First check in-memory
        in_memory = self._in_memory_turns.get(conversation_id)
        in_memory_results: tuple[MemoryTurn, ...] = ()
        if in_memory:
            in_memory_results = tuple(in_memory)[-limit:]
            if len(in_memory_results) >= limit:
                return in_memory_results
        # Otherwise fetch from Supabase
        try:
            response = self._client.table("conversation_turns")\
                .select("*")\
                .eq("conversation_id", conversation_id)\
                .order("timestamp", desc=True)\
                .limit(limit)\
                .execute()
            turns = [MemoryTurn.from_mapping(row) for row in response.data]
            turns.reverse()  # Reverse to get chronological order
            return tuple(turns)
        except Exception:
            return in_memory_results

    def clear_conversation(self, conversation_id: str) -> None:
        if conversation_id in self._in_memory_turns:
            self._in_memory_turns[conversation_id].clear()
        try:
            self._client.table("conversation_turns")\
                .delete()\
                .eq("conversation_id", conversation_id)\
                .execute()
        except Exception:
            pass


class SupabaseUserPreferenceMemory:
    """Supabase-backed user preference memory."""

    def __init__(self, client: Client):
        if not Client:
            raise RuntimeError("Supabase not installed. Install with 'pip install supabase'.")
        self._client = client
        self._in_memory: dict[str, dict[str, str]] = defaultdict(dict)

    def set_preference(self, user_id: str, key: str, value: str) -> None:
        if not user_id or not key:
            return
        self._in_memory[user_id][key] = value
        try:
            # Upsert the preference
            self._client.table("user_preferences").upsert({
                "user_id": user_id,
                "key": key,
                "value": value,
            }).execute()
        except Exception:
            pass

    def delete_preference(self, user_id: str, key: str) -> None:
        if not user_id or not key:
            return
        if user_id in self._in_memory and key in self._in_memory[user_id]:
            del self._in_memory[user_id][key]
        try:
            self._client.table("user_preferences")\
                .delete()\
                .eq("user_id", user_id)\
                .eq("key", key)\
                .execute()
        except Exception:
            pass

    def get_preferences(self, user_id: str) -> dict[str, str]:
        if user_id in self._in_memory:
            return dict(self._in_memory[user_id])
        try:
            response = self._client.table("user_preferences")\
                .select("key, value")\
                .eq("user_id", user_id)\
                .execute()
            prefs = {row["key"]: row["value"] for row in response.data}
            self._in_memory[user_id] = prefs
            return dict(prefs)
        except Exception:
            return dict(self._in_memory.get(user_id, {}))


class SupabaseSemanticMemory:
    """Supabase-backed semantic memory."""

    def __init__(self, client: Client):
        if not Client:
            raise RuntimeError("Supabase not installed. Install with 'pip install supabase'.")
        self._client = client
        self._in_memory_entries: list[SemanticEntry] = []

    def record(self, conversation_id: str, text: str) -> None:
        cleaned = _normalize_memory_text(text)
        if not cleaned or not _should_index_semantic(cleaned):
            return
        entry = SemanticEntry(conversation_id, cleaned, time.time())
        self._in_memory_entries.append(entry)
        try:
            self._client.table("semantic_memory").insert({
                "conversation_id": entry.conversation_id,
                "text": entry.text,
                "timestamp": entry.timestamp,
            }).execute()
        except Exception:
            pass

    def search(self, conversation_id: str, query: str, limit: int = 3) -> tuple[str, ...]:
        cleaned_query = _normalize_memory_text(query)
        if not cleaned_query:
            return ()
        # First try in-memory (simple cosine similarity)
        candidates = [
            e
            for e in self._in_memory_entries
            if e.conversation_id == conversation_id and _should_index_semantic(e.text)
        ]
        in_memory_results: tuple[str, ...] = ()
        if candidates:
            scored = []
            for entry in candidates:
                score = _cosine_similarity(entry.text, cleaned_query)
                if score > 0.1:
                    scored.append((score, entry.text))
            scored.sort(key=lambda item: item[0], reverse=True)
            in_memory_results = tuple(text for _, text in scored[:limit])
            if len(in_memory_results) >= limit:
                return in_memory_results
        # Then try Supabase if possible
        try:
            # TODO: If using Supabase Vector search, replace this with a vector query!
            # For now, just get all recent entries and compute similarity
            response = self._client.table("semantic_memory")\
                .select("text")\
                .eq("conversation_id", conversation_id)\
                .order("timestamp", desc=True)\
                .limit(50)\
                .execute()
            db_candidates = [row["text"] for row in response.data if _should_index_semantic(row["text"])]
            db_scored = []
            for text in db_candidates:
                score = _cosine_similarity(text, cleaned_query)
                if score > 0.1:
                    db_scored.append((score, text))
            db_scored.sort(key=lambda item: item[0], reverse=True)
            db_results = tuple(text for _, text in db_scored[:limit])
            # Combine and deduplicate, prioritizing in-memory
            combined = list(in_memory_results)
            seen = set(combined)
            for text in db_results:
                if text not in seen:
                    combined.append(text)
                    seen.add(text)
            return tuple(combined[:limit])
        except Exception:
            return in_memory_results

    def clear_conversation(self, conversation_id: str) -> None:
        self._in_memory_entries = [e for e in self._in_memory_entries if e.conversation_id != conversation_id]
        try:
            self._client.table("semantic_memory")\
                .delete()\
                .eq("conversation_id", conversation_id)\
                .execute()
        except Exception:
            pass


class MemoryStore:
    def __init__(
        self,
        settings: MemorySettings | None = None,
        conversation_memory: ConversationMemory | None = None,
        user_preference_memory: UserPreferenceMemory | None = None,
        semantic_memory: SemanticMemory | None = None,
    ) -> None:
        self._settings = settings or MemorySettings()

        # Check if Supabase is available and configured
        use_supabase = (
            self._settings.enabled
            and self._settings.use_supabase
            and Client
            and create_client
            and self._settings.supabase_url
            and self._settings.supabase_key
        )

        if use_supabase:
            try:
                client = create_client(self._settings.supabase_url, self._settings.supabase_key)
                if conversation_memory is not None:
                    self._conversation = conversation_memory
                else:
                    self._conversation = SupabaseConversationMemory(client, self._settings.max_turns_per_conversation)  # type: ignore[assignment]
                if user_preference_memory is not None:
                    self._user_preferences = user_preference_memory
                else:
                    self._user_preferences = SupabaseUserPreferenceMemory(client)  # type: ignore[assignment]
                if semantic_memory is not None:
                    self._semantic = semantic_memory
                else:
                    self._semantic = SupabaseSemanticMemory(client)  # type: ignore[assignment]
                return
            except Exception:
                pass

        if conversation_memory is not None:
            self._conversation = conversation_memory
        elif self._settings.enabled:
            self._conversation = ConversationMemory(
                max_turns_per_conversation=self._settings.max_turns_per_conversation,
                persist_path=self._settings.persist_path,
            )
        else:
            self._conversation = None

        if user_preference_memory is not None:
            self._user_preferences = user_preference_memory
        elif self._settings.enabled:
            pref_path = None
            if self._settings.persist_path:
                base_path = Path(self._settings.persist_path)
                pref_path = base_path.parent / "user_preferences.json"
            self._user_preferences = UserPreferenceMemory(persist_path=pref_path)
        else:
            self._user_preferences = None

        if semantic_memory is not None:
            self._semantic = semantic_memory
        elif self._settings.enabled:
            sem_path = None
            if self._settings.persist_path:
                base_path = Path(self._settings.persist_path)
                sem_path = base_path.parent / "semantic_memory.json"
            self._semantic = SemanticMemory(persist_path=sem_path)
        else:
            self._semantic = None

    def record_event(self, event: ConversationEvent) -> None:
        """Persist a user turn into durable memory systems."""

        if self._conversation is None:
            return
        content = _normalize_memory_text(event.text)
        if not content:
            return
        self._conversation.record(
            MemoryTurn(
                conversation_id=event.conversation_id,
                role="user",
                content=content,
                user_id=event.user_id,
                timestamp=time.time(),
            )
        )
        if self._semantic is not None and _should_index_semantic(content):
            self._semantic.record(event.conversation_id, content)

    def record_assistant_turn(self, conversation_id: str, content: str) -> None:
        """Persist an assistant turn into durable memory systems."""

        if self._conversation is None:
            return
        cleaned = _normalize_memory_text(content)
        if not cleaned:
            return
        self._conversation.record(
            MemoryTurn(
                conversation_id=conversation_id,
                role="assistant",
                content=cleaned,
                timestamp=time.time(),
            )
        )
        if self._semantic is not None and _should_index_semantic(cleaned):
            self._semantic.record(conversation_id, cleaned)

    def set_user_preference(self, user_id: str, key: str, value: str) -> None:
        if self._user_preferences is not None:
            self._user_preferences.set_preference(user_id, key, value)

    def delete_user_preference(self, user_id: str, key: str) -> None:
        if self._user_preferences is not None:
            self._user_preferences.delete_preference(user_id, key)

    def clear_conversation(self, conversation_id: str) -> None:
        if self._conversation is not None:
            self._conversation.clear_conversation(conversation_id)
        if self._semantic is not None:
            self._semantic.clear_conversation(conversation_id)

    def record_tool_result(self, conversation_id: str, tool_name: str, result: str) -> None:
        """Persist a tool execution result as conversation memory."""

        if self._conversation is None:
            return
        cleaned_name = tool_name.strip()
        cleaned_result = result.strip()
        if not cleaned_name or not cleaned_result:
            return
        content = f"{cleaned_name}: {cleaned_result}"
        self._conversation.record(
            MemoryTurn(
                conversation_id=conversation_id,
                role="tool",
                content=content,
                timestamp=time.time(),
            )
        )
        if self._semantic is not None:
            self._semantic.record(conversation_id, content)

    def get_user_preferences(self, user_id: str) -> dict[str, str]:
        if self._user_preferences is not None:
            return self._user_preferences.get_preferences(user_id)
        return {}

    async def retrieve(
        self,
        event: ConversationEvent,
        state: ConversationState,
    ) -> MemoryContext:
        conversation: tuple[str, ...] = ()
        if self._conversation is not None:
            turns = self._conversation.recent(
                event.conversation_id,
                self._settings.retrieval_turns,
            )
            conversation = tuple(
                f"{turn.role}: {turn.content}"
                for turn in turns
                if turn.role == "user" or _should_index_semantic(turn.content)
            )
        user_prefs = self.get_user_preferences(event.user_id)
        semantic_mems: tuple[str, ...] = ()
        if self._semantic is not None:
            query = _normalize_memory_text(event.text)
            semantic_mems = tuple(
                text
                for text in self._semantic.search(event.conversation_id, query)
                if _should_index_semantic(text)
            )
        return MemoryContext(
            working=tuple(state.context_items[-8:]),
            conversation=conversation,
            semantic=semantic_mems,
            user_preferences=user_prefs,
        )
