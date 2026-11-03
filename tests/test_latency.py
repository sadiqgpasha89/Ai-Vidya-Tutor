"""Latency: a lesson that is already written is served without waiting for the model, queued work wakes at once, items are made once, and the
background warm-up prepares what a student will want next without getting in anyone's way."""
import threading
import time

import pytest

from backend import config, curriculum, db, extras, lesson, prefetch, scheduler


def test_a_waiting_request_wakes_the_moment_a_slot_frees():
    sched = scheduler.Scheduler(lambda: 1)
    first = sched.enter(scheduler.LESSON)
    second = sched.enter(scheduler.CHAT)
    assert not sched.wait_ready(second, 0.05)
    threading.Timer(0.15, first.release).start()
    t0 = time.perf_counter()
    assert sched.wait_ready(second, 5.0) and time.perf_counter() - t0 < 0.5  # not "the next time it looks" (it used to sleep 0.7 s between looks)
    second.release()


def test_a_written_lesson_is_served_while_the_model_is_busy(student, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.app import app
    monkeypatch.setattr(config, "MOCK", True)
    monkeypatch.setattr(scheduler.scheduler, "_limit", lambda: 1)
    sub = "phy-9-force-and-laws-of-motion.3"
    c = TestClient(app)
    from backend import accounts
    accounts.create_user("lat_user1", "Passw0rd!x", "L", "student", 2005, profile={"grade": 9})
    assert c.post("/api/auth/login", json={"username": "lat_user1", "password": "Passw0rd!x"}).status_code == 200
    c.post("/api/lesson/stream", json={"subtopic_id": sub})  # writes it
    hog = scheduler.scheduler.enter(scheduler.LESSON)  # the model is now busy with someone else's lesson
    scheduler.scheduler.wait(hog)
    try:
        t0 = time.perf_counter()
        r = c.post("/api/lesson/stream", json={"subtopic_id": sub})
        assert r.status_code == 200 and '"type": "section"' in r.text and '"type": "queue"' not in r.text
        assert time.perf_counter() - t0 < 2.0
        chk = c.get("/api/lesson/check", params={"subtopic_id": sub}).json()
        assert chk["version"]["type"] == "version" and chk["version"]["version"]["id"] and chk["resume"] == 0
    finally:
        hog.release()


def test_check_counts_the_visit_once_and_a_tracked_stream_does_not_count_again(app_client_mock=None):
    from fastapi.testclient import TestClient

    from backend.app import app
    c = TestClient(app)
    from backend import accounts
    uid = accounts.create_user("lat_user2", "Passw0rd!x", "L", "student", 2005, profile={"grade": 9})["id"]
    assert c.post("/api/auth/login", json={"username": "lat_user2", "password": "Passw0rd!x"}).status_code == 200
    sub = "phy-9-force-and-laws-of-motion.4"
    opens = lambda: db.scalar("SELECT COUNT(*) FROM events WHERE user_id=? AND kind='lesson_open' AND subtopic_id=?", (uid, sub), 0)  # noqa: E731
    assert c.get("/api/lesson/check", params={"subtopic_id": sub}).json()["version"] is None  # nothing written yet
    assert opens() == 1
    c.post("/api/lesson/stream", json={"subtopic_id": sub, "tracked": True})
    assert opens() == 1
    c.post("/api/lesson/stream", json={"subtopic_id": sub})
    assert opens() == 2


def test_pictures_already_made_come_in_one_read_and_nothing_is_drawn(student, monkeypatch):
    monkeypatch.setattr(config, "MOCK", True)
    sub = "phy-9-force-and-laws-of-motion.5"
    list(lesson.stream_lesson(sub, "en", "standard", "CBSE"))
    assert extras.cached_figures(sub, "en", "standard", "CBSE") == {}
    extras.figure(sub, "en", "standard", "CBSE", 1)
    extras.figure(sub, "en", "standard", "CBSE", 3)
    got = extras.cached_figures(sub, "en", "standard", "CBSE")
    assert sorted(got) == ["1", "3"] and got["1"]["svg"].startswith("<svg") and extras.cached_figures(sub, "en", "standard", "CBSE", "quick") == {}
    assert extras.cached_figures("phy-9-gravitation.2", "en", "standard", "CBSE") == {}  # no lesson


def test_a_picture_asked_for_twice_at_once_is_drawn_once(student, monkeypatch):
    monkeypatch.setattr(config, "MOCK", True)
    sub = "phy-9-gravitation.1"
    list(lesson.stream_lesson(sub, "en", "standard", "CBSE"))
    calls = []
    real = extras.concept_diagram

    def slow(*a, **k):
        calls.append(1)
        time.sleep(0.3)
        return real(*a, **k)
    monkeypatch.setattr(extras, "concept_diagram", slow)
    out = []
    threads = [threading.Thread(target=lambda: out.append(extras.figure(sub, "en", "standard", "CBSE", 2))) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(calls) == 1 and len(out) == 4 and all(o and o["svg"] == out[0]["svg"] for o in out)


@pytest.fixture()
def quiet_prefetch(monkeypatch):
    monkeypatch.setattr(prefetch, "enabled", lambda: True)
    monkeypatch.setattr(prefetch, "_start", lambda: None)
    monkeypatch.setattr(prefetch, "_seen", set())
    monkeypatch.setattr(prefetch, "_pending_lessons", 0)
    while not prefetch._jobs.empty():
        prefetch._jobs.get_nowait()
    return prefetch


def test_the_next_topic_is_written_ahead_once(quiet_prefetch, monkeypatch):
    sub = "che-9-matter-in-our-surroundings.1"
    nxt = curriculum.get_subtopic(sub)["next"]["id"]
    quiet_prefetch.after_open(sub, "en", "standard", "CBSE")
    quiet_prefetch.after_open(sub, "en", "standard", "CBSE")  # a second student opening the same topic adds nothing
    assert quiet_prefetch._jobs.qsize() == 1
    rank, _, key, fn = quiet_prefetch._jobs.get_nowait()
    assert key.startswith(f"lesson|{nxt}|") and rank == quiet_prefetch.AHEAD
    seen = []
    monkeypatch.setattr(quiet_prefetch.lesson, "stream_lesson", lambda s, *a, **k: seen.append(s) or iter([{"type": "done"}]))
    monkeypatch.setattr(quiet_prefetch.scheduler, "pump", lambda factory, *a, **k: factory())
    fn()
    assert seen == [nxt]


def test_prefetch_is_bounded_and_skips_own_topics_and_written_lessons(quiet_prefetch, student, monkeypatch):
    quiet_prefetch.after_open("my-abc", "en", "standard", "CBSE")
    assert quiet_prefetch._jobs.qsize() == 0
    for i in range(1, 8):
        quiet_prefetch._submit(f"lesson|x{i}|v", lambda: None, quiet_prefetch.AHEAD)
    assert quiet_prefetch._jobs.qsize() == quiet_prefetch.MAX_LESSONS_AHEAD  # never a pile of speculative lessons
    monkeypatch.setattr(config, "MOCK", True)
    list(lesson.stream_lesson("che-9-matter-in-our-surroundings.3", "en", "standard", "CBSE"))
    while not quiet_prefetch._jobs.empty():
        quiet_prefetch._jobs.get_nowait()
    quiet_prefetch._pending_lessons = 0
    nxt = curriculum.get_subtopic("che-9-matter-in-our-surroundings.2")["next"]["id"]
    assert nxt == "che-9-matter-in-our-surroundings.3"
    quiet_prefetch.after_open("che-9-matter-in-our-surroundings.2", "en", "standard", "CBSE")
    assert quiet_prefetch._jobs.qsize() == 0  # already written


def test_warmup_makes_the_extras_for_a_written_lesson(quiet_prefetch, student, monkeypatch):
    monkeypatch.setattr(config, "MOCK", True)
    sub = "che-9-matter-in-our-surroundings.4"
    list(lesson.stream_lesson(sub, "en", "standard", "CBSE"))
    quiet_prefetch.after_lesson(sub, "en", "standard", "CBSE")
    quiet_prefetch.after_lesson(sub, "en", "standard", "CBSE")
    assert quiet_prefetch._jobs.qsize() == 1
    _, _, _, fn = quiet_prefetch._jobs.get_nowait()
    fn()
    assert len(extras.cached_figures(sub, "en", "standard", "CBSE")) == 12 and extras.did_you_know(sub, "en", "standard", "CBSE", cached_only=True)
    assert extras.cheatsheet(sub, "en", "standard", "CBSE") and extras.quick_summary(sub, "en", "standard", "CBSE")


def test_prefetch_is_off_in_demo_mode_and_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(config, "MOCK", True)
    assert prefetch.enabled() is False
    monkeypatch.setattr(config, "MOCK", False)
    monkeypatch.setattr(config, "PROVIDER", "ollama")
    monkeypatch.setattr(config, "PREFETCH", False)
    assert prefetch.enabled() is False


def test_background_jobs_run_in_a_kind_order_and_only_when_the_model_is_quiet(quiet_prefetch, monkeypatch):
    quiet_prefetch._submit("factcheck|1", lambda: None, quiet_prefetch.FACTCHECK)
    quiet_prefetch._submit("lesson|a|v", lambda: None, quiet_prefetch.AHEAD)
    quiet_prefetch._submit("extras|b|v", lambda: None, quiet_prefetch.EXTRAS)
    order = [quiet_prefetch._jobs.get_nowait()[2] for _ in range(3)]
    assert order == ["extras|b|v", "lesson|a|v", "factcheck|1"]  # everyday-model work first; the big model is swapped in last, once
    assert quiet_prefetch.IDLE_FOR[quiet_prefetch.EXTRAS] < quiet_prefetch.IDLE_FOR[quiet_prefetch.AHEAD] < quiet_prefetch.IDLE_FOR[quiet_prefetch.FACTCHECK]
    busy = scheduler.scheduler.enter(scheduler.CHAT)
    scheduler.scheduler.wait(busy)
    done = []
    threading.Thread(target=lambda: (quiet_prefetch._model_idle_for(0.6), done.append(1)), daemon=True).start()
    time.sleep(1.2)
    assert not done  # somebody is using the model: keep out of the way
    busy.release()
    time.sleep(1.6)
    assert done


def test_fact_check_is_queued_not_started_while_students_may_be_waiting(quiet_prefetch):
    from backend import factcheck
    factcheck.run_async(4242)
    rank, _, key, _ = quiet_prefetch._jobs.get_nowait()
    assert (rank, key) == (quiet_prefetch.FACTCHECK, "factcheck|4242")
