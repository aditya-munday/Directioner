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
- Chat output formatter: markdown normalisation, embed detection, smart message splitter
- Full ChatGateway: mention detection, slash commands, thread/reply, attachment summarisation
- Discord action tools: send_message, add_reaction, move_to_voice, kick_from_voice
- ABI contract tests: PcmFrameHeader layout verified
- Shared-memory cleanup policy implemented
- **140 tests passing**

Not yet production-complete:

- Native C++ unit tests not added
- Vector DB / embedding backend not chosen
- Reconnect/session recovery tests not added
- Embed/attachment send support in DPP native runtime (C++ side)

---

## What Was Completed In This Pass

### Full Voice Pipeline (end-to-end)

- `audio/vad.py` — Silero VAD: lazy-loads via torch.hub, 48 kHz stereo → 16 kHz mono, 512-sample chunks
- `audio/wakeword.py` — OpenWakeWord: lazy-loads, 1280-sample chunks, configurable threshold
- `diarization/service.py` — pyannote.audio speaker diarization with energy-based fallback
- `stt/parakeet_stream.py` — NeMo Parakeet TDT 0.6B v2, accumulates per-speaker audio, transcribes on FINAL flag
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

### Tools

- `tools/discord_actions.py` — discord_send_message, discord_add_reaction, discord_move_to_voice, discord_kick_from_voice

### Chat Output Pipeline

- `discord/chat_formatter.py` — MarkdownFormatter, EmbedDetector, MessageSplitter, ChatOutputFormatter
- `discord/chat_gateway.py` — Full ChatGateway: mention detection, slash commands, thread/reply, attachment summarisation, typing indicator
- `discord/chat_output.py` — DppChatSender with formatter, reply threading, typing indicator, cooldown
- `discord/standalone_process.py` — StandaloneDppChatSender updated to use ChatOutputFormatter, reply_to, send_typing

### Infrastructure

- `audio/cleanup.py` — cleanup_on_startup / cleanup_on_shutdown for stale shared-memory rings
- `config/settings.py` — VadSettings, WakeWordSettings, SttSettings, TtsSettings added
- `configs/app.example.yaml` — vad, wakeword, stt, tts sections added
- `pyproject.toml` — torch in core deps, [voice] extra for nemo/chatterbox/openwakeword

### Tests (140 passing)

- `tests/unit/test_vad.py` — 4 tests
- `tests/unit/test_wakeword.py` — 5 tests
- `tests/unit/test_voice_pipeline.py` — 6 tests (updated with barge-in stats)
- `tests/unit/test_voice_output_pipeline.py` — 7 tests
- `tests/unit/test_summarizer.py` — 4 tests
- `tests/unit/test_identity.py` — 5 tests
- `tests/unit/test_pipeline_metrics.py` — 13 tests
- `tests/unit/test_discord_action_tools.py` — 6 tests
- `tests/unit/test_chat_formatter.py` — 8 tests
- `tests/contracts/test_pcm_frame_abi.py` — 5 ABI contract tests

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
