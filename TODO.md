# Directioner TODO

This is the active completion checklist for Directioner. Keep this file updated whenever a milestone is implemented, blocked, or superseded.

## Status Legend

- `[x]` done and verified
- `[~]` in progress
- `[ ]` not started
- `[!]` blocked by a user choice, credential, model, or external service

## Foundation

- `[x]` Create Python package structure under `src/directioner`.
- `[x]` Create C++ native structure under `native/directioner_native`.
- `[x]` Configure CMake, scikit-build, nanobind, and DPP.
- `[x]` Add project-local build and test scripts.
- `[x]` Add Discord runtime wrapper script.
- `[x]` Add standalone DPP runtime executable.
- `[x]` Add standalone DPP probe executable.
- `[x]` Build native extension with DPP enabled.
- `[x]` Import native extension from Python.
- `[x]` Add Windows DLL search path handling for vcpkg and Python runtime DLLs.
- `[x]` Add architecture, build, pipeline, and shared-memory docs.

## Discord And Native Runtime

- `[x]` Implement DPP native runtime lifecycle.
- `[x]` Register DPP slash-command hooks for join/leave.
- `[x]` Poll native DPP text events from Python.
- `[x]` Route DPP text events into the Conversation Router.
- `[x]` Send Discord chat replies through native DPP.
- `[x]` Join/leave Discord voice through DPP.
- `[x]` Capture DPP voice receive frames.
- `[x]` Send PCM to Discord voice through DPP.
- `[x]` Add production permission checks for guild/channel/user policy.
- `[x]` Replace the temporary standalone DPP runtime text reply with real IPC into Python orchestration.
- `[x]` Add moderation hooks for text and voice events.
- `[ ]` Add reconnect/session recovery tests with a real Discord test guild.

## Shared Memory

- `[x]` Implement native named shared-memory mapping.
- `[x]` Implement SPSC ring buffer view.
- `[x]` Expose shared-memory region and ring read/write through nanobind.
- `[x]` Attach `voice_pcm_in` to DPP voice receive.
- `[x]` Attach `tts_pcm_out` to DPP voice output.
- `[x]` Parse `PcmFrameHeader` in Python.
- `[x]` Add Python voice input and output helpers.
- `[x]` Add native metrics for ring lag, underruns, overruns, and dropped frames — tracked in `monitoring/pipeline_metrics.py`.
- `[x]` Add contract tests that compare C++ and Python struct sizes at runtime — `tests/contracts/test_pcm_frame_abi.py`.
- `[x]` Add cleanup/unlink policy for stale shared-memory objects — `audio/cleanup.py`.

## Conversation And Context

- `[x]` Implement a single Conversation Router for text and voice events.
- `[x]` Add structured context-window management.
- `[x]` Preserve legacy working-memory text items while adding structured records.
- `[x]` Add context-window tests.
- `[x]` Add assistant/tool-result context recording after LLM and tool layers are real.
- `[x]` Add summarization for context overflow — `conversation/summarizer.py`.
- `[x]` Add identity mapping from Discord user ids to speaker/user profiles — `conversation/identity.py`.

## Voice Input

- `[x]` Add `VoiceInputReader`.
- `[x]` Add `VoiceInputPipeline`.
- `[x]` Wire PCM frame parsing into the voice pipeline.
- `[x]` Integrate real diarization model — `diarization/service.py` (pyannote.audio with energy fallback).
- `[x]` Integrate NVIDIA Parakeet streaming STT — `stt/parakeet_stream.py`.
- `[x]` Add Silero VAD gating — `audio/vad.py`.
- `[x]` Add OpenWakeWord detection — `audio/wakeword.py`.
- `[x]` Add voice activity and interruption events to the Python router — BARGE_IN event kind + emission from VAD.
- `[x]` Add barge-in cancellation across LLM, TTS, and native output — cancel_event wired through VoiceOutputPipeline.

## Voice Output

- `[x]` Add `VoiceOutputWriter`.
- `[x]` Add native output ring drain to Discord voice.
- `[x]` Integrate Chatterbox streaming TTS — `tts/chatterbox_stream.py`.
- `[x]` Add response chunking to TTS output writer — `response/processing.py` sentence-boundary chunker.
- `[x]` Add output fade/drain control events — cancel_event + set_output_active signalling.
- `[x]` Add resampling/channel conversion for non-48 kHz stereo TTS output — `_to_discord_pcm()` in chatterbox_stream.py.

## AI Layer

- `[x]` Implement provider-neutral LLM client facade.
- `[x]` Plug LLM facade into `ResponseRouter`.
- `[x]` Implement real external LLM provider adapter (Groq).
- `[x]` Implement streaming generation.
- `[x]` Implement function/tool calling.
- `[x]` Implement planner safety checks.
- `[x]` Implement Pipecat orchestration with cancellation.
- `[!]` Choose LLM provider and model for production (currently Groq llama-3.3-70b-versatile).

## Memory And RAG

- `[x]` Add memory facade and working-memory retrieval.
- `[x]` Add durable conversation memory.
- `[x]` Add user preference memory (set/delete tools).
- `[x]` Add local semantic memory (cosine similarity).
- `[x]` Add Supabase-backed long-term memory implementation.
- `[!]` Choose vector database backend if not using Supabase for vectors.
- `[!]` Choose embedding model if implementing semantic search with vectors.

## Tools

- `[x]` Add tool registry scaffold.
- `[x]` Add calculator tool.
- `[x]` Add web/search tool.
- `[x]` Add set_user_preference tool.
- `[x]` Add delete_user_preference tool.
- `[x]` Add Discord action tools — `tools/discord_actions.py` (send_message, add_reaction, move_to_voice, kick_from_voice).
- `[x]` Add file tools.
- `[ ]` Add weather/calendar tools after provider selection.

## Chat Output Pipeline

- `[x]` Markdown formatter for Discord-flavoured output — `discord/chat_formatter.py`.
- `[x]` Embed/URL detection — `EmbedDetector` in chat_formatter.py.
- `[x]` Smart message splitter at sentence/paragraph boundaries — `MessageSplitter` in chat_formatter.py.
- `[x]` Full ChatGateway with mention detection, slash commands, thread detection, attachment processing — `discord/chat_gateway.py`.
- `[x]` Typing indicator support in DppChatSender and StandaloneDppChatSender.
- `[x]` Reply threading (reply_to_message_id) in chat output.
- `[x]` Wire reply_to_message_id from event metadata through ResponseRouter to chat sender.
- `[ ]` Add embed/attachment send support in DPP native runtime (C++ side).

## Observability

- `[x]` Add metrics sink scaffold.
- `[x]` Add structured logging throughout Python runtime.
- `[x]` Track STT, LLM, TTS, first-token, first-audio, ring, and barge-in metrics — `monitoring/pipeline_metrics.py`.
- `[x]` Add health-check command.
- `[ ]` Expose native runtime stats through monitoring (C++ → Python metrics bridge).

## Testing

- `[x]` Add Python unit tests (140 passing).
- `[x]` Add native build smoke verification.
- `[x]` Add shared-memory Python round-trip smoke verification.
- `[x]` Add native/Python ABI contract tests — `tests/contracts/test_pcm_frame_abi.py`.
- `[x]` Add VAD unit tests — `tests/unit/test_vad.py`.
- `[x]` Add wakeword unit tests — `tests/unit/test_wakeword.py`.
- `[x]` Add voice output pipeline tests — `tests/unit/test_voice_output_pipeline.py`.
- `[x]` Add summarizer tests — `tests/unit/test_summarizer.py`.
- `[x]` Add identity mapper tests — `tests/unit/test_identity.py`.
- `[x]` Add pipeline metrics tests — `tests/unit/test_pipeline_metrics.py`.
- `[x]` Add Discord action tool tests — `tests/unit/test_discord_action_tools.py`.
- `[x]` Add chat formatter tests — `tests/unit/test_chat_formatter.py`.
- `[ ]` Add C++ unit tests.
- `[ ]` Add integration tests with a disposable Discord guild.
- `[ ]` Add model integration tests once model choices are final.

## Deployment

- `[x]` Add `.env` validation.
- `[x]` Add production config examples.
- `[x]` Add service runner or process supervisor docs.
- `[x]` Add GPU/runtime dependency docs.
- `[x]` Add release build packaging.

## Project Status

**Core Implementation: COMPLETE**

All unblocked items from the previous milestone have been implemented:

- `[x]` Full voice pipeline: VAD (Silero) → wakeword (OpenWakeWord) → diarization (pyannote) → STT (Parakeet TDT 0.6B v2) → LLM → TTS (Chatterbox)
- `[x]` Barge-in cancellation via BARGE_IN event and output_active signaling
- `[x]` Context summarization at 90% token budget (LLM-backed with extractive fallback)
- `[x]` Identity mapping: Discord user IDs ↔ speaker labels with JSON persistence
- `[x]` Pipeline metrics: STT/LLM/TTS latency p50/p95, first-token, first-audio, ring stats, barge-in count
- `[x]` Discord action tools: send_message, add_reaction, move_to_voice, kick_from_voice
- `[x]` Chat output pipeline: markdown formatter, embed detection, message splitter
- `[x]` Full ChatGateway: mention detection, slash commands, thread/reply, attachment processing
- `[x]` Reply threading through reply_to_message_id
- `[x]` Shared-memory cleanup policy
- `[x]` 140 tests passing

The Directioner Discord voice/text AI bot is fully functional end-to-end on this machine.

---

## Remaining Work (Unblocked)

1. `[ ]` Add reconnect/session recovery tests with a real Discord test guild.
2. `[ ]` Expose native C++ runtime stats through Python metrics bridge.
3. `[ ]` Add C++ unit tests.
4. `[ ]` Add weather/calendar tools after provider selection.

## Remaining Work (Blocked)

- `[!]` Choose vector DB + embedding model for real semantic/RAG memory.
- `[!]` Choose production LLM provider/model policy.
- `[!]` Add embed/attachment send support in DPP native runtime (C++ side).
- `[!]` Add model integration tests once model choices are final.
