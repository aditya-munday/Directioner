"""Embedding-based semantic memory using sentence-transformers.

This module provides SemanticMemoryWithEmbeddings which uses actual
vector embeddings for semantic search instead of simple cosine similarity
on word counts.

Dependencies:
    pip install sentence-transformers numpy

Default model: all-MiniLM-L6-v2 (fast, good quality, ~90MB)
Alternative models can be configured via settings.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy.typing as npt

# Optional imports - will fall back to keyword-based if not available
try:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    EMBEDDINGS_AVAILABLE = True
except ImportError:
    np = None
    SentenceTransformer = None
    EMBEDDINGS_AVAILABLE = False


@dataclass(frozen=True, slots=True)
class EmbeddingEntry:
    """A semantic memory entry with embedding vector."""
    conversation_id: str
    text: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "text": self.text,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmbeddingEntry":
        return cls(
            conversation_id=str(data.get("conversation_id", "")),
            text=str(data.get("text", "")),
            timestamp=float(data.get("timestamp", 0.0)),
            metadata=data.get("metadata", {}),
        )


class SemanticMemoryWithEmbeddings:
    """Semantic memory using sentence-transformers embeddings.

    This class provides:
    - Fast embedding-based semantic search
    - Persistent storage to JSON
    - Conversation-scoped memory
    - Lazy loading of the embedding model
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(
        self,
        model_name: str | None = None,
        persist_path: str | Path | None = None,
        embedding_dim: int = 384,  # all-MiniLM-L6-v2 outputs 384-dim vectors
        max_entries: int = 1000,
    ) -> None:
        if not EMBEDDINGS_AVAILABLE:
            raise ImportError(
                "sentence-transformers and numpy are required for SemanticMemoryWithEmbeddings. "
                "Install with: pip install sentence-transformers numpy"
            )

        self._model_name = model_name or self.DEFAULT_MODEL
        self._persist_path = Path(persist_path) if persist_path else None
        self._embedding_dim = embedding_dim
        self._max_entries = max_entries

        self._model: Any = None  # Lazy loaded
        self._entries: list[EmbeddingEntry] = []
        self._embeddings: "npt.NDArray" | None = None  # Cached embeddings matrix

        if self._persist_path:
            self._load()

    @property
    def model(self) -> Any:
        """Lazy-load the embedding model."""
        if self._model is None:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Loading embedding model: {self._model_name}")
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def record(self, conversation_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        """Record a new entry in semantic memory."""
        cleaned = text.strip()
        if not cleaned:
            return

        # Skip duplicate consecutive entries
        if self._entries and self._entries[-1].text == cleaned:
            return

        entry = EmbeddingEntry(
            conversation_id=conversation_id,
            text=cleaned,
            timestamp=time.time(),
            metadata=metadata or {},
        )

        self._entries.append(entry)

        # Update embeddings cache
        self._update_embeddings()

        # Trim if over limit
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]
            self._update_embeddings()

        self._save()

    def search(
        self,
        conversation_id: str,
        query: str,
        limit: int = 3,
        min_score: float = 0.3,
    ) -> tuple[tuple[str, float], ...]:
        """Search for relevant entries.

        Args:
            conversation_id: Only search within this conversation
            query: Search query text
            limit: Maximum number of results
            min_score: Minimum cosine similarity score (0-1)

        Returns:
            Tuple of (text, score) tuples, sorted by relevance
        """
        if not EMBEDDINGS_AVAILABLE or not self._entries:
            return ()

        # Encode query
        query_embedding = self.model.encode([query], convert_to_numpy=True)[0]

        # Find matching entries for this conversation
        results: list[tuple[float, str]] = []
        for i, entry in enumerate(self._entries):
            if entry.conversation_id != conversation_id:
                continue

            if self._embeddings is None or i >= len(self._embeddings):
                continue

            score = self._cosine_similarity(query_embedding, self._embeddings[i])
            if score >= min_score:
                results.append((score, entry.text))

        # Sort by score descending
        results.sort(key=lambda x: x[0], reverse=True)
        return tuple((text, score) for score, text in results[:limit])

    def _update_embeddings(self) -> None:
        """Recompute embeddings for all entries."""
        if not self._entries or np is None:
            self._embeddings = None
            return

        texts = [e.text for e in self._entries]
        self._embeddings = self.model.encode(texts, convert_to_numpy=True)

    @staticmethod
    def _cosine_similarity(a: "npt.NDArray", b: "npt.NDArray") -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def clear_conversation(self, conversation_id: str) -> None:
        """Clear all semantic memory for a specific conversation."""
        old_len = len(self._entries)
        self._entries = [e for e in self._entries if e.conversation_id != conversation_id]

        if len(self._entries) != old_len:
            self._update_embeddings()
            self._save()

    def _save(self) -> None:
        """Persist entries to JSON file."""
        if self._persist_path is None:
            return

        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "model": self._model_name,
            "embedding_dim": self._embedding_dim,
            "entries": [e.to_dict() for e in self._entries],
        }
        with self._persist_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def _load(self) -> None:
        """Load entries from JSON file."""
        if self._persist_path is None or not self._persist_path.exists():
            return

        try:
            with self._persist_path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            self._model_name = data.get("model", self.DEFAULT_MODEL)
            self._embedding_dim = data.get("embedding_dim", 384)
            self._entries = [
                EmbeddingEntry.from_dict(e) for e in data.get("entries", [])
            ]
            self._update_embeddings()
        except (json.JSONDecodeError, KeyError) as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load semantic memory: {e}")
            self._entries = []
            self._embeddings = None

    def stats(self) -> dict[str, Any]:
        """Get statistics about the semantic memory."""
        return {
            "model": self._model_name,
            "embedding_dim": self._embedding_dim,
            "total_entries": len(self._entries),
            "conversations": len(set(e.conversation_id for e in self._entries)),
            "persist_path": str(self._persist_path) if self._persist_path else None,
        }


def create_semantic_memory_with_embeddings(
    settings: Any | None = None,
) -> SemanticMemoryWithEmbeddings | None:
    """Create a SemanticMemoryWithEmbeddings from settings.

    Args:
        settings: Settings object with memory configuration

    Returns:
        SemanticMemoryWithEmbeddings instance, or None if embeddings not available
    """
    if not EMBEDDINGS_AVAILABLE:
        return None

    if settings is None:
        return SemanticMemoryWithEmbeddings()

    persist_path = getattr(settings, "embedding_persist_path", None)
    model_name = getattr(settings, "embedding_model", SemanticMemoryWithEmbeddings.DEFAULT_MODEL)

    return SemanticMemoryWithEmbeddings(
        model_name=model_name,
        persist_path=persist_path,
    )
