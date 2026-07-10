# Shared Memory Protocol

## Purpose

Shared memory carries high-frequency audio frames and low-latency control events between C++ and Python without making the audio path depend on Python callbacks.

## Transport Shape

Each channel is a single-producer/single-consumer ring buffer.

```text
+-----------------------+
| RingBufferHeader      |
| magic/version/layout  |
| write sequence        |
| read sequence         |
| counters              |
+-----------------------+
| byte ring payload     |
| length-prefixed frame |
| length-prefixed frame |
| ...                   |
+-----------------------+
```

## Channels

| Channel | Producer | Consumer | Payload |
| --- | --- | --- | --- |
| `voice_pcm_in` | C++ | Python | Clean PCM frames with frame metadata |
| `voice_events_in` | C++ | Python | VAD, packet loss, timing, reconnect, and underrun events |
| `tts_pcm_out` | Python | C++ | Streaming PCM from TTS |
| `voice_control_out` | Python | C++ | Stop, drain, fade, gain, and session-control events |
| `metrics_native` | C++ | Python | Native counters sampled by monitoring |

## Native Mapping Lifecycle

C++ exposes a `SharedMemoryRegion` through nanobind:

```text
SharedMemoryRegion.create_or_open(name, required_ring_bytes)
  -> map OS named shared memory
  -> initialize_ring(capacity_bytes)
  -> keep the region object alive for the runtime
```

On Windows this uses `CreateFileMappingA` and `MapViewOfFile`. On POSIX systems this uses `shm_open`, `ftruncate`, and `mmap`.

The Python side uses `SharedMemoryBus` to derive stable names such as:

```text
directioner-dev.voice_pcm_in
directioner-dev.tts_pcm_out
```

The native DPP runtime can attach `voice_pcm_in` directly. DPP voice receive events are wrapped with a `PcmFrameHeader` and written to that ring before Python diarization/STT consumes them.

Python can also write raw `s16le` stereo 48 kHz PCM chunks to `tts_pcm_out`. The native DPP runtime exposes `pump_voice_output_once(guild_id, max_frame_bytes)` to drain one frame from that ring and send it to Discord voice.

## PCM Frame Header

All multi-byte numeric fields are little-endian.

| Field | Type | Description |
| --- | --- | --- |
| `schema_version` | `uint16` | PCM frame schema version |
| `header_bytes` | `uint16` | Header size including extensions |
| `stream_id` | `uint64` | Native voice stream id |
| `sequence` | `uint64` | Monotonic frame sequence |
| `capture_time_ns` | `uint64` | Native monotonic clock timestamp |
| `sample_rate_hz` | `uint32` | PCM sample rate |
| `channels` | `uint16` | Channel count |
| `sample_format` | `uint16` | `1 = s16le`, `2 = f32le` |
| `frame_samples` | `uint32` | Samples per channel |
| `speaker_hint` | `uint32` | Optional native speaker/source hint |
| `flags` | `uint32` | VAD, silence, clipped, PLC, final, etc. |

Payload bytes follow the header.

## Backpressure Policy

- `voice_pcm_in`: prefer dropping oldest silence frames, then oldest non-final speech frames.
- `voice_events_in`: drop repeated low-priority metrics events before state-change events.
- `tts_pcm_out`: if full, Python slows TTS production first; if still full, C++ reports output lag.
- `voice_control_out`: small ring, no lossy drops for control events. Producer retries with timeout.
- `metrics_native`: lossy sampling is acceptable.

## Versioning

- Ring headers include a magic number and ABI version.
- Frame headers include schema version and header size.
- Unknown frame extensions are skipped using `header_bytes`.
- Contract tests must cover Python/C++ size, alignment, and enum agreement.
