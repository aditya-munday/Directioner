"""Write synthesized PCM frames to the native voice output ring."""

from __future__ import annotations

from directioner.audio.native_shared_memory import NativeSharedMemoryRing


class VoiceOutputWriter:
    def __init__(self, ring: NativeSharedMemoryRing) -> None:
        self._ring = ring

    def write_pcm_s16le_stereo_48khz(self, pcm: bytes) -> bool:
        if not pcm:
            return False
        return self._ring.write_frame(pcm)

