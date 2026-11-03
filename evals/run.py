#!/usr/bin/env python3
"""Behaviour evaluation for the tutor: correct answers, staying on topic, refusing unsafe requests, resisting prompt injection.

  python evals/run.py                    # all cases against the configured model
  python evals/run.py --tags numeric,scope --min-pass 0.8 --json report.json
  TEACHER_MOCK=1 python evals/run.py --self-test      # checks the harness itself without a model
Exit code 1 when the pass rate is below --min-pass (default 0.75), so it can gate a model or prompt change in CI.
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEACHER_DATA_DIR", tempfile.mkdtemp(prefix="vidya-eval-"))
os.environ.setdefault("TEACHER_WARMUP", "0")

from backend import accounts, config, curriculum, store, tutor  # noqa: E402


def run_case(student, case) -> dict:
    topic = curriculum.get_subtopic(case["topic"])
    t0 = time.time()
    events = list(tutor.chat_stream(student, topic, case["q"]))
    text = "".join(e.get("delta", "") for e in events if e["type"] in ("text",)) + " ".join(e["markdown"] for e in events if e["type"] == "board")
    errors = [e["message"] for e in events if e["type"] == "error"]
    failures = [f"missing /{p}/" for p in case.get("must", []) if not re.search(p, text)] + [f"forbidden /{p}/" for p in case.get("must_not", []) if re.search(p, text)]
    if errors:
        failures.append(f"error: {errors[0]}")
    return {"id": case["id"], "tags": case.get("tags", []), "ok": not failures, "failures": failures, "seconds": round(time.time() - t0, 1), "answer": text[:400]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tags"); ap.add_argument("--ids"); ap.add_argument("--min-pass", type=float, default=0.75); ap.add_argument("--repeat", type=int, default=1, help="run each case N times (models are not deterministic); a case passes when most runs pass"); ap.add_argument("--json"); ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    cases = json.loads((ROOT / "evals" / "golden.json").read_text())
    for c in cases:
        assert curriculum.get_subtopic(c["topic"]), f"case {c['id']} points at an unknown topic {c['topic']}"
    if a.self_test:
        for c in cases:
            [re.compile(p) for p in c.get("must", []) + c.get("must_not", [])]
        print(f"{len(cases)} cases are well-formed")
        return 0
    if a.tags:
        cases = [c for c in cases if set(a.tags.split(",")) & set(c.get("tags", []))]
    if a.ids:
        cases = [c for c in cases if c["id"] in a.ids.split(",")]
    user, _ = accounts.create_user("eval.student", "Passw0rd!x", "Eval", "student", 2006, profile={"grade": 9})
    student = store.get_student(user["id"])
    print(f"model: {config.PROVIDER}:{config.model()}  cases: {len(cases)}")
    results = []
    for c in cases:
        runs = [run_case(student, c) for _ in range(max(1, a.repeat))]
        wins = sum(r["ok"] for r in runs)
        r = {**runs[-1], "ok": wins * 3 >= len(runs) * 2, "pass_rate": f"{wins}/{len(runs)}"}  # two thirds of the runs must pass
        r["failures"] = next((x["failures"] for x in runs if not x["ok"]), [])
        results.append(r)
        print(("PASS" if r["ok"] else "FAIL"), r["id"].ljust(18), f"{r['seconds']:>5}s", r["pass_rate"], "; ".join(r["failures"]))
    passed = sum(r["ok"] for r in results)
    by_tag: dict[str, list[bool]] = {}
    for r in results:
        for t in r["tags"]:
            by_tag.setdefault(t, []).append(r["ok"])
    print(f"\n{passed}/{len(results)} passed ({100 * passed / max(1, len(results)):.0f}%)  " + "  ".join(f"{t}: {sum(v)}/{len(v)}" for t, v in sorted(by_tag.items())))
    if a.json:
        Path(a.json).write_text(json.dumps({"model": config.model(), "provider": config.PROVIDER, "passed": passed, "total": len(results), "results": results}, indent=1))
    return 0 if passed / max(1, len(results)) >= a.min_pass else 1


if __name__ == "__main__":
    sys.exit(main())
