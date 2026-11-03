"""AIVidya - FastAPI application: API routers, security middleware, static frontend and PWA files."""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import accounts, config, curriculum, db, llm, logs, metrics, notify, ops, semantic
from .deps import client_ip
from .ratelimit import limiter
from .routes import admin, auth, doubts, learn, staff, study, voice, worksheets

log = logs.get("app")
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
VERSION = "2.0.0"

CSP = ("default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob: data:; "
       "font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; frame-src https://www.youtube-nocookie.com; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logs.setup()
    for problem in config.validate():
        log.warning(f"configuration: {problem}")
    db.migrate()
    accounts.ensure_admin()
    ops.start()
    notify.start()
    if not config.MOCK:
        semantic.build_async()
    log.info(f"AIVidya {VERSION} ready: provider={config.PROVIDER} model={config.model()} auth={config.AUTH} sandbox={__import__('backend.sandbox', fromlist=['mode']).mode()}")
    yield


app = FastAPI(title="AIVidya - AI Teacher", version=VERSION, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=800)


@app.middleware("http")
async def guard(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:10]
    logs.request_id.set(rid)
    t0 = time.time()
    path = request.url.path
    # size limits (uploads are the only large bodies)
    length = int(request.headers.get("content-length") or 0)
    limit = int(config.MAX_UPLOAD * 1.4) if path.startswith(("/api/library", "/api/voice/stt")) else config.MAX_BODY
    if length > limit:
        return JSONResponse({"detail": "Request too large"}, status_code=413)
    if path.startswith("/api/"):
        ok, wait = limiter.allow(f"ip:{client_ip(request)}", config.RATE_GENERAL)
        if not ok:
            return JSONResponse({"detail": "Too many requests. Please slow down."}, status_code=429, headers={"Retry-After": str(int(wait) + 1)})
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "microphone=(self), camera=(self), geolocation=()"
    if not path.startswith("/api/"):
        if path.startswith(("/vendor/", "/icons/")):
            response.headers.setdefault("Cache-Control", "public, max-age=604800")  # libraries, fonts and icons change only when re-vendored: no need to ask again for a week
        elif path.endswith((".js", ".css", ".html", ".json", ".webmanifest")) or path == "/":
            response.headers.setdefault("Cache-Control", "no-cache")  # app code is always revalidated (a cheap 304 when unchanged)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Frame-Options"] = "DENY"
    ms = int((time.time() - t0) * 1000)
    metrics.inc("http_requests_total", method=request.method, status=response.status_code)
    metrics.observe("http_request_ms", ms)
    if path.startswith("/api/") and response.status_code >= 500:
        log.warning(f"{request.method} {path} -> {response.status_code} in {ms} ms")
    return response


@app.get("/api/health")
def health():
    h = llm.health()
    return {"ok": True, "version": VERSION, "mock": config.MOCK, "provider": config.PROVIDER, "model": config.model(), "ready": h["ready"], "problem": h["problem"], **curriculum.stats()}


@app.get("/metrics", response_class=PlainTextResponse)
def prometheus(request: Request):
    loopback = client_ip(request) in ("127.0.0.1", "::1", "localhost")
    token_ok = bool(config.METRICS_TOKEN) and request.headers.get("authorization") == f"Bearer {config.METRICS_TOKEN}"
    if not (loopback or token_ok):
        return PlainTextResponse("forbidden\n", status_code=403)
    return metrics.prometheus()


for module in (auth, learn, staff, admin, voice, study, doubts, worksheets):
    app.include_router(module.router)


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js")
def service_worker():
    return FileResponse(FRONTEND / "sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


app.mount("/", StaticFiles(directory=FRONTEND), name="static")
