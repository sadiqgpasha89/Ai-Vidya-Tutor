"""Text embeddings through Ollama (nomic-embed-text by default). Everything that uses them degrades to keywords if unavailable."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import numpy as np

from . import config
from .logs import get

log = get("embeddings")
_down_until = 0.0


def available() -> bool:
    return time.time() >= _down_until and not config.MOCK


def embed(texts: list[str]) -> np.ndarray | None:
    """-> float32 matrix (len(texts), dim), L2-normalised; None when the embedding model cannot be reached."""
    global _down_until
    if not texts or not available():
        return None
    out: list[list[float]] = []
    try:
        for i in range(0, len(texts), 32):
            payload = json.dumps({"model": config.EMBED_MODEL, "input": [t[:2000] for t in texts[i:i + 32]], "keep_alive": "10m"}).encode()
            req = urllib.request.Request(config.OLLAMA_HOST.rstrip("/") + "/api/embed", data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                out.extend(json.load(resp)["embeddings"])
    except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
        _down_until = time.time() + 60  # do not hammer a missing model; retry in a minute
        log.warning(f"embedding model unavailable ({exc}); falling back to keyword search")
        return None
    m = np.asarray(out, dtype=np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.maximum(norms, 1e-9)


def to_blob(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)
