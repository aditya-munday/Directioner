"""Unit tests for calendar tool."""

from __future__ import annotations

import pytest

from directioner.tools.calendar import calendar_tool, _mock_list_events, _mock_create_event


@pytest.mark.asyncio
async def test_calendar_list_default() -> None:
    tool = calendar_tool()
    result = await tool.handler({"action": "list"})
    
    assert "events" in result
    assert "source" in result
    assert result["source"] == "mock"
    assert len(result["events"]) == 2  # Mock has 2 events


@pytest.mark.asyncio
async def test_calendar_list_with_custom_provider() -> None:
    async def mock_list(start, end):
        return [{"id": "custom-1", "title": "Custom Event"}]

    tool = calendar_tool(list_events=mock_list)
    result = await tool.handler({"action": "list"})
    
    assert result["events"][0]["title"] == "Custom Event"


@pytest.mark.asyncio
async def test_calendar_create_requires_title() -> None:
    tool = calendar_tool()
    result = await tool.handler({"action": "create", "start_time": "2024-01-01T10:00", "end_time": "2024-01-01T11:00"})
    
    assert "error" in result
    assert "title" in result["error"]


@pytest.mark.asyncio
async def test_calendar_create_requires_times() -> None:
    tool = calendar_tool()
    result = await tool.handler({"action": "create", "title": "Test Event"})
    
    assert "error" in result


@pytest.mark.asyncio
async def test_calendar_create_default() -> None:
    tool = calendar_tool()
    result = await tool.handler({
        "action": "create",
        "title": "Test Meeting",
        "start_time": "2024-01-01T10:00:00Z",
        "end_time": "2024-01-01T11:00:00Z",
        "description": "A test meeting",
        "location": "Room 101",
    })
    
    assert result["created"] is True
    assert result["title"] == "Test Meeting"
    assert result["source"] == "mock"
    assert "id" in result


@pytest.mark.asyncio
async def test_calendar_create_with_custom_provider() -> None:
    async def mock_create(**kwargs):
        return {"id": "custom-123", **kwargs}

    tool = calendar_tool(create_event=mock_create)
    result = await tool.handler({
        "action": "create",
        "title": "Custom Event",
        "start_time": "2024-01-01T10:00",
        "end_time": "2024-01-01T11:00",
    })
    
    # The handler wraps custom provider result in "event" key
    assert result["event"]["id"] == "custom-123"
    assert result["created"] is True


@pytest.mark.asyncio
async def test_calendar_delete_requires_event_id() -> None:
    tool = calendar_tool()
    result = await tool.handler({"action": "delete"})
    
    assert "error" in result
    assert "event_id" in result["error"]


@pytest.mark.asyncio
async def test_calendar_delete_default() -> None:
    tool = calendar_tool()
    result = await tool.handler({"action": "delete", "event_id": "test-123"})
    
    assert result["deleted"] is True
    assert result["event_id"] == "test-123"


@pytest.mark.asyncio
async def test_calendar_unknown_action() -> None:
    tool = calendar_tool()
    result = await tool.handler({"action": "unknown"})
    
    assert "error" in result
    assert "Unknown action" in result["error"]


def test_calendar_tool_spec() -> None:
    tool = calendar_tool()
    assert tool.name == "calendar"
    assert "list" in tool.description
    assert "create" in tool.description
    assert "delete" in tool.description


def test_mock_list_events() -> None:
    result = _mock_list_events("2024-01-01", "2024-01-07")
    assert len(result["events"]) == 2
    assert result["source"] == "mock"


def test_mock_create_event() -> None:
    result = _mock_create_event(
        title="Test",
        start_time="2024-01-01T10:00",
        end_time="2024-01-01T11:00",
        description="A test",
        location="Test Location",
    )
    assert result["title"] == "Test"
    assert result["created"] is True
    assert result["source"] == "mock"
