"""Audio frame data structures shared by Python audio services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, IntFlag


class PcmFormat(IntEnum):
    S16LE = 1
    F32LE = 2


class PcmFrameFlags(IntFlag):
    NONE = 0
    SPEECH = 1 << 0
    SILENCE = 1 << 1
    CLIPPED = 1 << 2
    PACKET_LOSS_CONCEALMENT = 1 << 3
    FINAL = 1 << 4


@dataclass(frozen=True, slots=True)
class PcmFrame:
    stream_id: int
    sequence: int
    capture_time_ns: int
    sample_rate_hz: int
    channels: int
    sample_format: PcmFormat
    frame_samples: int
    payload: memoryview
    speaker_hint: int = 0
    flags: PcmFrameFlags = PcmFrameFlags.NONE

