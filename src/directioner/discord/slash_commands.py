"""Slash command handler for Discord bot commands.

This module handles slash commands like /interviewer, /coach, /help, etc.
that don't require LLM processing.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from directioner.tools.persona import PersonaRegistry, get_persona_registry

if TYPE_CHECKING:
    from directioner.discord.chat_output import ChatSender

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SlashCommand:
    """A slash command definition."""
    name: str
    aliases: tuple[str, ...]
    description: str
    handler: Callable


# Voice channel controller - set by the app at startup
_voice_controller: "ChatSender | None" = None


def set_voice_controller(controller: "ChatSender | None") -> None:
    """Set the voice controller for /join and /leave commands."""
    global _voice_controller
    _voice_controller = controller


# Built-in slash commands that don't need LLM
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
        "**Voice Commands:**",
        "  /join — Join your voice channel",
        "  /leave — Leave the voice channel",
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


async def _join_handler(args: dict, registry: PersonaRegistry) -> tuple[str, str]:
    """Handle /join command to join voice channel."""
    if _voice_controller is None:
        return "❌ Voice controller not available. I can't join voice channels right now.", "text"
    
    # Voice join is handled by the runtime - signal intent
    logger.info("slash_command.voice_join user_requested")
    return "🎤 I'll join your voice channel. Make sure I'm in a voice channel!", "text"


async def _leave_handler(args: dict, registry: PersonaRegistry) -> tuple[str, str]:
    """Handle /leave command to leave voice channel."""
    if _voice_controller is None:
        return "❌ Voice controller not available. I can't leave voice channels right now.", "text"
    
    logger.info("slash_command.voice_leave user_requested")
    return "👋 Leaving voice channel now. Goodbye!", "text"


# Create the slash command registry
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
        
        # Main name
        commands[persona.name] = SlashCommand(
            name=persona.name,
            aliases=persona.aliases,
            description=f"Switch to {persona.display_name} persona",
            handler=make_handler(),
        )
        
        # Aliases
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
    
    # Voice commands
    commands["join"] = SlashCommand(
        name="join",
        aliases=("voice_join",),
        description="Join voice channel",
        handler=lambda args, reg=registry: _join_handler(args, reg),
    )
    
    commands["leave"] = SlashCommand(
        name="leave",
        aliases=("voice_leave", "disconnect", "stop"),
        description="Leave voice channel",
        handler=lambda args, reg=registry: _leave_handler(args, reg),
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
