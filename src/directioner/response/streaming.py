"""Incremental chat streaming helpers.

The Discord chat gateway (both the native and standalone runtimes) can only
*send* whole messages; it cannot edit a message in place. To still deliver an
LLM response as it is generated, streamed chunks are accumulated in a
:class:`ChatStreamBuffer` and flushed as coalesced segments the moment a natural
boundary (sentence/newline) is reached or a size threshold is exceeded.

This keeps the perceived latency low (the first sentence is posted as soon as it
is ready) while avoiding one Discord message per token.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Discord hard-limits a single message to 2000 characters. Stay comfortably
# below that so a segment always fits in one message.
DEFAULT_HARD_LIMIT = 1900

# Once the buffered text grows past this size we start looking for a boundary to
# flush at, so the user sees partial output quickly.
DEFAULT_FLUSH_THRESHOLD = 280

# Characters that mark a reasonable place to break a message.
_BOUNDARY_CHARS = (".", "!", "?", "\n")


@dataclass(slots=True)
class ChatStreamBuffer:
    """Accumulates streamed text and yields flushable message segments."""

    flush_threshold: int = DEFAULT_FLUSH_THRESHOLD
    hard_limit: int = DEFAULT_HARD_LIMIT
    _buffer: str = field(default="", init=False)

    def add(self, chunk: str) -> list[str]:
        """Append ``chunk`` and return any segments that are ready to send."""

        if chunk:
            self._buffer += chunk
        return self._drain_ready()

    def drain(self) -> list[str]:
        """Return every remaining non-empty segment and clear the buffer."""

        segments: list[str] = []
        while len(self._buffer) > self.hard_limit:
            segments.append(self._buffer[: self.hard_limit])
            self._buffer = self._buffer[self.hard_limit :]
        tail = self._buffer.strip()
        if tail:
            segments.append(tail)
        self._buffer = ""
        return segments

    def _drain_ready(self) -> list[str]:
        segments: list[str] = []
        while True:
            split_at = self._next_split()
            if split_at is None:
                break
            segment = self._buffer[:split_at].strip()
            self._buffer = self._buffer[split_at:]
            if segment:
                segments.append(segment)
        return segments

    def _next_split(self) -> int | None:
        # Always split when the buffer would overflow a single Discord message.
        if len(self._buffer) >= self.hard_limit:
            return self.hard_limit

        if len(self._buffer) < self.flush_threshold:
            return None

        boundary = max(self._buffer.rfind(char) for char in _BOUNDARY_CHARS)
        if boundary == -1:
            # No natural boundary yet; wait for more text unless we are close to
            # the hard limit, in which case the overflow branch above handles it.
            return None
        return boundary + 1
