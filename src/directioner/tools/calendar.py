"""Calendar tool with provider-agnostic design."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from directioner.tools.registry import ToolSpec

logger = logging.getLogger(__name__)


def calendar_tool(
    list_events: Any = None,
    create_event: Any = None,
) -> ToolSpec:
    """Calendar tool for listing and creating events.
    
    Args:
        list_events: Callable that takes start_date, end_date, returns list of events.
                    If None, uses default mock implementation.
        create_event: Callable that takes event details, returns created event.
                     If None, uses default mock implementation.
    """

    async def _handle(arguments: dict[str, Any]) -> dict[str, Any]:
        action = arguments.get("action", "list")
        
        if action == "list":
            return await _handle_list(arguments, list_events)
        elif action == "create":
            return await _handle_create(arguments, create_event)
        elif action == "delete":
            return await _handle_delete(arguments)
        else:
            return {"error": f"Unknown action: {action}. Use list, create, or delete."}

    return ToolSpec(
        name="calendar",
        description=(
            "Manage calendar events. Actions: list (default), create, delete. "
            "List args: start_date (ISO), end_date (ISO). "
            "Create args: title, start_time (ISO), end_time (ISO), description, location. "
            "Delete args: event_id."
        ),
        handler=_handle,
    )


async def _handle_list(arguments: dict[str, Any], list_events: Any) -> dict[str, Any]:
    """Handle list events action."""
    start_date = arguments.get("start_date")
    end_date = arguments.get("end_date")
    
    if list_events is not None:
        try:
            events = await list_events(start_date, end_date)
            return {"events": events}
        except Exception as exc:
            logger.error("calendar.list_error err=%s", exc)
            return {"error": f"Failed to list events: {exc}"}
    
    # Default: mock implementation
    return _mock_list_events(start_date, end_date)


async def _handle_create(arguments: dict[str, Any], create_event: Any) -> dict[str, Any]:
    """Handle create event action."""
    title = arguments.get("title")
    start_time = arguments.get("start_time")
    end_time = arguments.get("end_time")
    
    if not title:
        return {"error": "title is required for create action"}
    if not start_time:
        return {"error": "start_time is required for create action"}
    if not end_time:
        return {"error": "end_time is required for create action"}
    
    if create_event is not None:
        try:
            event = await create_event(
                title=title,
                start_time=start_time,
                end_time=end_time,
                description=arguments.get("description"),
                location=arguments.get("location"),
            )
            return {"event": event, "created": True}
        except Exception as exc:
            logger.error("calendar.create_error err=%s", exc)
            return {"error": f"Failed to create event: {exc}"}
    
    # Default: mock implementation
    return _mock_create_event(
        title=title,
        start_time=start_time,
        end_time=end_time,
        description=arguments.get("description"),
        location=arguments.get("location"),
    )


async def _handle_delete(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle delete event action."""
    event_id = arguments.get("event_id")
    if not event_id:
        return {"error": "event_id is required for delete action"}
    
    # Default: mock implementation
    return {
        "deleted": True,
        "event_id": event_id,
        "message": f"Event {event_id} deleted (mock implementation)",
    }


def _mock_list_events(start_date: str | None, end_date: str | None) -> dict[str, Any]:
    """Mock implementation for listing events."""
    now = datetime.now(timezone.utc)
    
    if not start_date:
        start = now
    else:
        start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
    
    if not end_date:
        end = start + timedelta(days=7)
    else:
        end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
    
    # Generate some mock events
    events = [
        {
            "id": "mock-1",
            "title": "Team Meeting",
            "start_time": (start + timedelta(hours=2)).isoformat(),
            "end_time": (start + timedelta(hours=3)).isoformat(),
            "description": "Weekly team sync",
            "location": "Conference Room A",
        },
        {
            "id": "mock-2",
            "title": "Project Review",
            "start_time": (start + timedelta(days=1, hours=4)).isoformat(),
            "end_time": (start + timedelta(days=1, hours=5)).isoformat(),
            "description": "Sprint review meeting",
            "location": None,
        },
    ]
    
    return {
        "events": events,
        "source": "mock",
        "range": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
    }


def _mock_create_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    """Mock implementation for creating an event."""
    import uuid
    return {
        "id": f"mock-{uuid.uuid4().hex[:8]}",
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "description": description,
        "location": location,
        "created": True,
        "source": "mock",
    }
