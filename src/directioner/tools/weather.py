"""Weather tool with provider-agnostic design."""

from __future__ import annotations

import logging
from typing import Any

from directioner.tools.registry import ToolSpec

logger = logging.getLogger(__name__)


def weather_tool(get_forecast: Any = None) -> ToolSpec:
    """Weather forecast tool.
    
    Args:
        get_forecast: Callable that takes location string and returns forecast dict.
                      If None, uses default Open-Meteo API (free, no API key required).
    """

    async def _handle(arguments: dict[str, Any]) -> dict[str, Any]:
        location = arguments.get("location", "")
        if not location:
            raise ValueError("location is required")
        
        unit = arguments.get("unit", "celsius").lower()
        
        if get_forecast is not None:
            return await get_forecast(location, unit)
        
        # Default: Open-Meteo API (free, no API key required)
        try:
            return await _fetch_open_meteo(location, unit)
        except Exception as exc:
            logger.error("weather.fetch_error location=%s err=%s", location, exc)
            return {"error": f"Failed to fetch weather: {exc}"}

    return ToolSpec(
        name="get_weather",
        description="Get current weather and forecast for a location. Args: location (city name), unit (celsius/fahrenheit).",
        handler=_handle,
    )


async def _fetch_open_meteo(location: str, unit: str) -> dict[str, Any]:
    """Fetch weather from Open-Meteo API (free, no API key)."""
    import urllib.request
    import json
    
    # Geocode location first
    geocode_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.request.quote(location)}&count=1"
    
    with urllib.request.urlopen(geocode_url, timeout=10) as resp:
        geocode_data = json.loads(resp.read().decode())
    
    if not geocode_data.get("results"):
        return {"error": f"Location not found: {location}"}
    
    geo = geocode_data["results"][0]
    lat, lon = geo["latitude"], geo["longitude"]
    city_name = geo.get("name", location)
    country = geo.get("country", "")
    
    # Get weather
    temp_unit = "celsius" if unit in ("celsius", "c") else "fahrenheit"
    weather_url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        f"&temperature_unit={temp_unit}"
    )
    
    with urllib.request.urlopen(weather_url, timeout=10) as resp:
        weather_data = json.loads(resp.read().decode())
    
    current = weather_data.get("current", {})
    
    return {
        "location": f"{city_name}, {country}" if country else city_name,
        "temperature": current.get("temperature_2m"),
        "unit": temp_unit,
        "humidity": current.get("relative_humidity_2m"),
        "weather_code": current.get("weather_code"),
        "weather_description": _weather_code_to_description(current.get("weather_code", 0)),
        "wind_speed": current.get("wind_speed_10m"),
        "source": "Open-Meteo",
    }


def _weather_code_to_description(code: int) -> str:
    """Convert WMO weather code to description."""
    descriptions = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return descriptions.get(code, "Unknown")
