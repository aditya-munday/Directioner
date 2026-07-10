# Directioner Context

This file is the project handoff context. Read it first when resuming work.

## Current State

Directioner is a Discord voice/text AI assistant using:

- C++ for Discord/DPP, real-time audio, Opus, jitter buffering, VAD, and shared-memory ring buffers.
- Python for AI orchestration, diarization, STT, LLM, TTS, memory, tools, and conversation routing.
- nanobind for Python/C++ control APIs.
- OS named shared memory + SPSC ring buffers for high-rate PCM.

The full voice pipeline is implemented end-to-end. The chat pipeline is fully working. 140 tests pass.

## Verified Working

- DPP-enabled native extension builds in Release mode.
- `_native.cp312-win_amd64.pyd` imports from Python.
- SharedMemoryRegion create/open, SPSC ring read/write through nanobind.
- `voice_pcm_in` carries `PcmFrameHeader + PCM`.
- `tts_pcm_out` carries raw PCM for native Discord voice output.
- DPP text events polled into Python, chat responses sent back.
- Standalone DPP process bridges text events into Python via line protocol.
- Groq LLM (llama-3.3-70b-versatile) generates real replies end-to-end.
- Memory layer: durable conversation, user preferences, local semantic, Supabase-backed.
- Silero VAD gates speech frames before STT.
- OpenWakeWord detector gates utterances behind a wake word (optional).
- pyannote.audio diarization with energy-based fallback.
- Parakeet TDT 0.6B v2 STT adapter (lazy-loads NeMo).
- Chatterbox TTS adapter (lazy-loads, resamples to 48 kHz stereo S16LE).
- VoiceOutputPipeline: LLM → sentence chunker → TTS → PCM ring, with barge-in cancel.
- BARGE_IN event kind: VAD detects speech during TTS playback, cancels synthesis.
- Context summarizer: LLM-backed (extractive fallback) when token budget exceeded.
- Identity mapper: Discord user IDs ↔ diarization speaker labels, persisted to JSON.
- Pipeline metrics: STT/LLM/TTS latency p50/p95, first-token, first-audio, ring stats, barge-in count.
- Discord action tools: send_message, add_reaction, move_to_voice, kick_from_voice.
- Chat output formatter: markdown normalisation, embed/URL detection, smart message splitter.
- Full ChatGateway: mention detection, slash commands, thread/reply detection, attachment summarisation.
- ABI contract tests: PcmFrameHeader layout verified against documented wire protocol.
- Shared-memory cleanup policy: `audio/cleanup.py` unlinks stale rings on startup/shutdown.
- Test suite: 140 tests passing.

## Important Commands

Run tests (global Python — has numpy, torch, nemo, chatterbox, openwakeword):

```powershell
cd "P:\Projects A\Directioner"
set PYTHONPATH=src
python -m pytest tests/unit/ tests/contracts/ -v
```

Build DPP-enabled native extension:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-native.ps1
```

Start Discord bot (standalone DPP + Python bridge):

```powershell
$env:DISCORD_BOT_TOKEN = "..."
powershell -ExecutionPolicy Bypass -File .\scripts\run-discord.ps1 -SmokeFirst
```

Runtime checks:

```powershell
set PYTHONPATH=src
python -m directioner.app check
python -m directioner.app validate-env
python -m directioner.app health-check
python -m directioner.app native-smoke
```

## Local Dependency Assumptions

- Global Python 3.11 has: numpy, torch (CUDA), nemo_toolkit[asr], chatterbox-tts, openwakeword, groq, pytest, pytest-asyncio.
- DPP via vcpkg at `C:\vcpkg\installed\x64-windows`.
- Visual Studio dev command: `C:\Program Files\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat`.
- `directioner.native` registers DLL directories for vcpkg and Python before importing `_native`.
- Embedded DPP inside the Python/nanobind extension currently crashes during `dpp::cluster` construction — keep as diagnostic only via `run-discord.ps1 -Embedded`.

## Key Files

| Area | File |
|------|------|
| App entrypoint | `src/directioner/app.py` |
| Conversation router | `src/directioner/conversation/router.py` |
| Context summarizer | `src/directioner/conversation/summarizer.py` |
| Identity mapper | `src/directioner/conversation/identity.py` |
| Response router | `src/directioner/response/router.py` |
| Response processor (TTS chunker) | `src/directioner/response/processing.py` |
| Silero VAD | `src/directioner/audio/vad.py` |
| OpenWakeWord | `src/directioner/audio/wakeword.py` |
| Voice input pipeline | `src/directioner/audio/voice_pipeline.py` |
| Voice output pipeline | `src/directioner/audio/voice_output_pipeline.py` |
| Shared-memory cleanup | `src/directioner/audio/cleanup.py` |
| Diarization | `src/directioner/diarization/service.py` |
| Parakeet STT | `src/directioner/stt/parakeet_stream.py` |
| Chatterbox TTS | `src/directioner/tts/chatterbox_stream.py` |
| LLM facade | `src/directioner/llm/client.py` |
| Memory store | `src/directioner/memory/store.py` |
| Pipeline metrics | `src/directioner/monitoring/pipeline_metrics.py` |
| Discord action tools | `src/directioner/tools/discord_actions.py` |
| Chat formatter | `src/directioner/discord/chat_formatter.py` |
| Chat gateway | `src/directioner/discord/chat_gateway.py` |
| Chat output | `src/directioner/discord/chat_output.py` |
| Standalone DPP bridge | `src/directioner/discord/standalone_process.py` |
| ABI contract tests | `tests/contracts/test_pcm_frame_abi.py` |
| Settings | `src/directioner/config/settings.py` |

## Architecture Decisions

- DPP is the Discord C++ runtime.
- Python does not run inside real-time native audio callbacks.
- nanobind is for lifecycle/control APIs only — not hot audio callbacks.
- High-rate audio crosses the Python/C++ boundary through shared memory SPSC rings.
- `PcmFrameHeader` is packed to 48 bytes, little-endian, verified by ABI contract tests.
- Voice input uses `voice_pcm_in`; TTS output uses `tts_pcm_out`.
- Voice events use a `voice:{conv_id}` conversation namespace — completely separate from chat state.
- BARGE_IN fires when VAD detects speech while `_output_active=True` on the input pipeline.
- Context summarization triggers at 90% of token budget, replaces oldest half with LLM summary.
- Identity mapper links pyannote speaker labels to Discord user IDs via `discord_id` metadata hint.
- Pipeline metrics are a global singleton reset per test via `reset_metrics()`.

## Open Choices Needed From User

- Production LLM provider/model (currently Groq llama-3.3-70b-versatile).
- Vector database + embedding model for real semantic/RAG memory.
- Whether Parakeet/Chatterbox run in-process, sidecar, or behind inference servers.
- Production Discord guild and permission policy.
- Weather/calendar tool provider.

## Current Risks

- DPP voice receive is best-effort (Discord does not officially support bot voice receive).
- pyannote.audio requires a HuggingFace token for the speaker-diarization-3.1 model — falls back to energy heuristic without it.
- Chatterbox and Parakeet lazy-load on first use — first voice response will be slow.
- Native C++ unit tests not yet added.
- reply_to_message_id not yet threaded from event metadata back through ResponseRouter to chat sender.

## How To Continue

1. Check `TODO.md` — pick first unblocked item.
2. Run `python -m pytest tests/unit/ tests/contracts/ -q` after every Python change.
3. Run `scripts/build-native.ps1` after native changes.
4. Update this file and PROGRESS.md when major state changes.
