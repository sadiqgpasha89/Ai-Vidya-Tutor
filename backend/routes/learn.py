"""Student-facing learning API: browsing, lessons, tutor chat, quizzes, practice, tests, revision, notes, planner."""
from __future__ import annotations

import base64
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .. import (classes, config, curriculum, db, exams, extras, learning, lesson, llm, moderation, mytopics, notify, practice, prefetch, prompts, quiz, scheduler, semantic, store, studynotes,
                tutor, units, usage, viva)
from ..deps import ai_student, current_user, queued, sse, student_user

router = APIRouter(prefix="/api")


def _topic(subtopic_id: str, user: dict | None = None) -> dict:
    t = curriculum.get_subtopic(subtopic_id, owner=(user or {}).get("id", ""))  # a student's own topic is visible to that student only
    if not t:
        raise HTTPException(404, "Unknown topic")
    return t


def _screen(student: dict, *texts: str) -> None:
    """Free text a student sends to the model (anywhere, not only the chat) gets the same input guardrails: prohibited or injection text is refused politely."""
    text = "\n".join(t for t in texts if t and t.strip())
    verdict = moderation.check_input(text, student.get("language", "en"), deep=True) if text else {"action": "allow"}
    if verdict["action"] != "allow":
        raise HTTPException(422, verdict["reply"])


def _ai(fn, *args, **kw):
    """Run model-backed work inside a scheduler slot; turn model errors into friendly 502s."""
    try:
        with scheduler.slot(kw.pop("_priority", scheduler.ASSESS)):
            return fn(*args, **kw)
    except TimeoutError as exc:
        raise HTTPException(503, str(exc))
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, llm.friendly_error(exc))


# ---- meta & curriculum -------------------------------------------------------------------------
@router.get("/meta")
def meta():
    local = config.PROVIDER == "ollama" and not config.MOCK
    from .. import voice
    return {
        "subjects": [{"id": k, **v} for k, v in curriculum.SUBJECTS.items()], "grades": config.GRADES,
        "languages": [{"id": k, **v, "experimental": local and k not in config.LOCAL_LANGS} for k, v in config.LANGUAGES.items()],
        "levels": [{"id": k, "label": v} for k, v in config.LEVELS.items()], "boards": config.BOARDS,
        "goals": [{"id": k, "label": v} for k, v in config.GOALS.items()], "streams": [{"id": k, "label": v} for k, v in config.STREAMS.items()],
        "tracks": [{"id": k, "label": v} for k, v in config.TRACKS.items()], "stream_subjects": curriculum.STREAM_SUBJECTS,
        "voice": {"tts_languages": voice.tts_languages(), "stt": voice.stt_available()}, "auth": config.AUTH, "idle_minutes": config.IDLE_MINUTES, "picture_kinds": list(prompts.CONCEPT_KINDS),
        "sandbox": __import__("backend.sandbox", fromlist=["mode"]).mode(),
    }


@router.get("/curriculum")
def get_curriculum(subject: str, grade: int, user: dict = Depends(current_user)):
    if subject not in curriculum.SUBJECTS or grade not in config.GRADES:
        raise HTTPException(404, "Unknown subject or grade")
    st = store.get_student(user["id"]) if user["role"] == "student" else None
    track = ((st or {}).get("track") or "CS") if grade >= 11 else ""
    return {"subject": subject, "grade": grade, "track": track, "level": (st or {}).get("level", ""),
            "chapters": curriculum.chapter_tree(subject, grade, track, (st or {}).get("board", ""), (st or {}).get("level", ""))}


# ---- topics a student adds themselves ----------------------------------------------------------
class MyTopicIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    details: str = Field("", max_length=1000)
    subject: str = "general"


@router.get("/my-topics")
def my_topics(student: dict = Depends(student_user)):
    return {"items": mytopics.list_for(student["id"])}


@router.post("/my-topics")
def add_my_topic(body: MyTopicIn, student: dict = Depends(student_user)):
    try:
        item = mytopics.create(store.get_student(student["id"]) or student, body.title, body.details, body.subject)
    except mytopics.TopicError as exc:
        raise HTTPException(400, str(exc))
    usage.event(student["id"], "my_topic_added", item["id"])
    return {"item": item}


@router.delete("/my-topics/{subtopic_id}")
def remove_my_topic(subtopic_id: str, student: dict = Depends(student_user)):
    if not mytopics.delete(student["id"], subtopic_id):
        raise HTTPException(404, "Unknown topic")
    return {"ok": True}


@router.get("/topic/{subtopic_id}")
def get_topic(subtopic_id: str, user: dict = Depends(current_user)):
    t = _topic(subtopic_id, user)
    lang = (store.get_student(user["id"]) or {}).get("language", "en")
    t["prerequisites"] = curriculum.prerequisites(subtopic_id)
    t["objectives"] = extras.objectives(subtopic_id, lang, cached_only=True)
    t["media"] = db.all("SELECT id, kind, url, title FROM media WHERE subtopic_id=?", (subtopic_id,))
    t["bookmarked"] = subtopic_id in learning.bookmarks(user["id"]) if user["role"] == "student" else False
    return t


@router.get("/topic/{subtopic_id}/objectives")
def topic_objectives(subtopic_id: str, student: dict = Depends(ai_student)):
    _topic(subtopic_id, student)
    return _ai(extras.objectives, subtopic_id, student["language"], _priority=scheduler.ASSESS)


@router.get("/search")
def search(q: str, grade: int | None = None, user: dict = Depends(current_user)):
    q = q[:120]
    store.get_student(user["id"]) if user["role"] == "student" else None
    return semantic.search(q, grade, 14)


@router.get("/units")
def unit_table():
    return units.known()


@router.get("/units/convert")
def unit_convert(value: float, src: str, dst: str):
    try:
        return {"result": units.convert(value, src, dst)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ---- progress, plan, profile card --------------------------------------------------------------
@router.get("/me/progress")
def my_progress(student: dict = Depends(student_user)):
    sid = student["id"]
    due = []
    for tid in store.due_revisions(sid):
        t = curriculum.get_subtopic(tid)
        if t:
            due.append({k: t[k] for k in ("id", "title", "chapter", "subject", "subject_name", "grade")})
    return {"progress": store.progress_map(sid), "due": due, "streak": store.streak(sid), "card": learning.profile_card(sid), "cards": learning.card_counts(sid),
            "mistakes": db.scalar("SELECT COUNT(*) FROM mistakes WHERE student_id=? AND resolved_at IS NULL", (sid,), 0), "bookmarks": learning.bookmarks(sid),
            "unread": notify.unread_count(sid)}


@router.get("/me/activity")
def my_activity(student: dict = Depends(student_user)):
    return {"days": store.active_days(student["id"], 35)}


@router.get("/me/plan")
def my_plan(student: dict = Depends(student_user)):
    return learning.plan(student["id"])


@router.get("/me/assignments")
def my_assignments(student: dict = Depends(student_user)):
    return {"items": classes.assignments_for_student(student["id"]), "classes": classes.classes_for(student)}


class JoinIn(BaseModel):
    code: str
    nickname: str = Field("Student", max_length=20)
    share_leaderboard: bool = False


@router.post("/classes/join")
def join_class(body: JoinIn, student: dict = Depends(student_user)):
    cls = classes.join(student, body.code, body.nickname, body.share_leaderboard)
    return {"class": cls}


@router.get("/classes/{class_id}/leaderboard")
def class_leaderboard(class_id: str, student: dict = Depends(student_user)):
    if not db.one("SELECT 1 FROM class_members WHERE class_id=? AND student_id=?", (class_id, student["id"])):
        raise HTTPException(403, "You are not in this class")
    rows = classes.leaderboard(class_id)
    return {"rows": [{**r, "me": r["student_id"] == student["id"]} for r in rows], "note": "Weekly XP. Only students who opt in appear, with nicknames."}


# ---- lessons -----------------------------------------------------------------------------------
class LessonIn(BaseModel):
    subtopic_id: str
    force: bool = False
    tracked: bool = False  # the page already told us about this visit (see /lesson/check)


def _opened(student: dict, subtopic_id: str) -> int:
    """Record that a student opened a topic; -> the section they had reached. Also starts writing the next topic ahead of time."""
    store.mark_started(student["id"], subtopic_id)
    usage.event(student["id"], "lesson_open", subtopic_id)
    prefetch.after_open(subtopic_id, student["language"], student["level"], student["board"])
    return (store.progress_map(student["id"]).get(subtopic_id) or {}).get("last_section", 0)


@router.get("/lesson/check")
def lesson_check(subtopic_id: str, student: dict = Depends(student_user)):
    """What the server has for this student's lesson, without the lesson itself: lets a page that kept a copy open it at once.
    -> {"version": <the "version" event, or null if not written yet>, "resume": <section reached>}"""
    _topic(subtopic_id, student)
    resume = _opened(student, subtopic_id)
    v = lesson.active_version(subtopic_id, lesson.variant(student["language"], student["level"], student["board"]))
    return {"version": lesson.version_event(v) if v else None, "resume": resume}


@router.post("/lesson/stream")
def lesson_stream(body: LessonIn, student: dict = Depends(ai_student)):
    _topic(body.subtopic_id, student)
    args = (body.subtopic_id, student["language"], student["level"], student["board"])
    resume = (store.progress_map(student["id"]).get(body.subtopic_id) or {}).get("last_section", 0) if body.tracked else _opened(student, body.subtopic_id)
    cached = lesson.active_version(body.subtopic_id, lesson.variant(*args[1:])) is not None

    def run():
        yield {"type": "resume", "section": resume}
        generated = False
        for ev in lesson.stream_lesson(*args, force=False):
            generated = generated or (ev.get("type") == "done" and not ev.get("cached"))
            yield ev
        if generated:
            prefetch.after_lesson(*args)

    if cached:
        return sse(run())  # reading a lesson that is already written needs no model, so it must not wait in line behind one being written
    return queued(run, scheduler.LESSON, student["id"])


class SectionPos(BaseModel):
    subtopic_id: str
    section: int = Field(ge=0, le=40)


@router.post("/lesson/position")
def lesson_position(body: SectionPos, student: dict = Depends(student_user)):
    store.set_last_section(student["id"], body.subtopic_id, body.section)
    return {"ok": True}


class DoneIn(BaseModel):
    subtopic_id: str


@router.post("/lesson/complete")
def lesson_complete(body: DoneIn, student: dict = Depends(student_user)):
    _topic(body.subtopic_id, student)
    first = (store.progress_map(student["id"]).get(body.subtopic_id) or {}).get("status") != "completed"
    store.mark_completed(student["id"], body.subtopic_id)
    classes.auto_complete(student["id"], body.subtopic_id, "lesson")
    return {"ok": True, "reward": learning.award(student["id"], "lesson", 20 if first else 3)}


class RegenIn(BaseModel):
    subtopic_id: str
    section: int = Field(ge=0, le=11)
    guidance: str = Field("", max_length=300)


@router.post("/lesson/rewrite")
def rewrite_section(body: RegenIn, student: dict = Depends(ai_student)):
    """A student asks for one section to be explained another way. The new text is theirs only (not saved to the shared lesson)."""
    _topic(body.subtopic_id, student)
    _screen(student, body.guidance)
    return _ai(lesson.regenerate_section, body.subtopic_id, student["language"], student["level"], student["board"], body.section, body.guidance, _priority=scheduler.CHAT)


class ExtraIn(BaseModel):
    subtopic_id: str
    what: str = Field("", max_length=80)


@router.post("/lesson/cheatsheet")
def cheatsheet(body: ExtraIn, student: dict = Depends(ai_student)):
    _topic(body.subtopic_id, student)
    return {"markdown": _ai(extras.cheatsheet, body.subtopic_id, student["language"], student["level"], student["board"], _priority=scheduler.LESSON)}


@router.post("/lesson/diagram")
def diagram(body: ExtraIn, student: dict = Depends(ai_student)):
    _topic(body.subtopic_id, student)
    svg = _ai(extras.diagram, body.subtopic_id, student["language"], student["level"], student["board"], body.what, _priority=scheduler.LESSON)
    if not svg:
        raise HTTPException(502, "The diagram could not be drawn this time. Please try again.")
    return {"svg": svg}


class FigureIn(BaseModel):
    subtopic_id: str
    section: int = Field(ge=0, le=40)
    mode: Literal["full", "quick"] = "full"


@router.post("/lesson/figure")
def figure(body: FigureIn, student: dict = Depends(ai_student)):
    """A picture for one lesson section. {"figure": null} means this section has none (not an error)."""
    _topic(body.subtopic_id, student)
    return {"figure": _ai(extras.figure, body.subtopic_id, student["language"], student["level"], student["board"], body.section, body.mode, _priority=scheduler.BATCH)}


# ---- prepared study notes (bullet points + diagrams, kept per student) --------------------------
@router.get("/lesson-notes")
def lesson_notes(subtopic_id: str | None = None, student: dict = Depends(student_user)):
    """One topic's saved notes ({"notes": null} if none yet), or, without a topic, the list of everything the student has prepared."""
    if subtopic_id is None:
        return {"items": studynotes.list_for(student["id"])}
    _topic(subtopic_id, student)
    return {"notes": studynotes.get(student, subtopic_id)}


class NotesIn(BaseModel):
    subtopic_id: str


class FiguresIn(BaseModel):
    subtopic_id: str
    mode: Literal["full", "quick"] = "full"


@router.post("/lesson/figures")
def lesson_figures(body: FiguresIn, student: dict = Depends(student_user)):
    """Every picture already made for this lesson (or its 5-minute summary), in one read. Never draws anything."""
    _topic(body.subtopic_id, student)
    return {"figures": extras.cached_figures(body.subtopic_id, student["language"], student["level"], student["board"], body.mode)}


@router.post("/lesson-notes/prepare")
def lesson_notes_prepare(body: NotesIn, student: dict = Depends(ai_student)):
    """Write (or rewrite) the notes for a topic from its lesson, and keep them."""
    topic = _topic(body.subtopic_id, student)
    return {"notes": _ai(studynotes.prepare, student, body.subtopic_id, topic, _priority=scheduler.LESSON)}


@router.delete("/lesson-notes")
def lesson_notes_delete(subtopic_id: str, student: dict = Depends(student_user)):
    _topic(subtopic_id, student)
    studynotes.delete(student, subtopic_id)
    return {"ok": True}


@router.get("/lesson-notes/download")
def lesson_notes_download(subtopic_id: str, format: Literal["html", "md"] = "html", student: dict = Depends(student_user)):
    topic = _topic(subtopic_id, student)
    note = studynotes.get(student, subtopic_id)
    if not note:
        raise HTTPException(404, "Prepare the notes first.")
    name = (re.sub(r"[^A-Za-z0-9]+", "-", topic["title"]).strip("-") or "notes")[:60] + "-notes"
    if format == "md":
        return PlainTextResponse(studynotes.to_markdown(note), media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}.md"'})
    return HTMLResponse(studynotes.to_html(note), headers={"Content-Disposition": f'attachment; filename="{name}.html"'})


@router.post("/lesson/didyouknow")
def did_you_know(body: ExtraIn, student: dict = Depends(ai_student)):
    """Three curiosity-sparking facts about the topic (made once per lesson and kept)."""
    _topic(body.subtopic_id, student)
    return {"facts": _ai(extras.did_you_know, body.subtopic_id, student["language"], student["level"], student["board"], _priority=scheduler.ASSESS)}


@router.post("/lesson/quick")
def quick(body: ExtraIn, student: dict = Depends(ai_student)):
    _topic(body.subtopic_id, student)
    return {"sections": _ai(extras.quick_summary, body.subtopic_id, student["language"], student["level"], student["board"], _priority=scheduler.LESSON)}


@router.post("/lesson/exam-focus")
def exam_focus(body: ExtraIn, student: dict = Depends(ai_student)):
    _topic(body.subtopic_id, student)
    return {"markdown": _ai(extras.exam_focus, body.subtopic_id, student.get("goal") or "boards", student["level"], student["language"], _priority=scheduler.LESSON),
            "goal": student.get("goal") or "boards"}


class FeedbackIn(BaseModel):
    subtopic_id: str
    section: int = Field(ge=0, le=40)
    rating: int = Field(ge=-1, le=1)
    tag: Literal["", "too_easy", "too_hard", "confusing", "wrong", "great"] = ""


@router.post("/lesson/feedback")
def lesson_feedback(body: FeedbackIn, student: dict = Depends(student_user)):
    _topic(body.subtopic_id, student)
    learning.add_feedback(student["id"], body.subtopic_id, body.section, body.rating, body.tag)
    if body.tag == "wrong":
        learning.add_report(student["id"], "lesson", body.subtopic_id, f"section {body.section}", "Marked as wrong from the feedback buttons")
    return {"ok": True}


class ReportIn(BaseModel):
    kind: Literal["lesson", "chat", "quiz", "practice", "test", "other"] = "other"
    subtopic_id: str = ""
    ref: str = Field("", max_length=500)
    message: str = Field(min_length=3, max_length=2000)


@router.post("/report")
def report_mistake(body: ReportIn, user: dict = Depends(current_user)):
    rid = learning.add_report(user["id"], body.kind, body.subtopic_id, body.ref, body.message)
    usage.event(user["id"], "report", body.subtopic_id)
    return {"id": rid, "message": "Thank you! A teacher will check this."}


# ---- tutor chat --------------------------------------------------------------------------------
class ChatIn(BaseModel):
    subtopic_id: str
    message: str = Field("", max_length=4000)
    images: list[str] = Field(default_factory=list, max_length=3)
    regenerate: bool = False


@router.post("/chat/stream")
def chat_stream(body: ChatIn, student: dict = Depends(ai_student)):
    topic = _topic(body.subtopic_id, student)
    return queued(lambda: tutor.chat_stream(student, topic, body.message, body.images, body.regenerate), scheduler.CHAT, student["id"])


@router.get("/chat/history")
def chat_history(subtopic_id: str, student: dict = Depends(student_user)):
    _topic(subtopic_id, student)
    return {"messages": learning.chat_history(student["id"], subtopic_id), "boards": learning.boards(student["id"], subtopic_id)}


@router.delete("/chat/history")
def clear_chat(subtopic_id: str, student: dict = Depends(student_user)):
    learning.clear_chat(student["id"], subtopic_id)
    return {"ok": True}


# ---- quiz & teach-back -------------------------------------------------------------------------
class QuizIn(BaseModel):
    subtopic_id: str
    n: int = Field(5, ge=3, le=8)


@router.post("/quiz")
def make_quiz(body: QuizIn, student: dict = Depends(ai_student)):
    _topic(body.subtopic_id, student)
    return _ai(quiz.make_quiz, student, body.subtopic_id, student["language"], student["level"], body.n)


class MissedQ(BaseModel):
    question: str = Field(max_length=2000)
    options: list[str] = Field(default_factory=list, max_length=6)
    chosen: str = Field("", max_length=500)
    correct: str = Field("", max_length=500)
    explanation: str = Field("", max_length=2000)
    concept: str = Field("", max_length=200)


class QuizResultIn(BaseModel):
    subtopic_id: str
    correct: int = Field(ge=0, le=20)
    total: int = Field(ge=1, le=20)
    missed: list[MissedQ] = Field(default_factory=list, max_length=10)


@router.post("/quiz/result")
def quiz_result(body: QuizResultIn, student: dict = Depends(student_user)):
    _topic(body.subtopic_id, student)
    if body.correct > body.total:
        raise HTTPException(400, "correct cannot exceed total")
    mastery = store.record_evidence(student["id"], body.subtopic_id, body.correct / body.total, "quiz", weight=body.total)
    for m in body.missed[:6]:
        learning.add_mistake(student["id"], body.subtopic_id, "quiz", m.question, m.options, m.chosen, m.correct, m.explanation, m.concept)
        if m.concept:
            store.add_signal(student["id"], body.subtopic_id, "misconception", m.concept[:300])
    classes.auto_complete(student["id"], body.subtopic_id, "quiz", 100 * body.correct / body.total)
    reward = learning.award(student["id"], "quiz", 5 * body.correct + (10 if body.correct == body.total else 0), correct=body.correct, total=body.total)
    return {"mastery": round(mastery, 2), "reward": reward}


class TeachbackIn(BaseModel):
    subtopic_id: str
    explanation: str = Field(min_length=10, max_length=3000)


@router.post("/teachback")
def teachback(body: TeachbackIn, student: dict = Depends(ai_student)):
    _topic(body.subtopic_id, student)
    _screen(student, body.explanation)
    result = _ai(quiz.evaluate_teachback, student, body.subtopic_id, body.explanation)
    result["reward"] = learning.award(student["id"], "teachback", result["score"] // 5, score=result["score"])
    return result


# ---- practice, check my work -------------------------------------------------------------------
class PracticeIn(BaseModel):
    subtopic_id: str
    difficulty: Literal["", "easier", "standard", "harder"] = ""


@router.post("/practice/new")
def practice_new(body: PracticeIn, student: dict = Depends(ai_student)):
    _topic(body.subtopic_id, student)
    return _ai(practice.generate, student, body.subtopic_id, body.difficulty or None)


@router.get("/practice/{item_id}/hint")
def practice_hint(item_id: int, level: int = 0, student: dict = Depends(student_user)):
    try:
        return practice.hint(student["id"], item_id, level)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


class PracticeCheck(BaseModel):
    answer: str = Field("", max_length=500)
    steps: str = Field("", max_length=3000)
    reveal: bool = False


@router.post("/practice/{item_id}/check")
def practice_check(item_id: int, body: PracticeCheck, student: dict = Depends(ai_student)):
    _screen(student, body.steps or "")
    out = _ai(practice.check, student, item_id, body.answer, body.steps, body.reveal)
    if out.get("correct"):
        row = db.one("SELECT subtopic_id FROM practice_items WHERE id=?", (item_id,))
        classes.auto_complete(student["id"], row["subtopic_id"], "practice", 100)
    return out


class WorkIn(BaseModel):
    subtopic_id: str
    problem: str = Field(min_length=3, max_length=2000)
    steps: str = Field(min_length=3, max_length=4000)


@router.post("/check-work")
def check_work(body: WorkIn, student: dict = Depends(ai_student)):
    _topic(body.subtopic_id, student)
    _screen(student, body.problem, body.steps)
    return _ai(practice.check_work, student, body.subtopic_id, body.problem, body.steps)


# ---- viva --------------------------------------------------------------------------------------
@router.post("/viva/start")
def viva_start(body: DoneIn, student: dict = Depends(ai_student)):
    _topic(body.subtopic_id, student)
    return _ai(viva.start, student, body.subtopic_id)


class VivaAnswer(BaseModel):
    answer: str = Field(max_length=1500)


@router.post("/viva/{viva_id}/answer")
def viva_answer(viva_id: int, body: VivaAnswer, student: dict = Depends(ai_student)):
    _screen(student, body.answer)
    return _ai(viva.answer, student, viva_id, body.answer)


# ---- tests, papers, placement ------------------------------------------------------------------
class TestIn(BaseModel):
    subtopic_ids: list[str] = Field(min_length=1, max_length=12)
    preset: Literal["unit10", "half30", "board80"] = "unit10"
    assignment_id: str | None = None


@router.get("/tests/presets")
def test_presets():
    return {k: {"title": v["title"], "minutes": v["minutes"], "marks": sum(m * c for _, m, c in v["plan"]), "questions": sum(c for _, _, c in v["plan"])} for k, v in exams.PRESETS.items()}


@router.post("/tests")
def create_test(body: TestIn, student: dict = Depends(ai_student)):
    return _ai(exams.create_test, student, body.subtopic_ids, body.preset, body.assignment_id, _priority=scheduler.ASSESS)


@router.post("/tests/{test_id}/begin")
def begin_test(test_id: str, student: dict = Depends(student_user)):
    try:
        return exams.begin(student["id"], test_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


class SubmitIn(BaseModel):
    answers: dict[str, str | int | None] = Field(default_factory=dict)


@router.post("/tests/{test_id}/submit")
def submit_test(test_id: str, body: SubmitIn, student: dict = Depends(ai_student)):
    result = _ai(exams.submit, student, test_id, body.answers)
    if result.get("preset") == "diagnostic":
        result["advice"] = exams.diagnostic_advice(result)
    return result


@router.get("/tests")
def test_history(student: dict = Depends(student_user)):
    return {"items": exams.history(student["id"])}


@router.get("/tests/{test_id}/result")
def test_result(test_id: str, student: dict = Depends(student_user)):
    try:
        return exams.get_result(student["id"], test_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


class DiagIn(BaseModel):
    subject: str
    grade: int | None = None


@router.post("/diagnostic")
def start_diagnostic(body: DiagIn, student: dict = Depends(ai_student)):
    if body.subject not in curriculum.SUBJECTS:
        raise HTTPException(404, "Unknown subject")
    return _ai(exams.diagnostic, student, body.subject, body.grade)


# ---- mistakes notebook & revision --------------------------------------------------------------
@router.get("/mistakes")
def my_mistakes(all: bool = False, student: dict = Depends(student_user)):
    items = learning.mistakes(student["id"], all)
    for m in items:
        t = curriculum.get_subtopic(m["subtopic_id"]) or {}
        m["topic"] = t.get("title")
        m["subject_name"] = t.get("subject_name")
    return {"items": items}


@router.post("/mistakes/{mistake_id}/resolve")
def resolve_mistake(mistake_id: int, student: dict = Depends(student_user)):
    learning.resolve_mistake(student["id"], mistake_id)
    return {"ok": True, "reward": learning.award(student["id"], "mistake_fixed", 4)}


@router.get("/revision")
def revision(student: dict = Depends(student_user)):
    sid = student["id"]
    topics = []
    for tid in store.due_revisions(sid, 20):
        t = curriculum.get_subtopic(tid)
        if t:
            topics.append({k: t[k] for k in ("id", "title", "chapter", "subject", "subject_name", "grade")})
    return {"topics": topics, "cards": learning.due_cards(sid, 20), "counts": learning.card_counts(sid), "mistakes": len(learning.mistakes(sid))}


@router.post("/flashcards/generate")
def flashcards_generate(body: DoneIn, student: dict = Depends(ai_student)):
    _topic(body.subtopic_id, student)
    return {"cards": _ai(extras.flashcards, body.subtopic_id, student["language"], student["level"], student["board"])}


class CardIn(BaseModel):
    grade: int = Field(ge=0, le=3)


@router.post("/flashcards/{card_id}/review")
def card_review(card_id: int, body: CardIn, student: dict = Depends(student_user)):
    out = learning.review_card(student["id"], card_id, body.grade)
    out["reward"] = learning.award(student["id"], "card", 2)
    return out


# ---- notes, highlights, bookmarks --------------------------------------------------------------
class NoteIn(BaseModel):
    subtopic_id: str | None = None
    title: str = Field("", max_length=120)
    body: str = Field(max_length=20000)


@router.get("/notes")
def get_notes(subtopic_id: str | None = None, student: dict = Depends(student_user)):
    items = learning.notes(student["id"], subtopic_id)
    for n in items:
        t = curriculum.get_subtopic(n["subtopic_id"]) if n["subtopic_id"] else None
        n["topic"] = t["title"] if t else None
    return {"items": items, "bookmarks": [{"id": s, **{k: (curriculum.get_subtopic(s) or {}).get(k) for k in ("title", "subject_name", "grade")}} for s in learning.bookmarks(student["id"])]}


@router.post("/notes")
def add_note(body: NoteIn, student: dict = Depends(student_user)):
    return {"id": learning.add_note(student["id"], body.subtopic_id, body.title, body.body)}


@router.put("/notes/{note_id}")
def update_note(note_id: int, body: NoteIn, student: dict = Depends(student_user)):
    learning.update_note(student["id"], note_id, body.title, body.body)
    return {"ok": True}


@router.delete("/notes/{note_id}")
def delete_note(note_id: int, student: dict = Depends(student_user)):
    learning.delete_note(student["id"], note_id)
    return {"ok": True}


@router.get("/notes/export.md", response_class=PlainTextResponse)
def notes_export(student: dict = Depends(student_user)):
    return PlainTextResponse(learning.export_notes_markdown(student["id"]), headers={"Content-Disposition": 'attachment; filename="my-notes.md"'})


class HighlightIn(BaseModel):
    subtopic_id: str
    section: int = Field(ge=0, le=40)
    text: str = Field(min_length=2, max_length=600)
    color: str = "yellow"


@router.get("/highlights")
def get_highlights(subtopic_id: str, student: dict = Depends(student_user)):
    return {"items": learning.highlights(student["id"], subtopic_id)}


@router.post("/highlights")
def add_highlight(body: HighlightIn, student: dict = Depends(student_user)):
    return {"id": learning.add_highlight(student["id"], body.subtopic_id, body.section, body.text, body.color)}


@router.delete("/highlights/{hid}")
def delete_highlight(hid: int, student: dict = Depends(student_user)):
    learning.delete_highlight(student["id"], hid)
    return {"ok": True}


@router.post("/bookmarks/toggle")
def toggle_bookmark(body: DoneIn, student: dict = Depends(student_user)):
    _topic(body.subtopic_id, student)
    return {"bookmarked": learning.toggle_bookmark(student["id"], body.subtopic_id)}


# ---- textbook uploads (a student's own) ---------------------------------------------------------
@router.get("/library/mine")
def my_docs(student: dict = Depends(student_user)):
    from .. import rag
    return {"items": rag.docs("student", student["id"])}


class UploadIn(BaseModel):
    filename: str = Field(max_length=200)
    data_b64: str
    title: str = Field("", max_length=200)
    subject: str | None = None


@router.post("/library/mine")
def upload_mine(body: UploadIn, student: dict = Depends(ai_student)):
    try:
        raw = base64.b64decode(body.data_b64, validate=True)
    except ValueError:
        raise HTTPException(400, "The file could not be read")
    if len(raw) > config.MAX_UPLOAD:
        raise HTTPException(413, f"File is larger than {config.MAX_UPLOAD // 1024 // 1024} MB")
    return _ai(_ingest_upload, raw, body.filename, body.title or body.filename, student["id"], "student", body.subject, student["grade"])


def _ingest_upload(raw: bytes, filename: str, title: str, owner: str | None, scope: str, subject: str | None, grade: int | None) -> dict:
    import tempfile
    from pathlib import Path

    from .. import rag
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        if not raw.startswith(b"%PDF"):
            raise ValueError("That does not look like a PDF")
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(raw)
            f.flush()
            pages = rag.extract_pdf(Path(f.name))
    elif suffix in (".txt", ".md"):
        pages = [(1, raw.decode("utf-8", "replace"))]
    else:
        raise ValueError("Upload a PDF or a .txt / .md file")
    return rag.ingest(pages, scope, owner, title, filename, subject, grade)


@router.delete("/library/mine/{doc_id}")
def delete_mine(doc_id: int, student: dict = Depends(student_user)):
    from .. import rag
    if not rag.delete_doc(doc_id, student["id"]):
        raise HTTPException(404, "Not found")
    return {"ok": True}
