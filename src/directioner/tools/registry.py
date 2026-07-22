"""Tool registry with input validation and error handling."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

LOGGER = logging.getLogger(__name__)

# Input validation constants
MAX_INPUT_LENGTH = 10000
MAX_STRING_ARG_LENGTH = 2000
MAX_ARRAY_ITEMS = 100
MAX_OBJECT_KEYS = 50

# Dangerous patterns for path traversal prevention
DANGEROUS_PATH_PATTERNS = [
    r"\.\.",  # Path traversal
    r"^/",    # Absolute paths
    r"^~",    # Home directory
    r"\s",    # Whitespace in paths
]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler


class ToolValidationError(Exception):
    """Raised when tool input validation fails."""
    pass


def sanitize_string(value: Any, max_length: int = MAX_STRING_ARG_LENGTH) -> str:
    """Sanitize and validate string input."""
    if not isinstance(value, str):
        raise ToolValidationError(f"Expected string, got {type(value).__name__}")
    if len(value) > max_length:
        raise ToolValidationError(f"String exceeds max length of {max_length}")
    return value.strip()


def validate_path(path: str) -> str:
    """Validate path input to prevent path traversal attacks."""
    sanitized = sanitize_string(path)
    for pattern in DANGEROUS_PATH_PATTERNS:
        if re.search(pattern, sanitized):
            raise ToolValidationError(f"Invalid path pattern detected: {pattern}")
    return sanitized


def validate_positive_int(value: Any, name: str = "value") -> int:
    """Validate positive integer input."""
    if not isinstance(value, (int, float)):
        raise ToolValidationError(f"{name} must be a number")
    if value < 0:
        raise ToolValidationError(f"{name} must be non-negative")
    if isinstance(value, float) and not value.is_integer():
        raise ToolValidationError(f"{name} must be an integer")
    return int(value)


def validate_dict(obj: Any, max_keys: int = MAX_OBJECT_KEYS) -> dict[str, Any]:
    """Validate dictionary input."""
    if not isinstance(obj, dict):
        raise ToolValidationError(f"Expected dict, got {type(obj).__name__}")
    if len(obj) > max_keys:
        raise ToolValidationError(f"Object exceeds max keys of {max_keys}")
    return obj


def safe_handler_wrapper(handler: ToolHandler, name: str) -> ToolHandler:
    """Wrap a tool handler with input validation and error handling."""
    async def wrapper(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            # Basic input validation
            if not isinstance(arguments, dict):
                raise ToolValidationError("Arguments must be a dictionary")
            
            # Log tool invocation
            LOGGER.debug(
                "tool.invoke %s args=%s",
                name,
                {k: _truncate_for_log(v) for k, v in arguments.items()}
            )
            
            # Execute handler
            result = await handler(arguments)
            
            # Validate output
            if not isinstance(result, dict):
                raise ToolValidationError(f"Tool returned {type(result).__name__}, expected dict")
            
            return result
            
        except ToolValidationError:
            raise
        except Exception as exc:
            LOGGER.exception("tool.error %s: %s", name, exc)
            return {"error": str(exc), "tool": name}
    
    return wrapper


def _truncate_for_log(value: Any, max_len: int = 100) -> str:
    """Truncate value for logging."""
    s = str(value)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        """Register a tool with validation."""
        if not spec.name:
            raise ValueError("Tool name cannot be empty")
        if not re.match(r"^[a-z_][a-z0-9_]*$", spec.name):
            raise ValueError(f"Invalid tool name: {spec.name}. Use lowercase with underscores.")
        if spec.name in self._tools:
            LOGGER.warning("Tool %s already registered, overwriting", spec.name)
        
        # Wrap handler with safety
        safe_handler = safe_handler_wrapper(spec.handler, spec.name)
        self._tools[spec.name] = ToolSpec(
            name=spec.name,
            description=spec.description,
            handler=safe_handler,
        )

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        return self._tools[name]

    def list(self) -> tuple[ToolSpec, ...]:
        return tuple(self._tools.values())

    def __contains__(self, name: str) -> bool:
        return name in self._tools

