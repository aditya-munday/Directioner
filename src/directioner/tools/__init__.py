"""Tool registry and built-in tools."""

from __future__ import annotations

import os
from pathlib import Path

from .calculator import CalculatorError, calculator_tool, evaluate
from .filesystem import list_directory_tool, read_file_tool
from .persona import (
    Persona,
    PersonaRegistry,
    get_persona_registry,
    list_personas_tool,
    switch_persona_tool,
)
from .registry import ToolHandler, ToolRegistry, ToolSpec
from .user_preferences import set_user_preference_tool, delete_user_preference_tool
from .web_search import WebSearchToolError, web_search_tool

__all__ = [
    "CalculatorError",
    "WebSearchToolError",
    "ToolHandler",
    "ToolRegistry",
    "ToolSpec",
    "build_default_registry",
    "calculator_tool",
    "evaluate",
    "list_directory_tool",
    "read_file_tool",
    "register_builtin_tools",
    "set_user_preference_tool",
    "delete_user_preference_tool",
    "web_search_tool",
    "Persona",
    "PersonaRegistry",
    "get_persona_registry",
    "switch_persona_tool",
    "list_personas_tool",
]


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Register all built-in tools into ``registry``."""

    registry.register(calculator_tool())
    registry.register(web_search_tool())
    tool_base = Path(os.getenv("DIRECTIONER_TOOL_BASE_DIR") or ".").resolve()
    registry.register(read_file_tool(tool_base))
    registry.register(list_directory_tool(tool_base))
    # Register persona tools
    registry.register(switch_persona_tool())
    registry.register(list_personas_tool())


def build_default_registry() -> ToolRegistry:
    """Create a :class:`ToolRegistry` pre-populated with built-in tools."""

    registry = ToolRegistry()
    register_builtin_tools(registry)
    return registry
