"""Fair, prioritised access to the model so one student's lesson does not freeze everyone else's chat.

A single local GPU does best with one request at a time; the scheduler lets chat (priority 0) overtake quizzes (1)
and lesson writing (2) and tells waiting students where they are in line.
"""
from __future__ import annotations

import heapq
import itertools
import threading
import time
from contextlib import contextmanager
from typing import Callable, Iterator

from . import config, metrics

CHAT, ASSESS, LESSON, BATCH = 0, 1, 2, 3


class Ticket:
    def __init__(self, sched: "Scheduler", priority: int, seq: int) -> None:
        self.sched, self.priority, self.seq = sched, priority, seq
        self.released = False
        self.started_at = 0.0

    def ready(self) -> bool:
        return self.sched._is_running(self)

    def ahead(self) -> int:
        return self.sched._ahead(self)

    def release(self) -> None:
        self.sched._release(self)


class Scheduler:
    def __init__(self, limit: Callable[[], int]) -> None:
        self._limit = limit
        self._cv = threading.Condition()
        self._waiting: list[tuple[int, int, Ticket]] = []
        self._running: set[int] = set()
        self._seq = itertools.count()

    def enter(self, priority: int = LESSON) -> Ticket:
        with self._cv:
            seq = next(self._seq)
            t = Ticket(self, priority, seq)
            heapq.heappush(self._waiting, (priority, seq, t))
            self._promote()
            metrics.gauge("queue_waiting", len(self._waiting))
            return t

    def _promote(self) -> None:
        while self._waiting and len(self._running) < self._limit():
            _, seq, t = heapq.heappop(self._waiting)
            if t.released:
                continue
            t.started_at = time.monotonic()
            self._running.add(seq)
        self._cv.notify_all()

    def _is_running(self, t: Ticket) -> bool:
        with self._cv:
            return t.seq in self._running

    def _ahead(self, t: Ticket) -> int:
        with self._cv:
            return sum(1 for p, s, w in self._waiting if not w.released and (p, s) < (t.priority, t.seq)) + len(self._running)

    def _release(self, t: Ticket) -> None:
        with self._cv:
            if t.released:
                return
            t.released = True
            self._running.discard(t.seq)
            self._promote()
            metrics.gauge("queue_waiting", len(self._waiting))

    def wait(self, t: Ticket, timeout: float = 900.0) -> None:
        end = time.monotonic() + timeout
        with self._cv:
            while t.seq not in self._running:
                if time.monotonic() > end:
                    t.released = True
                    raise TimeoutError("The teacher is very busy. Please try again in a moment.")
                self._cv.wait(0.5)

    def wait_ready(self, t: Ticket, timeout: float) -> bool:
        """Sleep until this ticket may run (woken the instant a slot frees) or `timeout` passes. -> whether it may run."""
        with self._cv:
            return self._cv.wait_for(lambda: t.seq in self._running, timeout)

    def pending_above(self, priority: int) -> bool:
        """True when someone more important than `priority` is waiting for the model."""
        with self._cv:
            return any(not w.released and p < priority for p, _, w in self._waiting)

    def stats(self) -> dict:
        with self._cv:
            return {"running": len(self._running), "waiting": sum(1 for _, _, w in self._waiting if not w.released), "limit": self._limit()}


scheduler = Scheduler(lambda: config.CONCURRENCY)


_held = threading.local()


@contextmanager
def slot(priority: int = ASSESS):
    """Blocking gate for non-streaming work. Re-entrant per thread: a slot taken inside a slot is the same slot (with one
    model lane a second, nested slot would wait for itself forever)."""
    if getattr(_held, "depth", 0):
        yield None
        return
    t = scheduler.enter(priority)
    try:
        scheduler.wait(t)
        _held.depth = 1
        try:
            yield t
        finally:
            _held.depth = 0
    finally:
        t.release()


def _as_user(user_id: str | None, gen: Iterator[dict]) -> Iterator[dict]:
    """Re-assert the usage-attribution contextvar on every step (each step may run in a different worker thread)."""
    from . import usage
    while True:
        usage.current_user.set(user_id)
        try:
            ev = next(gen)
        except StopIteration:
            return
        yield ev


def pump(factory: Callable[[], Iterator[dict]], priority: int = CHAT, poll: float = 1.0, user_id: str | None = None) -> Iterator[dict]:
    """Run an event generator inside a scheduler slot, emitting `queue` events while waiting.

    The generator may yield {"type": "_yield_slot"} between units of work to let higher-priority requests in.
    """
    t = scheduler.enter(priority)
    try:
        last = None
        while not scheduler.wait_ready(t, poll):
            ahead = t.ahead()
            if ahead != last:
                yield {"type": "queue", "ahead": ahead}
                last = ahead
        if last is not None:
            yield {"type": "queue", "ahead": 0}
        for ev in _as_user(user_id, factory()):
            if ev.get("type") == "_yield_slot":
                t.release()
                t = scheduler.enter(priority)
                last = None
                while not scheduler.wait_ready(t, poll):
                    ahead = t.ahead()
                    if ahead != last:
                        yield {"type": "queue", "ahead": ahead}
                        last = ahead
                continue
            yield ev
    finally:
        t.release()
