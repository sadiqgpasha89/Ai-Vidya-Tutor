"""Textbook library: ingest PDFs/text (shared library or a student's own), then retrieve passages for grounding and citations."""
from __future__ import annotations

import re
import time
from pathlib import Path

import numpy as np

from . import db, embeddings
from .logs import get

log = get("rag")
CHUNK, OVERLAP = 900, 150


def _chunks(pages: list[tuple[int, str]]) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for page, text in pages:
        text = re.sub(r"[ \t]+", " ", text).strip()
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        buf = ""
        for p in paras:
            if len(buf) + len(p) < CHUNK:
                buf = f"{buf}\n{p}".strip()
                continue
            if buf:
                out.append((page, buf))
            while len(p) > CHUNK:  # a huge paragraph: slice with overlap
                out.append((page, p[:CHUNK]))
                p = p[CHUNK - OVERLAP:]
            buf = p
        if buf:
            out.append((page, buf))
    return [(pg, t) for pg, t in out if len(t) > 40]


def extract_pdf(path: Path) -> list[tuple[int, str]]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]


def ingest(pages: list[tuple[int, str]], scope: str, owner_id: str | None, title: str, filename: str = "",
           subject: str | None = None, grade: int | None = None) -> dict:
    """Store a document: scope is 'library' (shared, admin/teacher) or 'student' (private to owner_id)."""
    chunks = _chunks(pages)
    if not chunks:
        raise ValueError("No readable text found in that file. Scanned pages need OCR first.")
    doc_id = db.run("INSERT INTO library_docs (scope, owner_id, title, filename, subject, grade, pages, chunks, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (scope, owner_id, title[:200], filename[:200], subject, grade, len(pages), len(chunks), time.time()))
    vecs = embeddings.embed([t for _, t in chunks])
    with db.connect() as conn:
        for i, (page, text) in enumerate(chunks):
            conn.execute("INSERT INTO library_chunks (doc_id, ord, page, text, embedding) VALUES (?,?,?,?,?)",
                         (doc_id, i, page, text, embeddings.to_blob(vecs[i]) if vecs is not None else None))
    log.info(f"ingested '{title}': {len(pages)} pages, {len(chunks)} chunks, embedded={vecs is not None}")
    return {"id": doc_id, "title": title, "pages": len(pages), "chunks": len(chunks), "embedded": vecs is not None}


def delete_doc(doc_id: int, owner_id: str | None = None) -> bool:
    doc = db.one("SELECT * FROM library_docs WHERE id=?", (doc_id,))
    if not doc or (owner_id is not None and doc["owner_id"] != owner_id):
        return False
    db.run("DELETE FROM library_chunks WHERE doc_id=?", (doc_id,))
    db.run("DELETE FROM library_docs WHERE id=?", (doc_id,))
    return True


def docs(scope: str | None = None, owner_id: str | None = None) -> list[dict]:
    if scope == "student":
        return db.all("SELECT * FROM library_docs WHERE scope='student' AND owner_id=? ORDER BY id DESC", (owner_id,))
    return db.all("SELECT * FROM library_docs WHERE scope='library' ORDER BY id DESC")


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[^\W_]+", text.lower()) if len(t) > 2]


def retrieve(query: str, subject: str | None = None, grade: int | None = None, owner_id: str | None = None, k: int = 4) -> list[dict]:
    """Best passages for `query` from the shared library (filtered by subject/grade) and the student's own uploads."""
    where, args = ["(d.scope='library' AND (d.subject IS NULL OR d.subject=?) AND (d.grade IS NULL OR d.grade=?))"], [subject or "", grade or 0]
    if subject is None:
        where[0] = "(d.scope='library')"
        args = []
    if owner_id:
        where.append("(d.scope='student' AND d.owner_id=?)")
        args.append(owner_id)
    rows = db.all(f"SELECT c.id, c.text, c.page, c.embedding, d.title, d.id AS doc_id, d.scope FROM library_chunks c JOIN library_docs d ON d.id=c.doc_id WHERE {' OR '.join(where)}", tuple(args))
    if not rows:
        return []
    scores = np.zeros(len(rows), dtype=np.float32)
    qv = embeddings.embed([query])
    if qv is not None and all(r["embedding"] for r in rows):
        mat = np.stack([embeddings.from_blob(r["embedding"]) for r in rows])
        scores = mat @ qv[0]
    else:  # keyword fallback: share of query terms present, lightly length-normalised
        q = set(_tokens(query))
        for i, r in enumerate(rows):
            toks = _tokens(r["text"])
            scores[i] = len(q & set(toks)) / (len(q) or 1) - 0.0001 * len(toks)
    best = np.argsort(-scores)[:k]
    return [{"text": rows[i]["text"], "page": rows[i]["page"], "title": rows[i]["title"], "doc_id": rows[i]["doc_id"],
             "scope": rows[i]["scope"], "score": float(scores[i])} for i in best if scores[i] > (0.25 if qv is not None else 0.1)]


def format_sources(passages: list[dict]) -> str:
    return "\n\n".join(f"[{i}] ({p['title']}, p.{p['page']}) {p['text']}" for i, p in enumerate(passages, start=1))
