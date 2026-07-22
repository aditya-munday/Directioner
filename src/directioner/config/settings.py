"""Runtime settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuntimeSettings:
    asyncio_debug: bool = False


@dataclass(frozen=True)
class ConversationSettings:
    context_window_tokens: int = 32_000


@dataclass(frozen=True)
class MemorySettings:
    enabled: bool = True
    max_turns_per_conversation: int = 200
    retrieval_turns: int = 8
    persist_path: str | None = "./data/memory/turns.jsonl"
    use_supabase: bool = False
    supabase_url: str | None = None
    supabase_key: str | None = None


@dataclass(frozen=True)
class LlmSettings:
    provider: str = "mock"
    model: str = "directioner-mock"
    api_key: str | None = None
    base_url: str | None = None
    system_prompt: str = (
        "You are Directioner, a concise Discord assistant. "
        "Answer helpfully and keep replies suitable for chat."
    )
    max_output_chars: int = 1800
    stream_chat: bool = True
    temperature: float = 1.0
    top_p: float = 1.0
    max_completion_tokens: int = 8192


@dataclass(frozen=True)
class DiscordSettings:
    bot_token: str | None = None
    application_id: str | None = None
    shard_count: int = 0
    cluster_id: int = 0
    cluster_count: int = 1
    use_etf: bool = False
    compressed: bool = False
    register_global_commands: bool = False


@dataclass(frozen=True)
class Settings:
    app_name: str = "directioner"
    environment: str = "development"
    runtime: RuntimeSettings = RuntimeSettings()
    conversation: ConversationSettings = ConversationSettings()
    memory: MemorySettings = MemorySettings()
    llm: LlmSettings = LlmSettings()
    discord: DiscordSettings = DiscordSettings()

    def validate_environment(self, *, require_discord_token: bool = False) -> tuple[str, ...]:
        """Return configuration issues that prevent a healthy runtime."""
        issues: list[str] = []
        if require_discord_token and not (self.discord.bot_token or "").strip():
            issues.append("DISCORD_BOT_TOKEN is required for Discord runtime commands.")

        provider = self.llm.provider.strip().lower()
        if provider not in {"", "mock", "groq", "openai-compatible"}:
            issues.append(f"Unsupported LLM provider configured: {self.llm.provider!r}.")
        if provider in {"groq", "openai-compatible"}:
            if not (self.llm.api_key or "").strip():
                issues.append(
                    "DIRECTIONER_LLM_API_KEY is required for external LLM providers."
                )

        if self.llm.max_output_chars <= 0:
            issues.append("llm.max_output_chars must be greater than zero.")
        return tuple(issues)

    @classmethod
    def load(cls, path: str | None = None) -> "Settings":
        config_path = path or os.getenv("DIRECTIONER_CONFIG")
        if not config_path:
            return cls(
                memory=MemorySettings(
                    enabled=_env_bool("DIRECTIONER_MEMORY_ENABLED", True),
                    max_turns_per_conversation=_env_int("DIRECTIONER_MEMORY_MAX_TURNS", 200),
                    retrieval_turns=_env_int("DIRECTIONER_MEMORY_RETRIEVAL_TURNS", 8),
                    persist_path=os.getenv("DIRECTIONER_MEMORY_PERSIST_PATH"),
                    use_supabase=_env_bool("DIRECTIONER_MEMORY_USE_SUPABASE", False),
                    supabase_url=os.getenv("SUPABASE_URL"),
                    supabase_key=os.getenv("SUPABASE_KEY"),
                ),
                llm=LlmSettings(
                    provider=os.getenv("DIRECTIONER_LLM_PROVIDER", "mock"),
                    model=os.getenv("DIRECTIONER_LLM_MODEL", "directioner-mock"),
                    api_key=os.getenv("DIRECTIONER_LLM_API_KEY") or os.getenv("GROQ_API_KEY"),
                    base_url=os.getenv("DIRECTIONER_LLM_BASE_URL"),
                    temperature=_env_float("DIRECTIONER_LLM_TEMPERATURE", 1.0),
                    top_p=_env_float("DIRECTIONER_LLM_TOP_P", 1.0),
                    max_completion_tokens=_env_int("DIRECTIONER_LLM_MAX_COMPLETION_TOKENS", 8192),
                ),
                discord=DiscordSettings(
                    bot_token=os.getenv("DISCORD_BOT_TOKEN"),
                    application_id=os.getenv("DISCORD_APPLICATION_ID"),
                ),
            )

        raw = _load_yaml(Path(config_path))
        app = raw.get("app", {})
        runtime = raw.get("runtime", {})
        conversation = raw.get("conversation", {})
        discord = raw.get("discord", {})
        memory = raw.get("memory", {})
        llm = raw.get("llm", {})

        return cls(
            app_name=str(app.get("name", "directioner")),
            environment=str(app.get("environment", "development")),
            runtime=RuntimeSettings(
                asyncio_debug=bool(runtime.get("asyncio_debug", False)),
            ),
            conversation=ConversationSettings(
                context_window_tokens=int(conversation.get("context_window_tokens", 32_000)),
            ),
            memory=MemorySettings(
                enabled=_env_bool("DIRECTIONER_MEMORY_ENABLED", bool(memory.get("enabled", True))),
                max_turns_per_conversation=_env_int(
                    "DIRECTIONER_MEMORY_MAX_TURNS",
                    int(memory.get("max_turns_per_conversation", 200)),
                ),
                retrieval_turns=_env_int(
                    "DIRECTIONER_MEMORY_RETRIEVAL_TURNS",
                    int(memory.get("retrieval_turns", 8)),
                ),
                persist_path=os.getenv("DIRECTIONER_MEMORY_PERSIST_PATH")
                or _optional_str(memory.get("persist_path")),
                use_supabase=_env_bool(
                    "DIRECTIONER_MEMORY_USE_SUPABASE",
                    bool(memory.get("use_supabase", False)),
                ),
                supabase_url=os.getenv("SUPABASE_URL") or _optional_str(memory.get("supabase_url")),
                supabase_key=os.getenv("SUPABASE_KEY") or _optional_str(memory.get("supabase_key")),
            ),
            llm=LlmSettings(
                provider=os.getenv("DIRECTIONER_LLM_PROVIDER")
                or str(llm.get("provider", "mock")),
                model=os.getenv("DIRECTIONER_LLM_MODEL")
                or str(llm.get("model", "directioner-mock")),
                api_key=os.getenv("DIRECTIONER_LLM_API_KEY")
                or os.getenv("GROQ_API_KEY")
                or _optional_str(llm.get("api_key")),
                base_url=os.getenv("DIRECTIONER_LLM_BASE_URL")
                or _optional_str(llm.get("base_url")),
                system_prompt=str(
                    llm.get(
                        "system_prompt",
                        "You are Directioner, a concise Discord assistant. "
                        "Answer helpfully and keep replies suitable for chat.",
                    )
                ),
                max_output_chars=int(llm.get("max_output_chars", 1800)),
                stream_chat=_env_bool(
                    "DIRECTIONER_LLM_STREAM_CHAT",
                    bool(llm.get("stream_chat", True)),
                ),
                temperature=_env_float(
                    "DIRECTIONER_LLM_TEMPERATURE",
                    float(llm.get("temperature", 1.0)),
                ),
                top_p=_env_float("DIRECTIONER_LLM_TOP_P", float(llm.get("top_p", 1.0))),
                max_completion_tokens=_env_int(
                    "DIRECTIONER_LLM_MAX_COMPLETION_TOKENS",
                    int(llm.get("max_completion_tokens", 8192)),
                ),
            ),
            discord=DiscordSettings(
                bot_token=os.getenv("DISCORD_BOT_TOKEN") or _optional_str(discord.get("bot_token")),
                application_id=os.getenv("DISCORD_APPLICATION_ID")
                or _optional_str(discord.get("application_id")),
                shard_count=int(discord.get("shard_count", 0)),
                cluster_id=int(discord.get("cluster_id", 0)),
                cluster_count=int(discord.get("cluster_count", 1)),
                use_etf=_env_bool("DIRECTIONER_DPP_USE_ETF", bool(discord.get("use_etf", False))),
                compressed=_env_bool(
                    "DIRECTIONER_DPP_COMPRESSED",
                    bool(discord.get("compressed", False)),
                ),
                register_global_commands=_env_bool(
                    "DIRECTIONER_DPP_REGISTER_COMMANDS",
                    bool(discord.get("register_global_commands", False)),
                ),
            ),
        )


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected mapping at top level of config file: {path}")
    return loaded


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)
