"""Background housekeeping: model warm-up and automatic database backups."""
from __future__ import annotations

import threading
import time

from . import config, db, llm
from .logs import get

log = get("ops")
_started = False


def warm_models() -> None:
    """Load the model(s) into GPU memory so the first student does not wait."""
    if config.MOCK or config.PROVIDER != "ollama":
        return
    from .providers.ollama_provider import OllamaProvider
    prov = llm.provider()
    if not isinstance(prov, OllamaProvider):
        return
    for name in dict.fromkeys([prov.resolve("lesson"), prov.resolve("chat"), prov.resolve("quiz")]):
        try:
            t0 = time.time()
            prov.load(name)
            log.info("model warmed", extra={"extra_fields": {"model": name, "seconds": round(time.time() - t0, 1)}})
        except Exception as exc:  # noqa: BLE001 - warm-up is best effort
            log.warning(f"warm-up skipped for {name}: {exc}")


def _backup_loop() -> None:
    interval = config.BACKUP_HOURS * 3600
    while True:
        time.sleep(interval)
        try:
            out = db.backup()
            log.info(f"database backup written: {out.name}")
        except Exception:  # noqa: BLE001
            log.exception("database backup failed")


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    if config.WARMUP:
        threading.Thread(target=warm_models, daemon=True, name="warmup").start()
    if config.BACKUP_HOURS > 0 and not config.MOCK:
        threading.Thread(target=_backup_loop, daemon=True, name="backup").start()
