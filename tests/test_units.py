import pytest

from backend import curriculum, lesson, store, tools


@pytest.mark.parametrize("expr,expected", [("2+3*4", 14), ("sqrt(3**2+4**2)", 5.0), ("2^10", 1024), ("0.5*2*9.8**2", 96.04), ("10/4", 2.5)])
def test_calculator_ok(expr, expected):
    ctx = tools.ToolContext(student={}, topic={})
    assert float(tools.run_tool("calculator", {"expression": expr}, ctx)[0].rsplit("=", 1)[1]) == pytest.approx(expected)


@pytest.mark.parametrize("expr", ["__import__('os').system('echo hi')", "open('/etc/passwd')", "9**9**9", "1/0", "x+1", "().__class__", "factorial(100000)"])
def test_calculator_rejects_unsafe_or_bad(expr):
    text, is_error = tools.run_tool("calculator", {"expression": expr}, tools.ToolContext(student={}, topic={}))
    assert is_error and text.startswith("error:")


def test_calculator_refuses_trivial_input():
    text, is_error = tools.run_tool("calculator", {"expression": " 0 "}, tools.ToolContext(student={}, topic={}))
    assert is_error and "nothing to calculate" in text


def test_tool_input_validation():
    ctx = tools.ToolContext(student={}, topic={})
    assert tools.run_tool("show_on_board", {"title": "x"}, ctx)[1] is True
    assert tools.run_tool("show_on_board", "not a dict", ctx)[1] is True
    assert tools.run_tool("nope", {}, ctx)[1] is True


def test_curriculum_shape():
    s = curriculum.stats()
    assert s["chapters"] > 300 and s["subtopics"] > 1100 and s["subjects"] == 8
    for subject, meta in curriculum.SUBJECTS.items():
        for grade in meta["grades"]:
            assert curriculum.chapters(subject, grade), (subject, grade)
    ids = [st.id for c in curriculum.chapters() for st in c.subtopics]
    assert len(ids) == len(set(ids))
    assert curriculum.broken_prerequisites() == []


def test_tracks_boards_and_prerequisites():
    cs = {c.title for c in curriculum.chapters("computers", 12, "CS", "")}
    ip = {c.title for c in curriculum.chapters("computers", 12, "IP", "")}
    assert "File Handling" in cs - ip and "Data Handling using Pandas" in ip - cs
    icse = {c.title for c in curriculum.chapters("chemistry", 10, "", "icse")}
    assert "Study of Compounds" in icse and "Study of Compounds" not in {c.title for c in curriculum.chapters("chemistry", 10, "", "cbse")}
    pre = curriculum.prerequisites("phy-9-force-and-laws-of-motion.3")
    assert any(p.get("grade") == 8 for p in pre) and any(p["why"] == "earlier in this chapter" for p in pre)
    assert curriculum.subjects_for(12, "pcb") == ["physics", "chemistry", "biology", "english"]


def test_search_and_navigation():
    assert curriculum.search("photosynthesis")[0]["subject"] == "biology"
    t = curriculum.get_subtopic("phy-9-motion.1")
    assert t["prev"] is None and t["next"]["id"] == "phy-9-motion.2"


def test_parse_sections_ignores_unfinished_last_section():
    text = ("=== SECTION: hook | Hi ===\n[DISPLAY]\nA\n[SPEECH]\nSay A\n=== SECTION: idea | Two ===\n[DISPLAY]\nB\n[SPEECH]\nSay")
    assert [s["title"] for s in lesson.parse_sections(text)] == ["Hi"]
    full = text + " B\n=== END ===\n"
    assert [s["speech"] for s in lesson.parse_sections(full)] == ["Say A", "Say B"]


def test_learner_model_and_revision_schedule(student):
    sid = student["id"]
    store.record_evidence(sid, "phy-8-friction.1", 0.95, "quiz")
    assert store.due_revisions(sid) == []  # strong recall: next revision is days away
    p1 = store.progress_map(sid)["phy-8-friction.1"]
    assert p1["mastery"] > 0.6 and p1["retention"] > 0.6
    store.record_evidence(sid, "phy-8-friction.2", 0.1, "quiz")
    assert store.progress_map(sid)["phy-8-friction.2"]["mastery"] < 0.3
    assert store.difficulty_for(sid, "phy-8-friction.2") == "easier"
    assert store.streak(sid) == 1


def test_bkt_is_monotonic_and_forgetting_decays():
    assert store.bkt_update(0.3, 1.0, 3) > store.bkt_update(0.3, 0.5, 3) > store.bkt_update(0.3, 0.0, 3)
    now = 1_000_000.0
    assert store.retention(0.9, 2.0, now, now + 10 * 86400) < store.retention(0.9, 2.0, now, now + 1 * 86400) < 0.9


def test_slot_is_reentrant_with_one_lane():
    """A slot taken inside a slot must not wait for itself (this froze every lesson and chat on a one-lane Ollama setup)."""
    import threading
    from backend import scheduler
    done = threading.Event()

    def work():
        with scheduler.slot(scheduler.LESSON):
            with scheduler.slot(scheduler.LESSON):
                done.set()

    scheduler.scheduler._limit = lambda: 1
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(5)
    assert done.is_set(), "nested slot deadlocked"
    assert scheduler.scheduler.stats()["running"] == 0


def test_extras_work_with_one_model_lane(monkeypatch):
    """Cheat sheet / objectives / exam focus / diagram / flashcards go through routes._ai, which already holds the lane."""
    import threading
    from backend import config, extras, scheduler
    from backend.routes import learn

    class P:
        def structured(self, *a, **k):
            return {"objectives": ["a"], "key_terms": ["b"], "cards": [{"front": "q", "back": "a"}]}

        def stream_text(self, *a, **k):
            yield "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 10'><circle cx='5' cy='5' r='3'/></svg> ok"

    monkeypatch.setattr(config, "MOCK", False)
    monkeypatch.setattr(extras.llm, "provider", lambda: P())
    monkeypatch.setattr(scheduler.scheduler, "_limit", lambda: 1)
    out = {}

    def go():
        sub = "phy-9-motion.3"
        out["o"] = learn._ai(extras.objectives, sub, "en", _priority=scheduler.LESSON)
        out["c"] = learn._ai(extras.cheatsheet, sub, "en", "standard", "CBSE", _priority=scheduler.LESSON)
        out["e"] = learn._ai(extras.exam_focus, sub, "boards", "standard", "en", _priority=scheduler.LESSON)
        out["d"] = learn._ai(extras.diagram, sub, "en", "standard", "CBSE", "", _priority=scheduler.LESSON)
        out["f"] = learn._ai(extras.flashcards, sub, "en", "standard", "CBSE")

    th = threading.Thread(target=go, daemon=True)
    th.start()
    th.join(10)
    assert not th.is_alive() and len(out) == 5, f"deadlocked after {list(out)}"


def test_foreign_script_guard():
    from backend.lesson import foreign_script
    assert foreign_script("यह एक वैज्ञानिक ধারণা है", "hi") and not foreign_script("यह एक वैज्ञानिक धारणा है (Motion)", "hi")
    assert foreign_script("hello नमस्ते", "en") and not foreign_script("hola mundo", "es") and foreign_script("日本語", "es") and not foreign_script("日本語 (Japanese)", "ja") and foreign_script("हिन्दी", "ur")


def test_background_work_gives_way(monkeypatch):
    from backend import scheduler
    s = scheduler.Scheduler(lambda: 1)
    running = s.enter(scheduler.BATCH)
    assert running.ready() and not s.pending_above(scheduler.BATCH)
    waiting = s.enter(scheduler.CHAT)
    assert s.pending_above(scheduler.BATCH) and not s.pending_above(scheduler.CHAT)
    running.release()
    assert waiting.ready()


def test_twenty_languages_and_their_voices():
    from backend import config, server_text, voice
    langs = config.LANGUAGES
    assert len(langs) == 20 and sum(v["group"] == "india" for v in langs.values()) == 10 and "hinglish" not in langs
    assert {k for k, v in langs.items() if v.get("rtl")} == {"ar", "ur"}
    for code, v in langs.items():
        assert v["scripts"] and all(s in config.SCRIPTS for s in v["scripts"]), code
        assert code in voice.PIPER_VOICES or code in voice.MMS_VOICES, f"{code} has no local voice"
        assert code in voice.WHISPER_LANG
    assert "hindi" not in __import__("backend.curriculum", fromlist=["SUBJECTS"]).SUBJECTS
    # fixed server sentences: every language falls back to English, never to a KeyError
    assert server_text.get("redirect", "xx", subject="Physics", topic="Motion").startswith("I'm sorry")
    assert "{" not in server_text.get("redirect", "hi", subject="Physics", topic="Motion")
    assert server_text.title("idea", "en", "The big idea") == "The big idea"


def test_support_reply_is_translated_and_keeps_the_helplines():
    from backend import moderation
    for lang in ("en", "hi", "ta", "xx"):
        assert "14416" in moderation.support_reply(lang) and "112" in moderation.support_reply(lang)


def test_distress_in_other_languages_is_caught_by_the_model(monkeypatch):
    from backend import config, llm, moderation
    monkeypatch.setattr(config, "MOCK", False)

    class P:
        def structured(self, system, user, schema, effort, max_tokens=0, role=""):
            return {"category": "distress" if "SAD-MARKER" in user else "ok"}
    monkeypatch.setattr(llm, "provider", lambda: P())
    assert moderation.check_input("நான் SAD-MARKER", "ta", deep=True)["category"] == "distress"
    assert moderation.check_input("வேகம் என்றால் என்ன?", "ta", deep=True)["action"] == "allow"
    assert moderation.check_input("12 + 5 = ?", "ta", deep=True)["action"] == "allow"
    assert moderation.check_input("I want to end it all SAD-MARKER", "en")["action"] == "allow"  # without deep=True only the word lists run: no model call
