"""Lifecycle adapter for the C++ audio runtime."""

from __future__ import annotations

from dataclasses import dataclass

from directioner.audio.shared_memory import SharedMemoryBus
from directioner.native import require_native


@dataclass(slots=True)
class NativeAudioRuntime:
    bus: SharedMemoryBus
    worker_threads: int

    def start(self) -> None:
        native = require_native()
        native.start_audio_runtime(self.bus.namespace, self.worker_threads)

    def stop(self) -> None:
        native = require_native()
        native.stop_audio_runtime()

