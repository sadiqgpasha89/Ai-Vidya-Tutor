"""Server-side function plotting to a clean SVG (used by the tutor's plot_graph tool and the UI grapher)."""
from __future__ import annotations

import html
import math

from . import tools

COLORS = ["#2563eb", "#dc2626", "#16a34a", "#9333ea"]
W, H, PAD = 600, 400, 44


def _nice_ticks(lo: float, hi: float, n: int = 6) -> list[float]:
    span = hi - lo or 1.0
    step = 10 ** math.floor(math.log10(span / n))
    for mult in (1, 2, 5, 10):
        if span / (step * mult) <= n:
            step *= mult
            break
    first = math.ceil(lo / step) * step
    ticks, v = [], first
    while v <= hi + 1e-9:
        ticks.append(round(v, 10))
        v += step
    return ticks


def _fmt(v: float) -> str:
    return f"{v:g}" if abs(v) < 1e6 else f"{v:.1e}"


def plot(exprs: list[str], x_min: float, x_max: float, title: str = "") -> tuple[str, list[str]]:
    """-> (svg, warnings). Expressions use x, e.g. 'x**2 - 4', 'sin(x)', '1/x'."""
    if not exprs or len(exprs) > 4:
        raise ValueError("give between 1 and 4 expressions")
    if not (x_max > x_min) or x_max - x_min > 1e6:
        raise ValueError("x_max must be larger than x_min")
    samples, warnings, ys_all = [], [], []
    n = 400
    for expr in exprs:
        pts = []
        for i in range(n + 1):
            x = x_min + (x_max - x_min) * i / n
            try:
                y = float(tools.safe_eval(expr, {"x": x}))
                ok = math.isfinite(y)
            except (ValueError, ZeroDivisionError, OverflowError, TypeError, SyntaxError):
                y, ok = 0.0, False
            pts.append((x, y if ok else None))
            if ok:
                ys_all.append(y)
        if not any(p[1] is not None for p in pts):
            warnings.append(f"'{expr}' has no real values on this range")
        samples.append(pts)
    if not ys_all:
        raise ValueError("nothing to plot on this range")
    ys_all.sort()
    lo, hi = ys_all[int(0.01 * (len(ys_all) - 1))], ys_all[int(0.99 * (len(ys_all) - 1))]
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    margin = (hi - lo) * 0.08
    lo, hi = lo - margin, hi + margin
    sx = lambda x: PAD + (x - x_min) / (x_max - x_min) * (W - 2 * PAD)  # noqa: E731
    sy = lambda y: H - PAD - (y - lo) / (hi - lo) * (H - 2 * PAD)  # noqa: E731
    out = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg"><rect width="{W}" height="{H}" fill="#fff"/>']
    for t in _nice_ticks(x_min, x_max):
        out.append(f'<line x1="{sx(t):.1f}" y1="{PAD}" x2="{sx(t):.1f}" y2="{H - PAD}" stroke="#e5e7eb"/><text x="{sx(t):.1f}" y="{H - PAD + 16}" text-anchor="middle" font-size="12" fill="#374151">{_fmt(t)}</text>')
    for t in _nice_ticks(lo, hi):
        out.append(f'<line x1="{PAD}" y1="{sy(t):.1f}" x2="{W - PAD}" y2="{sy(t):.1f}" stroke="#e5e7eb"/><text x="{PAD - 6}" y="{sy(t) + 4:.1f}" text-anchor="end" font-size="12" fill="#374151">{_fmt(t)}</text>')
    if x_min <= 0 <= x_max:
        out.append(f'<line x1="{sx(0):.1f}" y1="{PAD}" x2="{sx(0):.1f}" y2="{H - PAD}" stroke="#111827" stroke-width="1.5"/>')
    if lo <= 0 <= hi:
        out.append(f'<line x1="{PAD}" y1="{sy(0):.1f}" x2="{W - PAD}" y2="{sy(0):.1f}" stroke="#111827" stroke-width="1.5"/>')
    for k, pts in enumerate(samples):
        run: list[str] = []
        for x, y in pts + [(0, None)]:
            if y is not None and lo - (hi - lo) <= y <= hi + (hi - lo):
                run.append(f"{sx(x):.1f},{sy(y):.1f}")
            elif run:
                if len(run) > 1:
                    out.append(f'<polyline points="{" ".join(run)}" fill="none" stroke="{COLORS[k]}" stroke-width="2.5" stroke-linejoin="round"/>')
                run = []
        out.append(f'<text x="{W - PAD}" y="{PAD + 14 + 16 * k}" text-anchor="end" font-size="14" fill="{COLORS[k]}">y = {html.escape(exprs[k])}</text>')
    if title:
        out.append(f'<text x="{W / 2}" y="22" text-anchor="middle" font-size="16" font-weight="bold" fill="#111827">{html.escape(title)}</text>')
    out.append("</svg>")
    return "".join(out), warnings
