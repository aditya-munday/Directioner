"""Application entry point with comprehensive health checks."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from directioner.config.settings import Settings
from directioner.monitoring import configure_logging, event_fields, get_logger

LOGGER = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="directioner")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to the main YAML configuration file.",
    )
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("check", help="Load configuration and report runtime readiness.")
    subcommands.add_parser(
        "validate-env",
        help="Validate required environment and configuration settings.",
    )
    subcommands.add_parser(
        "health-check",
        help="Run a lightweight runtime health report and emit JSON.",
    )
    subcommands.add_parser("native-smoke", help="Verify the native extension.")
    subcommands.add_parser("dpp-smoke", help="Construct a DPP cluster without connecting.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings.load(args.config)
    LOGGER.info(
        "app.command %s",
        event_fields(command=args.command or "check", env=settings.environment),
    )

    command = args.command or "check"
    if command == "check":
        return _check(settings)

    if command == "validate-env":
        return _validate_env(settings)

    if command == "health-check":
        return _health_check(settings)

    if command == "native-smoke":
        return _native_smoke()

    if command == "dpp-smoke":
        return _dpp_smoke(settings)

    parser.error(f"Unknown command: {command}")
    return 0


def _check(settings: Settings) -> int:
    """Run basic configuration check."""
    print(f"Directioner ready: {settings.app_name}")
    print(f"Environment: {settings.environment}")
    print(f"Discord token configured: {bool(settings.discord.bot_token)}")
    print(f"LLM Provider: {settings.llm.provider}")
    print("Mode: text-only")
    
    issues = settings.validate_environment(require_discord_token=False)
    if issues:
        print(f"\nValidation issues ({len(issues)}):")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    
    print("\nAll checks passed.")
    return 0


def _native_smoke() -> int:
    """Verify the native extension is working."""
    try:
        from directioner.native import native_build_info
        native_info = native_build_info()
        print(f"Native extension: {native_info}")
        print("Native smoke test: PASSED")
        return 0
    except Exception as exc:
        print(f"Native smoke test: FAILED - {exc}")
        return 1


def _dpp_smoke(settings: Settings) -> int:
    """Construct a DPP cluster without connecting."""
    try:
        from directioner.discord import DppDiscordRuntime
        runtime = DppDiscordRuntime(settings.discord)
        print(runtime.construct_smoke(), flush=True)
        return 0
    except Exception as exc:
        print(f"DPP smoke test: FAILED - {exc}", flush=True)
        return 1


def _validate_env(settings: Settings) -> int:
    issues = settings.validate_environment(require_discord_token=True)
    if not issues:
        print("Environment validation passed.", flush=True)
        return 0

    print("Environment validation failed:", flush=True)
    for issue in issues:
        print(f"- {issue}", flush=True)
    return 1


def _health_check(settings: Settings) -> int:
    """Run comprehensive health check with dependency verification."""
    checks: dict[str, Any] = {}
    issues: list[str] = []
    
    # Configuration validation
    config_issues = list(settings.validate_environment(require_discord_token=False))
    checks["configuration"] = {
        "ok": len(config_issues) == 0,
        "issues": config_issues,
    }
    issues.extend(config_issues)

    # Native extension check
    try:
        from directioner.native import native_build_info
        native_info = native_build_info()
        checks["native_extension"] = {
            "ok": True,
            "info": native_info,
        }
    except Exception as exc:
        checks["native_extension"] = {
            "ok": False,
            "error": str(exc),
        }
        issues.append(f"Native extension failed: {exc}")

    # LLM provider check
    llm_ok = True
    llm_error = ""
    try:
        from directioner.llm.client import build_llm_client, LlmError
        client = build_llm_client(settings.llm)
        checks["llm_provider"] = {
            "ok": True,
            "provider": settings.llm.provider,
            "model": settings.llm.model,
        }
    except LlmError as exc:
        llm_ok = False
        llm_error = str(exc)
        checks["llm_provider"] = {
            "ok": False,
            "error": llm_error,
        }
        issues.append(f"LLM provider error: {exc}")
    except Exception as exc:
        llm_ok = False
        llm_error = str(exc)
        checks["llm_provider"] = {
            "ok": False,
            "error": llm_error,
        }
        issues.append(f"LLM provider error: {exc}")

    # Memory check
    memory_ok = True
    memory_error = ""
    try:
        from directioner.memory.store import MemoryStore
        store = MemoryStore(settings.memory)
        stats = store.get_stats()
        checks["memory"] = {
            "ok": True,
            "enabled": settings.memory.enabled,
            "use_supabase": settings.memory.use_supabase,
            "persist_path": str(settings.memory.persist_path) if settings.memory.persist_path else None,
            "stats": stats,
        }
    except Exception as exc:
        memory_ok = False
        memory_error = str(exc)
        checks["memory"] = {
            "ok": False,
            "error": memory_error,
        }
        issues.append(f"Memory store error: {exc}")

    # Tool registry check
    tools_ok = True
    tools_error = ""
    try:
        from directioner.tools import build_default_registry
        registry = build_default_registry()
        tool_names = [t.name for t in registry.list()]
        checks["tools"] = {
            "ok": True,
            "count": len(tool_names),
            "tools": tool_names,
        }
    except Exception as exc:
        tools_ok = False
        tools_error = str(exc)
        checks["tools"] = {
            "ok": False,
            "error": tools_error,
        }
        issues.append(f"Tool registry error: {exc}")

    # Performance metrics
    try:
        from directioner.monitoring.performance import global_latency_tracker
        checks["performance"] = {
            "ok": True,
            "latency_stats": global_latency_tracker.get_stats(),
        }
    except Exception as exc:
        checks["performance"] = {
            "ok": False,
            "error": str(exc),
        }

    # LLM cache stats
    try:
        from directioner.llm.client import GroqLlmClient
        cache_info = {
            "cache_size": len(GroqLlmClient._response_cache),
            "cache_max_size": GroqLlmClient._cache_max_size,
        }
        if "llm_provider" in checks:
            checks["llm_provider"]["cache"] = cache_info
    except Exception:
        pass

    # Supabase database stats
    try:
        from directioner.database import get_supabase_stats
        supabase_stats = get_supabase_stats()
        if supabase_stats:
            checks["database"] = {
                "ok": True,
                "enabled": settings.memory.use_supabase,
                **supabase_stats,
            }
        else:
            checks["database"] = {
                "ok": True,
                "enabled": False,
                "message": "Supabase not configured",
            }
    except Exception as exc:
        checks["database"] = {
            "ok": True,
            "enabled": settings.memory.use_supabase,
            "available": False,
            "error": str(exc),
        }

    # Determine overall status
    status = "ok" if not issues else "degraded"
    if any(not c.get("ok", False) for c in checks.values() if isinstance(c, dict)):
        status = "degraded"
    if all(not c.get("ok", False) for c in checks.values() if isinstance(c, dict)):
        status = "unhealthy"

    report = {
        "status": status,
        "app_name": settings.app_name,
        "environment": settings.environment,
        "mode": "text-only",
        "checks": checks,
        "issues": issues,
    }
    
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
