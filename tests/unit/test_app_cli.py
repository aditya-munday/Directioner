from __future__ import annotations

import json

from directioner.app import main


def test_validate_env_command_fails_without_required_token(monkeypatch) -> None:
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setenv("DIRECTIONER_LLM_PROVIDER", "mock")

    code = main(["validate-env"])

    assert code == 1


def test_health_check_outputs_json_report(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setenv("DIRECTIONER_LLM_PROVIDER", "mock")

    code = main(["health-check"])
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)

    assert code in {0, 1}
    assert payload["status"] in {"ok", "degraded"}
    assert "native_extension" in payload
