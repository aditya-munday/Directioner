# Directioner

Directioner is a real-time Discord voice and text AI system. The project is split into a low-latency C++ audio/Discord plane and a Python AI orchestration plane, connected through nanobind and shared-memory ring buffers.

## Architecture At A Glance

- C++ owns Discord connectivity through DPP, voice networking, RTP/UDP, Opus, jitter buffering, packet-loss recovery, real-time DSP, VAD, and outbound audio transport.
- Python owns AI orchestration, diarization, streaming STT, text cleanup, conversation state, memory, planning, tools, LLM calls, response shaping, and streaming TTS.
- nanobind exposes the native audio runtime and shared-memory handles to Python without turning real-time audio callbacks into Python callbacks.
- Shared-memory SPSC ring buffers carry high-frequency PCM frames and control events between the C++ and Python planes.

## Primary Runtime Flows

Voice:

```text
Discord Voice -> C++ Gateway -> C++ Audio Engine -> Shared PCM In
  -> Python Diarization -> Parakeet STT -> Text Processing
  -> Conversation Router -> Memory -> Planner -> Pipecat -> LLM
  -> Response Processing -> Chatterbox TTS -> Shared PCM Out
  -> C++ Output Engine -> Discord Voice
```

Text chat:

```text
Discord Chat -> C++ DPP Process -> Python Bridge -> Conversation Router -> Memory
  -> Planner -> Pipecat -> LLM -> Tools -> Response Formatter
  -> Discord Chat Reply
```

## Repository Layout

- `src/directioner/` - Python AI plane and orchestration package.
- `native/directioner_native/` - C++ DPP Discord runtime, real-time audio plane, shared-memory protocol, and nanobind extension.
- `configs/` - example runtime, model, Discord, and observability configuration.
- `docs/` - architecture, file structure, pipeline, and shared-memory design notes.
- `tests/` - unit, integration, native, and contract tests.
- `TODO.md` - active project completion checklist.
- `CONTEXT.md` - current handoff context and setup state.
- `PROGRESS.md` - latest working progress, fixes, and full runbook/commands.

## Build And Test

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install nanobind PyYAML pytest pytest-asyncio
powershell -ExecutionPolicy Bypass -File .\scripts\build-native.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run-discord.ps1 -SmokeFirst
```

Runtime checks:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m directioner.app validate-env
.\.venv\Scripts\python.exe -m directioner.app health-check
```

`run-discord.ps1` starts the Python bridge over the standalone native DPP process by default. The embedded Python/nanobind DPP path is currently diagnostic-only because this vcpkg DPP build crashes when `dpp::cluster` is constructed inside the Python extension process.

## Current Implementation Slice

- Native DPP runtime scaffold with bot lifecycle, text event polling, slash-command hooks, voice join/leave, PCM send, and voice receive capture.
- Native named shared-memory mappings plus SPSC ring initialization.
- DPP voice receive can attach to `voice_pcm_in` and write `PcmFrameHeader + PCM` frames into shared memory.
- Python can read `voice_pcm_in`, parse `PcmFrameHeader`, and write raw PCM to `tts_pcm_out`.
- Python `VoiceInputPipeline` routes shared-memory PCM through diarization/STT/text cleanup into the Conversation Router.
- Python `DppEventPump` routes native text events into the shared Conversation Router.
- Python `StandaloneDppProcess` supervises the standalone DPP executable and sends chat responses back through stdin IPC.

See `CONTEXT.md`, `TODO.md`, `docs/ARCHITECTURE.md`, `docs/FILE_STRUCTURE.md`, `docs/BUILDING.md`, and `docs/OPERATIONS.md` for the full design and current state.

## Built-in Tooling

Directioner currently includes these built-in tools in the default registry:

- `calculator` for safe arithmetic evaluation.
- `web_search` for public-web lookup snippets (DuckDuckGo instant-answer API).
- `read_file` and `list_directory` for sandboxed file exploration under `DIRECTIONER_TOOL_BASE_DIR` (defaults to current working directory).
