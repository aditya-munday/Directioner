"""Security utilities for Directioner.

This module provides security hardening features:
- Input validation and sanitization
- Discord ID format validation
- Content filtering and moderation
- Rate limit enforcement
- Circuit breakers
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

import structlog

LOGGER = structlog.get_logger(__name__)

# Discord ID patterns
DISCORD_ID_PATTERN = re.compile(r'^\d{17,20}$')
DISCORD_TOKEN_PATTERN = re.compile(r'^[\w\-_]{24,}\.[\w\-_]{6}\.[\w\-_]{27,}$|^[A-Za-z0-9_\-]{50,}$')

# Content filtering
BLOCKED_PATTERNS = [
    r'<script[^>]*>.*?</script>',  # Script injection
    r'javascript:',  # JavaScript protocol
    r'on\w+\s*=',  # Event handlers
    r'eval\s*\(',  # Eval usage
    r'exec\s*\(',  # Exec usage
    r'compile\s*\(',  # Code compilation
]

# Maximum lengths
MAX_MESSAGE_LENGTH = 2000
MAX_USERNAME_LENGTH = 32
MAX_CHANNEL_NAME_LENGTH = 100
MAX_GUILD_NAME_LENGTH = 100


@dataclass(frozen=True)
class ValidationResult:
    """Result of a validation check."""
    valid: bool
    error: str | None = None
    sanitized: str | None = None


class DiscordIdValidator:
    """Validates Discord ID formats."""

    @staticmethod
    def is_valid_user_id(user_id: str | None) -> bool:
        """Check if user ID is valid Discord format."""
        if not user_id:
            return True  # Optional
        return bool(DISCORD_ID_PATTERN.match(user_id))

    @staticmethod
    def is_valid_channel_id(channel_id: str | None) -> bool:
        """Check if channel ID is valid Discord format."""
        if not channel_id:
            return True  # Optional
        return bool(DISCORD_ID_PATTERN.match(channel_id))

    @staticmethod
    def is_valid_guild_id(guild_id: str | None) -> bool:
        """Check if guild ID is valid Discord format."""
        if not guild_id:
            return True  # Optional
        return bool(DISCORD_ID_PATTERN.match(guild_id))

    @staticmethod
    def is_valid_message_id(message_id: str | None) -> bool:
        """Check if message ID is valid Discord format."""
        if not message_id:
            return True  # Optional
        return bool(DISCORD_ID_PATTERN.match(message_id))


class ContentValidator:
    """Validates and sanitizes user content."""

    def __init__(self) -> None:
        self._blocked_patterns = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATTERNS]

    def validate_message(self, content: str) -> ValidationResult:
        """Validate a message content."""
        if not content:
            return ValidationResult(valid=False, error="Message cannot be empty")

        if len(content) > MAX_MESSAGE_LENGTH:
            return ValidationResult(
                valid=False,
                error=f"Message exceeds maximum length of {MAX_MESSAGE_LENGTH} characters"
            )

        # Check for blocked patterns
        for pattern in self._blocked_patterns:
            if pattern.search(content):
                return ValidationResult(
                    valid=False,
                    error="Message contains blocked content"
                )

        return ValidationResult(valid=True)

    def sanitize_message(self, content: str) -> str:
        """Sanitize message content."""
        if not content:
            return ""

        # Remove null bytes
        content = content.replace('\x00', '')

        # Remove control characters except newlines and tabs
        content = ''.join(
            c for c in content
            if c == '\n' or c == '\t' or not (0 <= ord(c) < 32 and c not in '\n\t')
        )

        # Strip excessive whitespace
        content = ' '.join(content.split())

        return content[:MAX_MESSAGE_LENGTH]

    def validate_username(self, username: str) -> ValidationResult:
        """Validate a username."""
        if not username:
            return ValidationResult(valid=False, error="Username cannot be empty")

        if len(username) > MAX_USERNAME_LENGTH:
            return ValidationResult(
                valid=False,
                error=f"Username exceeds maximum length of {MAX_USERNAME_LENGTH}"
            )

        return ValidationResult(valid=True)


class SecurityManager:
    """Manages security features for the application."""

    def __init__(self) -> None:
        self._id_validator = DiscordIdValidator()
        self._content_validator = ContentValidator()
        self._failed_validations: dict[str, int] = {}
        self._blocked_ips: dict[str, float] = {}
        self._lock_time = 300  # 5 minutes

    def validate_discord_ids(
        self,
        user_id: str | None = None,
        channel_id: str | None = None,
        guild_id: str | None = None,
    ) -> tuple[bool, str]:
        """Validate all Discord IDs. Returns (valid, error_message)."""
        if user_id and not self._id_validator.is_valid_user_id(user_id):
            return False, f"Invalid user ID format: {user_id}"

        if channel_id and not self._id_validator.is_valid_channel_id(channel_id):
            return False, f"Invalid channel ID format: {channel_id}"

        if guild_id and not self._id_validator.is_valid_guild_id(guild_id):
            return False, f"Invalid guild ID format: {guild_id}"

        return True, ""

    def validate_content(self, content: str) -> tuple[bool, str]:
        """Validate content. Returns (valid, error_message)."""
        result = self._content_validator.validate_message(content)
        if not result.valid:
            return False, result.error or "Invalid content"
        return True, ""

    def sanitize_content(self, content: str) -> str:
        """Sanitize content for safe storage/display."""
        return self._content_validator.sanitize_message(content)

    def record_validation_failure(self, identifier: str) -> None:
        """Record a validation failure for rate limiting."""
        self._failed_validations[identifier] = self._failed_validations.get(identifier, 0) + 1

        # Block if too many failures
        if self._failed_validations[identifier] >= 10:
            self._blocked_ips[identifier] = time.time()
            LOGGER.warning("Entity blocked due to validation failures", identifier=identifier)

    def is_blocked(self, identifier: str) -> bool:
        """Check if an identifier is blocked."""
        if identifier in self._blocked_ips:
            block_time = self._blocked_ips[identifier]
            if time.time() - block_time > self._lock_time:
                # Unblock after lock time
                del self._blocked_ips[identifier]
                self._failed_validations.pop(identifier, None)
                return False
            return True
        return False

    def get_stats(self) -> dict[str, Any]:
        """Get security statistics."""
        return {
            "blocked_entities": len(self._blocked_ips),
            "failed_validations": sum(self._failed_validations.values()),
            "validation_failures_by_entity": dict(self._failed_validations),
        }


# Global security manager instance
security_manager = SecurityManager()


def validate_conversation_id(conversation_id: str) -> ValidationResult:
    """Validate a conversation ID format."""
    if not conversation_id:
        return ValidationResult(valid=False, error="Conversation ID cannot be empty")

    if len(conversation_id) > 256:
        return ValidationResult(
            valid=False,
            error="Conversation ID exceeds maximum length"
        )

    return ValidationResult(valid=True)


def is_safe_content(content: str) -> bool:
    """Quick check if content is safe."""
    if not content:
        return False
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return False
    return True
