from directioner.text.cleanup import strip_discord_mentions


def test_strip_discord_mentions_removes_user_mention() -> None:
    assert strip_discord_mentions("<@1512144742060654612> hi") == "hi"


def test_strip_discord_mentions_removes_nickname_mention() -> None:
    assert strip_discord_mentions("<@!123456789> hello") == "hello"
