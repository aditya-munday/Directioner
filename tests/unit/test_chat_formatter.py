"""Unit tests for ChatOutputFormatter."""

from __future__ import annotations

import pytest

from directioner.discord.chat_formatter import (
    ChatOutputFormatter,
    EmbedDetector,
    MarkdownFormatter,
    MessageSplitter,
)


def test_markdown_formatter_strips_html() -> None:
    md = MarkdownFormatter()
    assert md.format("<b>bold</b> text") == "bold text"
    assert md.format("<div>content</div>") == "content"


def test_markdown_formatter_normalises_blank_lines() -> None:
    md = MarkdownFormatter()
    text = "line1\n\n\n\nline2"
    assert md.format(text) == "line1\n\nline2"


def test_markdown_formatter_fixes_unclosed_code_fences() -> None:
    md = MarkdownFormatter()
    text = "```\ncode block"
    assert md.format(text) == "```\ncode block\n```"


def test_embed_detector_detects_url_only_response() -> None:
    embed = EmbedDetector()
    assert embed.detect_embed_url("https://example.com") == "https://example.com"
    assert embed.detect_embed_url("https://example.com\n") == "https://example.com"
    assert embed.detect_embed_url("Check this: https://example.com") is None


def test_embed_detector_detects_code_only() -> None:
    embed = EmbedDetector()
    assert embed.is_code_only("```python\nprint('hi')\n```") is True
    assert embed.is_code_only("some text\n```code```") is False


def test_message_splitter_short_text() -> None:
    splitter = MessageSplitter()
    assert splitter.split("short") == ["short"]


def test_message_splitter_exact_limit() -> None:
    splitter = MessageSplitter()
    text = "a" * 1900
    assert splitter.split(text) == [text]


def test_message_splitter_over_limit_splits_at_paragraph() -> None:
    splitter = MessageSplitter()
    text = "First paragraph.\n\nSecond paragraph with more text."
    parts = splitter.split(text, max_chars=30)
    assert len(parts) >= 2


def test_chat_formatter_formats_and_splits() -> None:
    fmt = ChatOutputFormatter()
    messages = fmt.format("Hello **world**. How are you?")
    assert len(messages) == 1
    # MarkdownFormatter strips HTML but not markdown - that's intentional
    assert "**" in messages[0].content


def test_chat_formatter_detects_embed_url() -> None:
    fmt = ChatOutputFormatter()
    messages = fmt.format("https://example.com/image.png")
    assert len(messages) == 1
    assert messages[0].embed_url == "https://example.com/image.png"


def test_chat_formatter_detects_code_only() -> None:
    fmt = ChatOutputFormatter()
    messages = fmt.format("```python\nprint('hi')\n```")
    assert len(messages) == 1
    assert messages[0].is_code_only is True


def test_chat_formatter_reply_to_message_id() -> None:
    fmt = ChatOutputFormatter()
    messages = fmt.format("Hello", reply_to_message_id="12345")
    assert len(messages) == 1
    assert messages[0].reply_to_message_id == "12345"


def test_chat_formatter_empty_text_returns_empty_list() -> None:
    fmt = ChatOutputFormatter()
    assert fmt.format("") == []
    assert fmt.format("   ") == []
