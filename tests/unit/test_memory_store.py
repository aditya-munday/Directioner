from __future__ import annotations

from pathlib import Path

import pytest

from directioner.config.settings import MemorySettings
from directioner.conversation.events import ConversationEvent, ConversationEventKind
from directioner.conversation.state import ConversationState
from directioner.memory.store import ConversationMemory, MemoryStore, MemoryTurn, UserPreferenceMemory, SemanticMemory


def _chat_event(conversation_id: str, text: str, user_id: str = "u1") -> ConversationEvent:
    return ConversationEvent(
        kind=ConversationEventKind.CHAT_MESSAGE,
        conversation_id=conversation_id,
        user_id=user_id,
        channel_id=conversation_id,
        text=text,
    )


async def test_memory_store_records_and_retrieves_conversation_turns() -> None:
    store = MemoryStore(MemorySettings(retrieval_turns=5, persist_path=None))
    state = ConversationState(conversation_id="c1")

    store.record_event(_chat_event("c1", "hello there"))
    store.record_event(_chat_event("c1", "how are you"))

    context = await store.retrieve(_chat_event("c1", "again"), state)

    assert context.conversation == ("user: hello there", "user: how are you")


async def test_memory_store_scopes_by_conversation() -> None:
    store = MemoryStore(MemorySettings(persist_path=None))
    store.record_event(_chat_event("a", "first"))
    store.record_event(_chat_event("b", "second"))

    context = await store.retrieve(_chat_event("a", "x"), ConversationState(conversation_id="a"))

    assert context.conversation == ("user: first",)


async def test_memory_store_disabled_records_nothing() -> None:
    store = MemoryStore(MemorySettings(enabled=False, persist_path=None))
    store.record_event(_chat_event("c1", "hello"))

    context = await store.retrieve(_chat_event("c1", "x"), ConversationState(conversation_id="c1"))

    assert context.conversation == ()


async def test_memory_store_ignores_blank_turns() -> None:
    store = MemoryStore(MemorySettings(persist_path=None))
    store.record_event(_chat_event("c1", "   "))

    context = await store.retrieve(_chat_event("c1", "x"), ConversationState(conversation_id="c1"))

    assert context.conversation == ()


def test_conversation_memory_respects_max_turns() -> None:
    memory = ConversationMemory(max_turns_per_conversation=2)
    for i in range(5):
        memory.record(MemoryTurn(conversation_id="c", role="user", content=f"m{i}"))

    recent = memory.recent("c", limit=10)

    assert [turn.content for turn in recent] == ["m3", "m4"]


def test_conversation_memory_persists_and_reloads(tmp_path: Path) -> None:
    path = tmp_path / "mem.jsonl"
    first = ConversationMemory(persist_path=path)
    first.record(MemoryTurn(conversation_id="c", role="user", content="persisted"))

    reloaded = ConversationMemory(persist_path=path)

    recent = reloaded.recent("c", limit=10)
    assert [turn.content for turn in recent] == ["persisted"]


def test_conversation_memory_rejects_invalid_max_turns() -> None:
    with pytest.raises(ValueError):
        ConversationMemory(max_turns_per_conversation=0)


def test_user_preference_memory(tmp_path: Path) -> None:
    pref_path = tmp_path / "user_preferences.json"
    memory = UserPreferenceMemory(persist_path=pref_path)
    memory.set_preference("user_123", "name", "Alice")
    assert memory.get_preferences("user_123") == {"name": "Alice"}

    # Reload
    reloaded = UserPreferenceMemory(persist_path=pref_path)
    assert reloaded.get_preferences("user_123") == {"name": "Alice"}


def test_semantic_memory(tmp_path: Path) -> None:
    sem_path = tmp_path / "semantic_memory.json"
    memory = SemanticMemory(persist_path=sem_path)
    memory.record("conv_1", "I love writing Python code.")
    memory.record("conv_1", "Rust is a compiled systems programming language.")

    # Match Python query
    results = memory.search("conv_1", "python coding")
    assert len(results) == 1
    assert "Python" in results[0]

    # Match Rust query
    results_rust = memory.search("conv_1", "Rust systems")
    assert len(results_rust) == 1
    assert "Rust" in results_rust[0]

    # Match irrelevant query
    assert memory.search("conv_1", "banana milk") == ()


def test_memory_store_filters_mock_boilerplate_from_semantic() -> None:
    memory = SemanticMemory()
    memory.record("conv_1", "You said: hi\n\nI am running through Directioner's Python LLM facade now.")
    memory.record("conv_1", "I love writing Python code.")

    results = memory.search("conv_1", "python coding")

    assert len(results) == 1
    assert "Python code" in results[0]


@pytest.mark.asyncio
async def test_memory_store_normalizes_mentions_on_record() -> None:
    store = MemoryStore(MemorySettings(persist_path=None))
    store.record_event(
        ConversationEvent(
            kind=ConversationEventKind.CHAT_MESSAGE,
            conversation_id="c1",
            user_id="u1",
            channel_id="c1",
            text="<@1512144742060654612> hi",
        )
    )

    context = await store.retrieve(
        ConversationEvent(
            kind=ConversationEventKind.CHAT_MESSAGE,
            conversation_id="c1",
            user_id="u1",
            channel_id="c1",
            text="hi",
        ),
        ConversationState(conversation_id="c1"),
    )

    assert context.conversation == ("user: hi",)


@pytest.mark.asyncio
async def test_memory_store_retrieves_preferences_and_semantic(tmp_path: Path) -> None:
    persist_path = tmp_path / "conversation.jsonl"
    settings = MemorySettings(enabled=True, persist_path=persist_path)
    store = MemoryStore(settings)

    event1 = _chat_event("c1", "I really prefer Python as my favorite language", user_id="user_abc")
    store.record_event(event1)

    store.set_user_preference("user_abc", "name", "Alice")

    # Retrieve context
    event2 = _chat_event("c1", "What is my favorite programming language?", user_id="user_abc")
    state = ConversationState(conversation_id="c1")
    context = await store.retrieve(event2, state)

    assert context.user_preferences == {"name": "Alice"}
    assert len(context.semantic) == 1
    assert "Python" in context.semantic[0]
