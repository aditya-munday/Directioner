# File Structure

This structure separates the latency-sensitive C++ DPP/audio plane from the Python AI orchestration plane while keeping their bridge contract explicit.

```text
Directioner/
  CONTEXT.md
  README.md
  TODO.md
  pyproject.toml
  CMakeLists.txt
  CMakePresets.json
  configs/
    app.example.yaml
    discord.example.yaml
    logging.example.yaml
    models.example.yaml
  docs/
    ARCHITECTURE.md
    FILE_STRUCTURE.md
    PIPELINES.md
    SHARED_MEMORY_PROTOCOL.md
    BUILDING.md
    CONTEXT_MANAGEMENT.md
    adr/
      0001-cpp-python-boundary.md
  native/
    CMakeLists.txt
    directioner_native/
      CMakeLists.txt
      bindings/
        module.cpp
      include/directioner_native/
        audio/
          frame.hpp
          processing_engine.hpp
        discord/
          voice_gateway.hpp
        runtime/
          build_info.hpp
          worker_pool.hpp
        shared_memory/
          channel.hpp
          mapped_region.hpp
          spsc_ring_buffer.hpp
      src/
        audio/
          processing_engine.cpp
        discord/
          voice_gateway.cpp
        runtime/
          worker_pool.cpp
        shared_memory/
          mapped_region.cpp
          spsc_ring_buffer.cpp
  src/
    directioner/
      __init__.py
      app.py
      native.py
      audio/
        native_shared_memory.py
        pcm_codec.py
        voice_input.py
        voice_output.py
      config/
      conversation/
      diarization/
      discord/
      intent/
      llm/
      memory/
      monitoring/
      orchestrator/
      response/
      stt/
      text/
      tools/
      tts/
  tests/
    unit/
    integration/
    native/
    contracts/
```

## Boundary Rules

- `native/directioner_native` owns DPP Discord connectivity and may not import Python or call Python callbacks from real-time audio paths.
- `src/directioner` may control native lifecycle through `directioner.native`, but must communicate high-rate audio through shared memory.
- `src/directioner/discord/event_pump.py` is the Python bridge that converts native DPP text events into `ConversationEvent` values.
- `docs/SHARED_MEMORY_PROTOCOL.md` is the source of truth for channel names, frame headers, versioning, and backpressure policy.
- `tests/contracts` validates that Python and C++ agree on shared-memory layout and event schemas.
- `configs` contains examples only. Secrets stay in environment variables or external secret stores.
