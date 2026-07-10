"""Built-in tools for managing user preferences."""

from __future__ import annotations

from typing import Any
from .registry import ToolSpec
from directioner.memory.store import MemoryStore


def set_user_preference_tool(store: MemoryStore, user_id: str) -> ToolSpec:
    """Return a tool that sets a preference for the current user."""

    async def _handle(arguments: dict[str, Any]) -> dict[str, Any]:
        key = arguments.get("key")
        value = arguments.get("value")
        if not key or not value:
            raise ValueError("Both 'key' and 'value' arguments are required")

        # Save to memory store
        store.set_user_preference(user_id, str(key), str(value))
        return {
            "status": "success",
            "key": key,
            "value": value,
        }

    return ToolSpec(
        name="set_user_preference",
        description=(
            "Set or update a preference, fact, or detail about the current user "
            "to remember for future sessions (e.g. name, programming language, interests). "
            "Arguments: key, value."
        ),
        handler=_handle,
    )


def delete_user_preference_tool(store: MemoryStore, user_id: str) -> ToolSpec:
    """Return a tool that deletes a preference for the current user."""

    async def _handle(arguments: dict[str, Any]) -> dict[str, Any]:
        key = arguments.get("key")
        if not key:
            raise ValueError("The 'key' argument is required")

        # Delete from memory store
        store.delete_user_preference(user_id, str(key))
        return {
            "status": "success",
            "key": key,
        }

    return ToolSpec(
        name="delete_user_preference",
        description=(
            "Delete a previously set preference, fact, or detail about the current user. "
            "Arguments: key."
        ),
        handler=_handle,
    )
