"""ABI contract tests: verify C++ and Python agree on PcmFrameHeader layout.

These tests do not require the native extension to be built — they verify the
Python-side struct format string matches the documented wire protocol so that
any accidental field reordering or size change is caught immediately.
"""

from __future__ import annotations

import struct

from directioner.audio.pcm_codec import PCM_FRAME_HEADER, PCM_FRAME_HEADER_BYTES


# ── Documented wire layout (from docs/SHARED_MEMORY_PROTOCOL.md) ─────────────
# Offset  Size  Type    Field
#  0       2    uint16  schema_version
#  2       2    uint16  header_bytes
#  4       8    uint64  stream_id
# 12       8    uint64  sequence
# 20       8    uint64  capture_time_ns
# 28       4    uint32  sample_rate_hz
# 32       2    uint16  channels
# 34       2    uint16  sample_format
# 36       4    uint32  frame_samples
# 40       4    uint32  speaker_hint
# 44       4    uint32  flags
# Total = 48 bytes
# ─────────────────────────────────────────────────────────────────────────────

_EXPECTED_HEADER_BYTES = 48
_EXPECTED_FORMAT = "<HHQQQIHHIII"
_EXPECTED_FIELD_COUNT = 11


def test_pcm_frame_header_total_size_matches_protocol() -> None:
    assert PCM_FRAME_HEADER_BYTES == _EXPECTED_HEADER_BYTES, (
        f"PcmFrameHeader size mismatch: Python={PCM_FRAME_HEADER_BYTES} "
        f"expected={_EXPECTED_HEADER_BYTES}. "
        "Update the struct format or the C++ definition."
    )


def test_pcm_frame_header_format_string_matches_protocol() -> None:
    assert PCM_FRAME_HEADER.format == _EXPECTED_FORMAT, (
        f"PcmFrameHeader format mismatch: got={PCM_FRAME_HEADER.format!r} "
        f"expected={_EXPECTED_FORMAT!r}"
    )


def test_pcm_frame_header_field_count() -> None:
    # struct.unpack returns one value per format character (excluding endian prefix)
    fmt_chars = [c for c in _EXPECTED_FORMAT if c not in "<>!=@"]
    assert len(fmt_chars) == _EXPECTED_FIELD_COUNT


def test_pcm_frame_header_field_offsets() -> None:
    """Verify each field lands at the documented byte offset."""
    expected_offsets = {
        "schema_version": 0,
        "header_bytes": 2,
        "stream_id": 4,
        "sequence": 12,
        "capture_time_ns": 20,
        "sample_rate_hz": 28,
        "channels": 32,
        "sample_format": 34,
        "frame_samples": 36,
        "speaker_hint": 40,
        "flags": 44,
    }
    field_formats = ["H", "H", "Q", "Q", "Q", "I", "H", "H", "I", "I", "I"]
    field_names = list(expected_offsets.keys())

    offset = 0
    for name, fmt in zip(field_names, field_formats):
        assert offset == expected_offsets[name], (
            f"Field '{name}' offset mismatch: computed={offset} "
            f"expected={expected_offsets[name]}"
        )
        offset += struct.calcsize(fmt)


def test_pcm_frame_header_round_trip_preserves_all_fields() -> None:
    """Pack and unpack a header and verify every field survives the round trip."""
    from directioner.audio.pcm_codec import PcmFrameHeader, pack_pcm_frame_header, parse_pcm_frame_header
    from directioner.audio.frames import PcmFormat, PcmFrameFlags

    original = PcmFrameHeader(
        schema_version=1,
        header_bytes=_EXPECTED_HEADER_BYTES,
        stream_id=0xDEADBEEF,
        sequence=42,
        capture_time_ns=1_000_000_000,
        sample_rate_hz=48_000,
        channels=2,
        sample_format=PcmFormat.S16LE,
        frame_samples=960,
        speaker_hint=7,
        flags=PcmFrameFlags.SPEECH,
    )
    packed = pack_pcm_frame_header(original)
    assert len(packed) == _EXPECTED_HEADER_BYTES

    recovered = parse_pcm_frame_header(packed)
    assert recovered.schema_version == original.schema_version
    assert recovered.header_bytes == original.header_bytes
    assert recovered.stream_id == original.stream_id
    assert recovered.sequence == original.sequence
    assert recovered.capture_time_ns == original.capture_time_ns
    assert recovered.sample_rate_hz == original.sample_rate_hz
    assert recovered.channels == original.channels
    assert recovered.sample_format == original.sample_format
    assert recovered.frame_samples == original.frame_samples
    assert recovered.speaker_hint == original.speaker_hint
    assert recovered.flags == original.flags
