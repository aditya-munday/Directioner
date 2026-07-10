"""Unit tests for SileroVad (mocked torch model)."""

from __future__ import annotations

import struct
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from directioner.audio.frames import PcmFormat, PcmFrame, PcmFrameFlags
from directioner.audio.vad import SileroVad, _SILERO_CHUNK_SAMPLES


def _make_frame(samples: int = _SILERO_CHUNK_SAMPLES * 3, rate: int = 48_000, channels: int = 2) -> PcmFrame:
    pcm = (np.zeros(samples * channels, dtype=np.int16)).tobytes()
    return PcmFrame(
        stream_id=1,
        sequence=1,
        capture_time_ns=0,
        sample_rate_hz=rate,
        channels=channels,
        sample_format=PcmFormat.S16LE,
        frame_samples=samples,
        payload=memoryview(pcm),
    )


def _mock_model(prob: float) -> MagicMock:
    model = MagicMock()
    tensor_out = MagicMock()
    tensor_out.item.return_value = prob
    model.return_value = tensor_out
    model.reset_states = MagicMock()
    return model


def _patch_hub(prob: float):
    return patch(
        "torch.hub.load",
        return_value=(_mock_model(prob), None),
    )


def test_vad_speech_above_threshold() -> None:
    with _patch_hub(0.9):
        vad = SileroVad(threshold=0.5)
        result = vad.process(_make_frame())
    assert result.is_speech is True
    assert result.probability == pytest.approx(0.9)


def test_vad_silence_below_threshold() -> None:
    with _patch_hub(0.1):
        vad = SileroVad(threshold=0.5)
        result = vad.process(_make_frame())
    assert result.is_speech is False


def test_vad_insufficient_samples_returns_no_speech() -> None:
    """A frame with fewer samples than the Silero chunk should not trigger inference."""
    with _patch_hub(0.99):
        vad = SileroVad(threshold=0.5)
        # Only 10 samples — well below _SILERO_CHUNK_SAMPLES
        tiny_pcm = (np.zeros(10 * 2, dtype=np.int16)).tobytes()
        frame = PcmFrame(
            stream_id=1, sequence=1, capture_time_ns=0,
            sample_rate_hz=48_000, channels=2,
            sample_format=PcmFormat.S16LE, frame_samples=10,
            payload=memoryview(tiny_pcm),
        )
        result = vad.process(frame)
    assert result.is_speech is False


def test_vad_reset_clears_buffer() -> None:
    with _patch_hub(0.9):
        vad = SileroVad(threshold=0.5)
        vad.process(_make_frame())
        vad.reset()
        assert vad._buffer_samples == 0
