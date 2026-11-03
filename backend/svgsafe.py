"""Whitelist SVG sanitiser: model- or user-supplied SVG is rebuilt from allowed tags/attributes only."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
ALLOWED_TAGS = {"svg", "g", "rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "text", "tspan", "defs", "marker", "title", "desc"}
ALLOWED_ATTRS = {
    "viewBox", "width", "height", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "points", "d", "fill", "stroke", "stroke-width",
    "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "opacity", "fill-opacity", "stroke-opacity", "transform", "font-size", "font-family",
    "font-weight", "text-anchor", "dominant-baseline", "id", "marker-start", "marker-end", "markerWidth", "markerHeight", "refX", "refY",
    "orient", "markerUnits", "preserveAspectRatio", "xmlns",
}
_BAD_VALUE = re.compile(r"(javascript:|data:|url\s*\(\s*['\"]?(?!#)|expression\()", re.I)
MAX_BYTES = 60_000


def sanitize(svg: str) -> str | None:
    """-> cleaned SVG string, or None when it is not usable."""
    if not isinstance(svg, str):
        return None
    svg = svg.strip()
    m = re.search(r"<svg[\s\S]*</svg>", svg, re.I)
    if not m or len(svg) > MAX_BYTES:
        return None
    svg = m.group(0)
    if re.search(r"<!DOCTYPE|<!ENTITY|<\?xml-stylesheet", svg, re.I):
        return None
    if "xmlns" not in svg[:200]:
        svg = svg.replace("<svg", f'<svg xmlns="{SVG_NS}"', 1)
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return None

    def clean(el: ET.Element) -> ET.Element | None:
        tag = el.tag.split("}")[-1]
        if tag not in ALLOWED_TAGS:
            return None
        out = ET.Element(tag)
        for k, v in el.attrib.items():
            k = k.split("}")[-1]
            if k in ALLOWED_ATTRS and not _BAD_VALUE.search(v):
                out.set(k, v)
        if el.text and tag in ("text", "tspan", "title", "desc"):
            out.text = el.text
        for child in el:
            c = clean(child)
            if c is not None:
                if child.tail and tag in ("text", "tspan"):
                    c.tail = child.tail
                out.append(c)
        return out

    cleaned = clean(root)
    if cleaned is None or cleaned.tag != "svg":
        return None
    cleaned.set("xmlns", SVG_NS)
    if not cleaned.get("viewBox"):
        cleaned.set("viewBox", "0 0 600 400")
    ET.register_namespace("", SVG_NS)
    return ET.tostring(cleaned, encoding="unicode").replace(f' xmlns:ns0="{SVG_NS}"', "")
