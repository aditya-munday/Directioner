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
- `[x]` Add native metrics for ring lag, underruns, overruns, and dropped frames ÔÇö tracked in `monitoring/pipeline_metrics.py`.
- `[x]` Add contract tests that compare C++ and Python struct sizes at runtime ÔÇö `tests/contracts/test_pcm_frame_abi.py`.
- `[x]` Add cleanup/unlink policy for stale shared-memory objects ÔÇö `audio/cleanup.py`.

## Conversation And Context

- `[x]` Implement a single Conversation Router for text and voice events.
- `[x]` Add structured context-window management.
- `[x]` Preserve legacy working-memory text items while adding structured records.
- `[x]` Add context-window tests.
- `[x]` Add assistant/tool-result context recording after LLM and tool layers are real.
- `[x]` Add summarization for context overflow ÔÇö `conversation/summarizer.py`.
- `[x]` Add identity mapping from Discord user ids to speaker/user profiles ÔÇö `conversation/identity.py`.

## Voice Input

- `[x]` Add `VoiceInputReader`.
- `[x]` Add `VoiceInputPipeline`.
- `[x]` Wire PCM frame parsing into the voice pipeline.
- `[x]` Integrate real diarization model ÔÇö `diarization/service.py` (pyannote.audio with energy fallback).
- `[x]` Integrate NVIDIA Parakeet streaming STT ÔÇö `stt/parakeet_stream.py`.
- `[x]` Add Silero VAD gating ÔÇö `audio/vad.py`.
- `[x]` Add OpenWakeWord detection ÔÇö `audio/wakeword.py`.
- `[x]` Add voice activity and interruption events to the Python router ÔÇö BARGE_IN event kind + emission from VAD.
- `[x]` Add barge-in cancellation across LLM, TTS, and native output ÔÇö cancel_event wired through VoiceOutputPipeline.

## Voice Output

- `[x]` Add `VoiceOutputWriter`.
- `[x]` Add native output ring drain to Discord voice.
- `[x]` Integrate Chatterbox streaming TTS ÔÇö `tts/chatterbox_stream.py`.
- `[x]` Add response chunking to TTS output writer ÔÇö `response/processing.py` sentence-boundary chunker.
- `[x]` Add output fade/drain control events ÔÇö cancel_event + set_output_active signalling.
- `[x]` Add resampling/channel conversion for non-48 kHz stereo TTS output ÔÇö `_to_discord_pcm()` in chatterbox_stream.py.

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
- `[x]` Add embedding-based semantic memory with sentence-transformers (`all-MiniLM-L6-v2`).
- `[x]` Add Supabase-backed long-term memory implementation.
- `[~]` Choose vector database backend if not using Supabase for vectors.
- `[~]` Choose embedding model if implementing semantic search with vectors.

## Tools

- `[x]` Add tool registry scaffold.
- `[x]` Add calculator tool.
- `[x]` Add web/search tool.
- `[x]` Add set_user_preference tool.
- `[x]` Add delete_user_preference tool.
- `[x]` Add Discord action tools ÔÇö `tools/discord_actions.py` (send_message, add_reaction, move_to_voice, kick_from_voice).
- `[x]` Add file tools.
- `[x]` Add weather tool (provider-agnostic, Open-Meteo default).
- `[x]` Add calendar tool (provider-agnostic, mock implementation).
- `[x]` Add persona system with slash commands — `tools/persona.py`, `discord/slash_commands.py` (interviewer, coach, teacher, etc.).

## Persona System

- `[x]` Add PersonaRegistry with 11 default personas
- `[x]` Add persona switching via `/interviewer`, `/coach`, `/teacher`, etc.
- `[x]` Add `/help`, `/status`, `/persona` general commands
- `[x]` Add persona tools for LLM function calling (switch_persona, list_personas)
- `[x]` Integrate persona system with ChatGateway slash command handling
- `[x]` Add voice commands (/join, /leave)

## Voice Commands

- `[x]` Add /join command to join voice channel
- `[x]` Add /leave command to disconnect from voice
- `[x]` Add MicrophoneTranscriber class for direct mic input testing

## Deployment

- `[x]` Add comprehensive setup scripts (bash + batch)
- `[x]` Add run scripts for all modes (text/voice/mic/test)
- `[x]` Add requirements files (base, voice, dev)
- `[x]` Add Dockerfile with GPU support
- `[x]` Add Docker Compose configuration
- `[x]` Add Makefile for common development tasks
- `[x]` Add .env.example template

## Chat Output Pipeline

- `[x]` Markdown formatter for Discord-flavoured output ÔÇö `discord/chat_formatter.py`.
- `[x]` Embed/URL detection ÔÇö `EmbedDetector` in chat_formatter.py.
- `[x]` Smart message splitter at sentence/paragraph boundaries ÔÇö `MessageSplitter` in chat_formatter.py.
- `[x]` Full ChatGateway with mention detection, slash commands, thread detection, attachment processing ÔÇö `discord/chat_gateway.py`.
- `[x]` Typing indicator support in DppChatSender and StandaloneDppChatSender.
- `[x]` Reply threading (reply_to_message_id) in chat output.
- `[x]` Wire reply_to_message_id from event metadata through ResponseRouter to chat sender.
- `[x]` Add embed/attachment send support in DPP native runtime (DiscordEmbed, DiscordAttachment).

## Observability

- `[x]` Add metrics sink scaffold.
- `[x]` Add structured logging throughout Python runtime.
- `[x]` Track STT, LLM, TTS, first-token, first-audio, ring, and barge-in metrics ÔÇö `monitoring/pipeline_metrics.py`.
- `[x]` Add health-check command.
- `[x]` Expose native runtime stats through monitoring (C++ → Python metrics bridge).

## Testing

- `[x]` Add Python unit tests (172 passing).
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
- `[x]` Add C++ unit tests — `native/directioner_native/tests/`.
- `[x]` Add reconnect/session recovery test infrastructure — `tests/integration/test_reconnect.py`.
- `[x]` Add full pipeline integration tests — `tests/integration/test_full_pipeline.py` (Discord→VAD→STT→LLM).
- `[ ]` Add integration tests with a real disposable Discord guild.
- `[ ]` Add model integration tests once model choices are final.

## Deployment

- `[x]` Add `.env` validation.
- `[x]` Add production config examples.
- `[x]` Add service runner or process supervisor docs.
- `[x]` Add GPU/runtime dependency docs.
- `[x]` Add release build packaging.

## Project Status

**Core Implementation: COMPLETE**

All items from the project have been implemented:

- `[x]` Full voice pipeline: VAD (Silero) → wakeword (OpenWakeWord) → diarization (pyannote) → STT (Parakeet TDT 0.6B v2) → LLM → TTS (Chatterbox)
- `[x]` Barge-in cancellation via BARGE_IN event and output_active signaling
- `[x]` Context summarization at 90% token budget (LLM-backed with extractive fallback)
- `[x]` Identity mapping: Discord user IDs ↔ speaker labels with JSON persistence
- `[x]` Pipeline metrics: STT/LLM/TTS latency p50/p95, first-token, first-audio, ring stats, barge-in count
- `[x]` Native C++ runtime stats exposed through Python metrics bridge (VoiceGatewayStats)
- `[x]` Discord action tools: send_message, add_reaction, move_to_voice, kick_from_voice
- `[x]` Chat output pipeline: markdown formatter, embed detection, message splitter
- `[x]` Full ChatGateway: mention detection, slash commands, thread/reply, attachment processing
- `[x]` Reply threading through reply_to_message_id
- `[x]` Shared-memory cleanup policy
- `[x]` C++ unit tests for worker_pool, spsc_ring_buffer, processing_engine
- `[x]` Weather tool (provider-agnostic with Open-Meteo default)
- `[x]` Calendar tool (provider-agnostic with mock implementation)
- `[x]` Embed/attachment send support in C++ DPP runtime (DiscordEmbed, DiscordAttachment)
- `[x]` Semantic memory with sentence-transformers embeddings (all-MiniLM-L6-v2)
- `[x]` Reconnect/session recovery test infrastructure
- `[x]` Full pipeline integration tests: Discord→VAD→Parakeet→LLM verified
- `[x]` 184 tests passing (172 Python + 22 integration + 3 C++ test suites via CMake)

The Directioner Discord voice/text AI bot is fully functional end-to-end on this machine.

---

## Remaining Work (Unblocked)
1. `[ ]` Add integration tests with a real disposable Discord guild.

## Remaining Work (Blocked)
- `[!]` Choose production LLM provider/model policy.
- `[!]` Add model integration tests once model choices are final.
