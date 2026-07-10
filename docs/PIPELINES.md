# Runtime Pipelines

## Voice Input

```text
Discord Voice Gateway
  -> DPP Voice Runtime
  -> RTP/Opus Receive
  -> PcmFrameHeader
  -> Jitter Buffer
  -> Packet-Loss Recovery
  -> Resampler
  -> Mixer
  -> Gain
  -> High-Pass Filter
  -> Noise Suppression
  -> Acoustic Echo Cancellation
  -> Automatic Gain Control
  -> Voice Activity Detection
  -> Shared Memory: voice_pcm_in
  -> Python VoiceInputReader
  -> Diarization
  -> Parakeet Streaming STT
  -> Text Processing
  -> Conversation Router
```

## Conversation And Planning

```text
Conversation Router
  -> Identity Resolution
  -> Session State
  -> Working Memory
  -> Conversation Memory
  -> Semantic Memory Retrieval
  -> User Preferences
  -> Intent Detection
  -> Tool Selection
  -> Multi-Step Planning
  -> Safety Checks
  -> Pipecat Orchestrator
  -> LLM Layer
```

## Voice Output

```text
LLM Stream
  -> Response Processing
  -> Sentence Chunking
  -> Prosody Hints
  -> Chatterbox Streaming TTS
  -> Shared Memory: tts_pcm_out
  -> PCM Buffering
  -> Resampler
  -> Opus Encoder
  -> RTP Packetizer
  -> DPP Discord Voice Transmission
```

## Chat Output

```text
LLM Stream
  -> Markdown Formatter
  -> Embed Generator
  -> Attachment Handler
  -> Message Splitter
  -> Discord API
  -> Chat Channel
```

## Barge-In And Cancellation

Voice activity while the assistant is speaking creates an interruption event:

1. C++ VAD emits an interrupt candidate with timing metadata.
2. Python Conversation Router confirms whether the speaker may interrupt.
3. Pipecat cancels in-flight LLM/tool/TTS work where safe.
4. Python writes an output-control event to drain or fade the outbound audio ring.
5. The new user utterance becomes the active turn.
