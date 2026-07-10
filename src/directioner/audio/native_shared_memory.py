"""Python lifetime wrappers for native shared-memory ring regions."""

from __future__ import annotations

from dataclasses import dataclass

from directioner.audio.shared_memory import ChannelName, SharedMemoryBus
from directioner.native import require_native


@dataclass(slots=True)
class NativeSharedMemoryRing:
    name: str
    capacity_bytes: int
    region: object

    @classmethod
    def create_or_open(
        cls,
        bus: SharedMemoryBus,
        channel: ChannelName,
        capacity_bytes: int,
        *,
        initialize: bool = True,
    ) -> "NativeSharedMemoryRing":
        native = require_native()
        object_name = bus.object_name(channel)
        required_bytes = int(native.required_ring_bytes(capacity_bytes))
        region = native.SharedMemoryRegion.create_or_open(object_name, required_bytes)
        if initialize:
            region.initialize_ring(capacity_bytes)
        return cls(name=object_name, capacity_bytes=capacity_bytes, region=region)

    @classmethod
    def open_existing(
        cls,
        bus: SharedMemoryBus,
        channel: ChannelName,
        capacity_bytes: int,
    ) -> "NativeSharedMemoryRing":
        native = require_native()
        object_name = bus.object_name(channel)
        required_bytes = int(native.required_ring_bytes(capacity_bytes))
        region = native.SharedMemoryRegion.open_existing(object_name, required_bytes)
        return cls(name=object_name, capacity_bytes=capacity_bytes, region=region)

    def close(self) -> None:
        self.region.close()

    def read_frame(self, max_bytes: int) -> bytes | None:
        frame = self.region.read_ring_frame(max_bytes)
        if frame is None:
            return None
        return bytes(frame)

    def write_frame(self, payload: bytes) -> bool:
        return bool(self.region.write_ring_frame(payload))

