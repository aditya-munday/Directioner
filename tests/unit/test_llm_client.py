from __future__ import annotations

import sys
import types

import pytest

from directioner.config.settings import LlmSettings
from directioner.intent.planner import Plan, PlanKind
from directioner.llm.client import LlmRequest, build_llm_client


@pytest.mark.asyncio
async def test_mock_llm_client_generates_chat_reply() -> None:
    client = build_llm_client(LlmSettings(provider="mock"))

    response = await client.complete(
        LlmRequest(
            system_prompt="Be useful.",
            plan=Plan(kind=PlanKind.CHAT, prompt="hello"),
        )
    )

    assert response.provider == "mock"
    assert "Directioner" in response.content


def test_unknown_llm_provider_fails_clearly() -> None:
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        build_llm_client(LlmSettings(provider="mystery"))


@pytest.mark.asyncio
async def test_groq_client_uses_configured_chat_completion_arguments(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeMessage:
        content = "hello from groq"
        tool_calls = None

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletion:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs: object) -> FakeCompletion:
            captured.update(kwargs)
            return FakeCompletion()

    class FakeChat:
        completions = FakeCompletions()

    class FakeGroq:
        def __init__(self, **kwargs: object) -> None:
            captured["client_kwargs"] = kwargs
            self.chat = FakeChat()

    fake_module = types.SimpleNamespace(Groq=FakeGroq)
    monkeypatch.setitem(sys.modules, "groq", fake_module)

    client = build_llm_client(
        LlmSettings(
            provider="groq",
            model="openai/gpt-oss-120b",
            api_key="test-key",
            temperature=1,
            top_p=1,
            max_completion_tokens=8192,
        )
    )

    response = await client.complete(
        LlmRequest(
            system_prompt="Be useful.",
            plan=Plan(kind=PlanKind.CHAT, prompt="hello"),
        )
    )

    assert response.provider == "groq"
    assert response.content == "hello from groq"
    assert captured["model"] == "openai/gpt-oss-120b"
    assert captured["temperature"] == 1
    assert captured["max_completion_tokens"] == 1024
    assert captured["top_p"] == 1
    assert captured["stream"] is False
    assert captured["stop"] is None
    assert captured["messages"] == [
        {"role": "system", "content": "Be useful."},
        {"role": "user", "content": "hello"},
    ]
    assert captured["client_kwargs"] == {"api_key": "test-key"}
