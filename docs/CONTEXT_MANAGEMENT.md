# Context Management

Directioner has two kinds of context:

- Project context for developers and future agent sessions.
- Conversation context for runtime Discord interactions.

## Project Context

Project context lives in:

- `CONTEXT.md` - current handoff state, setup, decisions, and risks.
- `TODO.md` - active completion backlog.
- `docs/` - stable architecture and protocol documentation.

When resuming work, read `CONTEXT.md` first, then `TODO.md`.

## Runtime Conversation Context

Runtime context is implemented in `src/directioner/conversation/context.py`.

The main classes are:

- `ContextRecord` - one structured context item.
- `ContextSnapshot` - a bounded view of recent context for prompts/planning.
- `ContextManager` - records events and builds token-budgeted snapshots.

The Conversation Router calls `ContextManager.remember_event()` for every non-interruption event. This preserves:

- role
- content
- event source
- token estimate
- speaker id
- user id
- guild/channel ids
- event metadata

The old `ConversationState.context_items` list is still maintained for the current memory facade. New code should prefer `context_records` and `ContextSnapshot`.

## Token Budgeting

Token counts are approximate until a model-specific tokenizer is chosen.

Current estimate:

```text
ceil(character_count / 4)
```

This is good enough for budget trimming and tests, but final LLM integration should replace or augment it with provider-specific tokenization.

## Next Upgrades

- Add assistant response recording.
- Add tool-result recording.
- Add context overflow summarization.
- Add model-specific token counting.
- Add retrieved memory citations/references.
- Add speaker/user profile injection.

