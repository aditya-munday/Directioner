"""Discord chat output formatting pipeline.

Stages:
  raw LLM text
    → MarkdownFormatter   (Discord-flavoured markdown, code fence normalisation)
    → EmbedDetector       (detect URL/image/code-only responses → embed hint)
    → MessageSplitter     (split at sentence/paragraph boundaries ≤ 2000 chars)
    → FormattedMessage    (ready to send)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class FormattedMessage:
    content: str
    reply_to_message_id: str | None = None
    embed_url: str | None = None          # single URL to unfurl as embed
    is_code_only: bool = False            # entire response is a code block


# ── Constants ─────────────────────────────────────────────────────────────────

_DISCORD_MAX_CHARS = 2000
_SAFE_MAX_CHARS = 1900          # leave headroom for reply prefix

_URL_RE = re.compile(r"https?://\S+")
_CODE_FENCE_RE = re.compile(r"^```[\s\S]*?```$", re.MULTILINE)
_MENTION_STRIP_RE = re.compile(r"<@!?\d+>|<@&\d+>|<#\d+>")

# Sentence-boundary split characters (in priority order)
_SPLIT_CHARS = ("\n\n", "\n", ". ", "! ", "? ", ", ", " ")


# ── Markdown formatter ────────────────────────────────────────────────────────

class MarkdownFormatter:
    """Normalise LLM output to Discord-flavoured markdown.

    - Preserves existing ``` code fences.
    - Converts bare ` backtick ` inline code.
    - Strips HTML tags that sometimes leak from LLMs.
    - Normalises excessive blank lines to at most two.
    """

    def format(self, text: str) -> str:
        text = self._strip_html(text)
        text = self._normalise_blank_lines(text)
        text = self._fix_code_fences(text)
        return text.strip()

    @staticmethod
    def _strip_html(text: str) -> str:
        return re.sub(r"<[^>]+>", "", text)

    @staticmethod
    def _normalise_blank_lines(text: str) -> str:
        return re.sub(r"\n{3,}", "\n\n", text)

    @staticmethod
    def _fix_code_fences(text: str) -> str:
        # Ensure unclosed fences are closed
        count = text.count("```")
        if count % 2 != 0:
            text = text.rstrip() + "\n```"
        return text


# ── Embed detector ────────────────────────────────────────────────────────────

class EmbedDetector:
    """Detect whether the response should be sent as an embed or has a URL to unfurl."""

    def detect_embed_url(self, text: str) -> str | None:
        """Return the first URL if the response is *only* a URL (possibly with whitespace)."""
        stripped = text.strip()
        urls = _URL_RE.findall(stripped)
        if urls and stripped == urls[0]:
            return urls[0]
        return None

    def is_code_only(self, text: str) -> bool:
        stripped = text.strip()
        return bool(_CODE_FENCE_RE.match(stripped)) and stripped.count("```") == 2


# ── Message splitter ──────────────────────────────────────────────────────────

class MessageSplitter:
    """Split a long formatted string into ≤ _SAFE_MAX_CHARS Discord messages.

    Splits at paragraph → sentence → word boundaries in that order so words
    and code fences are never broken mid-token.
    """

    def split(self, text: str, max_chars: int = _SAFE_MAX_CHARS) -> list[str]:
        if len(text) <= max_chars:
            return [text] if text.strip() else []

        parts: list[str] = []
        remaining = text
        while len(remaining) > max_chars:
            split_at = self._find_split(remaining, max_chars)
            parts.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()
        if remaining.strip():
            parts.append(remaining.strip())
        return parts

    @staticmethod
    def _find_split(text: str, max_chars: int) -> int:
        window = text[:max_chars]
        for sep in _SPLIT_CHARS:
            idx = window.rfind(sep)
            if idx > max_chars // 2:          # only split in the second half
                return idx + len(sep)
        return max_chars                       # hard split as last resort


# ── Full pipeline ─────────────────────────────────────────────────────────────

class ChatOutputFormatter:
    """Run the full LLM text → FormattedMessage list pipeline."""

    def __init__(self) -> None:
        self._md = MarkdownFormatter()
        self._embed = EmbedDetector()
        self._splitter = MessageSplitter()

    def format(
        self,
        text: str,
        reply_to_message_id: str | None = None,
    ) -> list[FormattedMessage]:
        formatted = self._md.format(text)
        if not formatted:
            return []

        embed_url = self._embed.detect_embed_url(formatted)
        code_only = self._embed.is_code_only(formatted)

        parts = self._splitter.split(formatted)
        if not parts:
            return []

        messages: list[FormattedMessage] = []
        for i, part in enumerate(parts):
            messages.append(
                FormattedMessage(
                    content=part,
                    reply_to_message_id=reply_to_message_id if i == 0 else None,
                    embed_url=embed_url if i == 0 else None,
                    is_code_only=code_only if i == 0 else False,
                )
            )
        return messages
