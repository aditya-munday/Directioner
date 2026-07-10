"""Read native voice PCM frames from shared memory."""

from __future__ import annotations

from directioner.audio.frames import PcmFrame
from directioner.audio.native_shared_memory import NativeSharedMemoryRing
from directioner.audio.pcm_codec import parse_pcm_frame


class VoiceInputReader:
    def __init__(self, ring: NativeSharedMemoryRing, max_frame_bytes: int = 8192) -> None:
        self._ring = ring
        self._max_frame_bytes = max_frame_bytes

    def read(self) -> PcmFrame | None:
        payload = self._ring.read_frame(self._max_frame_bytes)
        if payload is None:
            return None
        return parse_pcm_frame(payload)

