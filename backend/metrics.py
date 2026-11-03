"""Tiny in-process metrics, exposed in Prometheus text format at /metrics."""
from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()
_counters: dict[tuple, float] = defaultdict(float)
_sums: dict[tuple, float] = defaultdict(float)
_gauges: dict[str, float] = {}


def inc(name: str, value: float = 1, **labels) -> None:
    with _lock:
        _counters[(name, tuple(sorted(labels.items())))] += value


def observe(name: str, value: float, **labels) -> None:
    """Record a duration/size: exported as `<name>_sum` and `<name>_count`."""
    key = tuple(sorted(labels.items()))
    with _lock:
        _sums[(name, key)] += value
        _counters[(name + "_count", key)] += 1


def gauge(name: str, value: float) -> None:
    with _lock:
        _gauges[name] = value


def _fmt(labels: tuple) -> str:
    return "{" + ",".join(f'{k}="{v}"' for k, v in labels) + "}" if labels else ""


def prometheus() -> str:
    lines = []
    with _lock:
        for (name, labels), v in sorted(_counters.items()):
            lines.append(f"vidya_{name}{_fmt(labels)} {v}")
        for (name, labels), v in sorted(_sums.items()):
            lines.append(f"vidya_{name}_sum{_fmt(labels)} {v}")
        for name, v in sorted(_gauges.items()):
            lines.append(f"vidya_{name} {v}")
    return "\n".join(lines) + "\n"


def snapshot() -> dict:
    with _lock:
        return {"counters": {f"{n}{_fmt(l)}": v for (n, l), v in _counters.items()}, "gauges": dict(_gauges)}
