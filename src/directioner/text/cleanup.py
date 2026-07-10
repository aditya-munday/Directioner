"""Text post-processing after STT and chat input."""

from __future__ import annotations

import re

_MENTION_RE = re.compile(r"<@!?\d+>|<@&\d+>|<#\d+>")


def strip_discord_mentions(text: str) -> str:
    """Remove user, role, and channel mention markup from Discord message text."""

    cleaned = _MENTION_RE.sub("", text)
    return " ".join(cleaned.split())


class TextCleanup:
    def normalize(self, text: str) -> str:
        return strip_discord_mentions(" ".join(text.strip().split()))

