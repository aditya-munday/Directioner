"""Unit tests for embedding store."""

from __future__ import annotations

import pytest

from directioner.memory.embedding_store import (
    EmbeddingEntry,
    SemanticMemoryWithEmbeddings,
    EMBEDDINGS_AVAILABLE,
)


@pytest.mark.skipif(not EMBEDDINGS_AVAILABLE, reason="sentence-transformers not available")
class TestEmbeddingEntry:
    """Tests for EmbeddingEntry dataclass."""

    def test_create_entry(self) -> None:
        entry = EmbeddingEntry(
            conversation_id="conv-1",
            text="Hello world",
            timestamp=1234567890.0,
        )
        assert entry.conversation_id == "conv-1"
        assert entry.text == "Hello world"
        assert entry.timestamp == 1234567890.0
        assert entry.metadata == {}

    def test_to_dict(self) -> None:
        entry = EmbeddingEntry(
            conversation_id="conv-1",
            text="Test text",
            timestamp=1000.0,
            metadata={"key": "value"},
        )
        data = entry.to_dict()
        assert data["conversation_id"] == "conv-1"
        assert data["text"] == "Test text"
        assert data["timestamp"] == 1000.0
        assert data["metadata"] == {"key": "value"}

    def test_from_dict(self) -> None:
        data = {
            "conversation_id": "conv-2",
            "text": "From dict",
            "timestamp": 2000.0,
            "metadata": {"foo": "bar"},
        }
        entry = EmbeddingEntry.from_dict(data)
        assert entry.conversation_id == "conv-2"
        assert entry.text == "From dict"
        assert entry.timestamp == 2000.0
        assert entry.metadata == {"foo": "bar"}


@pytest.mark.skipif(not EMBEDDINGS_AVAILABLE, reason="sentence-transformers not available")
class TestSemanticMemoryWithEmbeddings:
    """Tests for SemanticMemoryWithEmbeddings."""

    def test_initialization(self, tmp_path: pytest.TempPathFactory) -> None:
        store = SemanticMemoryWithEmbeddings(
            model_name="all-MiniLM-L6-v2",
            persist_path=tmp_path / "test_embeddings.json",
        )
        assert store._model_name == "all-MiniLM-L6-v2"
        assert store._embeddings is None  # Lazy load

    def test_record_entry(self, tmp_path: pytest.TempPathFactory) -> None:
        store = SemanticMemoryWithEmbeddings(
            persist_path=tmp_path / "test.json",
            max_entries=100,
        )
        store.record("conv-1", "Hello there!")
        assert len(store._entries) == 1
        assert store._entries[0].text == "Hello there!"
        # Embeddings should be computed after first record
        assert store._embeddings is not None

    def test_duplicate_consecutive_skipped(self, tmp_path: pytest.TempPathFactory) -> None:
        store = SemanticMemoryWithEmbeddings(persist_path=tmp_path / "test.json")
        store.record("conv-1", "Same text")
        store.record("conv-1", "Same text")
        assert len(store._entries) == 1

    def test_search_returns_relevant(self, tmp_path: pytest.TempPathFactory) -> None:
        store = SemanticMemoryWithEmbeddings(persist_path=tmp_path / "test.json")

        store.record("conv-1", "I love playing video games")
        store.record("conv-1", "The weather is nice today")
        store.record("conv-1", "Gaming on my PC is fun")

        # Search for gaming-related content
        results = store.search("conv-1", "video game", limit=2)
        assert len(results) >= 1
        # The gaming entries should score higher than weather
        gaming_scores = [score for text, score in results if "game" in text.lower()]
        assert len(gaming_scores) >= 1

    def test_search_conversation_scoped(self, tmp_path: pytest.TempPathFactory) -> None:
        store = SemanticMemoryWithEmbeddings(persist_path=tmp_path / "test.json")

        store.record("conv-1", "Project deadline tomorrow")
        store.record("conv-2", "Lunch at noon")

        # Search in conv-1 should not return conv-2 entries
        results = store.search("conv-1", "lunch food eat")
        for text, _ in results:
            assert text != "Lunch at noon"

    def test_clear_conversation(self, tmp_path: pytest.TempPathFactory) -> None:
        store = SemanticMemoryWithEmbeddings(persist_path=tmp_path / "test.json")

        store.record("conv-1", "Entry 1")
        store.record("conv-2", "Entry 2")
        store.record("conv-1", "Entry 3")

        assert len(store._entries) == 3

        store.clear_conversation("conv-1")
        assert len(store._entries) == 1
        assert store._entries[0].conversation_id == "conv-2"

    def test_max_entries_trim(self, tmp_path: pytest.TempPathFactory) -> None:
        store = SemanticMemoryWithEmbeddings(persist_path=tmp_path / "test.json", max_entries=5)

        for i in range(10):
            store.record("conv-1", f"Entry {i}")

        assert len(store._entries) == 5
        assert store._entries[-1].text == "Entry 9"

    def test_stats(self, tmp_path: pytest.TempPathFactory) -> None:
        store = SemanticMemoryWithEmbeddings(persist_path=tmp_path / "test.json")

        store.record("conv-1", "Text 1")
        store.record("conv-1", "Text 2")
        store.record("conv-2", "Text 3")

        stats = store.stats()
        assert stats["total_entries"] == 3
        assert stats["conversations"] == 2
        assert stats["model"] == "all-MiniLM-L6-v2"

    def test_persistence_round_trip(self, tmp_path: pytest.TempPathFactory) -> None:
        persist_path = tmp_path / "test_persist.json"

        # Create and populate first store
        store1 = SemanticMemoryWithEmbeddings(persist_path=persist_path)
        store1.record("conv-1", "Persisted text")

        # Create new store from same path
        store2 = SemanticMemoryWithEmbeddings(persist_path=persist_path)

        assert len(store2._entries) == 1
        assert store2._entries[0].text == "Persisted text"


def test_embeddings_not_available() -> None:
    """Test behavior when embeddings are not available."""
    if EMBEDDINGS_AVAILABLE:
        pytest.skip("Embeddings are available")

    with pytest.raises(ImportError, match="sentence-transformers"):
        SemanticMemoryWithEmbeddings()
