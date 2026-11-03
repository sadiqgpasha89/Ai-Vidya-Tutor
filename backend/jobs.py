"""Bulk work an administrator starts from the console: write the lessons for a whole class or chapter ahead of time.

Jobs run one at a time in the background, one topic after another, at the lowest model priority (a student's question or lesson still goes first).
They live in memory: a restart forgets the list, but every lesson already written stays in the database, and starting the same job again skips them.
"""
from __future__ import annotations

import itertools
import queue
import threading
import time

from . import lesson, scheduler
from .logs import get

log = get("jobs")
MAX_TOPICS = 600
_ids = itertools.count(1)
_jobs: dict[int, dict] = {}
_queue: queue.Queue = queue.Queue()
_guard = threading.Lock()
_started = False


def submit(title: str, topic_ids: list[str], language: str, level: str, board: str, extras: bool = False, force: bool = False, by: str | None = None) -> dict:
    topic_ids = list(dict.fromkeys(topic_ids))[:MAX_TOPICS]
    if not topic_ids:
        raise ValueError("There are no topics in that selection.")
    global _started
    job = {"id": next(_ids), "title": title[:120], "language": language, "level": level, "board": board, "extras": extras, "force": force, "by": by,
           "status": "queued", "total": len(topic_ids), "done": 0, "skipped": 0, "failed": 0, "current": "", "errors": [], "created_at": time.time(), "started_at": None, "finished_at": None,
           "_topics": topic_ids, "_cancel": False}
    with _guard:
        _jobs[job["id"]] = job
        for old in sorted(_jobs)[:-30]:  # remember the last 30
            if _jobs[old]["status"] not in ("queued", "running"):
                del _jobs[old]
        if not _started:
            _started = True
            threading.Thread(target=_worker, daemon=True, name="admin-jobs").start()
    _queue.put(job["id"])
    return public(job)


def public(job: dict) -> dict:
    return {k: v for k, v in job.items() if not k.startswith("_")}


def listing() -> list[dict]:
    with _guard:
        return [public(j) for j in sorted(_jobs.values(), key=lambda j: -j["id"])]


def get_job(job_id: int) -> dict | None:
    with _guard:
        j = _jobs.get(job_id)
        return public(j) if j else None


def cancel(job_id: int) -> bool:
    with _guard:
        j = _jobs.get(job_id)
        if not j or j["status"] not in ("queued", "running"):
            return False
        j["_cancel"] = True
        if j["status"] == "queued":
            j["status"], j["finished_at"] = "cancelled", time.time()
        return True


def _write(job: dict, subtopic_id: str) -> None:
    language, level, board = job["language"], job["level"], job["board"]
    var = lesson.variant(language, level, board)
    if lesson.active_version(subtopic_id, var) and not job["force"]:
        job["skipped"] += 1
    else:
        err = None
        for ev in scheduler.pump(lambda: lesson.stream_lesson(subtopic_id, language, level, board, force=job["force"]), scheduler.BATCH, poll=2.0):
            if ev.get("type") == "error":
                err = ev["message"]
        if err:
            raise RuntimeError(err)
        job["done"] += 1
    if job["extras"]:
        from . import extras
        v = lesson.active_version(subtopic_id, var)
        steps = [(extras.did_you_know, ()), *[(extras.figure, (i,)) for i in range(len(v["sections"]))], (extras.quick_summary, ()), (extras.cheatsheet, ())] if v else []
        for fn, args in steps:
            with scheduler.slot(scheduler.BATCH):
                fn(subtopic_id, language, level, board, *args)


def _worker() -> None:
    while True:
        job = _jobs.get(_queue.get())
        if not job or job["status"] != "queued":
            continue
        job["status"], job["started_at"] = "running", time.time()
        for sid in job["_topics"]:
            if job["_cancel"]:
                break
            job["current"] = sid
            try:
                _write(job, sid)
            except Exception as exc:  # noqa: BLE001 - one bad topic must not stop the rest
                job["failed"] += 1
                job["errors"] = (job["errors"] + [f"{sid}: {exc}"])[-20:]
                log.warning(f"job {job['id']} {sid} failed: {exc}")
        job["current"] = ""
        job["status"] = "cancelled" if job["_cancel"] else "failed" if job["failed"] and not job["done"] and not job["skipped"] else "done"
        job["finished_at"] = time.time()
