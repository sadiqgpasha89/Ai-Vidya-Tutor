"""Tools the tutor agent can call. Each handler validates its own input (tool inputs are model output)."""
from __future__ import annotations

import ast
import json
import math
import operator
import re
from dataclasses import dataclass, field

from . import config, curriculum, graphing, rag, sandbox, store, svgsafe, units
from .logs import get


log = get("tools")

# ---- tool specs --------------------------------------------------------------------------------
_S = {"eager_input_streaming": True}
SPECS: dict[str, dict] = {
    "calculator": {
        "name": "calculator", **_S,
        "description": (
            "Evaluate a mathematical expression exactly and return it as 'expression = result'. Supports + - * / // % ** ^ (power), "
            "parentheses, constants pi and e, and functions sqrt, sin, cos, tan (radians), asin, acos, atan, log (natural), "
            "log10, log2, exp, abs, factorial, radians, degrees. Use it for any arithmetic you are not completely sure about. "
            "ALWAYS put parentheses around every sum or difference that is divided or multiplied: (30 - 10) / 5, not 30 - 10 / 5. "
            "Do not call it when there is nothing to calculate."),
        "input_schema": {"type": "object", "properties": {"expression": {"type": "string", "description": "e.g. '0.5 * 2 * 9.8 ** 2'"}}, "required": ["expression"]},
    },
    "algebra": {
        "name": "algebra", **_S,
        "description": (
            "Exact symbolic maths (SymPy): simplify, expand, factor, solve (equations like 'x**2 - 5*x + 6 = 0'; list several separated by ';' for a system), "
            "diff (derivative), integrate (add 'extra' = 'a,b' for a definite integral), limit (extra = the point, e.g. '0' or 'oo'), "
            "evaluate (extra = substitutions such as 'x=2,y=3'), equals (extra = a second expression; checks they are identical). "
            "Use ** for powers. Use it to verify algebra, calculus and equation answers."),
        "input_schema": {"type": "object", "properties": {
            "operation": {"type": "string", "enum": ["simplify", "expand", "factor", "solve", "diff", "integrate", "limit", "evaluate", "equals"]},
            "expression": {"type": "string"}, "variable": {"type": "string", "description": "default x"}, "extra": {"type": "string"}},
            "required": ["operation", "expression"]},
    },
    "show_on_board": {
        "name": "show_on_board", **_S,
        "description": (
            "Put content on the student's whiteboard panel next to the chat: formulas, derivations, step-by-step solutions, "
            "tables, code, or a labelled diagram. Use Markdown with LaTeX ($...$ inline, $$...$$ block). For diagrams pass a "
            "self-contained SVG (viewBox 0 0 600 400, no scripts, readable labels, high contrast on a white background)."),
        "input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "markdown": {"type": "string"}, "svg": {"type": "string"}}, "required": ["title", "markdown"]},
    },
    "plot_graph": {
        "name": "plot_graph", **_S,
        "description": "Draw the graph of one to four functions of x on the board (e.g. 'x**2 - 4', 'sin(x)'). Use for functions, motion graphs and Ohm's law lines.",
        "input_schema": {"type": "object", "properties": {"expressions": {"type": "array", "items": {"type": "string"}}, "x_min": {"type": "number"},
                                                          "x_max": {"type": "number"}, "title": {"type": "string"}}, "required": ["expressions", "x_min", "x_max"]},
    },
    "run_python": {
        "name": "run_python", **_S,
        "description": "Run a short Python program in a locked-down sandbox (no network or files; math, statistics, fractions, random, itertools, sympy, numpy only) and return its printed output. Use it to demonstrate or verify code.",
        "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
    },
    "unit_convert": {
        "name": "unit_convert", **_S,
        "description": "Convert a value between units (length, mass, time, speed, area, volume, force, energy, power, pressure, temperature C/K/F, angle, data...).",
        "input_schema": {"type": "object", "properties": {"value": {"type": "number"}, "from_unit": {"type": "string"}, "to_unit": {"type": "string"}}, "required": ["value", "from_unit", "to_unit"]},
    },
    "search_textbook": {
        "name": "search_textbook", **_S,
        "description": "Search the school's textbook library and this student's own uploaded notes/PDFs for passages about a question. Quote and cite what you use as [1], [2].",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    "web_search": {
        "name": "web_search", **_S,
        "description": "Search the web for current facts the textbook would not have. Use sparingly; prefer the syllabus and textbook.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    "check_student_work": {
        "name": "check_student_work", **_S,
        "description": "Check a student's written solution step by step. Pass the problem and the student's steps exactly as written; returns per-step verdicts.",
        "input_schema": {"type": "object", "properties": {"problem": {"type": "string"}, "student_steps": {"type": "string"}}, "required": ["problem", "student_steps"]},
    },
    "find_topics": {
        "name": "find_topics", **_S,
        "description": (
            "Search the syllabus (all subjects, Grades 7-12) for topics matching a query. Use when the student asks about "
            "something that belongs to a different topic, so you can point them to the right lesson. Results appear to the student as clickable chips."),
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "subject": {"type": "string", "enum": list(curriculum.SUBJECTS)},
                                                          "grade": {"type": "integer", "description": "Restrict to one grade (7-12)"}}, "required": ["query"]},
    },
    "get_prerequisites": {
        "name": "get_prerequisites", **_S,
        "description": "List the topics a student should know before the current topic (earlier in the chapter and from earlier chapters/grades).",
        "input_schema": {"type": "object", "properties": {}},
    },
    "get_student_profile": {
        "name": "get_student_profile", **_S,
        "description": "Get this student's grade, level, mastery of the current topic, recent topics, and learning signals you recorded earlier.",
        "input_schema": {"type": "object", "properties": {}},
    },
    "record_learning_signal": {
        "name": "record_learning_signal", **_S,
        "description": (
            "Remember something important about how this student is doing so future lessons and revision adapt. Use sparingly, "
            "only when you clearly observe it. kind: misconception (a wrong belief), struggling (needs more help), "
            "mastered (clearly understands), curious (wants to go deeper)."),
        "input_schema": {"type": "object", "properties": {"kind": {"type": "string", "enum": ["misconception", "struggling", "mastered", "curious"]},
                                                          "note": {"type": "string", "description": "One short sentence"}}, "required": ["kind", "note"]},
    },
}
TOOLS = list(SPECS.values())  # everything (used by tests / Claude)

_MATHY = {"maths", "physics", "chemistry", "commerce"}


def specs_for(topic: dict, student: dict, small_model: bool = False, has_docs: bool = False) -> list[dict]:
    """Subset of tools worth offering for this topic (a small model gets confused by a long tool menu)."""
    names = ["calculator", "show_on_board", "find_topics", "record_learning_signal"]
    subject = topic["subject"]
    if subject in _MATHY:
        names += ["unit_convert"] if subject in ("physics", "chemistry") else []
        names += ["check_student_work"]
    if subject in ("maths", "physics"):
        names += ["plot_graph", "algebra"]
    if subject == "computers":
        names += ["run_python"]
    if subject == "chemistry":
        names += ["algebra"]
    if has_docs:
        names += ["search_textbook"]
    if config.WEB_SEARCH:
        names += ["web_search"]
    if not small_model:
        names += ["get_student_profile", "get_prerequisites"]
    return [SPECS[n] for n in dict.fromkeys(names)]


@dataclass
class ToolContext:
    student: dict
    topic: dict
    events: list[dict] = field(default_factory=list)  # UI events produced by tool calls
    board_shown: bool = False


# ---- safe calculator ---------------------------------------------------------------------------
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos,
    "atan": math.atan, "log": math.log, "log10": math.log10, "log2": math.log2, "exp": math.exp, "abs": abs,
    "factorial": math.factorial, "radians": math.radians, "degrees": math.degrees,
}
_CONSTS = {"pi": math.pi, "e": math.e}


def safe_eval(expression: str, names: dict[str, float] | None = None) -> float | int:
    """Evaluate arithmetic with a whitelist of operators/functions. `names` supplies variables such as x."""
    if len(expression) > 300:
        raise ValueError("expression too long")
    tree = ast.parse(expression.replace("^", "**").replace("×", "*").replace("÷", "/").replace("−", "-"), mode="eval")
    names = names or {}

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.Name) and node.id in names:
            return names[node.id]
        if isinstance(node, ast.Name) and node.id in _CONSTS:
            return _CONSTS[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and (abs(right) > 1000 or abs(left) > 1e12):
                raise ValueError("power too large")
            return _BIN[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UN:
            return _UN[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
            args = [ev(a) for a in node.args]
            if node.func.id == "factorial" and (not args or args[0] > 500):
                raise ValueError("factorial too large")
            return _FUNCS[node.func.id](*args)
        raise ValueError("unsupported expression")

    return ev(tree)


def _str(args: dict, key: str, limit: int = 2000) -> str | None:
    v = args.get(key)
    return v.strip()[:limit] if isinstance(v, str) and v.strip() else None


def _calculator(args: dict, ctx: ToolContext) -> str:
    expr = _str(args, "expression", 300)
    if not expr:
        return "error: 'expression' must be a non-empty string"
    if re.fullmatch(r"\s*[-+]?[\d.]+\s*", expr):
        return "error: nothing to calculate here; just answer in words."
    try:
        value = safe_eval(expr)
    except ZeroDivisionError:
        return "error: division by zero (undefined)"
    except (ValueError, SyntaxError, TypeError, OverflowError) as exc:
        return f"error: {exc}"
    if isinstance(value, float):
        value = float(f"{value:.12g}")
    return f"{expr} = {value}"  # echo the expression so a wrong one (missing brackets) is visible to the model


_ALGEBRA = r'''
import json, sympy as sp
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application, convert_xor
T = standard_transformations + (implicit_multiplication_application, convert_xor)
op, expr, var, extra = json.loads(__PAYLOAD__)
names = {c: sp.Symbol(c) for c in "abcdefghijklmnopqrstuvwxyz"}
names.update({"pi": sp.pi, "e": sp.E, "oo": sp.oo, "E": sp.E, "I": sp.I})
for f in "sin cos tan asin acos atan sinh cosh tanh exp log sqrt Abs factorial".split():
    names[f] = getattr(sp, f)
names["ln"] = sp.log
def P(s):
    return parse_expr(s.replace("^", "**"), local_dict=names, transformations=T)
v = names.get(var or "x", sp.Symbol(var or "x"))
if op == "solve":
    parts = [p for p in expr.split(";") if p.strip()]
    eqs = [sp.Eq(P(a), P(b)) if "=" in p else sp.Eq(P(p), 0) for p in parts for a, b in [(p.split("=") + ["0"])[:2]]]
    res = sp.solve(eqs if len(eqs) > 1 else eqs[0], dict=True) if len(eqs) > 1 else sp.solve(eqs[0], v)
elif op == "diff":
    res = sp.diff(P(expr), v)
elif op == "integrate":
    lim = [P(t) for t in extra.split(",")] if extra and "," in extra else None
    res = sp.integrate(P(expr), (v, lim[0], lim[1])) if lim else sp.integrate(P(expr), v)
elif op == "limit":
    res = sp.limit(P(expr), v, P(extra or "0"))
elif op == "evaluate":
    subs = {names.get(k.strip(), sp.Symbol(k.strip())): P(val) for k, val in (kv.split("=") for kv in (extra or "").split(",") if "=" in kv)}
    res = sp.simplify(P(expr).subs(subs))
elif op == "equals":
    res = sp.simplify(P(expr) - P(extra or "0")) == 0
else:
    res = {"simplify": sp.simplify, "expand": sp.expand, "factor": sp.factor}[op](P(expr))
print("result:", res)
if not isinstance(res, (bool, list, dict)):
    print("latex:", sp.latex(res))
    try:
        print("decimal:", sp.N(res, 8))
    except Exception:
        pass
'''


def _algebra(args: dict, ctx: ToolContext) -> str:
    op, expr = _str(args, "operation", 20), _str(args, "expression", 400)
    if op not in ("simplify", "expand", "factor", "solve", "diff", "integrate", "limit", "evaluate", "equals") or not expr:
        return "error: need a valid operation and a non-empty expression"
    var = (_str(args, "variable", 3) or "x")[:1]
    # Maths needs only letters, digits and operators: refuse anything else before it reaches the interpreter.
    for text in (expr, _str(args, "extra", 200) or ""):
        if "__" in text or not re.fullmatch(r"[\w\s+\-*/^().,=;<>|!]*", text) or re.search(r"import|exec|eval|open|lambda|getattr|compile", text):
            return "error: that expression contains characters or words that are not allowed"
    payload = json.dumps(json.dumps([op, expr, var, _str(args, "extra", 200) or ""]))
    res = sandbox.run_python(_ALGEBRA.replace("__PAYLOAD__", payload), timeout=15, check=False)
    if not res["ok"]:
        tail = res["stderr"].strip().splitlines()[-1:] or ["failed"]
        return f"error: could not do that ({tail[0][:150]})"
    return res["stdout"].strip()[:1500]


def _show_on_board(args: dict, ctx: ToolContext) -> str:
    title, md, svg = _str(args, "title", 120), _str(args, "markdown", 6000), args.get("svg")
    if not title or not md:
        return "error: 'title' and 'markdown' must be non-empty strings"
    event = {"type": "board", "title": title, "markdown": md}
    if isinstance(svg, str) and svg.strip():
        clean = svgsafe.sanitize(svg)
        if clean:
            event["svg"] = clean
    ctx.events.append(event)
    ctx.board_shown = True
    return "Shown on the student's board."


def _plot_graph(args: dict, ctx: ToolContext) -> str:
    exprs = args.get("expressions")
    if isinstance(exprs, str):
        exprs = [exprs]
    if not isinstance(exprs, list) or not all(isinstance(e, str) for e in exprs):
        return "error: 'expressions' must be a list of strings in x"
    try:
        svg, warnings = graphing.plot([e.strip() for e in exprs], float(args.get("x_min")), float(args.get("x_max")), _str(args, "title", 80) or "")
    except (ValueError, TypeError) as exc:
        return f"error: {exc}"
    ctx.events.append({"type": "board", "title": _str(args, "title", 80) or "Graph", "markdown": "", "svg": svg})
    ctx.board_shown = True
    return "Graph drawn on the board." + (" Note: " + "; ".join(warnings) if warnings else "")


def _run_python(args: dict, ctx: ToolContext) -> str:
    code = _str(args, "code", 6000)
    if not code:
        return "error: 'code' must be non-empty"
    res = sandbox.run_python(code, timeout=8)
    if not res["ok"]:
        return f"error: {res['stderr'].strip()[-600:]}"
    ctx.events.append({"type": "board", "title": "Python output", "markdown": f"```python\n{code}\n```\n\n**Output**\n\n```\n{res['stdout'].strip() or '(no output)'}\n```"})
    ctx.board_shown = True
    return "Output:\n" + (res["stdout"].strip() or "(no output)")


def _unit_convert(args: dict, ctx: ToolContext) -> str:
    try:
        v = float(args.get("value"))
        out = units.convert(v, str(args.get("from_unit", "")), str(args.get("to_unit", "")))
    except (TypeError, ValueError) as exc:
        return f"error: {exc}"
    return f"{v:g} {args['from_unit']} = {out:.10g} {args['to_unit']}"


def _search_textbook(args: dict, ctx: ToolContext) -> str:
    q = _str(args, "query", 300)
    if not q:
        return "error: 'query' must be a non-empty string"
    passages = rag.retrieve(q, ctx.topic["subject"], ctx.student["grade"], owner_id=ctx.student["id"], k=3)
    if not passages:
        return "No matching passage found in the textbook library or the student's uploads."
    ctx.events.append({"type": "sources", "passages": [{"title": p["title"], "page": p["page"], "scope": p["scope"]} for p in passages]})
    return rag.format_sources(passages)


def _web_search(args: dict, ctx: ToolContext) -> str:
    q = _str(args, "query", 200)
    if not q or not config.WEB_SEARCH:
        return "error: web search is not enabled"
    try:
        from ddgs import DDGS
        hits = list(DDGS().text(q, max_results=4))
    except Exception as exc:  # noqa: BLE001
        return f"error: web search unavailable ({type(exc).__name__})"
    return "\n".join(f"- {h.get('title')}: {h.get('body')} ({h.get('href')})" for h in hits) or "No results."


def _check_student_work(args: dict, ctx: ToolContext) -> str:
    from . import practice
    problem, steps = _str(args, "problem", 2000), _str(args, "student_steps", 4000)
    if not problem or not steps:
        return "error: need both the problem and the student's steps"
    r = practice.check_work(ctx.student, ctx.topic["id"], problem, steps)
    return json.dumps({"final_answer_correct": r.get("final_answer_correct"), "overall": r["overall"],
                       "steps": [{"step": s["text"][:80], "verdict": s["verdict"], "comment": s["comment"]} for s in r["steps"]], "suggestion": r["suggestion"]})


def _find_topics(args: dict, ctx: ToolContext) -> str:
    query = _str(args, "query", 200)
    if not query:
        return "error: 'query' must be a string"
    subject = args.get("subject") if args.get("subject") in curriculum.SUBJECTS else None
    grade = args.get("grade") if isinstance(args.get("grade"), int) else None
    hits = curriculum.search(query, subject, grade, limit=4)
    if hits:
        ctx.events.append({"type": "suggest", "topics": hits})
    return json.dumps(hits) if hits else "No matching topic found in the syllabus."


def _get_prerequisites(args: dict, ctx: ToolContext) -> str:
    pre = curriculum.prerequisites(ctx.topic["id"])
    return json.dumps([{"topic": p["title"], "why": p["why"]} for p in pre[:8]]) if pre else "No prerequisites recorded for this topic."


def _get_student_profile(args: dict, ctx: ToolContext) -> str:
    sid, st = ctx.student["id"], ctx.student
    progress = store.progress_map(sid)
    here = progress.get(ctx.topic["id"])
    recent = sorted(progress.items(), key=lambda kv: -(kv[1]["last"] or 0))[:5]
    names = []
    for tid, p in recent:
        t = curriculum.get_subtopic(tid)
        if t:
            names.append({"topic": f"{t['subject_name']} G{t['grade']}: {t['title']}", "mastery": p["mastery"]})
    return json.dumps({"name": st["name"], "grade": st["grade"], "level": st["level"], "current_topic_mastery": here["mastery"] if here else None,
                       "recent_topics": names, "signals": store.recent_signals(sid, limit=6)})


def _record_signal(args: dict, ctx: ToolContext) -> str:
    kind, note = args.get("kind"), _str(args, "note", 400)
    if kind not in ("misconception", "struggling", "mastered", "curious") or not note:
        return "error: need kind in {misconception, struggling, mastered, curious} and a non-empty note"
    store.add_signal(ctx.student["id"], ctx.topic["id"], kind, note)
    ctx.events.append({"type": "signal", "kind": kind, "note": note[:200]})
    return "Noted."


HANDLERS = {
    "calculator": _calculator, "algebra": _algebra, "show_on_board": _show_on_board, "plot_graph": _plot_graph, "run_python": _run_python,
    "unit_convert": _unit_convert, "search_textbook": _search_textbook, "web_search": _web_search, "check_student_work": _check_student_work,
    "find_topics": _find_topics, "get_prerequisites": _get_prerequisites, "get_student_profile": _get_student_profile, "record_learning_signal": _record_signal,
}


def run_tool(name: str, args, ctx: ToolContext) -> tuple[str, bool]:
    """Returns (result_text, is_error)."""
    handler = HANDLERS.get(name)
    if handler is None:
        return f"error: unknown tool {name}", True
    if not isinstance(args, dict):
        return "error: tool input was not a JSON object", True
    try:
        result = handler(args, ctx)
    except Exception as exc:  # noqa: BLE001 - a broken tool must not kill the lesson
        log.warning(f"tool {name} failed: {exc}")
        return f"error: {exc}", True
    return result, result.startswith("error:")
