"""Identity mapping: Discord user IDs and diarization speaker labels → user profiles."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class UserProfile:
    user_id: str                        # canonical ID (Discord snowflake or generated)
    display_name: str = ""
    discord_id: str | None = None       # Discord snowflake string
    speaker_labels: list[str] = field(default_factory=list)  # diarization labels

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "discord_id": self.discord_id,
            "speaker_labels": self.speaker_labels,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserProfile":
        return cls(
            user_id=str(data["user_id"]),
            display_name=str(data.get("display_name", "")),
            discord_id=data.get("discord_id"),
            speaker_labels=list(data.get("speaker_labels", [])),
        )


class IdentityMapper:
    """Maps Discord user IDs and pyannote speaker labels to UserProfiles.

    Persists to a JSON file when a path is provided.  Thread-safe for
    single-threaded asyncio use.
    """

    def __init__(self, persist_path: str | Path | None = None) -> None:
        self._persist_path = Path(persist_path) if persist_path else None
        # discord_id -> UserProfile
        self._by_discord: dict[str, UserProfile] = {}
        # speaker_label -> UserProfile
        self._by_speaker: dict[str, UserProfile] = {}
        if self._persist_path:
            self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create_discord(self, discord_id: str, display_name: str = "") -> UserProfile:
        """Return the profile for a Discord user, creating one if needed."""
        discord_id = str(discord_id)
        if discord_id in self._by_discord:
            profile = self._by_discord[discord_id]
            if display_name and not profile.display_name:
                profile.display_name = display_name
                self._save()
            return profile
        profile = UserProfile(
            user_id=discord_id,
            display_name=display_name,
            discord_id=discord_id,
        )
        self._by_discord[discord_id] = profile
        self._save()
        return profile

    def get_or_create_speaker(self, speaker_label: str) -> UserProfile:
        """Return the profile for a diarization speaker label."""
        if speaker_label in self._by_speaker:
            return self._by_speaker[speaker_label]
        profile = UserProfile(
            user_id=speaker_label,
            speaker_labels=[speaker_label],
        )
        self._by_speaker[speaker_label] = profile
        self._save()
        return profile

    def link_speaker_to_discord(self, speaker_label: str, discord_id: str) -> UserProfile:
        """Associate a diarization speaker label with a known Discord user."""
        discord_id = str(discord_id)
        profile = self._by_discord.get(discord_id) or self.get_or_create_discord(discord_id)
        if speaker_label not in profile.speaker_labels:
            profile.speaker_labels.append(speaker_label)
        self._by_speaker[speaker_label] = profile
        self._save()
        logger.info("identity.linked speaker=%s discord=%s", speaker_label, discord_id)
        return profile

    def resolve(self, user_id: str) -> UserProfile | None:
        """Look up a profile by any known ID (Discord ID or speaker label)."""
        return self._by_discord.get(user_id) or self._by_speaker.get(user_id)

    def display_name(self, user_id: str) -> str:
        """Return a human-readable name for any user_id, falling back to the ID."""
        profile = self.resolve(user_id)
        if profile and profile.display_name:
            return profile.display_name
        return user_id

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        if not self._persist_path:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            # Deduplicate: one entry per unique user_id
            seen: dict[str, UserProfile] = {}
            for p in list(self._by_discord.values()) + list(self._by_speaker.values()):
                seen[p.user_id] = p
            with self._persist_path.open("w", encoding="utf-8") as fh:
                json.dump([p.to_dict() for p in seen.values()], fh, indent=2)
        except Exception as exc:
            logger.debug("identity.save_error err=%s", exc)

    def _load(self) -> None:
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            with self._persist_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            for item in data:
                profile = UserProfile.from_dict(item)
                if profile.discord_id:
                    self._by_discord[profile.discord_id] = profile
                for label in profile.speaker_labels:
                    self._by_speaker[label] = profile
        except Exception as exc:
            logger.debug("identity.load_error err=%s", exc)
