"""Unit tests for OpenWakeWordDetector (mocked openwakeword)."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from directioner.audio.frames import PcmFormat, PcmFrame
from directioner.audio.vad import VadResult
from directioner.audio.wakeword import OpenWakeWordDetector, _OWW_CHUNK_SAMPLES


def _make_vad_result(speech: bool = True, samples: int = _OWW_CHUNK_SAMPLES * 3) -> VadResult:
    pcm = (np.zeros(samples * 2, dtype=np.int16)).tobytes()
    frame = PcmFrame(
        stream_id=1, sequence=1, capture_time_ns=0,
        sample_rate_hz=48_000, channels=2,
        sample_format=PcmFormat.S16LE, frame_samples=samples,
        payload=memoryview(pcm),
    )
    return VadResult(is_speech=speech, probability=0.9 if speech else 0.0, frame=frame)


def _install_mock_oww(score: float) -> MagicMock:
    """Inject a fake openwakeword module into sys.modules."""
    mock_model_instance = MagicMock()
    mock_model_instance.predict.return_value = {"hey_directioner": [score]}

    mock_model_cls = MagicMock(return_value=mock_model_instance)

    oww_module = types.ModuleType("openwakeword")
    oww_module.utils = MagicMock()
    oww_module.utils.download_models = MagicMock()
    oww_model_module = types.ModuleType("openwakeword.model")
    oww_model_module.Model = mock_model_cls

    sys.modules["openwakeword"] = oww_module
    sys.modules["openwakeword.model"] = oww_model_module
    return mock_model_instance


def _remove_mock_oww() -> None:
    sys.modules.pop("openwakeword", None)
    sys.modules.pop("openwakeword.model", None)


def test_wakeword_triggers_above_threshold() -> None:
    _install_mock_oww(score=0.8)
    try:
        detector = OpenWakeWordDetector(threshold=0.5)
        event = detector.process(_make_vad_result(speech=True))
        assert event is not None
        assert event.model_name == "hey_directioner"
        assert event.score == pytest.approx(0.8)
    finally:
        _remove_mock_oww()


def test_wakeword_no_trigger_below_threshold() -> None:
    _install_mock_oww(score=0.2)
    try:
        detector = OpenWakeWordDetector(threshold=0.5)
        event = detector.process(_make_vad_result(speech=True))
        assert event is None
    finally:
        _remove_mock_oww()


def test_wakeword_skips_silence_frames() -> None:
    _install_mock_oww(score=0.99)
    try:
        detector = OpenWakeWordDetector(threshold=0.5)
        event = detector.process(_make_vad_result(speech=False))
        assert event is None
    finally:
        _remove_mock_oww()


def test_wakeword_insufficient_samples_returns_none() -> None:
    _install_mock_oww(score=0.99)
    try:
        detector = OpenWakeWordDetector(threshold=0.5)
        tiny_pcm = (np.zeros(10 * 2, dtype=np.int16)).tobytes()
        frame = PcmFrame(
            stream_id=1, sequence=1, capture_time_ns=0,
            sample_rate_hz=48_000, channels=2,
            sample_format=PcmFormat.S16LE, frame_samples=10,
            payload=memoryview(tiny_pcm),
        )
        result = VadResult(is_speech=True, probability=0.9, frame=frame)
        event = detector.process(result)
        assert event is None
    finally:
        _remove_mock_oww()


def test_wakeword_reset_clears_buffer() -> None:
    _install_mock_oww(score=0.8)
    try:
        detector = OpenWakeWordDetector(threshold=0.5)
        detector.process(_make_vad_result(speech=True))
        detector.reset()
        assert detector._buffer_samples == 0
    finally:
        _remove_mock_oww()
