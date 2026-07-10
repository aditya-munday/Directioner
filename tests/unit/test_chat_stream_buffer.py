from __future__ import annotations

from directioner.response.streaming import ChatStreamBuffer


def test_buffer_holds_small_input_until_drain() -> None:
    buffer = ChatStreamBuffer(flush_threshold=280)

    assert buffer.add("hello") == []
    assert buffer.add(" world") == []
    assert buffer.drain() == ["hello world"]


def test_buffer_flushes_at_sentence_boundary_after_threshold() -> None:
    buffer = ChatStreamBuffer(flush_threshold=10)

    flushed: list[str] = []
    flushed += buffer.add("Hello there friend. ")
    flushed += buffer.add("Second part still buffered")

    assert flushed == ["Hello there friend."]
    assert buffer.drain() == ["Second part still buffered"]


def test_buffer_splits_when_exceeding_hard_limit() -> None:
    buffer = ChatStreamBuffer(flush_threshold=1000, hard_limit=5)

    segments = buffer.add("abcdefghij")

    assert segments == ["abcde", "fghij"] or segments == ["abcde"]
    # Remaining content is emitted on drain.
    all_text = "".join(segments) + "".join(buffer.drain())
    assert all_text.replace(" ", "") == "abcdefghij"


def test_buffer_ignores_empty_chunks() -> None:
    buffer = ChatStreamBuffer()

    assert buffer.add("") == []
    assert buffer.drain() == []
