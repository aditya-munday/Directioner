"""Unit tests for IdentityMapper."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from directioner.conversation.identity import IdentityMapper


def test_get_or_create_discord_returns_stable_profile() -> None:
    mapper = IdentityMapper()
    p1 = mapper.get_or_create_discord("123456", "Alice")
    p2 = mapper.get_or_create_discord("123456")
    assert p1 is p2
    assert p1.discord_id == "123456"
    assert p1.display_name == "Alice"


def test_get_or_create_speaker_returns_stable_profile() -> None:
    mapper = IdentityMapper()
    p1 = mapper.get_or_create_speaker("SPEAKER_00")
    p2 = mapper.get_or_create_speaker("SPEAKER_00")
    assert p1 is p2
    assert "SPEAKER_00" in p1.speaker_labels


def test_link_speaker_to_discord_merges_profiles() -> None:
    mapper = IdentityMapper()
    mapper.get_or_create_discord("999", "Bob")
    profile = mapper.link_speaker_to_discord("SPEAKER_01", "999")
    assert profile.discord_id == "999"
    assert "SPEAKER_01" in profile.speaker_labels
    # Both lookups should return the same object
    assert mapper.resolve("SPEAKER_01") is mapper.resolve("999")


def test_display_name_falls_back_to_id() -> None:
    mapper = IdentityMapper()
    assert mapper.display_name("unknown_id") == "unknown_id"
    mapper.get_or_create_discord("42", "Carol")
    assert mapper.display_name("42") == "Carol"


def test_persistence_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "identities.json"
        mapper = IdentityMapper(persist_path=path)
        mapper.get_or_create_discord("7", "Dave")
        mapper.get_or_create_speaker("SPEAKER_02")
        mapper.link_speaker_to_discord("SPEAKER_02", "7")

        # Reload from disk
        mapper2 = IdentityMapper(persist_path=path)
        profile = mapper2.resolve("7")
        assert profile is not None
        assert profile.display_name == "Dave"
        assert "SPEAKER_02" in profile.speaker_labels
