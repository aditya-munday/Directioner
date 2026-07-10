"""Unit tests for weather tool."""

from __future__ import annotations

import pytest

from directioner.tools.weather import weather_tool, _weather_code_to_description


@pytest.mark.asyncio
async def test_weather_tool_requires_location() -> None:
    tool = weather_tool()
    with pytest.raises(ValueError, match="location is required"):
        await tool.handler({})


@pytest.mark.asyncio
async def test_weather_tool_with_custom_provider() -> None:
    async def mock_forecast(location: str, unit: str):
        return {
            "location": location,
            "temperature": 25.0,
            "unit": unit,
            "source": "mock",
        }

    tool = weather_tool(get_forecast=mock_forecast)
    result = await tool.handler({"location": "Test City", "unit": "celsius"})
    
    assert result["location"] == "Test City"
    assert result["temperature"] == 25.0
    assert result["unit"] == "celsius"
    assert result["source"] == "mock"


@pytest.mark.asyncio
async def test_weather_tool_default_unit() -> None:
    """Test that default unit is celsius."""
    async def mock_forecast(location: str, unit: str):
        return {"location": location, "unit": unit}

    tool = weather_tool(get_forecast=mock_forecast)
    result = await tool.handler({"location": "NYC"})
    
    assert result["unit"] == "celsius"


def test_weather_code_descriptions() -> None:
    assert _weather_code_to_description(0) == "Clear sky"
    assert _weather_code_to_description(1) == "Mainly clear"
    assert _weather_code_to_description(3) == "Overcast"
    assert _weather_code_to_description(61) == "Slight rain"
    assert _weather_code_to_description(95) == "Thunderstorm"
    assert _weather_code_to_description(999) == "Unknown"


def test_weather_tool_spec() -> None:
    tool = weather_tool()
    assert tool.name == "get_weather"
    assert "location" in tool.description
    assert "unit" in tool.description
