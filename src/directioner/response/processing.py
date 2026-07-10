"""Response shaping for voice and chat output."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Split after sentence-ending punctuation followed by whitespace or end-of-string.
_SENTENCE_END = re.compile(r'(?<=[.!?])\s+')
# Clause boundaries for long sentences (comma/semicolon/colon + space)
_CLAUSE_BREAK = re.compile(r'(?<=[,;:])\s+')

_DEFAULT_MAX_CHUNK_CHARS = 200
_DEFAULT_MIN_CHUNK_CHARS = 20


@dataclass(frozen=True, slots=True)
class ResponseChunk:
    text: str
    emotion: str | None = None
    speaking_style: str | None = None
    pause_after_ms: int = 0


class ResponseProcessor:
    """Splits LLM text into natural spoken chunks for streaming TTS.

    Chunks are split at sentence boundaries first, then clause boundaries
    if a sentence is still too long.  Short fragments are merged with the
    next chunk to avoid choppy synthesis.
    """

    def __init__(
        self,
        max_chunk_chars: int = _DEFAULT_MAX_CHUNK_CHARS,
        min_chunk_chars: int = _DEFAULT_MIN_CHUNK_CHARS,
    ) -> None:
        self._max = max_chunk_chars
        self._min = min_chunk_chars

    def chunk_for_tts(self, text: str) -> tuple[ResponseChunk, ...]:
        cleaned = _strip_markdown(text.strip())
        if not cleaned:
            return ()

        sentences = _SENTENCE_END.split(cleaned)
        fragments: list[str] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= self._max:
                fragments.append(sentence)
            else:
                # Split long sentence at clause boundaries
                clauses = _CLAUSE_BREAK.split(sentence)
                buf = ""
                for clause in clauses:
                    clause = clause.strip()
                    if not clause:
                        continue
                    candidate = (buf + " " + clause).strip() if buf else clause
                    if len(candidate) > self._max and buf:
                        fragments.append(buf)
                        buf = clause
                    else:
                        buf = candidate
                if buf:
                    fragments.append(buf)

        # Merge short trailing fragments into the previous one
        merged: list[str] = []
        for frag in fragments:
            if merged and len(frag) < self._min:
                merged[-1] = merged[-1].rstrip() + " " + frag
            else:
                merged.append(frag)

        return tuple(
            ResponseChunk(
                text=frag.strip(),
                pause_after_ms=_pause_after(frag),
            )
            for frag in merged
            if frag.strip()
        )


def _pause_after(text: str) -> int:
    """Return a post-chunk pause in ms based on the trailing punctuation."""
    t = text.rstrip()
    if not t:
        return 0
    if t[-1] in ".!?":
        return 300
    if t[-1] in ",;:":
        return 100
    return 0


def _strip_markdown(text: str) -> str:
    """Remove common markdown that sounds bad when spoken aloud."""
    # Bold/italic
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}(.*?)_{1,3}', r'\1', text)
    # Inline code
    text = re.sub(r'`[^`]*`', '', text)
    # Code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Bullet points — replace with a pause marker
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    # URLs
    text = re.sub(r'https?://\S+', 'a link', text)
    # Collapse whitespace
    return ' '.join(text.split())
