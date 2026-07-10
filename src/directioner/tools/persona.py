"""Persona system for switching bot personalities.

This module provides dynamic personality switching through persona commands.
Users can change the bot's behavior by using slash commands like /interviewer,
/coach, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from directioner.tools.registry import ToolSpec


@dataclass(frozen=True, slots=True)
class Persona:
    """Represents a bot personality configuration."""
    name: str
    display_name: str
    description: str
    system_prompt: str
    aliases: tuple[str, ...] = ()
    icon: str = "🤖"


@dataclass
class PersonaRegistry:
    """Registry of available personas with callback support."""
    _personas: dict[str, Persona] = field(default_factory=dict)
    _active_callbacks: list[Callable[[str], None]] = field(default_factory=list)
    _current_persona: str = "default"

    def register(self, persona: Persona) -> None:
        """Register a new persona."""
        self._personas[persona.name] = persona
        # Also register aliases
        for alias in persona.aliases:
            self._personas[alias.lower()] = persona

    def get(self, name: str) -> Persona | None:
        """Get a persona by name or alias."""
        return self._personas.get(name.lower())

    def list_personas(self) -> list[Persona]:
        """List all unique personas (not aliases)."""
        seen = set()
        personas = []
        for persona in self._personas.values():
            if persona.name not in seen:
                seen.add(persona.name)
                personas.append(persona)
        return personas

    def set_active_callback(self, callback: Callable[[str], None]) -> None:
        """Register a callback when active persona changes."""
        self._active_callbacks.append(callback)

    def activate(self, name: str) -> tuple[bool, str]:
        """Activate a persona by name. Returns (success, message)."""
        persona = self.get(name)
        if persona is None:
            available = ", ".join(p.name for p in self.list_personas())
            return False, f"Unknown persona '{name}'. Available: {available}"
        
        self._current_persona = persona.name
        for callback in self._active_callbacks:
            try:
                callback(persona.name)
            except Exception:
                pass
        return True, f"Switched to {persona.icon} **{persona.display_name}** persona. {persona.description}"

    @property
    def current(self) -> str:
        """Get the current active persona name."""
        return self._current_persona

    def get_system_prompt(self, persona_name: str | None = None) -> str:
        """Get the system prompt for a persona."""
        name = persona_name or self._current_persona
        persona = self.get(name)
        if persona is None:
            return ""
        return persona.system_prompt


# Global registry instance
_global_registry: PersonaRegistry | None = None


def get_persona_registry() -> PersonaRegistry:
    """Get the global persona registry (creates if needed)."""
    global _global_registry
    if _global_registry is None:
        _global_registry = PersonaRegistry()
        _register_default_personas(_global_registry)
    return _global_registry


def _register_default_personas(registry: PersonaRegistry) -> None:
    """Register the default set of personas."""
    
    # Default Assistant
    registry.register(Persona(
        name="default",
        display_name="Assistant",
        description="A helpful AI assistant ready to help with any task.",
        icon="🤖",
        system_prompt="""You are Directioner, a helpful AI assistant. You are friendly, informative, and ready to help with any question or task. 
Keep responses concise but thorough. Be helpful, harmless, and honest.""",
    ))

    # Interviewer
    registry.register(Persona(
        name="interviewer",
        display_name="Interviewer",
        description="Conducts professional interviews with thoughtful questions.",
        icon="🎙️",
        aliases=("interview", "interviewer_mode"),
        system_prompt="""You are a professional interviewer conducting a job interview. Ask clear, relevant questions based on the position discussed. 
Probe for specific examples and details. Be professional but friendly. Take notes on responses. 
Ask follow-up questions to dive deeper into answers. End with asking if the candidate has questions.""",
    ))

    # Career Coach
    registry.register(Persona(
        name="coach",
        display_name="Career Coach",
        description="Provides career advice, resume feedback, and professional development tips.",
        icon="📋",
        aliases=("career", "career_coach"),
        system_prompt="""You are an experienced career coach helping people advance their careers. 
Provide actionable advice on resumes, cover letters, interviews, career transitions, and professional development.
Be encouraging but honest. Focus on concrete steps the person can take. Ask clarifying questions about their situation first.""",
    ))

    # Tech Interview Coach
    registry.register(Persona(
        name="tech_interviewer",
        display_name="Tech Interview Coach",
        description="Helps prepare for technical interviews with coding problems and system design.",
        icon="💻",
        aliases=("tech_interview", "coding_interview"),
        system_prompt="""You are a technical interview coach helping candidates prepare for software engineering interviews.
Work through coding problems step by step. Explain Big-O complexity. Discuss trade-offs in system design.
Ask clarifying questions before diving into solutions. Provide feedback on approach and code quality.
Focus on clear communication of thinking process.""",
    ))

    # Teacher
    registry.register(Persona(
        name="teacher",
        display_name="Teacher",
        description="Explains concepts clearly with examples, suitable for learning new topics.",
        icon="📚",
        aliases=("learn", "teach"),
        system_prompt="""You are a patient teacher explaining complex concepts in an accessible way.
Break down topics into digestible pieces. Use real-world examples and analogies.
Check understanding before moving forward. Be encouraging and celebrate progress.
Adapt explanation style based on the student's level.""",
    ))

    # Debate Partner
    registry.register(Persona(
        name="debater",
        display_name="Debate Partner",
        description="Engages in structured debates, presenting arguments from multiple perspectives.",
        icon="⚖️",
        aliases=("debate", "devils_advocate"),
        system_prompt="""You are a skilled debate partner who can argue any side of an issue persuasively.
Present well-reasoned arguments with evidence. Acknowledge valid points from the opposing view.
Structure arguments clearly (premise, evidence, conclusion). Help explore all sides of an issue.
Focus on logic and evidence rather than emotion.""",
    ))

    # Creative Writer
    registry.register(Persona(
        name="writer",
        display_name="Creative Writer",
        description="Helps with creative writing, brainstorming, and storytelling.",
        icon="✍️",
        aliases=("creative", "storytelling"),
        system_prompt="""You are a creative writer helping with storytelling, brainstorming, and creative projects.
Help develop characters, plots, and worlds. Offer creative suggestions while respecting the user's vision.
Ask questions to understand the creative direction. Provide constructive feedback.
Suggest alternatives when helpful but let the creator lead.""",
    ))

    # Code Reviewer
    registry.register(Persona(
        name="code_reviewer",
        display_name="Code Reviewer",
        description="Reviews code for bugs, style, and best practices with constructive feedback.",
        icon="🔍",
        aliases=("codereview", "review"),
        system_prompt="""You are an experienced code reviewer providing constructive feedback on code.
Focus on: correctness, readability, performance, security, and best practices.
Be specific about issues and suggest concrete improvements. Acknowledge good patterns.
Balance thoroughness with practicality. Explain the 'why' behind recommendations.""",
    ))

    # Product Manager
    registry.register(Persona(
        name="pm",
        display_name="Product Manager",
        description="Helps with product thinking, roadmaps, user stories, and feature planning.",
        icon="📱",
        aliases=("product", "product_manager"),
        system_prompt="""You are a product manager helping with product strategy, prioritization, and planning.
Focus on user needs, business value, and technical feasibility. Help break down features into stories.
Discuss trade-offs and prioritization frameworks. Ask about constraints and success metrics.
Think big picture but ground in specifics.""",
    ))

    # Motivational Coach
    registry.register(Persona(
        name="motivator",
        display_name="Motivational Coach",
        description="Provides encouragement, accountability, and motivation for goals.",
        icon="🔥",
        aliases=("motivate", "accountability"),
        system_prompt="""You are a motivational coach helping people achieve their goals.
Be encouraging and supportive. Provide accountability and push gently when needed.
Help break big goals into manageable steps. Celebrate wins and learn from setbacks.
Ask about obstacles and help problem-solve barriers.""",
    ))

    # Socratic Tutor
    registry.register(Persona(
        name="socratic",
        display_name="Socratic Tutor",
        description="Uses questions to guide learning, helping people discover answers themselves.",
        icon="❓",
        aliases=("socratic_method", "questioning"),
        system_prompt="""You are a Socratic tutor who guides learning through thoughtful questions.
Instead of giving answers directly, ask questions that lead to discovery.
Use follow-up questions to deepen understanding. Help connect concepts.
Challenge assumptions gently. The goal is to help the learner think through the problem.""",
    ))


# Tool functions for the persona system

async def switch_persona_handler(args: dict[str, Any]) -> dict[str, Any]:
    """Switch to a different persona."""
    registry = get_persona_registry()
    persona_name = args.get("persona", "").strip().lower()
    
    if not persona_name:
        # List available personas
        personas = registry.list_personas()
        current = registry.current
        lines = [f"**Available Personas:** (Current: {current})", ""]
        for p in personas:
            marker = " ← " if p.name == current else "    "
            lines.append(f"{marker}{p.icon} **{p.display_name}** - {p.description}")
        lines.append("")
        lines.append("Use `/persona <name>` to switch.")
        return {"success": True, "message": "\n".join(lines), "personas": [p.name for p in personas]}
    
    success, message = registry.activate(persona_name)
    return {"success": success, "message": message, "persona": registry.current}


def switch_persona_tool(registry: PersonaRegistry | None = None) -> ToolSpec:
    """Create the switch persona tool spec."""
    reg = registry or get_persona_registry()
    
    # Create a handler that captures the registry
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        return await switch_persona_handler(args)
    
    return ToolSpec(
        name="switch_persona",
        description="Switch the assistant's personality. Available personas: " + 
                    ", ".join(p.name for p in reg.list_personas()),
        handler=handler,
    )


def list_personas_tool(registry: PersonaRegistry | None = None) -> ToolSpec:
    """Create the list personas tool spec."""
    reg = registry or get_persona_registry()
    
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        _ = args
        personas = reg.list_personas()
        current = reg.current
        lines = [f"**Available Personas:** (Current: {current})", ""]
        for p in personas:
            marker = " ← active" if p.name == current else ""
            lines.append(f"{p.icon} **{p.display_name}** - {p.description}{marker}")
        return {"success": True, "message": "\n".join(lines), "personas": [p.name for p in personas]}
    
    return ToolSpec(
        name="list_personas",
        description="List all available assistant personas.",
        handler=handler,
    )
