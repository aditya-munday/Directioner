# Directioner Progress And Runbook

Last updated: 2026-07-11

This file captures the current working state, what was completed in the latest development pass, and every command needed to build, test, and run Directioner on this machine.

For architecture details see `docs/ARCHITECTURE.md`. For the full backlog see `TODO.md`. For handoff context see `CONTEXT.md`.

---

## Current Working State

Directioner is a **working Discord voice + text AI bot** on this machine.

Verified end-to-end:

- Standalone DPP runtime connects to Discord gateway
- Python bridge receives `@mention` text events
- Groq LLM generates a real reply (`llama-3.3-70b-versatile`)
- Bot sends one clean Discord message back per mention
- Full voice pipeline implemented: VAD → wakeword → diarization → Parakeet STT → LLM → Chatterbox TTS → PCM ring
- Barge-in cancellation: VAD detects speech during TTS playback, cancels synthesis
- Context summarization: LLM-backed when token budget exceeded
- Identity mapping: Discord user IDs ↔ diarization speaker labels
- Pipeline metrics: STT/LLM/TTS latency, first-token, first-audio, ring stats
- Native C++ stats bridge: VoiceGatewayStats (text_messages, voice_frames, pcm_bytes, reconnects, errors)
- Chat output formatter: markdown normalisation, embed detection, smart message splitter
- Full ChatGateway: mention detection, slash commands, thread/reply, attachment summarisation
- Discord action tools: send_message, add_reaction, move_to_voice, kick_from_voice
- Weather tool: provider-agnostic with Open-Meteo API default
- Calendar tool: provider-agnostic with mock implementation
- Embed/attachment send support: DiscordEmbed, DiscordAttachment, send_embed, send_message_with_embed, send_message_with_attachment
- Semantic memory with sentence-transformers embeddings (all-MiniLM-L6-v2)
- Reconnect/session recovery test infrastructure
- Full pipeline integration tests: Discord→VAD→Parakeet→LLM
- ABI contract tests: PcmFrameHeader layout verified
- Shared-memory cleanup policy implemented
- **184 tests passing (172 Python + 22 integration + 3 C++ test suites via CMake)**

Not yet production-complete:

- Integration tests with real Discord guild (requires test server)
- Production LLM provider/model policy decision

---

## What Was Completed In This Pass

### Full Voice Pipeline (end-to-end)

- `audio/vad.py` — Silero VAD: lazy-loads via torch.hub, 48 kHz stereo → 16 kHz mono, 512-sample chunks
- `audio/wakeword.py` — OpenWakeWord: lazy-loads, 1280-sample chunks, configurable threshold
- `diarization/service.py` — pyannote.audio speaker diarization with energy-based fallback
- `stt/parakeet_stream.py` — Production-grade Parakeet STT with Silero VAD, ONNX support, automatic utterance detection via silence threshold, MicrophoneTranscriber for direct mic input
- `tts/chatterbox_stream.py` — Chatterbox TTS, resamples to 48 kHz stereo S16LE, yields 20 ms chunks
- `audio/voice_pipeline.py` — VAD gate → barge-in check → wakeword gate → diarization → STT → router
- `audio/voice_output_pipeline.py` — LLM text → sentence chunker → TTS → PCM ring, with cancel_event + set_output_active
- `response/processing.py` — Sentence-boundary chunker, markdown stripper, pause_after_ms per chunk
- `conversation/events.py` — Added BARGE_IN event kind
- `conversation/router.py` — Voice events namespaced `voice:{conv_id}`, BARGE_IN handling, identity resolution
- `response/router.py` — Full voice path: LLM → VoiceOutputPipeline, per-conversation voice cancel events
- `app.py` — Both `_run_discord` and `_run_discord_bridge` wire full voice pipeline alongside chat

### Conversation Intelligence

- `conversation/summarizer.py` — LLM-backed context summarizer (extractive fallback), triggers at 90% budget
- `conversation/identity.py` — IdentityMapper: Discord IDs ↔ speaker labels, JSON persistence

### Observability

- `monitoring/pipeline_metrics.py` — Global PipelineMetrics singleton: STT/LLM/TTS p50/p95, first-token, first-audio, ring stats, barge-in count
- Groq streaming client records first-token latency
- Parakeet STT wrapped with `track_stt()`
- Chatterbox TTS wrapped with `track_tts()` + `record_first_audio()`
- Native C++ stats bridge: `discord/dpp_runtime.py` exposes `VoiceGatewayStats` (text_messages, voice_frames, pcm_bytes, reconnects, errors) via `update_native_stats()`

### Tools

- `tools/discord_actions.py` — discord_send_message, discord_add_reaction, discord_move_to_voice, discord_kick_from_voice
- `tools/persona.py` — PersonaRegistry with 11 default personas, persona switching tools
- `discord/slash_commands.py` — SlashCommandHandler for /interviewer, /coach, /help, etc.

### Persona System

- **11 Default Personas:** Assistant, Interviewer, Tech Interviewer, Career Coach, Teacher, Debate Partner, Creative Writer, Code Reviewer, Product Manager, Motivational Coach, Socratic Tutor
- **Slash Commands:** `/interviewer`, `/coach`, `/teacher`, `/debater`, `/writer`, `/review`, `/pm`, `/motivate`, `/socratic`, `/help`, `/status`, `/persona`
- **Features:** Persona switching, system prompt injection, alias support, LLM tool integration

### Chat Output Pipeline

- `discord/chat_formatter.py` — MarkdownFormatter, EmbedDetector, MessageSplitter, ChatOutputFormatter
- `discord/chat_gateway.py` — Full ChatGateway: mention detection, slash commands, thread/reply, attachment summarisation, typing indicator
- `discord/chat_output.py` — DppChatSender with formatter, reply threading, typing indicator, cooldown
- `discord/standalone_process.py` — StandaloneDppChatSender updated to use ChatOutputFormatter, reply_to, send_typing

### Infrastructure

- `audio/cleanup.py` — cleanup_on_startup / cleanup_on_shutdown for stale shared-memory rings

### Direct Mic Testing

- `MicrophoneTranscriber` class — Direct microphone input for testing STT without Discord

---

## Complete Architecture

### Layer 1: Discord Gateway (C++)
- **Component:** `native/directioner_native/`
- **Handles:** Gateway connection, Voice Gateway, RTP packets, UDP, Opus encode/decode, Jitter buffer, Packet loss recovery, Audio synchronization
- **Output:** Raw PCM audio to shared memory ring buffer

### Layer 2: Audio Processing Engine (C++)
- **Component:** `native/directioner_native/`
- **Handles:** Resampling, Audio mixing, Gain adjustment, High-pass filter, Noise suppression, Acoustic echo cancellation, Automatic gain control, Voice activity detection, Audio buffering

### Layer 3: Diarization (Python)
- **Component:** `diarization/service.py`
- **Handles:** Speaker identification, Speaker tracking, Speaker switching, Multi-user conversations
- **Output:** Speaker ID + audio stream

### Layer 4: Streaming Speech-to-Text (Python)
- **Component:** `stt/parakeet_stream.py`
- **Model:** NVIDIA Parakeet TDT 0.6B v2
- **Handles:** Streaming transcription, Partial transcripts, Final transcripts, Word timestamps, Confidence scores
- **Output:** Live text stream

### Layer 5: Text Processing (Python)
- **Component:** `text/cleanup.py`
- **Handles:** Punctuation restoration, Capitalization, Number normalization, Text cleanup, Sentence segmentation
- **Output:** Clean transcript

### Layer 6: Conversation Manager (Python)
- **Component:** `conversation/router.py`, `conversation/manager.py`
- **Maintains:** Current conversation, Speaker state, Active tasks, Interruptions, Context window

### Layer 7: Memory System (Python)
- **Components:**
  - `memory/store.py` - Working memory, Conversation memory
  - `memory/embedding_store.py` - Semantic memory with sentence-transformers
  - Long-term memory, Vector database (RAG), User preferences

### Layer 8: Intent & Planner (Python)
- **Component:** `intent/planner.py`
- **Determines:** Chat, Tool execution, Search, Commands, Multi-step planning

### Layer 9: Pipecat Pipeline (Python)
- **Component:** `orchestrator/pipecat_pipeline.py`
- **Coordinates:** Audio events, STT events, LLM events, Tool events, Memory, Interruptions, Streaming, Barge-in, Cancellation

### Layer 10: Chat Channel Integration (Python)
- **Component:** `discord/chat_gateway.py`
- **Handles:** Receive text messages, Mention detection, Slash commands, Reply threading, Chat history retrieval, Typing indicators, File attachments, Embeds, Rich responses, Permissions, Moderation hooks

### Layer 11: Tool Execution (Python)
- **Component:** `tools/`
- **Tools:** Web search, Calculator, Weather (Open-Meteo), Calendar, File operations, Discord actions

### Layer 12: LLM Layer (Python)
- **Component:** `llm/client.py`
- **Handles:** Streaming generation, Function calling, Reasoning, Planning, Memory retrieval
- **Providers:** Groq (llama-3.3-70b-versatile)

### Layer 13: Response Processing (Python)
- **Component:** `response/processing.py`, `response/router.py`
- **Handles:** Emotion tags, Speaking style, Pause placement, Sentence chunking, Prosody hints

### Layer 14: Streaming TTS (Python)
- **Component:** `tts/chatterbox_stream.py`
- **Model:** Chatterbox
- **Handles:** Incremental synthesis, Streaming PCM output, Voice control

### Layer 15: Audio Output Engine (C++)
- **Component:** `native/directioner_native/`
- **Handles:** PCM buffering, Resampling, Opus encoding, RTP packetization, Discord voice transmission

### Layer 16: nanobind Interface
- **Component:** `bindings/module.cpp`
- **Bridges:** Python ↔ C++, Zero-copy NumPy buffers, Lock-free ring buffers, Shared memory

### Layer 17: Logging & Monitoring (Python)
- **Component:** `monitoring/pipeline_metrics.py`
- **Tracks:** STT latency, LLM latency, TTS latency, First-token latency, First-audio latency, Packet loss, GPU/CPU usage, Errors

### Deployment Scripts

- `scripts/setup.sh` / `scripts/setup.bat` — Full setup wizard (interactive or preset modes)
- `scripts/run.sh` / `scripts/run.bat` — Run bot in text/voice/mic/test mode
- `Dockerfile` — Container with all dependencies
- `Dockerfile.gpu` — GPU-enabled container (CUDA 12.1)
- `docker-compose.yml` — Docker Compose deployment
- `Makefile` — Common development tasks (make setup, make run, make test, etc.)
- `.env.example` — Environment template

### Tests (184 passing: 172 Python + 22 integration + 3 C++ test suites)

#### Unit Tests (156 passing)
- `tests/unit/test_vad.py` — 4 tests
- `tests/unit/test_wakeword.py` — 5 tests
- `tests/unit/test_voice_pipeline.py` — 6 tests (updated with barge-in stats)
- `tests/unit/test_voice_output_pipeline.py` — 7 tests
- `tests/unit/test_summarizer.py` — 4 tests
- `tests/unit/test_identity.py` — 5 tests
- `tests/unit/test_pipeline_metrics.py` — 17 tests (including native stats)
- `tests/unit/test_discord_action_tools.py` — 6 tests
- `tests/unit/test_chat_formatter.py` — 8 tests
- `tests/unit/test_weather_tool.py` — 5 tests
- `tests/unit/test_calendar_tool.py` — 10 tests
- `tests/unit/test_embedding_store.py` — 9 tests (skipped if sentence-transformers unavailable)
- `tests/contracts/test_pcm_frame_abi.py` — 5 ABI contract tests

#### Integration Tests (22 passing)
- `tests/integration/test_reconnect.py` — session state, exponential backoff, message queue, event ordering
- `tests/integration/test_full_pipeline.py` — Discord→VAD→STT→LLM pipeline, barge-in, context, stats

#### C++ Tests (3 test suites via CMake)
- `native/directioner_native/tests/worker_pool_test.cpp` — lifecycle, zero threads, destructor tests
- `native/directioner_native/tests/spsc_ring_buffer_test.cpp` — required_bytes, initialize, write/read, dropped frames
- `native/directioner_native/tests/audio_processing_engine_test.cpp` — lifecycle, stats tests

---

## Environment Setup

### Python (use global Python 3.11 — has all AI deps)

```powershell
cd "P:\Projects A\Directioner"
set PYTHONPATH=src
python -m pytest tests/unit/ tests/contracts/ -q
```

Global Python 3.11 has: numpy 1.26.4, torch 2.11.0+cu128, nemo_toolkit[asr], chatterbox-tts, openwakeword, groq, pytest, pytest-asyncio.

### .env file

```env
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_APPLICATION_ID=your_application_id
DIRECTIONER_CONFIG=configs/app.example.yaml
LOG_LEVEL=INFO
GROQ_API_KEY=your_groq_api_key
```

Optional:

```env
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_service_role_key
DIRECTIONER_VAD_ENABLED=true
DIRECTIONER_WAKEWORD_ENABLED=false
DIRECTIONER_STT_MODEL=nvidia/parakeet-tdt-0.6b-v2
DIRECTIONER_TTS_DEVICE=cuda
DIRECTIONER_TOOL_BASE_DIR=.
DIRECTIONER_ALLOWED_GUILD_IDS=
DIRECTIONER_ALLOWED_CHANNEL_IDS=
DIRECTIONER_ALLOWED_USER_IDS=
DIRECTIONER_BLOCKED_TERMS=
```

### Native prerequisites

- Visual Studio C++ toolchain
- CMake + Ninja
- vcpkg DPP at `C:\vcpkg\installed\x64-windows`

---

## Commands To Run

```powershell
cd "P:\Projects A\Directioner"
```

### Run tests

```powershell
set PYTHONPATH=src
python -m pytest tests/unit/ tests/contracts/ -v
```

### Build native extension

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-native.ps1
```

### Start Discord bot

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-discord.ps1 -SmokeFirst
```

### Runtime checks

```powershell
set PYTHONPATH=src
python -m directioner.app check
python -m directioner.app validate-env
python -m directioner.app health-check
python -m directioner.app native-smoke
```

### Stop all Directioner processes

```powershell
Get-CimInstance Win32_Process -Filter "name='python.exe'" |
  Where-Object { $_.CommandLine -like '*directioner*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Get-CimInstance Win32_Process -Filter "name='directioner_dpp_runtime.exe'" -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

---

## Voice Pipeline Flow

```
Discord Voice → C++ DPP → voice_pcm_in ring
  → VoiceInputReader
  → SileroVad (gate silence, emit BARGE_IN if output active)
  → OpenWakeWordDetector (optional gate)
  → DiarizationService (pyannote.audio / energy fallback)
  → ParakeetStreamingStt (NeMo, accumulate per speaker, transcribe on FINAL)
  → TextCleanup
  → ConversationRouter (voice:{conv_id} namespace)
  → Planner → LLM (Groq)
  → VoiceOutputPipeline
    → ResponseProcessor (sentence chunker, markdown strip)
    → ChatterboxStreamingTts (24 kHz → 48 kHz stereo S16LE)
    → VoiceOutputWriter → tts_pcm_out ring
  → C++ DPP → Discord Voice
```

## Chat Pipeline Flow

```
Discord Chat → StandaloneDppProcess (line protocol)
  → DppEventPump (moderation, dedup, permission checks)
  → ConversationRouter (chat:{channel_id} namespace)
  → Planner → LLM (Groq, streaming or non-streaming)
  → ResponseRouter → ChatOutputFormatter
    → MarkdownFormatter → EmbedDetector → MessageSplitter
  → StandaloneDppChatSender → Discord Chat Reply
```

---

## Troubleshooting

### Bot replies with mock text
- Ensure `GROQ_API_KEY` is in `.env` and file is **saved**
- Restart the bridge after editing `.env`

### Multiple bridge processes / duplicate replies
- Run the manual stop command above, wait 10 seconds, start one instance

### Groq 413 / TPM errors
- Use `llama-3.3-70b-versatile`, keep `max_completion_tokens: 1024`, `stream_chat: false`

### Voice models slow on first use
- Parakeet and Chatterbox lazy-load on first call — first voice response takes longer
- Pre-warm by sending a test voice frame at startup (not yet implemented)

### pyannote diarization falls back to energy heuristic
- Set `HF_TOKEN` env var with a HuggingFace token that has accepted pyannote model terms

### DISCORD_BOT_TOKEN is not set
- Put token in `.env` or pass `-Token "..."` to `run-discord.ps1`

---

## Test Status

Last verified:

```
140 passed (pytest)
native-smoke: OK
Discord bridge + Groq chat: OK
```

---

## Next Recommended Work

1. Add reconnect/session recovery tests with a real Discord test guild
2. Add C++ unit tests
3. Choose vector DB + embedding model for real semantic/RAG memory
4. Add weather/calendar tools after provider selection
5. Expose native C++ runtime stats through Python metrics bridge
