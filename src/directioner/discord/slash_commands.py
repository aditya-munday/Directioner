"""Slash command handler for Discord bot commands."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from directioner.tools.persona import PersonaRegistry, get_persona_registry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SlashCommand:
    """A slash command definition."""
    name: str
    aliases: tuple[str, ...]
    description: str
    handler: Callable


async def _help_handler(args: dict, registry: PersonaRegistry) -> tuple[str, str]:
    """Handle /help command."""
    personas = registry.list_personas()
    lines = [
        "**Available Commands:**",
        "",
        "**Persona Commands:**",
    ]
    for p in personas:
        aliases = ", ".join(f"/{a}" for a in p.aliases) if p.aliases else f"/{p.name}"
        lines.append(f"  {p.icon} {aliases} — {p.description}")
    
    lines.extend([
        "",
        "**General Commands:**",
        "  /help — Show this help message",
        "  /status — Show current persona and stats",
        "",
        "Just send a message to chat with me!",
    ])
    return "\n".join(lines), "text"


async def _status_handler(args: dict, registry: PersonaRegistry) -> tuple[str, str]:
    """Handle /status command."""
    current = registry.get(registry.current)
    if current:
        return (
            f"**Current Persona:** {current.icon} **{current.display_name}**\n"
            f"_{current.description}_"
        ), "text"
    return "**Current Persona:** 🤖 **Assistant**", "text"


async def _persona_handler(args: dict, registry: PersonaRegistry) -> tuple[str, str]:
    """Handle /persona command for listing personas."""
    personas = registry.list_personas()
    current = registry.current
    lines = [
        f"**Available Personas** (Current: {current}):",
        "",
    ]
    for p in personas:
        marker = " ← **active**" if p.name == current else ""
        lines.append(f"{p.icon} **{p.name}** — {p.description}{marker}")
    
    lines.extend([
        "",
        "Use `/persona <name>` or `/<name>` to switch.",
    ])
    return "\n".join(lines), "text"


def _create_slash_commands(registry: PersonaRegistry) -> dict[str, SlashCommand]:
    """Create all slash commands."""
    commands = {}
    
    # Persona commands
    for persona in registry.list_personas():
        async def make_handler(p=persona):
            async def handler(args: dict, reg=registry) -> tuple[str, str]:
                success, message = reg.activate(p.name)
                return message, "text"
            return handler
        commands[persona.name] = SlashCommand(
            name=persona.name,
            aliases=persona.aliases,
            description=f"Switch to {persona.display_name} persona",
            handler=make_handler(),
        )
        for alias in persona.aliases:
            commands[alias] = SlashCommand(
                name=persona.name,
                aliases=(),
                description=f"Switch to {persona.display_name} persona",
                handler=make_handler(),
            )
    
    # General commands
    commands["help"] = SlashCommand(
        name="help",
        aliases=("commands",),
        description="Show available commands",
        handler=lambda args, reg=registry: _help_handler(args, reg),
    )
    
    commands["status"] = SlashCommand(
        name="status",
        aliases=("who",),
        description="Show current persona",
        handler=lambda args, reg=registry: _status_handler(args, reg),
    )
    
    commands["persona"] = SlashCommand(
        name="persona",
        aliases=(),
        description="List all personas",
        handler=lambda args, reg=registry: _persona_handler(args, reg),
    )
    
    return commands


class SlashCommandHandler:
    """Handler for slash commands that bypass the LLM."""
    
    def __init__(self, registry: PersonaRegistry | None = None) -> None:
        self._registry = registry or get_persona_registry()
        self._commands = _create_slash_commands(self._registry)
    
    def get_command(self, name: str) -> SlashCommand | None:
        """Get a command by name (case-insensitive)."""
        return self._commands.get(name.lower())
    
    async def execute(self, command_name: str, args: dict) -> tuple[str, str] | None:
        """Execute a slash command. Returns (message, message_type) or None if not found."""
        command = self.get_command(command_name)
        if command is None:
            return None
        try:
            return await command.handler(args)
        except Exception:
            logger.exception("slash_command.error command=%s", command_name)
            return "Sorry, an error occurred processing that command.", "text"
    
    def list_commands(self) -> list[SlashCommand]:
        """List all available commands."""
        return list(self._commands.values())


# Global instance
_global_handler: SlashCommandHandler | None = None


def get_slash_command_handler() -> SlashCommandHandler:
    """Get the global slash command handler."""
    global _global_handler
    if _global_handler is None:
        _global_handler = SlashCommandHandler()
    return _global_handler
