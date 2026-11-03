"""Daily 5, the answer-writing coach, the doubt inbox and the teacher worksheet maker (model replaced by canned responses)."""
import json

import pytest
from fastapi.testclient import TestClient

from backend import accounts, config, db, learning, store

from .test_api import signup, sse_events

TOPIC = "phy-9-motion.1"


@pytest.fixture(scope="module")
def app_client():
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "MOCK", True)
    from backend.app import app
    yield app
    mp.undo()


@pytest.fixture()
def no_bank(monkeypatch):
    """Other tests leave approved questions in the shared bank (with other answer keys); the Daily 5 rightly prefers them, so these tests start from an empty bank."""
    from backend import exams
    monkeypatch.setattr(exams, "bank_search", lambda *a, **k: [])


def client(app_client):
    return TestClient(app_client)


def learner(app_client, name, studied=True):
    c = client(app_client)
    uid = signup(c, name)["user"]["id"]
    if studied:
        store.mark_started(uid, TOPIC)
    return c, uid


# ---- Daily 5 -----------------------------------------------------------------------------------
def test_daily_needs_something_studied_first(app_client):
    c, _ = learner(app_client, "daily_new", studied=False)
    assert c.get("/api/daily").json()["state"] == "locked"
    r = c.post("/api/daily/open")
    assert r.status_code == 400 and "Study a topic first" in r.json()["detail"]


def test_daily_set_is_made_once_and_the_key_stays_hidden(app_client, no_bank):
    c, _ = learner(app_client, "daily_one")
    assert c.get("/api/daily").json()["state"] == "new"
    s = c.post("/api/daily/open").json()
    assert s["total"] == 5 and len(s["questions"]) == 5 and not s["done"]
    assert all("answer_index" not in q and "explanation" not in q and len(q["options"]) == 4 for q in s["questions"])
    again = c.post("/api/daily/open").json()
    assert [q["id"] for q in again["questions"]] == [q["id"] for q in s["questions"]]  # the same set all day
    assert c.get("/api/daily").json()["state"] == "new"


def test_daily_marks_on_the_server_and_finishing_updates_everything(app_client, no_bank):
    c, uid = learner(app_client, "daily_two")
    qs = c.post("/api/daily/open").json()["questions"]
    first = c.post("/api/daily/answer", json={"question_id": qs[0]["id"], "choice": 1}).json()  # the mock key is option 1
    assert first["answered"]["correct"] and first["answered"]["answer_index"] == 1 and first["count"] == 1 and not first["done"]
    again = c.post("/api/daily/answer", json={"question_id": qs[0]["id"], "choice": 3}).json()
    assert again["answered"]["correct"] and again["count"] == 1  # an answer is final
    assert c.get("/api/daily").json()["state"] == "started"
    out = None
    for i, q in enumerate(qs[1:], start=1):
        out = c.post("/api/daily/answer", json={"question_id": q["id"], "choice": 1 if i < 3 else 0}).json()  # two more right, two wrong
    assert out["done"] and out["summary"]["score"] == 3 and out["summary"]["total"] == 5
    assert out["reward"]["points"] == 4 * 3 + 10 and out["reward"]["xp"] >= 22
    assert any(b["id"] == "daily_first" for b in out["reward"]["new_badges"])
    assert db.scalar("SELECT COUNT(*) FROM mistakes WHERE student_id=? AND source='daily'", (uid,), 0) == 2
    assert c.get("/api/daily").json()["state"] == "done" and c.get("/api/daily").json()["score"] == 3
    done = c.post("/api/daily/open").json()
    assert done["done"] and done["summary"]["score"] == 3 and all("answered" in q for q in done["questions"])
    assert c.post("/api/daily/answer", json={"question_id": qs[0]["id"], "choice": 1}).json()["count"] == 5  # nothing is awarded twice
    assert learning.total_xp(uid) == out["reward"]["xp"]
    assert c.post("/api/daily/answer", json={"question_id": "nope", "choice": 1}).status_code == 400


def test_daily_brings_back_a_mistake_and_clears_it_when_right(app_client, no_bank):
    c, uid = learner(app_client, "daily_three")
    mid = learning.add_mistake(uid, TOPIC, "quiz", "What is speed?", ["a", "b", "c", "d"], "a", "c", "Distance over time.")
    s = c.post("/api/daily/open").json()
    q = next(x for x in s["questions"] if x["source"] == "mistake")
    assert q["question"] == "What is speed?"
    right = c.post("/api/daily/answer", json={"question_id": q["id"], "choice": 2}).json()
    assert right["answered"]["correct"] and right["answered"]["explanation"] == "Distance over time."
    for x in s["questions"]:
        if x["id"] != q["id"]:
            c.post("/api/daily/answer", json={"question_id": x["id"], "choice": 1})
    assert db.one("SELECT resolved_at FROM mistakes WHERE id=?", (mid,))["resolved_at"] is not None


def test_daily_a_choice_outside_the_options_is_refused(app_client, no_bank):
    c, _ = learner(app_client, "daily_four")
    q = c.post("/api/daily/open").json()["questions"][0]
    assert c.post("/api/daily/answer", json={"question_id": q["id"], "choice": 5}).status_code == 400
    assert c.post("/api/daily/answer", json={"question_id": q["id"], "choice": 9}).status_code == 422


# ---- answer-writing coach ----------------------------------------------------------------------
def test_coach_marks_an_answer_and_hides_the_model_answer_until_then(app_client):
    c, uid = learner(app_client, "coach_one")
    st = c.post("/api/coach/start", json={"subtopic_id": TOPIC, "marks": 3}).json()
    assert st["marks"] == 3 and st["question"] and st["words"] == [60, 100] and st["topic"]
    shown = c.get(f"/api/coach/{st['id']}").json()
    assert "model_answer" not in shown and "scheme" not in shown and "awarded" not in shown
    r = c.post(f"/api/coach/{st['id']}/submit", json={"answer": "Speed is distance travelled divided by the time taken, measured in metres per second."})
    assert r.status_code == 200
    res = r.json()
    assert 0 <= res["awarded"] <= 3 and res["marks"] == 3 and res["points"] and res["model_answer"] and res["scheme"] and res["feedback"]
    assert any("short for 3 marks" in tip for tip in res["tips"])  # a very short answer is told so
    assert res["reward"]["points"] >= 3
    assert c.get(f"/api/coach/{st['id']}").json()["submitted"] is True
    assert c.post(f"/api/coach/{st['id']}/submit", json={"answer": "A second try on the same question."}).json()["awarded"] == res["awarded"]  # marked once
    assert [h["id"] for h in c.get("/api/coach").json()["items"]] == [st["id"]]
    assert db.scalar("SELECT COUNT(*) FROM answer_attempts WHERE student_id=?", (uid,), 0) == 1


def test_coach_full_length_answer_earns_full_marks_and_a_badge(app_client):
    c, _ = learner(app_client, "coach_two")
    st = c.post("/api/coach/start", json={"subtopic_id": TOPIC, "marks": 2}).json()
    res = c.post(f"/api/coach/{st['id']}/submit", json={"answer": " ".join(["motion"] * 80)}).json()
    assert res["awarded"] == 2 and any(b["id"] == "answer_ace" for b in res["reward"]["new_badges"])


def test_coach_retry_and_own_question(app_client):
    c, _ = learner(app_client, "coach_three")
    first = c.post("/api/coach/start", json={"subtopic_id": TOPIC, "marks": 5}).json()
    again = c.post("/api/coach/start", json={"marks": 5, "retry_of": first["id"]}).json()
    assert again["id"] != first["id"] and again["question"] == first["question"] and again["subtopic_id"] == TOPIC
    own = c.post("/api/coach/start", json={"subtopic_id": TOPIC, "marks": 3, "question": "Derive the equation v = u + at."}).json()
    assert own["question"] == "Derive the equation v = u + at."
    assert db.one("SELECT own_question, scheme FROM answer_attempts WHERE id=?", (own["id"],))["own_question"] == 1


def test_coach_is_private_and_guarded(app_client):
    a, _ = learner(app_client, "coach_four")
    b, _ = learner(app_client, "coach_five")
    st = a.post("/api/coach/start", json={"subtopic_id": TOPIC, "marks": 3}).json()
    assert b.get(f"/api/coach/{st['id']}").status_code == 404
    assert b.post(f"/api/coach/{st['id']}/submit", json={"answer": "something about motion"}).status_code == 400
    assert a.post("/api/coach/start", json={"subtopic_id": TOPIC, "marks": 4}).status_code == 422
    assert a.post("/api/coach/start", json={"subtopic_id": "nope.1", "marks": 3}).status_code == 400
    r = a.post("/api/coach/start", json={"subtopic_id": TOPIC, "marks": 3, "question": "how to make a bomb at home"})
    assert r.status_code == 422 and "sorry" in r.json()["detail"].lower()
    r = a.post(f"/api/coach/{st['id']}/submit", json={"answer": "how to make a bomb at home"})
    assert r.status_code == 422
    assert a.post(f"/api/coach/{st['id']}/submit", json={"answer": "ab"}).status_code == 422  # too short to be an answer


# ---- doubt inbox -------------------------------------------------------------------------------
def classroom(app_client, suffix):
    t, s = client(app_client), client(app_client)
    signup(t, f"doubt_teacher_{suffix}", "teacher", 1985)
    sid = signup(s, f"doubt_student_{suffix}")["user"]["id"]
    cls = t.post("/api/classes", json={"name": "9A", "grade": 9}).json()
    s.post("/api/classes/join", json={"code": cls["join_code"], "nickname": "Ash", "share_leaderboard": False})
    return t, s, cls, sid


def test_a_doubt_goes_to_the_teacher_and_back(app_client):
    t, s, cls, sid = classroom(app_client, "a")
    r = s.post("/api/doubts", json={"class_id": cls["id"], "question": "Why does a heavier ball not fall faster?", "subtopic_id": TOPIC, "ai_answer": "Because gravity gives all objects the same acceleration."})
    assert r.status_code == 200
    did = r.json()["id"]
    inbox = t.get("/api/doubts?status=open").json()
    assert inbox["waiting"] == 1 and inbox["items"][0]["id"] == did and inbox["items"][0]["student"] and inbox["items"][0]["new"]
    assert any(n["kind"] == "doubt" and n["link"] == f"#/teach/doubts/{did}" for n in t.get("/api/notifications").json()["items"])
    th = t.get(f"/api/doubts/{did}").json()
    assert th["question_full"].startswith("Why does") and th["ai_answer"] and th["topic"] and th["messages"] == []
    assert not t.get("/api/doubts?status=open").json()["items"][0]["new"]  # opening it marks it as seen
    assert t.post(f"/api/doubts/{did}/reply", json={"body": "Air resistance is the same for both here, so they land together."}).status_code == 200
    mine = s.get("/api/doubts").json()["items"][0]
    assert mine["status"] == "answered" and mine["new"] and mine["last"].startswith("Air resistance")
    assert any(n["link"] == f"#/doubts/{did}" for n in s.get("/api/notifications").json()["items"])
    assert t.get("/api/doubts?status=open").json()["items"] == []
    s.post(f"/api/doubts/{did}/reply", json={"body": "I still do not get the air part."})
    assert t.get("/api/doubts?status=open").json()["waiting"] == 1  # a follow-up puts it back in the teacher's queue
    t.post(f"/api/doubts/{did}/reply", json={"body": "Think of a feather and a stone in a vacuum."})
    assert s.post(f"/api/doubts/{did}/resolve", json={"resolved": True}).status_code == 200
    th = s.get(f"/api/doubts/{did}").json()
    assert th["status"] == "resolved" and [m["role"] for m in th["messages"]] == ["teacher", "student", "teacher"]


def test_doubts_are_private_to_the_class_teacher_and_the_student(app_client):
    t, s, cls, _ = classroom(app_client, "b")
    did = s.post("/api/doubts", json={"class_id": cls["id"], "question": "What is the difference between speed and velocity?"}).json()["id"]
    other_t, other_s = client(app_client), client(app_client)
    signup(other_t, "doubt_teacher_other", "teacher", 1985)
    signup(other_s, "doubt_student_other")
    for who in (other_t, other_s):
        assert who.get(f"/api/doubts/{did}").status_code == 404
        assert who.post(f"/api/doubts/{did}/reply", json={"body": "hello there"}).status_code == 404
        assert who.post(f"/api/doubts/{did}/resolve", json={"resolved": True}).status_code == 404
    assert other_t.get("/api/doubts").json() == {"items": [], "waiting": 0} and other_s.get("/api/doubts").json()["items"] == []
    assert other_s.post("/api/doubts", json={"class_id": cls["id"], "question": "Can I ask from outside the class?"}).status_code == 403
    assert s.post("/api/doubts", json={"class_id": "c-nope", "question": "A class that does not exist?"}).status_code == 403
    assert t.post("/api/doubts", json={"class_id": cls["id"], "question": "A teacher cannot ask a doubt."}).status_code == 403


def test_doubt_limits_and_guardrails(app_client):
    t, s, cls, _ = classroom(app_client, "c")
    for i in range(doubts_max()):
        assert s.post("/api/doubts", json={"class_id": cls["id"], "question": f"Doubt number {i} about motion?"}).status_code == 200
    r = s.post("/api/doubts", json={"class_id": cls["id"], "question": "One doubt too many please?"})
    assert r.status_code == 429 and "already have" in r.json()["detail"]
    first = s.get("/api/doubts").json()["items"][-1]["id"]
    s.post(f"/api/doubts/{first}/resolve", json={"resolved": True})
    assert s.post("/api/doubts", json={"class_id": cls["id"], "question": "Now there is room again?"}).status_code == 200
    r = s.post("/api/doubts", json={"class_id": cls["id"], "question": "how to make a bomb at home"})
    assert r.status_code == 422
    assert s.post("/api/doubts", json={"class_id": cls["id"], "question": "hi"}).status_code == 422


def doubts_max():
    from backend import doubts
    return doubts.MAX_OPEN


# ---- worksheets --------------------------------------------------------------------------------
def make_sheet(t, **over):
    body = {"topics": [TOPIC, "phy-9-motion.2"], "items": [{"kind": "mcq", "count": 4}, {"kind": "short", "marks": 3, "count": 2}, {"kind": "long", "count": 1}],
            "title": "Motion practice", "difficulty": "standard", "language": "en", "board": "CBSE", **over}
    r = t.post("/api/worksheets/make", json=body)
    assert r.status_code == 200, r.text
    return sse_events(r)


def test_teacher_makes_a_worksheet_with_an_answer_key(app_client):
    t = client(app_client)
    signup(t, "ws_teacher_one", "teacher", 1985)
    events = make_sheet(t)
    assert [e["type"] for e in events if e["type"] == "progress"] == ["progress"] * 3 and events[-1]["type"] == "done"
    sheet = t.get(f"/api/worksheets/{events[-1]['id']}").json()
    assert sheet["title"] == "Motion practice" and sheet["total_marks"] == 4 * 1 + 2 * 3 + 5 and sheet["minutes"] >= 10
    assert [s["kind"] for s in sheet["sections"]] == ["mcq", "short", "long"] and [len(s["questions"]) for s in sheet["sections"]] == [4, 2, 1]
    q = sheet["sections"][0]["questions"][0]
    assert q["question"] and len(q["options"]) == 4 and "answer_index" in q and sheet["sections"][1]["questions"][0]["marking_scheme"]
    assert sheet["topic_names"] and sheet["board"] == "CBSE"
    assert [w["id"] for w in t.get("/api/worksheets").json()["items"]] == [sheet["id"]]
    assert t.get("/api/worksheets").json()["items"][0]["questions"] == 7


def test_worksheet_edit_replace_delete_and_privacy(app_client):
    t, other, stu = client(app_client), client(app_client), client(app_client)
    signup(t, "ws_teacher_two", "teacher", 1985)
    signup(other, "ws_teacher_three", "teacher", 1985)
    signup(stu, "ws_student")
    wid = make_sheet(t, items=[{"kind": "short", "count": 2}])[-1]["id"]
    assert other.get(f"/api/worksheets/{wid}").status_code == 404 and other.delete(f"/api/worksheets/{wid}").status_code == 404
    assert stu.get("/api/worksheets").status_code == 403 and stu.post("/api/worksheets/make", json={"topics": [TOPIC], "items": [{"kind": "mcq", "count": 1}]}).status_code == 403
    assert t.put(f"/api/worksheets/{wid}", json={"title": "Unit 1 homework"}).status_code == 200
    sheet = t.get(f"/api/worksheets/{wid}").json()
    assert sheet["title"] == "Unit 1 homework"
    old = sheet["sections"][0]["questions"][0]
    r = t.post(f"/api/worksheets/{wid}/replace", json={"question_id": old["id"]})
    assert r.status_code == 200
    new = t.get(f"/api/worksheets/{wid}").json()["sections"][0]["questions"][0]
    assert new["id"] != old["id"] and new["marks"] == old["marks"]
    assert t.post(f"/api/worksheets/{wid}/replace", json={"question_id": "nope"}).status_code == 404
    assert t.delete(f"/api/worksheets/{wid}").status_code == 200 and t.get(f"/api/worksheets/{wid}").status_code == 404


def test_worksheet_input_is_checked(app_client):
    t = client(app_client)
    signup(t, "ws_teacher_four", "teacher", 1985)
    assert t.post("/api/worksheets/make", json={"topics": [TOPIC], "items": [{"kind": "mcq", "count": 20}, {"kind": "short", "count": 20}, {"kind": "long", "count": 5}]}).status_code == 400  # 45 questions
    assert t.post("/api/worksheets/make", json={"topics": [TOPIC], "items": [{"kind": "poem", "count": 2}]}).status_code == 422
    assert t.post("/api/worksheets/make", json={"topics": [], "items": [{"kind": "mcq", "count": 2}]}).status_code == 422
    assert t.post("/api/worksheets/make", json={"topics": [TOPIC], "items": [{"kind": "mcq", "count": 2}], "language": "xx"}).status_code == 400
    events = sse_events(t.post("/api/worksheets/make", json={"topics": ["nope.1"], "items": [{"kind": "mcq", "count": 2}]}))
    assert events[-1]["type"] == "error" and "topic" in events[-1]["message"].lower()  # said in words, not a crash


# ---- privacy -----------------------------------------------------------------------------------
def test_everything_is_erased_with_the_account_and_exported_before(app_client):
    t, s, cls, sid = classroom(app_client, "d")
    s.post("/api/doubts", json={"class_id": cls["id"], "question": "Will this be erased with the account?"})
    store.mark_started(sid, TOPIC)
    s.post("/api/daily/open")
    s.post("/api/coach/start", json={"subtopic_id": TOPIC, "marks": 2})
    exported = accounts.export_data(sid)
    assert exported["daily_sets"] and exported["answer_attempts"] and exported["doubts"] and "doubt_messages" in exported
    wid = make_sheet(t, items=[{"kind": "mcq", "count": 1}])[-1]["id"]
    tid = db.one("SELECT id FROM users WHERE username='doubt_teacher_d'")["id"]
    accounts.delete_account(sid)
    for table in ("daily_sets", "answer_attempts", "doubts"):
        assert db.scalar(f"SELECT COUNT(*) FROM {table} WHERE student_id=?", (sid,), 0) == 0, table
    assert db.scalar("SELECT COUNT(*) FROM doubt_messages WHERE doubt_id NOT IN (SELECT id FROM doubts)", (), 0) == 0
    accounts.delete_account(tid)
    assert db.one("SELECT 1 FROM worksheets WHERE id=?", (wid,)) is None
    json.dumps(exported)  # the export is plain data
