from __future__ import annotations

import pytest

from directioner.conversation.context import ContextManager
from directioner.conversation.events import ConversationEvent, ConversationEventKind
from directioner.conversation.state import ConversationState


def test_context_manager_records_event_and_preserves_legacy_items() -> None:
    manager = ContextManager(token_budget=100)
    state = ConversationState(conversation_id="c1")

    manager.remember_event(
        state,
        ConversationEvent(
            kind=ConversationEventKind.CHAT_MESSAGE,
            conversation_id="c1",
            user_id="u1",
            text="hello there",
            channel_id="ch1",
            guild_id="g1",
        ),
    )

    assert state.context_items == ["hello there"]
    assert state.context_records[0].source == "chat_message"
    assert state.context_records[0].user_id == "u1"


def test_context_snapshot_respects_token_budget() -> None:
    manager = ContextManager(token_budget=3)
    state = ConversationState(conversation_id="c1")

    for text in ("aaaa", "bbbb", "cccc", "dddd"):
        manager.remember_event(
            state,
            ConversationEvent(
                kind=ConversationEventKind.CHAT_MESSAGE,
                conversation_id="c1",
                user_id="u1",
                text=text,
            ),
        )

    snapshot = manager.snapshot(state)

    assert snapshot.text_items == ("bbbb", "cccc", "dddd")
    assert snapshot.dropped_records == 1
    assert snapshot.token_estimate == 3


def test_context_manager_rejects_invalid_budget() -> None:
    with pytest.raises(ValueError):
        ContextManager(token_budget=0)

