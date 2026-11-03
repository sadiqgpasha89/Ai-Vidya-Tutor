"""Append-only audit trail of security- and content-relevant actions."""
from __future__ import annotations

import json
import time

from . import db


def log(actor_id: str | None, action: str, target: str = "", detail: dict | str | None = None, ip: str = "") -> None:
    if isinstance(detail, dict):
        detail = json.dumps(detail, ensure_ascii=False)
    db.run("INSERT INTO audit_log (ts, actor_id, action, target, detail, ip) VALUES (?,?,?,?,?,?)",
           (time.time(), actor_id, action, target, (detail or "")[:1000], ip[:64]))


def recent(limit: int = 200, action: str | None = None) -> list[dict]:
    if action:
        return db.all("SELECT * FROM audit_log WHERE action=? ORDER BY id DESC LIMIT ?", (action, limit))
    return db.all("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
