from directioner.config.settings import Settings


def test_default_settings_load_without_config() -> None:
    settings = Settings.load(None)

    assert settings.app_name == "directioner"
    assert settings.audio.sample_rate_hz == 48_000


def test_discord_token_can_come_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")

    settings = Settings.load(None)

    assert settings.discord.bot_token == "test-token"


def test_llm_settings_can_come_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DIRECTIONER_LLM_PROVIDER", "mock")
    monkeypatch.setenv("DIRECTIONER_LLM_MODEL", "test-model")

    settings = Settings.load(None)

    assert settings.llm.provider == "mock"
    assert settings.llm.model == "test-model"


def test_validate_environment_requires_discord_token_for_runtime(monkeypatch) -> None:
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    settings = Settings.load(None)

    issues = settings.validate_environment(require_discord_token=True)

    assert any("DISCORD_BOT_TOKEN" in issue for issue in issues)


def test_validate_environment_requires_api_key_for_external_provider(monkeypatch) -> None:
    monkeypatch.setenv("DIRECTIONER_LLM_PROVIDER", "groq")
    monkeypatch.delenv("DIRECTIONER_LLM_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    settings = Settings.load(None)

    issues = settings.validate_environment(require_discord_token=False)

    assert any("DIRECTIONER_LLM_API_KEY" in issue for issue in issues)
