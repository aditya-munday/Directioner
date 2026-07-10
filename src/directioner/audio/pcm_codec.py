"""PCM frame wire-format helpers."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from directioner.audio.frames import PcmFormat, PcmFrame, PcmFrameFlags

PCM_FRAME_HEADER = struct.Struct("<HHQQQIHHIII")
PCM_FRAME_HEADER_BYTES = PCM_FRAME_HEADER.size


@dataclass(frozen=True, slots=True)
class PcmFrameHeader:
    schema_version: int
    header_bytes: int
    stream_id: int
    sequence: int
    capture_time_ns: int
    sample_rate_hz: int
    channels: int
    sample_format: PcmFormat
    frame_samples: int
    speaker_hint: int
    flags: PcmFrameFlags


def parse_pcm_frame(payload: bytes) -> PcmFrame:
    header = parse_pcm_frame_header(payload)
    if len(payload) < header.header_bytes:
        raise ValueError("PCM frame is shorter than its header")

    return PcmFrame(
        stream_id=header.stream_id,
        sequence=header.sequence,
        capture_time_ns=header.capture_time_ns,
        sample_rate_hz=header.sample_rate_hz,
        channels=header.channels,
        sample_format=header.sample_format,
        frame_samples=header.frame_samples,
        payload=memoryview(payload)[header.header_bytes :],
        speaker_hint=header.speaker_hint,
        flags=header.flags,
    )


def parse_pcm_frame_header(payload: bytes) -> PcmFrameHeader:
    if len(payload) < PCM_FRAME_HEADER_BYTES:
        raise ValueError("PCM frame is too short for PcmFrameHeader")

    (
        schema_version,
        header_bytes,
        stream_id,
        sequence,
        capture_time_ns,
        sample_rate_hz,
        channels,
        sample_format,
        frame_samples,
        speaker_hint,
        flags,
    ) = PCM_FRAME_HEADER.unpack_from(payload)

    if header_bytes < PCM_FRAME_HEADER_BYTES:
        raise ValueError("PCM frame header_bytes is smaller than the base header")

    return PcmFrameHeader(
        schema_version=schema_version,
        header_bytes=header_bytes,
        stream_id=stream_id,
        sequence=sequence,
        capture_time_ns=capture_time_ns,
        sample_rate_hz=sample_rate_hz,
        channels=channels,
        sample_format=PcmFormat(sample_format),
        frame_samples=frame_samples,
        speaker_hint=speaker_hint,
        flags=PcmFrameFlags(flags),
    )


def pack_pcm_frame_header(header: PcmFrameHeader) -> bytes:
    return PCM_FRAME_HEADER.pack(
        header.schema_version,
        header.header_bytes,
        header.stream_id,
        header.sequence,
        header.capture_time_ns,
        header.sample_rate_hz,
        header.channels,
        int(header.sample_format),
        header.frame_samples,
        header.speaker_hint,
        int(header.flags),
    )

