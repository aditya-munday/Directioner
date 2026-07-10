"""Unit tests for persona system."""

from __future__ import annotations

import pytest

from directioner.tools.persona import (
    Persona,
    PersonaRegistry,
    get_persona_registry,
    switch_persona_handler,
    switch_persona_tool,
    list_personas_tool,
)


class TestPersona:
    """Tests for Persona dataclass."""

    def test_create_persona(self) -> None:
        persona = Persona(
            name="test",
            display_name="Test Persona",
            description="A test persona",
            system_prompt="You are a test.",
            icon="🧪",
            aliases=("alias1", "alias2"),
        )
        assert persona.name == "test"
        assert persona.display_name == "Test Persona"
        assert persona.icon == "🧪"
        assert "alias1" in persona.aliases


class TestPersonaRegistry:
    """Tests for PersonaRegistry."""

    def test_register_and_get(self) -> None:
        registry = PersonaRegistry()
        persona = Persona(
            name="test",
            display_name="Test",
            description="Test persona",
            system_prompt="You are a test.",
        )
        registry.register(persona)
        assert registry.get("test") == persona
        assert registry.get("TEST") == persona  # case insensitive

    def test_register_aliases(self) -> None:
        registry = PersonaRegistry()
        persona = Persona(
            name="test",
            display_name="Test",
            description="Test",
            system_prompt="Test",
            aliases=("alias1", "alias2"),
        )
        registry.register(persona)
        assert registry.get("alias1") == persona
        assert registry.get("alias2") == persona

    def test_list_personas(self) -> None:
        registry = PersonaRegistry()
        registry.register(Persona("p1", "P1", "D1", "S1"))
        registry.register(Persona("p2", "P2", "D2", "S2"))
        registry.register(Persona("p3", "P3", "D3", "S3", aliases=("alias3",)))
        
        personas = registry.list_personas()
        assert len(personas) == 3
        names = [p.name for p in personas]
        assert "p1" in names
        assert "p2" in names
        assert "p3" in names

    def test_activate_success(self) -> None:
        registry = PersonaRegistry()
        registry.register(Persona("test", "Test", "Test", "Test"))
        
        success, message = registry.activate("test")
        assert success is True
        assert "Test" in message
        assert registry.current == "test"

    def test_activate_unknown(self) -> None:
        registry = PersonaRegistry()
        registry.register(Persona("test", "Test", "Test", "Test"))
        
        success, message = registry.activate("unknown")
        assert success is False
        assert "Unknown" in message

    def test_active_callback(self) -> None:
        registry = PersonaRegistry()
        registry.register(Persona("test", "Test", "Test", "Test"))
        
        called_with: list[str] = []
        registry.set_active_callback(lambda name: called_with.append(name))
        
        registry.activate("test")
        assert called_with == ["test"]

    def test_get_system_prompt(self) -> None:
        registry = PersonaRegistry()
        registry.register(Persona("test", "Test", "Test", "You are test."))
        registry.activate("test")
        
        assert registry.get_system_prompt() == "You are test."
        assert registry.get_system_prompt("test") == "You are test."

    def test_get_system_prompt_unknown(self) -> None:
        registry = PersonaRegistry()
        registry.register(Persona("test", "Test", "Test", "Test"))
        
        assert registry.get_system_prompt("unknown") == ""


@pytest.mark.asyncio
class TestPersonaTools:
    """Tests for persona tool functions."""

    async def test_switch_persona_handler(self) -> None:
        registry = PersonaRegistry()
        registry.register(Persona("interviewer", "Interviewer", "Interviews", "You interview."))
        
        result = await switch_persona_handler({"persona": "interviewer"})
        assert result["success"] is True
        assert result["persona"] == "interviewer"
        assert "Interviewer" in result["message"]

    async def test_switch_persona_list_all(self) -> None:
        # Note: switch_persona_handler uses global registry which has default personas
        result = await switch_persona_handler({})
        assert result["success"] is True
        assert "Available Personas" in result["message"]
        assert "default" in result["personas"]
        assert len(result["personas"]) >= 2  # At least default + interviewer

    async def test_list_personas_tool(self) -> None:
        registry = PersonaRegistry()
        registry.register(Persona("p1", "Persona 1", "Desc 1", "Prompt 1"))
        
        tool = list_personas_tool(registry)
        result = await tool.handler({})
        
        assert result["success"] is True
        assert "Persona 1" in result["message"]


class TestGlobalRegistry:
    """Tests for the global persona registry."""

    def test_get_persona_registry(self) -> None:
        """Test that global registry is created and has default personas."""
        registry = get_persona_registry()
        
        # Should have default personas
        personas = registry.list_personas()
        assert len(personas) > 5
        
        # Should be able to get known personas
        assert registry.get("interviewer") is not None
        assert registry.get("coach") is not None
        assert registry.get("teacher") is not None

    def test_default_persona(self) -> None:
        """Test that 'default' persona exists."""
        registry = get_persona_registry()
        default = registry.get("default")
        assert default is not None
        assert default.name == "default"

    def test_interviewer_persona(self) -> None:
        """Test interviewer persona has expected attributes."""
        registry = get_persona_registry()
        interviewer = registry.get("interviewer")
        
        assert interviewer is not None
        assert "interview" in interviewer.system_prompt.lower()
        assert "🎙️" == interviewer.icon

    def test_tech_interviewer_alias(self) -> None:
        """Test that tech_interview alias works."""
        registry = get_persona_registry()
        
        # Alias should resolve to main persona
        assert registry.get("tech_interview") is not None
        assert registry.get("coding_interview") is not None
