#!/usr/bin/env python3
"""Write lessons ahead of time, so no student ever waits for one: every lesson (and, with --extras, its pictures, curiosity facts, 5-minute summary and
cheat sheet) is made once with the local model and kept in the database. Safe to stop and run again: anything already written is skipped.

  python scripts/pregenerate.py --subject maths --grade 9                      # one subject and class, English, standard level
  python scripts/pregenerate.py --subject physics --grade 10 --extras          # also pictures, facts, summary and cheat sheet
  python scripts/pregenerate.py --grade 9 --language hi --limit 20             # every subject of class 9 in Hindi, at most 20 new lessons
  python scripts/pregenerate.py --subject maths --grade 9 --dry-run            # just list what is missing

Run it when the teacher server is quiet (or on the same machine overnight): it uses the same model and the same database as the app.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config, curriculum, extras, lesson  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subject", help="subject id (physics, chemistry, biology, maths, computers, ...); default: all")
    ap.add_argument("--grade", type=int, help="class 7-12; default: all")
    ap.add_argument("--language", default="en", choices=list(config.LANGUAGES))
    ap.add_argument("--level", default="standard", choices=list(config.LEVELS))
    ap.add_argument("--board", default="CBSE", choices=config.BOARDS)
    ap.add_argument("--limit", type=int, default=0, help="stop after writing this many new lessons (0 = no limit)")
    ap.add_argument("--extras", action="store_true", help="also make pictures, curiosity facts, the 5-minute summary and the cheat sheet")
    ap.add_argument("--dry-run", action="store_true", help="only list the lessons that are not written yet")
    a = ap.parse_args()
    if a.subject and a.subject not in curriculum.SUBJECTS:
        ap.error(f"unknown subject {a.subject!r}; choose from {', '.join(curriculum.SUBJECTS)}")
    var = lesson.variant(a.language, a.level, a.board)
    subjects = [a.subject] if a.subject else list(curriculum.SUBJECTS)
    grades = [a.grade] if a.grade else config.GRADES
    topics = [s.id for sub in subjects for g in grades for c in curriculum.chapters(sub, g, "", "" if a.board == "CBSE" else a.board, a.level) for s in c.subtopics]
    todo = [t for t in topics if not lesson.active_version(t, var)]
    print(f"{len(topics)} topics, {len(topics) - len(todo)} already written, {len(todo)} to write ({a.language}, {a.level}, {a.board})")
    if a.dry_run:
        print("\n".join(todo))
        return 0
    done = failed = 0
    for sid in todo:
        if a.limit and done >= a.limit:
            break
        t0 = time.time()
        err = None
        for ev in lesson.stream_lesson(sid, a.language, a.level, a.board):
            if ev["type"] == "error":
                err = ev["message"]
        if err:
            failed += 1
            print(f"FAIL {sid}: {err}")
            continue
        done += 1
        print(f"ok   {sid}  {time.time() - t0:.0f}s  ({done}/{len(todo)})", flush=True)
    if a.extras:
        for sid in topics:
            v = lesson.active_version(sid, var)
            if not v:
                continue
            t0 = time.time()
            for fn, args in ((extras.did_you_know, ()), (extras.quick_summary, ()), (extras.cheatsheet, ())):
                try:
                    fn(sid, a.language, a.level, a.board, *args)
                except Exception as exc:  # noqa: BLE001 - keep going, report at the end
                    print(f"     {sid} {fn.__name__}: {exc}")
            for i in range(len(v["sections"])):
                extras.figure(sid, a.language, a.level, a.board, i)
            print(f"extras {sid}  {time.time() - t0:.0f}s", flush=True)
    print(f"finished: {done} written, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
