"""Per-request attribution of model usage (tokens, latency) and product events, for analytics and cost tracking."""
from __future__ import annotations

import contextvars
import json
import time

from . import config, db, metrics

current_user: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_user", default=None)


def record_call(kind: str, model: str, input_tokens: int = 0, output_tokens: int = 0, latency_ms: int = 0, ok: bool = True) -> None:
    metrics.inc("model_calls_total", kind=kind, ok=int(ok))
    metrics.observe("model_latency_ms", latency_ms, kind=kind)
    metrics.inc("model_tokens_total", input_tokens + output_tokens, kind=kind)
    try:
        db.run("INSERT INTO usage (ts, user_id, kind, provider, model, input_tokens, output_tokens, latency_ms, ok) VALUES (?,?,?,?,?,?,?,?,?)",
               (time.time(), current_user.get(), kind, config.PROVIDER, model, input_tokens, output_tokens, latency_ms, int(ok)))
    except Exception:  # noqa: BLE001 - accounting must never break a lesson
        pass


def event(user_id: str | None, kind: str, subtopic_id: str = "", **meta) -> None:
    metrics.inc("events_total", kind=kind)
    db.run("INSERT INTO events (ts, user_id, kind, subtopic_id, meta) VALUES (?,?,?,?,?)", (time.time(), user_id, kind, subtopic_id, json.dumps(meta) if meta else ""))
