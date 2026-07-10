"""Metrics names and simple in-process sink."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetricSample:
    name: str
    value: float
    tags: tuple[tuple[str, str], ...] = ()


class MetricsSink:
    def __init__(self) -> None:
        self._latest: dict[str, float] = defaultdict(float)

    def record(self, sample: MetricSample) -> None:
        self._latest[sample.name] = sample.value

    def latest(self, name: str) -> float:
        return self._latest[name]

