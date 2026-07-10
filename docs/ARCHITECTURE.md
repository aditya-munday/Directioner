# Directioner Architecture

## Goal

Directioner is designed as a real-time multimodal Discord assistant. Voice and text interactions share the same identity, conversation state, memory, planner, tools, and response routing so users can switch between speaking and typing without losing context.

## Planes

### C++ Discord And Real-Time Audio Plane

The C++ plane owns Discord connectivity through DPP and everything with tight latency, timing, packet, or callback constraints:

- Discord Gateway, text-message events, slash commands, voice join/leave, and voice session state through DPP.
- Discord Voice Gateway session management.
- UDP, RTP, sequence numbers, timestamps, and packet scheduling.
- Opus encode/decode.
- Jitter buffering and packet-loss recovery.
- PCM frame buffering.
- DSP: resampling, mixing, gain, high-pass filtering, noise suppression, AEC, AGC, and VAD.
- Outbound PCM buffering, Opus encoding, RTP packetization, and Discord voice transmission.
- Real-time worker threads and bounded queues.

Python code never runs inside C++ audio callbacks. Python receives and sends audio through shared-memory ring buffers.

### Python AI Orchestration Plane

The Python plane owns model-driven and stateful behavior:

- Routing and AI handling for Discord text events surfaced by the native DPP runtime.
- Reply formatting, embeds, attachments, permissions, and moderation hooks.
- Diarization and speaker tracking.
- NVIDIA Parakeet streaming STT integration.
- Text cleanup: punctuation, capitalization, number normalization, and sentence segmentation.
- Conversation routing across voice and text.
- Working, conversation, long-term, semantic, and user preference memory.
- Intent detection, planning, safety checks, and tool selection.
- Pipecat pipeline orchestration.
- LLM streaming, reasoning, and function calling.
- Response processing, emotion tags, speaking style, pauses, and prosody hints.
- Chatterbox streaming TTS.
- Logging, metrics, tracing, and health checks.

### Bridge Plane

The bridge uses process IPC, nanobind, and shared memory:

- nanobind exposes lifecycle controls, native statistics, shared-memory descriptors, and low-frequency configuration calls.
- The standalone DPP executable emits structured text events on stdout and receives low-frequency command messages on stdin when DPP cannot safely live inside the Python process.
- Shared-memory ring buffers carry high-frequency audio and event frames.
- Python sees native buffers through NumPy-compatible views where practical.
- The bridge contract is versioned and tested with contract tests.

## Component Topology

```text
                       +---------------------------+
                       |      Discord Gateway      |
                       |  chat events + voice rtc  |
                       +-------------+-------------+
                                     |
              +----------------------+----------------------+
              |                                             |
              v                                             v
   +-------------------------+                 +-------------------------+
   | Python Event Router     |                 | C++ DPP Runtime         |
   | AI orchestration        |                 | chat, voice, slash cmds |
   +------------+------------+                 +------------+------------+
                |                                           |
                v                                           v
   +-------------------------+                 +-------------------------+
   | Conversation Router     |<-- shared PCM --| C++ Audio Engine        |
   | one entry for all input |                 | DSP, VAD, buffering     |
   +------------+------------+                 +------------+------------+
                |                                           ^
                v                                           |
   +-------------------------+                 +-------------------------+
   | Memory + Planner        |                 | C++ Output Engine       |
   | RAG, tools, state       |                 | Opus, RTP, scheduling   |
   +------------+------------+                 +------------+------------+
                |                                           ^
                v                                           |
   +-------------------------+      PCM out     +-------------------------+
   | Pipecat + LLM + TTS     |---------------->| Shared Output Ring      |
   | streaming orchestration |                 | Python producer         |
   +-------------------------+                 +-------------------------+
```

## Voice Pipeline

1. C++ uses DPP to join the Discord voice session and receives decoded voice audio events from DPP.
2. C++ wraps DPP PCM receive events in Directioner's `PcmFrameHeader` format.
3. C++ writes PCM frames and timing metadata into the `voice_pcm_in` shared-memory ring.
4. The C++ audio processing engine applies resampling, gain, filters, noise suppression, AEC, AGC, and VAD as the DSP implementation is filled in.
5. Python reads PCM frames, performs diarization, streams audio to Parakeet STT, and emits partial/final transcripts.
6. Python normalizes text and forwards utterances to the Conversation Router.
7. The Conversation Router merges the event with session state, memory, and speaker identity.
8. The Planner decides whether to chat, call tools, search, execute commands, or run a multi-step plan.
9. Pipecat coordinates streaming LLM output, function calls, cancellation, and barge-in.
10. Response Processing chunks text for speech and adds speaking-style metadata.
11. Chatterbox produces streaming PCM chunks into the output shared-memory ring.
12. C++ reads output PCM, resamples if needed, encodes Opus, packetizes RTP, and sends audio back to Discord.

## Text Pipeline

1. C++ DPP receives a Discord message, slash command, reply, thread message, or mention.
2. The standalone DPP process emits a structured IPC event for Python, or the embedded diagnostic path exposes the same event shape through nanobind.
3. Python polls the bridge through `DppEventPump`.
4. Bot-authored messages are ignored to prevent response loops.
5. The Conversation Router merges the text event with the same state used by voice.
6. Memory retrieval and planning run as they do for voice input.
7. The response layer calls the configured responder, then sends chat output back through the native DPP runtime.
8. Markdown formatting, embeds, attachments, and message splitting are applied before replying through the Discord API.

## Concurrency Model

- C++ uses dedicated worker threads for voice network IO, decode, DSP, encode, and packet scheduling.
- Shared-memory rings are single-producer/single-consumer per channel to keep the hot path lock-free.
- Python uses `asyncio` for Discord chat, model streaming, tools, memory retrieval, and Pipecat orchestration.
- CPU or GPU-heavy model work is isolated behind async adapters that support cancellation.
- Backpressure is explicit. If rings fill, the writer drops or compresses frames according to the channel policy and increments metrics.

## Shared State Model

The Conversation Router is the single entry point for user interactions. It owns:

- Conversation id.
- Discord guild, channel, thread, and voice-session identity.
- Speaker id and user id mapping.
- Active task id.
- Barge-in/cancellation state.
- Current context window.
- Recent tool calls.
- Memory retrieval references.

Voice and text events become the same internal `ConversationEvent` shape before they reach planning.

## Latency Budget

Target first-response behavior:

- Voice packet receive to clean PCM frame: under 40 ms.
- Clean PCM frame to STT partial: model-dependent, tracked continuously.
- Final transcript to first LLM token: under 800 ms for simple turns.
- First TTS audio after response text begins: under 500 ms where the model allows it.
- PCM output frame to Discord packet send: under 40 ms.

The numbers are goals, not hard guarantees. Every stage emits metrics so the slow stage is visible.

## Failure Boundaries

- C++ audio sessions can restart without destroying Python conversation memory.
- Python AI tasks can cancel without tearing down the Discord voice socket.
- Shared-memory versions are checked at startup and by contract tests.
- Model failures route to chat or voice fallback responses.
- Tool failures become structured planner observations.
- Discord reconnects preserve session state when Discord identity remains stable.
