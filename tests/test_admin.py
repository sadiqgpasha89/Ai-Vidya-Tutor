"""The administrator's console: who may use it, and what it can do to people, schools, topics, lessons, custom topics, bulk jobs, notices and the system."""
import time

import pytest
from fastapi.testclient import TestClient

from backend import accounts, config, curriculum, db, jobs, lesson

PW = "Passw0rd!x"


@pytest.fixture(scope="module")
def app():
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "MOCK", True)
    from backend.app import app
    yield app
    mp.undo()


@pytest.fixture(autouse=True)
def own_curriculum_edits(tmp_path, monkeypatch):
    """Curriculum edits are a file: every test gets a fresh one so edits never leak between tests."""
    monkeypatch.setattr(curriculum, "EDITS_FILE", tmp_path / "curriculum_edits.json")
    curriculum.reload()
    yield
    curriculum.reload()


def login(app, username, role="student", school_id=None):
    if not accounts.get_by_username(username):
        accounts.create_user(username, PW, username.title(), "teacher" if role in ("admin", "school_admin") else role, 2006 if role == "student" else 1985, profile={"grade": 9})
        db.run("UPDATE users SET role=?, school_id=? WHERE username=?", (role, school_id, username))
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": username, "password": PW}).status_code == 200
    return c


@pytest.fixture()
def admin(app):
    return login(app, "adm_root", "admin")


def test_only_administrators_get_in(app):
    anon = TestClient(app)
    student, teacher, sa = login(app, "adm_stu"), login(app, "adm_tea", "teacher"), login(app, "adm_sa", "school_admin")
    admin_paths = ["/api/admin/overview", "/api/admin/analytics", "/api/admin/audit", "/api/admin/health", "/api/admin/lessons", "/api/admin/custom-topics", "/api/admin/jobs", "/api/admin/system"]
    for path in admin_paths:
        assert anon.get(path).status_code == 401, path
        assert student.get(path).status_code == 403 and teacher.get(path).status_code == 403 and sa.get(path).status_code == 403, path
    for path in ("/api/admin/users", "/api/admin/schools", "/api/admin/curriculum?subject=maths&grade=9"):  # a school administrator may look at these
        assert student.get(path).status_code == 403 and teacher.get(path).status_code == 403 and sa.get(path).status_code == 200, path
    for method, path, body in (("post", "/api/admin/users", {"username": "x_new1", "display_name": "X"}), ("post", "/api/admin/announce", {"title": "Hello there"}), ("post", "/api/admin/jobs", {"subject": "maths", "grade": 9}),
                               ("post", "/api/admin/system/purge", {"what": "codes"}), ("post", "/api/admin/backup", {}), ("post", "/api/admin/schools", {"name": "Nope School"})):
        assert getattr(sa, method)(path, json=body).status_code == 403, path
        assert getattr(student, method)(path, json=body).status_code == 403, path


def test_overview_counts_what_is_there(admin):
    o = admin.get("/api/admin/overview").json()
    assert o["users"]["by_role"]["admin"] >= 1 and o["users"]["total"] >= 1 and "coverage" in o["content"] and o["content"]["topics"] > 1000
    assert {"reports_open", "drafts", "flagged", "guardrail_blocks_7d"} <= set(o["attention"]) and "running" in o["queue"]


def test_people_create_find_edit_reset_signout_delete(admin, app):
    r = admin.post("/api/admin/users", json={"username": "adm_new_student", "display_name": "Nita", "role": "student", "grade": 8, "email": "nita@example.com"})
    assert r.status_code == 200 and len(r.json()["password"]) == 12  # made up and shown once
    uid, pw = r.json()["id"], r.json()["password"]
    got = TestClient(app)
    assert got.post("/api/auth/login", json={"username": "adm_new_student", "password": pw}).status_code == 200
    assert got.get("/api/auth/me").json()["email_verified"] is True  # an address an administrator types counts as confirmed
    assert admin.post("/api/admin/users", json={"username": "adm_new_student", "display_name": "Dup"}).status_code == 409
    assert admin.post("/api/admin/users", json={"username": "adm_new_pw", "display_name": "P", "password": "short"}).status_code == 400
    found = admin.get("/api/admin/users", params={"q": "nita"}).json()
    assert found["total"] == 1 and found["items"][0]["id"] == uid and "password_hash" not in found["items"][0]
    assert any(u["id"] == uid for u in admin.get("/api/admin/users", params={"role": "student"}).json()["items"])
    assert all(u["id"] != uid for u in admin.get("/api/admin/users", params={"role": "teacher"}).json()["items"])
    d = admin.get(f"/api/admin/users/{uid}").json()
    assert d["profile"]["grade"] == 8 and d["email_verified"] == 1 and "password_hash" not in d and "learning" in d and d["sessions"] == 1
    assert admin.put(f"/api/admin/users/{uid}", json={"role": "teacher", "display_name": "Nita T."}).status_code == 200
    assert accounts.get_user(uid)["role"] == "teacher" and accounts.get_user(uid)["display_name"] == "Nita T."
    assert admin.post(f"/api/admin/users/{uid}/signout").json()["sessions"] == 1 and got.get("/api/auth/me").status_code == 401
    r = admin.post(f"/api/admin/users/{uid}/password", json={})
    new = r.json()["password"]
    assert new and got.post("/api/auth/login", json={"username": "adm_new_student", "password": pw}).status_code == 401
    assert got.post("/api/auth/login", json={"username": "adm_new_student", "password": new}).status_code == 200
    assert admin.put(f"/api/admin/users/{uid}", json={"role": "teacher", "disabled": True}).status_code == 200
    assert got.get("/api/auth/me").status_code == 401 and TestClient(app).post("/api/auth/login", json={"username": "adm_new_student", "password": new}).status_code == 401
    assert [u["id"] for u in admin.get("/api/admin/users", params={"status": "disabled"}).json()["items"]].count(uid) == 1
    assert admin.delete(f"/api/admin/users/{uid}").status_code == 200 and accounts.get_user(uid) is None
    assert admin.get(f"/api/admin/users/{uid}").status_code == 404


def test_you_cannot_lock_yourself_out(app):
    solo = login(app, "adm_solo", "admin")
    me = solo.get("/api/auth/me").json()["user"]["id"]
    assert solo.delete(f"/api/admin/users/{me}").status_code == 400
    assert solo.put(f"/api/admin/users/{me}", json={"role": "teacher"}).status_code == 400
    assert solo.put(f"/api/admin/users/{me}", json={"role": "admin", "disabled": True}).status_code == 400
    assert solo.put(f"/api/admin/users/{me}", json={"role": "admin", "display_name": "Still me"}).status_code == 200  # changing other things about yourself is fine
    assert solo.get("/api/auth/me").status_code == 200


def test_a_school_administrator_sees_only_their_school(app, admin):
    school = admin.post("/api/admin/schools", json={"name": "Scope School"}).json()
    other = admin.post("/api/admin/schools", json={"name": "Other School"}).json()
    sa = login(app, "adm_sa2", "school_admin", school["id"])
    mine = admin.post("/api/admin/users", json={"username": "adm_in_scope", "display_name": "In", "school_id": school["id"]}).json()["id"]
    theirs = admin.post("/api/admin/users", json={"username": "adm_out_scope", "display_name": "Out", "school_id": other["id"]}).json()["id"]
    ids = [u["id"] for u in sa.get("/api/admin/users").json()["items"]]
    assert mine in ids and theirs not in ids
    assert sa.get(f"/api/admin/users/{mine}").status_code == 200 and sa.get(f"/api/admin/users/{theirs}").status_code == 404
    assert [s["id"] for s in sa.get("/api/admin/schools").json()["items"]] == [school["id"]]


def test_schools_rename_new_code_delete(admin):
    s = admin.post("/api/admin/schools", json={"name": "Old Name School"}).json()
    assert admin.put(f"/api/admin/schools/{s['id']}", json={"name": "New Name School"}).status_code == 200
    code = admin.post(f"/api/admin/schools/{s['id']}/code").json()["code"]
    assert len(code) == 6 and code != s["code"]
    row = [x for x in admin.get("/api/admin/schools").json()["items"] if x["id"] == s["id"]][0]
    assert row["name"] == "New Name School" and row["code"] == code and row["people"] == 0
    admin.post("/api/admin/users", json={"username": "adm_in_school", "display_name": "In", "school_id": s["id"]})
    assert admin.delete(f"/api/admin/schools/{s['id']}").status_code == 409  # people still belong to it
    db.run("UPDATE users SET school_id=NULL WHERE username='adm_in_school'")
    assert admin.delete(f"/api/admin/schools/{s['id']}").status_code == 200
    assert admin.put("/api/admin/schools/nope", json={"name": "Whatever Name"}).status_code == 404 and admin.post("/api/admin/schools/nope/code").status_code == 404


def test_curriculum_view_edit_hide_unhide_and_undo(admin):
    tree = admin.get("/api/admin/curriculum", params={"subject": "maths", "grade": 9}).json()
    first = tree["chapters"][0]
    sub = first["subtopics"][1]
    assert first["origin"] == "syllabus" and not first["hidden"] and sub["lessons"] == 0
    assert admin.get("/api/admin/curriculum", params={"subject": "nope", "grade": 9}).status_code == 400
    edit = lambda **b: admin.post("/api/admin/curriculum/edit", json=b)  # noqa: E731

    def find(tree_):
        chap = next(c for c in tree_["chapters"] if c["id"] == first["id"])
        return chap, next((s for s in chap["subtopics"] if s["id"] == sub["id"]), None)
    assert edit(op="hide_subtopic", id=sub["id"]).status_code == 200
    chap, s = find(admin.get("/api/admin/curriculum", params={"subject": "maths", "grade": 9}).json())
    assert s["hidden"] is True and sub["id"] not in [x.id for c in curriculum.chapters("maths", 9) for x in c.subtopics]  # students no longer see it
    assert edit(op="unhide_subtopic", id=sub["id"]).status_code == 200
    chap, s = find(admin.get("/api/admin/curriculum", params={"subject": "maths", "grade": 9}).json())
    assert s["hidden"] is False and [x["id"] for x in chap["subtopics"]].index(sub["id"]) == 1  # back where it was
    assert edit(op="rename_subtopic", id=sub["id"], title="A better title").status_code == 200
    assert edit(op="hide_chapter", id=first["id"], hidden=True).status_code == 200
    assert next(c for c in admin.get("/api/admin/curriculum", params={"subject": "maths", "grade": 9}).json()["chapters"] if c["id"] == first["id"])["hidden"] is True
    assert edit(op="add_chapter", subject="maths", grade=9, title="Vedic Maths", subtopics=["Squares", "Cubes"]).status_code == 200
    added = next(c for c in admin.get("/api/admin/curriculum", params={"subject": "maths", "grade": 9}).json()["chapters"] if c["title"] == "Vedic Maths")
    assert added["origin"] == "added" and len(added["subtopics"]) == 2
    assert edit(op="add_subtopic", chapter=added["id"], title="Roots").status_code == 200
    assert edit(op="rename_chapter").status_code == 400
    assert admin.post("/api/admin/curriculum/undo").json()["undone"]["op"] == "add_subtopic"
    assert len(next(c for c in admin.get("/api/admin/curriculum", params={"subject": "maths", "grade": 9}).json()["chapters"] if c["title"] == "Vedic Maths")["subtopics"]) == 2
    assert len(admin.get("/api/admin/curriculum/edits").json()["edits"]) == 5
    for _ in range(5):
        assert admin.post("/api/admin/curriculum/undo").status_code == 200
    assert admin.post("/api/admin/curriculum/undo").status_code == 404  # nothing left to take back
    assert next(c for c in admin.get("/api/admin/curriculum", params={"subject": "maths", "grade": 9}).json()["chapters"] if c["id"] == first["id"])["hidden"] is False


def test_lessons_are_listed_judged_activated_and_deleted(admin, monkeypatch):
    monkeypatch.setattr(config, "MOCK", True)
    sub = "phy-8-heat-and-temperature.1" if curriculum.get_subtopic("phy-8-heat-and-temperature.1") else "phy-9-motion.2"
    list(lesson.stream_lesson(sub, "en", "standard", "CBSE"))
    var = lesson.variant("en", "standard", "CBSE")
    v1 = lesson.active_version(sub, var)["id"]
    v2 = lesson.save_version(sub, var, lesson.active_version(sub, var)["sections"], [], "test", "teacher", "draft")
    found = admin.get("/api/admin/lessons", params={"q": sub}).json()
    assert {i["id"] for i in found["items"]} >= {v1, v2} and next(i for i in found["items"] if i["id"] == v2)["active"] is True
    assert all(i["id"] != v1 or i["active"] is False for i in found["items"])
    assert admin.get("/api/admin/lessons", params={"status": "approved", "q": sub}).json()["total"] == 0
    full = admin.get(f"/api/admin/lessons/{v2}").json()
    assert full["sections"] and full["title"]
    assert admin.post(f"/api/admin/lessons/{v2}/status", json={"status": "approved", "note": "good"}).status_code == 200
    assert admin.get("/api/admin/lessons", params={"status": "approved", "q": sub}).json()["total"] == 1
    assert admin.post(f"/api/admin/lessons/{v1}/activate").status_code == 200 and lesson.active_version(sub, var)["id"] == v1
    from backend import extras
    extras.figure(sub, "en", "standard", "CBSE", 1)  # a picture made from v1
    assert db.scalar("SELECT COUNT(*) FROM extras WHERE subtopic_id=? AND kind LIKE ?", (sub, f"pic:v{v1}:%"), 0) == 1
    out = admin.delete(f"/api/admin/lessons/{v1}").json()
    assert out["now_active"] == v2 and lesson.active_version(sub, var)["id"] == v2  # the newest takes over
    assert db.scalar("SELECT COUNT(*) FROM extras WHERE subtopic_id=? AND kind LIKE ?", (sub, f"pic:v{v1}:%"), 0) == 0  # and what was made from v1 goes with it
    assert admin.delete(f"/api/admin/lessons/{v1}").status_code == 404 and admin.get(f"/api/admin/lessons/{v1}").status_code == 404
    out = admin.post(f"/api/admin/topics/{sub}/clear", json={"what": "lessons"}).json()
    assert out["lessons"] == 1 and lesson.active_version(sub, var) is None
    assert admin.post("/api/admin/topics/nope.1/clear", json={"what": "extras"}).status_code == 404
    assert admin.post("/api/admin/topics/my-abc/clear", json={"what": "extras"}).status_code == 404


def test_students_own_topics_can_be_reviewed_and_removed(admin, monkeypatch):
    from backend import mytopics, store
    monkeypatch.setattr(config, "MOCK", True)
    stu = accounts.create_user("adm_topic_owner", PW, "Owner", "student", 2006, profile={"grade": 9})
    item = mytopics.create(store.get_student(stu["id"]) | {"language": "en"}, "How do black holes form?", "", "physics")
    listed = admin.get("/api/admin/custom-topics", params={"q": "black holes"}).json()
    assert listed["total"] == 1 and listed["items"][0]["username"] == "adm_topic_owner" and listed["items"][0]["id"] == item["id"]
    # a student's private lessons never show up in the lesson list
    assert all(not i["subtopic_id"].startswith("my-") for i in admin.get("/api/admin/lessons").json()["items"])
    assert admin.delete(f"/api/admin/custom-topics/{item['id']}").status_code == 200
    assert admin.get("/api/admin/custom-topics", params={"q": "black holes"}).json()["total"] == 0 and admin.delete(f"/api/admin/custom-topics/{item['id']}").status_code == 404


def test_announcements_reach_the_right_people(admin, app):
    school = admin.post("/api/admin/schools", json={"name": "Notice School"}).json()
    a = admin.post("/api/admin/users", json={"username": "adm_note_a", "display_name": "A", "role": "student", "school_id": school["id"], "password": PW}).json()["id"]
    t = admin.post("/api/admin/users", json={"username": "adm_note_t", "display_name": "T", "role": "teacher", "school_id": school["id"]}).json()["id"]
    b = admin.post("/api/admin/users", json={"username": "adm_note_b", "display_name": "B", "role": "student"}).json()["id"]
    n = lambda uid: db.scalar("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='announcement'", (uid,), 0)  # noqa: E731
    assert admin.post("/api/admin/announce", json={"title": "School only", "audience": "school", "school_id": school["id"]}).json()["recipients"] == 2
    assert (n(a), n(t), n(b)) == (1, 1, 0)
    assert admin.post("/api/admin/announce", json={"title": "Students", "body": "Exams soon", "audience": "students"}).json()["recipients"] >= 2
    assert (n(a), n(t), n(b)) == (2, 1, 1)
    assert admin.post("/api/admin/announce", json={"title": "Pick one", "audience": "school"}).status_code == 400
    assert admin.post("/api/admin/announce", json={"title": "Bad link", "audience": "all", "link": "javascript:alert(1)"}).status_code == 400
    assert admin.post("/api/admin/announce", json={"title": "x"}).status_code == 422
    db.run("UPDATE users SET disabled=1 WHERE id=?", (b,))
    before = n(b)
    admin.post("/api/admin/announce", json={"title": "Everyone", "audience": "all"})
    assert n(b) == before  # a disabled account is not sent anything
    student = login(app, "adm_note_a")  # the person sees it under the bell
    seen = student.get("/api/notifications").json()["items"]
    assert [x["title"] for x in seen if x["kind"] == "announcement"][:2] == ["Everyone", "Students"] and seen[0]["read_at"] is None


def test_bulk_job_writes_a_chapters_lessons_and_can_be_cancelled(admin, monkeypatch):
    monkeypatch.setattr(config, "MOCK", True)
    chapter = next(c for c in curriculum.admin_tree("maths", 8) if not c["hidden"])
    ids = [s["id"] for s in chapter["subtopics"]]
    var = lesson.variant("en", "standard", "CBSE")
    assert not any(lesson.active_version(i, var) for i in ids)
    job = admin.post("/api/admin/jobs", json={"subject": "maths", "grade": 8, "chapter_id": chapter["id"], "extras": True}).json()
    assert job["total"] == len(ids) and job["status"] in ("queued", "running", "done")
    for _ in range(100):
        j = next(x for x in admin.get("/api/admin/jobs").json()["items"] if x["id"] == job["id"])
        if j["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.1)
    assert j["status"] == "done" and j["done"] == len(ids) and j["failed"] == 0 and all(lesson.active_version(i, var) for i in ids)
    assert db.scalar("SELECT COUNT(*) FROM extras WHERE subtopic_id=? AND kind LIKE 'pic:%'", (ids[0],), 0) == 12  # the extras option made the pictures too
    again = admin.post("/api/admin/jobs", json={"subject": "maths", "grade": 8, "chapter_id": chapter["id"]}).json()
    for _ in range(100):
        j = next(x for x in admin.get("/api/admin/jobs").json()["items"] if x["id"] == again["id"])
        if j["status"] != "queued" and j["status"] != "running":
            break
        time.sleep(0.1)
    assert j["skipped"] == len(ids) and j["done"] == 0  # already written: nothing repeated
    assert admin.post("/api/admin/jobs", json={"subject": "nope", "grade": 8}).status_code == 400
    assert admin.post(f"/api/admin/jobs/{again['id']}/cancel").status_code == 404  # it has finished
    jobs.submit("hold", ["phy-9-motion.1"], "en", "standard", "CBSE")
    queued = jobs.submit("will be cancelled", ["phy-9-motion.2"], "en", "standard", "CBSE")
    assert jobs.cancel(queued["id"]) in (True, False)
    with pytest.raises(ValueError):
        jobs.submit("empty", [], "en", "standard", "CBSE")


def test_system_page_housekeeping_and_backups(admin, app):
    s = admin.get("/api/admin/system").json()
    assert s["app"]["auth"] == config.AUTH and s["storage"]["db_bytes"] > 0 and {"email", "push", "whatsapp"} == set(s["channels"]) and s["settings"]["idle_minutes"] == config.IDLE_MINUTES
    assert "password" not in str(s).lower() or "smtp_password" not in str(s).lower()  # no secrets are shown
    made = admin.post("/api/admin/backup").json()
    assert made["bytes"] > 0 and made["file"] in [b["name"] for b in admin.get("/api/admin/system").json()["storage"]["backups"]]
    got = admin.get(f"/api/admin/backups/{made['file']}")
    assert got.status_code == 200 and got.content[:15] == b"SQLite format 3"
    for bad in ("../../etc/passwd", "..%2F..%2Fsecret.db", "teacher-x/../../a.db", "notes.txt", "teacher-nope.db"):
        assert admin.get(f"/api/admin/backups/{bad}").status_code in (404, 405), bad
    assert admin.delete(f"/api/admin/backups/{made['file']}").status_code == 200 and admin.get(f"/api/admin/backups/{made['file']}").status_code == 404
    db.run("INSERT INTO email_otps (id, purpose, email, code_hash, salt, created_at, last_sent, expires_at) VALUES ('old1','signup','a@b.co','x','y',1,1,2)")
    assert admin.post("/api/admin/system/purge", json={"what": "codes"}).json()["removed"] >= 1
    db.run("INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen) VALUES ('stale1','nobody',1,2,1)")
    assert admin.post("/api/admin/system/purge", json={"what": "sessions"}).json()["removed"] >= 1 and admin.get("/api/auth/me").status_code == 200  # signed-in people stay signed in
    assert admin.post("/api/admin/system/purge", json={"what": "everything"}).status_code == 422


def test_what_an_administrator_does_is_written_to_the_audit_trail(admin):
    admin.post("/api/admin/schools", json={"name": "Audited School"})
    admin.post("/api/admin/announce", json={"title": "Audit me", "audience": "teachers"})
    actions = admin.get("/api/admin/audit/actions").json()["items"]
    assert "school_created" in actions and "announcement" in actions
    assert any(i["action"] == "announcement" for i in admin.get("/api/admin/audit", params={"q": "Audit me"}).json()["items"])


def test_the_lessons_list_accepts_the_filters_the_page_sends(admin):
    """An empty filter means "any"; a class that is not a number is refused."""
    assert admin.get("/api/admin/lessons", params={"offset": 0, "limit": 50}).status_code == 200
    assert admin.get("/api/admin/lessons?status=&q=&subject=&grade=&flagged=false&offset=0&limit=50").status_code == 200  # empty filters mean "any"
    assert admin.get("/api/admin/lessons", params={"grade": "nine"}).status_code == 400
    assert admin.get("/api/admin/lessons", params={"status": "draft", "grade": 9, "subject": "physics", "flagged": "true"}).status_code == 200
    assert admin.get("/api/admin/lessons", params={"status": "weird"}).status_code == 422
