from directioner.audio.frames import PcmFormat, PcmFrameFlags
from directioner.audio.pcm_codec import (
    PCM_FRAME_HEADER_BYTES,
    PcmFrameHeader,
    pack_pcm_frame_header,
    parse_pcm_frame,
)


def test_pcm_frame_header_layout_matches_native_protocol() -> None:
    assert PCM_FRAME_HEADER_BYTES == 48


def test_parse_pcm_frame_round_trip() -> None:
    header = PcmFrameHeader(
        schema_version=1,
        header_bytes=PCM_FRAME_HEADER_BYTES,
        stream_id=10,
        sequence=11,
        capture_time_ns=12,
        sample_rate_hz=48_000,
        channels=2,
        sample_format=PcmFormat.S16LE,
        frame_samples=4,
        speaker_hint=123,
        flags=PcmFrameFlags.SPEECH,
    )
    pcm = b"\x01\x00\x02\x00" * 4

    frame = parse_pcm_frame(pack_pcm_frame_header(header) + pcm)

    assert frame.stream_id == 10
    assert frame.sequence == 11
    assert frame.sample_rate_hz == 48_000
    assert frame.channels == 2
    assert frame.sample_format is PcmFormat.S16LE
    assert frame.flags == PcmFrameFlags.SPEECH
    assert frame.payload.tobytes() == pcm

