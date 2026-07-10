"""Shared-memory channel definitions for the Python side."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChannelName(StrEnum):
    VOICE_PCM_IN = "voice_pcm_in"
    VOICE_EVENTS_IN = "voice_events_in"
    TTS_PCM_OUT = "tts_pcm_out"
    VOICE_CONTROL_OUT = "voice_control_out"
    METRICS_NATIVE = "metrics_native"


@dataclass(frozen=True, slots=True)
class ChannelSpec:
    name: ChannelName
    producer: str
    consumer: str
    frame_capacity: int
    max_frame_bytes: int
    lossy: bool

    @property
    def ring_capacity_bytes(self) -> int:
        return self.frame_capacity * self.max_frame_bytes


DEFAULT_CHANNELS: tuple[ChannelSpec, ...] = (
    ChannelSpec(ChannelName.VOICE_PCM_IN, "cpp", "python", 512, 4096, True),
    ChannelSpec(ChannelName.VOICE_EVENTS_IN, "cpp", "python", 256, 1024, True),
    ChannelSpec(ChannelName.TTS_PCM_OUT, "python", "cpp", 512, 4096, False),
    ChannelSpec(ChannelName.VOICE_CONTROL_OUT, "python", "cpp", 64, 512, False),
    ChannelSpec(ChannelName.METRICS_NATIVE, "cpp", "python", 128, 1024, True),
)


class SharedMemoryBus:
    """Names and validates the shared-memory channels for one runtime namespace."""

    def __init__(self, namespace: str, channels: tuple[ChannelSpec, ...] = DEFAULT_CHANNELS) -> None:
        self.namespace = namespace
        self.channels = {spec.name: spec for spec in channels}

    def object_name(self, channel: ChannelName) -> str:
        if channel not in self.channels:
            raise KeyError(f"Unknown shared-memory channel: {channel}")
        return f"{self.namespace}.{channel.value}"

    def specs(self) -> tuple[ChannelSpec, ...]:
        return tuple(self.channels.values())

