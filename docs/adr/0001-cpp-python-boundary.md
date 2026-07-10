# ADR 0001: C++ And Python Boundary

## Status

Accepted.

## Context

Discord voice transport and audio DSP have hard timing requirements. Python is excellent for AI orchestration and model integrations, but Python callbacks in real-time audio paths would create latency spikes and failure coupling.

## Decision

Use C++ for real-time audio and Python for AI orchestration. Use nanobind for lifecycle and typed control APIs. Use shared-memory SPSC ring buffers for high-rate PCM and real-time events.

## Consequences

- The C++ audio path remains predictable under Python GC, model latency, and network calls.
- Python can evolve model and planning code quickly.
- The bridge contract must be explicit and tested.
- Debugging requires observability on both sides of the boundary.

