"""Concept diagrams drawn by code from a small description the model writes (boxes, arrows and short labels).

The model only chooses the layout and the words; positions, text wrapping and arrows are computed here, so labels never overlap and the
picture is always readable - unlike free-hand SVG from a small model.
"""
from __future__ import annotations

import math
import re
import unicodedata
from xml.sax.saxutils import escape

from . import svgsafe

LAYOUTS = ("flow", "cycle", "compare", "map")
W, PAD = 600, 24
INK, MUTED = "#1f2937", "#4b5563"
TINTS = [("#dbeafe", "#2563eb"), ("#dcfce7", "#16a34a"), ("#fef3c7", "#d97706"), ("#fce7f3", "#db2777"), ("#ede9fe", "#7c3aed"), ("#cffafe", "#0891b2")]
RTL = {"ar", "ur"}
FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans', 'Noto Sans Devanagari', sans-serif"


_LATEX = {r"\\Delta": "Δ", r"\\delta": "δ", r"\\theta": "θ", r"\\pi": "π", r"\\times": "×", r"\\div": "÷", r"\\pm": "±", r"\\rightarrow": "→", r"\\to": "→", r"\\alpha": "α", r"\\beta": "β",
          r"\\omega": "ω", r"\\mu": "μ", r"\\lambda": "λ", r"\\sqrt": "√", r"\\cdot": "·", r"\\circ": "°", r"\\approx": "≈", r"\\leq": "≤", r"\\geq": "≥", r"\\infty": "∞"}


def unlatex(svg: str) -> str:
    """Models sometimes put LaTeX in diagram labels; an SVG label cannot render it, so write the symbols out."""
    for k, v in _LATEX.items():
        svg = re.sub(k + r"(?![A-Za-z])", v, svg)
    svg = re.sub(r"\\(?:frac|text|mathrm|mathbf)\{([^{}]*)\}(?:\{([^{}]*)\})?", lambda m: f"{m.group(1)}/{m.group(2)}" if m.group(2) else m.group(1), svg)
    svg = re.sub(r"\^\{?2\}?", "²", svg)
    return svg.replace("$", "").replace("\\", "")


def plain(text) -> str:
    """One line of label text with maths and Markdown written out (no $, no **, no backslashes)."""
    t = unlatex(re.sub(r"\*\*|__|`", "", str(text or "")))
    t = re.sub(r"\^\{?3\}?", "³", t)
    return " ".join(t.split())


def _w(text: str, size: float) -> float:
    """Rough rendered width: narrow for plain Latin, wide for scripts that draw bigger glyphs (CJK, Indic, Arabic...)."""
    total = 0.0
    for ch in text:
        if unicodedata.category(ch) in ("Mn", "Me", "Cf"):  # vowel signs and accents sit on the letter before them
            continue
        total += size * (1.0 if unicodedata.east_asian_width(ch) in "WF" else 0.58 if ord(ch) < 0x250 else 0.72)
    return total


def _wrap(text: str, size: float, width: float, max_lines: int = 4) -> list[str]:
    words, lines, cur = str(text).split(), [], ""
    for word in words:
        while _w(word, size) > width and len(word) > 1:  # one long word (or Chinese/Japanese, which has no spaces): cut it
            k = max(1, int(len(word) * width / _w(word, size)))
            if cur:
                lines.append(cur); cur = ""
            lines.append(word[:k]); word = word[k:]
        trial = f"{cur} {word}".strip()
        if _w(trial, size) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]; lines[-1] = lines[-1].rstrip(" ,;:.") + "…"
    return lines or [""]


class _Svg:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def rect(self, x, y, w, h, fill, stroke, r=10, sw=1.5) -> None:
        self.parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def text(self, x, y, s, size=15, fill=INK, anchor="middle", bold=False) -> None:
        weight = ' font-weight="bold"' if bold else ""
        self.parts.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}"{weight}>{escape(s)}</text>')

    def line(self, x1, y1, x2, y2, arrow=True, color=MUTED) -> None:
        head = ' marker-end="url(#arr)"' if arrow else ""
        self.parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="2"{head}/>')

    def circle(self, cx, cy, r, fill, stroke) -> None:
        self.parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')

    def done(self, height: float) -> str:
        defs = f'<defs><marker id="arr" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="{MUTED}"/></marker></defs>'
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {math.ceil(height)}" font-family="{FONT}"><rect width="{W}" height="{math.ceil(height)}" fill="#ffffff"/>'
                f'{defs}{"".join(self.parts)}</svg>')


def _title(g: _Svg, title: str) -> float:
    lines = _wrap(title, 22, W - 2 * PAD, 2)
    for i, ln in enumerate(lines):
        g.text(W / 2, PAD + 16 + i * 27, ln, 22, INK, bold=True)
    return PAD + 16 + (len(lines) - 1) * 27 + 24


def _box(g: _Svg, cx: float, top: float, width: float, item: dict, tint: tuple[str, str], min_h: float = 0) -> float:
    """A rounded box with a bold label and a smaller note under it, centred on cx. -> its height."""
    label = _wrap(item["label"], 19, width - 20, 2)
    note = _wrap(item["note"], 15, width - 20, 3) if item.get("note") else []
    h = max(min_h, 14 + len(label) * 23 + (len(note) * 19 + 4 if note else 0) + 10)
    g.rect(cx - width / 2, top, width, h, tint[0], tint[1])
    y = top + 14 + 16
    for ln in label:
        g.text(cx, y, ln, 19, INK, bold=True); y += 23
    y += 2
    for ln in note:
        g.text(cx, y, ln, 15, MUTED); y += 19
    return h


def _flow(spec: dict, rtl: bool) -> tuple[_Svg, float, list[tuple[float, float, float, float]]]:
    g, boxes, y = _Svg(), [], 0.0
    y = _title(g, spec["title"])
    items, bw = spec["items"][:6], 480
    for i, it in enumerate(items):
        tint = TINTS[i % len(TINTS)]
        top = y + 8
        h = _box(g, W / 2 + 14, top, bw, it, tint)
        bx = W / 2 - bw / 2 + 14
        g.circle(bx - 22, top + h / 2, 14, tint[1], tint[1])
        g.text(bx - 22, top + h / 2 + 5, str(i + 1), 14, "#ffffff", bold=True)
        boxes.append((bx, top, bw, h))
        y = top + h
        if i < len(items) - 1:
            g.line(W / 2 + 14, y, W / 2 + 14, y + 22)
            y += 22
    return g, y + PAD, boxes


def _cycle(spec: dict, rtl: bool):
    g, items = _Svg(), spec["items"][:6]
    top = _title(g, spec["title"])
    n, bw = len(items), 176
    rx, ry = 160, 28 * n if n > 3 else 120
    ry = max(ry, 110)
    cx, cy = W / 2, top + ry + 40
    nodes, boxes = [], []
    for i, it in enumerate(items):
        a = -math.pi / 2 + 2 * math.pi * i / n
        x, y = cx + rx * math.cos(a), cy + ry * math.sin(a)
        nodes.append((x, y))
    probe = _Svg()
    heights = [_box(probe, 0, 0, bw, it, TINTS[0]) for it in items]
    for i, (it, (x, y)) in enumerate(zip(items, nodes)):
        h = heights[i]
        _box(g, x, y - h / 2, bw, it, TINTS[i % len(TINTS)])
        boxes.append((x - bw / 2, y - h / 2, bw, h))
    for i in range(n):  # arrows between neighbouring boxes, drawn from edge to edge so they never run over a label
        (x1, y1), (x2, y2) = nodes[i], nodes[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        d = math.hypot(dx, dy) or 1
        def edge(px, py, h, sx, sy):  # where the segment leaves the box around (px, py)
            t = min((bw / 2) / abs(sx) if sx else 1e9, (h / 2) / abs(sy) if sy else 1e9)
            return px + sx * t, py + sy * t
        ax, ay = edge(x1, y1, heights[i], dx / d, dy / d)
        bx_, by_ = edge(x2, y2, heights[(i + 1) % n], -dx / d, -dy / d)
        if math.hypot(bx_ - ax, by_ - ay) > 14:
            g.line(ax, ay, bx_, by_)
    bottom = max(b[1] + b[3] for b in boxes)
    return g, bottom + PAD, boxes


def _compare(spec: dict, rtl: bool):
    g, cols = _Svg(), spec["columns"][:3]
    y = _title(g, spec["title"])
    n = len(cols)
    gap = 14
    cw = (W - 2 * PAD - gap * (n - 1)) / n
    size = 15 if n > 2 else 17
    blocks, boxes, heights = [], [], []
    for c in cols:
        head = _wrap(c["heading"], 19, cw - 16, 2)
        pts = [_wrap(p, size, cw - 34, 4) for p in c["points"][:5]]
        h = 12 + len(head) * 23 + 8 + sum(len(p) * (size + 5) + 8 for p in pts) + 6
        blocks.append((head, pts)); heights.append(h)
    full = max(heights)
    for i, (head, pts) in enumerate(blocks):
        tint = TINTS[i % len(TINTS)]
        x = PAD + i * (cw + gap)
        g.rect(x, y, cw, full, "#ffffff", tint[1])
        hh = 12 + len(head) * 23 + 4
        g.rect(x, y, cw, hh, tint[0], tint[1])
        ty = y + 12 + 16
        for ln in head:
            g.text(x + cw / 2, ty, ln, 19, INK, bold=True); ty += 23
        ty = y + hh + 8 + size
        for p in pts:
            g.circle(x + (cw - 14 if rtl else 14), ty - size / 3, 3, tint[1], tint[1])
            for ln in p:
                g.text(x + (cw - 26 if rtl else 26), ty, ln, size, INK, anchor="end" if rtl else "start"); ty += size + 5
            ty += 8
        boxes.append((x, y, cw, full))
    return g, y + full + PAD, boxes


def _map(spec: dict, rtl: bool):
    g, items = _Svg(), spec["items"][:7]
    top = _title(g, spec["title"])
    centre, spokes = items[0], items[1:] or []
    left, right = spokes[0::2], spokes[1::2]
    sw = 160
    probe = _Svg()
    heights = [_box(probe, 0, 0, sw, it, TINTS[0]) for it in spokes]
    lh, rh = heights[0::2], heights[1::2]
    colh = max(sum(lh) + 14 * max(len(lh) - 1, 0), sum(rh) + 14 * max(len(rh) - 1, 0), 90)
    cy, cw = top + 8 + colh / 2, 150
    ch = max(_box(probe, 0, 0, cw, centre, TINTS[0], 70), 70, 14 + len(_wrap(centre["label"], 20, cw - 20, 3)) * 24)
    boxes = []
    # the centre box: dark fill, white text
    lines = _wrap(centre["label"], 20, cw - 20, 3)
    g.rect(W / 2 - cw / 2, cy - ch / 2, cw, ch, "#1f2937", "#111827", r=14)
    ty = cy - (len(lines) - 1) * 12 + 6
    for ln in lines:
        g.text(W / 2, ty, ln, 20, "#ffffff", bold=True); ty += 24
    boxes.append((W / 2 - cw / 2, cy - ch / 2, cw, ch))
    for side, group, hs in ((0, left, lh), (1, right, rh)):
        total = sum(hs) + 14 * max(len(group) - 1, 0)
        y = cy - total / 2
        x = PAD + sw / 2 if side == 0 else W - PAD - sw / 2
        for it, h in zip(group, hs):
            idx = spokes.index(it)
            _box(g, x, y, sw, it, TINTS[(idx + 1) % len(TINTS)])
            ex = x + sw / 2 if side == 0 else x - sw / 2
            g.line(ex, y + h / 2, W / 2 - cw / 2 if side == 0 else W / 2 + cw / 2, cy, arrow=False)
            boxes.append((x - sw / 2, y, sw, h)); y += h + 14
    return g, top + 8 + colh + PAD, boxes


_BUILD = {"flow": _flow, "cycle": _cycle, "compare": _compare, "map": _map}


def clean_spec(raw: dict) -> dict | None:
    """Keep only what a layout can draw. -> a tidy spec, or None when the model's description is too thin to be a useful picture."""
    if not isinstance(raw, dict):
        return None
    layout = str(raw.get("layout", "")).strip().lower()
    title = plain(raw.get("title", ""))[:90]
    if layout not in LAYOUTS or not title:
        return None
    def s(v, n):
        return plain(v)[:n]
    if layout == "compare":
        cols = [{"heading": s(c.get("heading"), 40), "points": [s(p, 90) for p in (c.get("points") or []) if s(p, 90)][:5]}
                for c in (raw.get("columns") or []) if isinstance(c, dict)]
        cols = [c for c in cols if c["heading"] and c["points"]][:3]
        return {"layout": layout, "title": title, "columns": cols} if len(cols) >= 2 else None
    items = [{"label": s(i.get("label"), 48), "note": s(i.get("note"), 80)} for i in (raw.get("items") or []) if isinstance(i, dict)]
    items = [i for i in items if i["label"]]
    need = {"flow": 3, "cycle": 3, "map": 4}[layout]
    return {"layout": layout, "title": title, "items": items[:7]} if len(items) >= need else None


def _overlaps(boxes: list[tuple[float, float, float, float]]) -> bool:
    for i, (x1, y1, w1, h1) in enumerate(boxes):
        for x2, y2, w2, h2 in boxes[i + 1:]:
            if x1 < x2 + w2 - 1 and x2 < x1 + w1 - 1 and y1 < y2 + h2 - 1 and y2 < y1 + h1 - 1:
                return True
    return False


def render(spec: dict, language: str = "en") -> str | None:
    """-> sanitised SVG text for a spec from clean_spec(), or None if it cannot be laid out cleanly."""
    spec = clean_spec(spec)
    if not spec:
        return None
    rtl = language in RTL
    g, height, boxes = _BUILD[spec["layout"]](spec, rtl)
    if _overlaps(boxes) and spec["layout"] == "cycle":  # too many/wide boxes for a ring: a straight list always fits
        g, height, boxes = _flow(spec, rtl)
    if _overlaps(boxes):
        return None
    return svgsafe.sanitize(g.done(height))


_MD_STRIP = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")


def _phrase(text: str, words: int = 5) -> str:
    text = plain(re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)).strip(" :-–—.,;")
    w = text.split()
    return " ".join(w[:words]) + ("…" if len(w) > words else "")


def fallback_spec(title: str, display: str, kind: str = "") -> dict | None:
    """A plain diagram built straight from the section's own text (its bold terms and list items), for when the model's description is unusable.
    Steps for process-like sections, otherwise a concept map around the section title."""
    title = plain(title) or "Key points"
    bold = [m for m in re.findall(r"\*\*([^*\n]{2,60})\*\*", display or "")]
    bullets = [_MD_STRIP.sub("", ln) for ln in (display or "").splitlines() if _MD_STRIP.match(ln)]
    sentences = [x for x in re.split(r"(?<=[.!?।])\s+", re.sub(r"[#>*_`$]", "", display or "")) if len(x.split()) >= 4]
    seen, items = set(), []
    for src, limit in ((bold, 4), (bullets, 6), (sentences, 6)):
        for raw in src:
            label = _phrase(raw, 4 if src is bold else 5)
            if label and label.lower() not in seen:
                seen.add(label.lower())
                note = _phrase(raw, 12) if src is not bold and _phrase(raw, 12) != label else ""
                items.append({"label": label, "note": note})
            if len(items) >= limit and src is not sentences:
                break
        if len(items) >= 3:
            break
    items = items[:6]
    if len(items) < 3:
        return None
    if kind in ("how", "example", "tryit", "connect"):
        return {"layout": "flow", "title": title, "items": items}
    return {"layout": "map", "title": title, "items": [{"label": title, "note": ""}] + items[:6]}
