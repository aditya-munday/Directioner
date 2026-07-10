from __future__ import annotations

from directioner.discord.standalone_process import (
    decode_protocol_text,
    encode_protocol_text,
    parse_runtime_event,
)


def test_protocol_text_round_trips_unicode_and_tabs() -> None:
    content = "hello\tDirectioner"

    encoded = encode_protocol_text(content)

    assert "\t" not in encoded
    assert decode_protocol_text(encoded) == content


def test_parse_runtime_text_event() -> None:
    line = (
        "DIRECTIONER_EVENT\tTEXT_MESSAGE\t1\t2\t3\t4\t0\t"
        f"{encode_protocol_text('hello')}"
    )

    event = parse_runtime_event(line)

    assert event is not None
    assert event.guild_id == 1
    assert event.channel_id == 2
    assert event.message_id == 3
    assert event.author_id == 4
    assert event.author_is_bot is False
    assert event.content == "hello"


def test_parse_runtime_ignores_non_event_line() -> None:
    assert parse_runtime_event("Directioner standalone DPP runtime") is None
