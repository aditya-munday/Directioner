"""Runtime metrics tracking for the full voice + chat pipeline."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

logger = logging.getLogger(__name__)


@dataclass
class PipelineMetrics:
    stt_latencies: list[float] = field(default_factory=list)
    llm_latencies: list[float] = field(default_factory=list)
    tts_latencies: list[float] = field(default_factory=list)
    first_token_latencies: list[float] = field(default_factory=list)
    first_audio_latencies: list[float] = field(default_factory=list)
    stt_requests: int = 0
    stt_errors: int = 0
    llm_requests: int = 0
    llm_errors: int = 0
    tts_requests: int = 0
    tts_errors: int = 0
    ring_frames_written: int = 0
    ring_frames_read: int = 0
    ring_overruns: int = 0
    ring_underruns: int = 0
    ring_dropped: int = 0
    barge_in_count: int = 0

    def _p50(self, s: list[float]) -> float:
        if not s:
            return 0.0
        ss = sorted(s)
        return ss[len(ss) // 2]

    def _p95(self, s: list[float]) -> float:
        if not s:
            return 0.0
        ss = sorted(s)
        return ss[int(len(ss) * 0.95)]

    def summary(self) -> dict:
        return {
            "stt": {
                "requests": self.stt_requests,
                "errors": self.stt_errors,
                "p50_ms": round(self._p50(self.stt_latencies) * 1000, 1),
                "p95_ms": round(self._p95(self.stt_latencies) * 1000, 1),
            },
            "llm": {
                "requests": self.llm_requests,
                "errors": self.llm_errors,
                "p50_ms": round(self._p50(self.llm_latencies) * 1000, 1),
                "p95_ms": round(self._p95(self.llm_latencies) * 1000, 1),
                "first_token_p50_ms": round(self._p50(self.first_token_latencies) * 1000, 1),
            },
            "tts": {
                "requests": self.tts_requests,
                "errors": self.tts_errors,
                "p50_ms": round(self._p50(self.tts_latencies) * 1000, 1),
                "p95_ms": round(self._p95(self.tts_latencies) * 1000, 1),
                "first_audio_p50_ms": round(self._p50(self.first_audio_latencies) * 1000, 1),
            },
            "ring": {
                "frames_written": self.ring_frames_written,
                "frames_read": self.ring_frames_read,
                "overruns": self.ring_overruns,
                "underruns": self.ring_underruns,
                "dropped": self.ring_dropped,
            },
            "barge_in_count": self.barge_in_count,
        }

    def log_summary(self) -> None:
        import json
        logger.info("metrics.summary %s", json.dumps(self.summary()))


_metrics = PipelineMetrics()


def get_metrics() -> PipelineMetrics:
    return _metrics


def reset_metrics() -> PipelineMetrics:
    global _metrics
    _metrics = PipelineMetrics()
    return _metrics


@contextmanager
def track_stt() -> Iterator[None]:
    m = get_metrics()
    m.stt_requests += 1
    t0 = time.perf_counter()
    try:
        yield
        m.stt_latencies.append(time.perf_counter() - t0)
    except Exception:
        m.stt_errors += 1
        raise


@contextmanager
def track_llm() -> Iterator[None]:
    m = get_metrics()
    m.llm_requests += 1
    t0 = time.perf_counter()
    try:
        yield
        m.llm_latencies.append(time.perf_counter() - t0)
    except Exception:
        m.llm_errors += 1
        raise


@contextmanager
def track_tts() -> Iterator[None]:
    m = get_metrics()
    m.tts_requests += 1
    t0 = time.perf_counter()
    try:
        yield
        m.tts_latencies.append(time.perf_counter() - t0)
    except Exception:
        m.tts_errors += 1
        raise


def record_first_token(latency_s: float) -> None:
    get_metrics().first_token_latencies.append(latency_s)


def record_first_audio(latency_s: float) -> None:
    get_metrics().first_audio_latencies.append(latency_s)


def record_ring_write(ok: bool) -> None:
    m = get_metrics()
    if ok:
        m.ring_frames_written += 1
    else:
        m.ring_overruns += 1


def record_ring_read(frame_or_none: object) -> None:
    m = get_metrics()
    if frame_or_none is not None:
        m.ring_frames_read += 1
    else:
        m.ring_underruns += 1


def record_barge_in() -> None:
    get_metrics().barge_in_count += 1
