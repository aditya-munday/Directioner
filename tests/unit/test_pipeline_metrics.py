"""Unit tests for pipeline_metrics."""

from __future__ import annotations

import pytest

from directioner.monitoring.pipeline_metrics import (
    PipelineMetrics,
    get_metrics,
    record_barge_in,
    record_first_audio,
    record_first_token,
    record_ring_read,
    record_ring_write,
    reset_metrics,
    track_llm,
    track_stt,
    track_tts,
)


def setup_function():
    reset_metrics()


def test_track_stt_increments_requests() -> None:
    with track_stt():
        pass
    m = get_metrics()
    assert m.stt_requests == 1
    assert len(m.stt_latencies) == 1
    assert m.stt_errors == 0


def test_track_stt_records_error() -> None:
    with pytest.raises(ValueError):
        with track_stt():
            raise ValueError("boom")
    assert get_metrics().stt_errors == 1


def test_track_llm_increments_requests() -> None:
    with track_llm():
        pass
    assert get_metrics().llm_requests == 1
    assert len(get_metrics().llm_latencies) == 1


def test_track_tts_increments_requests() -> None:
    with track_tts():
        pass
    assert get_metrics().tts_requests == 1


def test_record_first_token() -> None:
    record_first_token(0.123)
    assert get_metrics().first_token_latencies == [0.123]


def test_record_first_audio() -> None:
    record_first_audio(0.456)
    assert get_metrics().first_audio_latencies == [0.456]


def test_record_ring_write_ok() -> None:
    record_ring_write(True)
    assert get_metrics().ring_frames_written == 1
    assert get_metrics().ring_overruns == 0


def test_record_ring_write_overrun() -> None:
    record_ring_write(False)
    assert get_metrics().ring_overruns == 1


def test_record_ring_read_ok() -> None:
    record_ring_read(object())
    assert get_metrics().ring_frames_read == 1


def test_record_ring_read_underrun() -> None:
    record_ring_read(None)
    assert get_metrics().ring_underruns == 1


def test_record_barge_in() -> None:
    record_barge_in()
    record_barge_in()
    assert get_metrics().barge_in_count == 2


def test_summary_structure() -> None:
    with track_stt():
        pass
    with track_llm():
        pass
    record_first_token(0.1)
    record_first_audio(0.2)
    s = get_metrics().summary()
    assert "stt" in s
    assert "llm" in s
    assert "tts" in s
    assert "ring" in s
    assert s["stt"]["requests"] == 1
    assert s["llm"]["first_token_p50_ms"] > 0


def test_reset_clears_all() -> None:
    with track_stt():
        pass
    reset_metrics()
    m = get_metrics()
    assert m.stt_requests == 0
    assert m.stt_latencies == []
