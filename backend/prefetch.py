"""Quiet background preparation: while the model has nothing better to do, make the things a student is likely to ask for next.

After a student's lesson is written, its pictures, curiosity facts, 5-minute summary and cheat sheet are made (so they are there by the time the
student scrolls or taps); when a student opens a topic, the lesson for the next topic in their syllabus is written ahead; the automatic fact-check of
new lessons runs last. Everything is stored in the local database, so each thing is made once for everyone with the same language, level and board.

Nothing here may slow a student down: a job starts only after the model has been idle for a few seconds, a student's question, quiz or lesson always goes
first at the model's queue, a job in progress is a few seconds' work (a lesson written ahead gives way after each part), and the jobs that use the
everyday model run together before the fact-check swaps the big model in (loading it evicts the everyday model, which costs every student a reload).
"""
from __future__ import annotations

import itertools
import queue
import threading
import time

from . import config, curriculum, lesson, scheduler
from .logs import get

log = get("prefetch")
EXTRAS, AHEAD, FACTCHECK = 1, 2, 3  # run in this order; each waits for the model to be idle this long (seconds):
IDLE_FOR = {EXTRAS: 3.0, AHEAD: 6.0, FACTCHECK: 25.0}
MAX_LESSONS_AHEAD = 3
_jobs: queue.PriorityQueue = queue.PriorityQueue()
_seq = itertools.count()
_seen: set[str] = set()
_pending_lessons = 0
_guard = threading.Lock()
_started = False


def enabled() -> bool:
    return config.PREFETCH and not config.MOCK and config.PROVIDER == "ollama"


def _submit(key: str, fn, rank: int) -> bool:
    global _pending_lessons
    with _guard:
        if key in _seen or (rank == AHEAD and _pending_lessons >= MAX_LESSONS_AHEAD):
            return False
        _seen.add(key)
        _pending_lessons += rank == AHEAD
    _jobs.put((rank, next(_seq), key, fn))
    _start()
    return True


def _start() -> None:
    global _started
    with _guard:
        if _started:
            return
        _started = True
    threading.Thread(target=_worker, daemon=True, name="prefetch").start()


def _model_idle_for(seconds: float) -> None:
    quiet_since = None
    while True:
        s = scheduler.scheduler.stats()
        if s["running"] == 0 and s["waiting"] == 0:
            quiet_since = quiet_since or time.monotonic()
            if time.monotonic() - quiet_since >= seconds:
                return
        else:
            quiet_since = None
        time.sleep(0.5)


def _worker() -> None:
    global _pending_lessons
    while True:
        rank, seq, key, fn = _jobs.get()
        requeued = False
        try:
            _model_idle_for(IDLE_FOR[rank])
            if _jobs.queue and _jobs.queue[0][0] < rank:  # something that should go before this arrived while it waited
                _jobs.put((rank, seq, key, fn))
                requeued = True
                continue
            fn()
        except Exception as exc:  # noqa: BLE001 - background work must never take anything down
            log.warning(f"prefetch {key} failed: {exc}")
            with _guard:
                _seen.discard(key)  # a later visit may try again
        finally:
            if rank == AHEAD and not requeued:
                with _guard:
                    _pending_lessons = max(0, _pending_lessons - 1)


def _extras_job(subtopic_id: str, language: str, level: str, board: str):
    from . import extras

    def run() -> None:
        var = lesson.variant(language, level, board)
        v = lesson.active_version(subtopic_id, var)
        if not v:
            return

        def step(fn, *a) -> None:
            try:
                with scheduler.slot(scheduler.BATCH):
                    fn(subtopic_id, language, level, board, *a)
            except Exception as exc:  # noqa: BLE001 - each bonus is independent
                log.warning(f"prefetch step {fn.__name__} for {subtopic_id} failed: {exc}")

        step(extras.did_you_know)
        for i in range(len(v["sections"])):
            step(extras.figure, i)
        step(extras.quick_summary)
        step(extras.cheatsheet)
    return run


def after_lesson(subtopic_id: str, language: str, level: str, board: str) -> None:
    """A lesson was just written for a student: get its pictures, facts, summary and cheat sheet ready."""
    if enabled():
        _submit(f"extras|{subtopic_id}|{lesson.variant(language, level, board)}", _extras_job(subtopic_id, language, level, board), EXTRAS)


def _lesson_job(subtopic_id: str, language: str, level: str, board: str):
    def run() -> None:
        if lesson.active_version(subtopic_id, lesson.variant(language, level, board)):
            return
        log.info(f"writing {subtopic_id} ahead of time")
        for _ in scheduler.pump(lambda: lesson.stream_lesson(subtopic_id, language, level, board), scheduler.BATCH, poll=2.0):
            pass
    return run


def after_open(subtopic_id: str, language: str, level: str, board: str) -> None:
    """A student opened a topic: write the next topic in their syllabus ahead of time."""
    if not enabled() or subtopic_id.startswith("my-"):
        return
    topic = curriculum.get_subtopic(subtopic_id)
    nxt = (topic or {}).get("next")
    var = lesson.variant(language, level, board)
    if not nxt or lesson.active_version(nxt["id"], var):
        return
    _submit(f"lesson|{nxt['id']}|{var}", _lesson_job(nxt["id"], language, level, board), AHEAD)


def daily_ahead(student: dict) -> None:
    """The student's home page was opened and today's Daily 5 does not exist yet: write it now, in the quiet, so it is there when they tap it."""
    if not enabled():
        return

    def run() -> None:
        from . import daily
        if daily.existing(student):
            return
        with scheduler.slot(scheduler.BATCH):
            daily.today(student)

    _submit(f"daily|{student['id']}|{time.strftime('%Y-%m-%d')}", run, EXTRAS)


def factcheck_later(version_id: int, run) -> None:
    """The automatic fact-check of a new lesson uses the big model: do it once the model has been quiet for a while, after everything else."""
    _submit(f"factcheck|{version_id}", lambda: run(version_id), FACTCHECK)
