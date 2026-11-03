"""Local models through Ollama (default: Gemma 4 for everyday work, gpt-oss for drawing and checking; each job has its own setting). Standard library only - no extra dependencies."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Iterator

import time

from .. import config, usage
from . import Preempted, Provider, ProviderError, ToolRunner

MAX_TURNS = 4
TIMEOUT = 600  # seconds between bytes; a cold model load can take a while

JSON_HINT = "\n\nReply with JSON only. Inside JSON strings, write every LaTeX backslash doubled (for example \"\\\\frac{1}{2}\")."

LOCAL_HINT = """

LOCAL-MODEL RULES (important - you are a small model that makes arithmetic slips)
- NUMBERS: if the question needs a calculation, FIRST call `calculator` with the full expression (use ** for powers, and brackets around every sum or difference that is divided or multiplied: (30 - 10) / 5), THEN explain using exactly the result it returned. Never state a numeric result before you have it. Conceptual questions need NO tool - just explain.
- BOARD: call `show_on_board` for formulas, step-by-step solutions, tables or diagrams. Only say "look at the board" if you actually called it in this reply.
- Always write your explanation as plain text for the student, in short spoken sentences. After a tool returns, continue with the explanation.
- Never write JSON, tool names or function-call syntax inside your reply text."""


_CTRL_FIX = {"\x0c": "\\f", "\x08": "\\b", "\t": "\\t", "\r": "\\r"}  # \frac \beta \times \rho eaten by JSON escapes
_NL_FIX = re.compile(r"\n(?=(?:eq|abla|u)\b)")  # \neq \nabla \nu


TOOL_ESCAPE_NOTE = ("When you call a tool, the arguments are JSON: write every backslash in LaTeX twice (\\\\frac, \\\\sqrt, \\\\pm) and keep the markdown short. "
                    "If that is awkward, put the maths in the normal reply instead of the tool.")


def repair_latex(value):
    """Small models write LaTeX like "\\frac" inside JSON with a single backslash, which JSON decodes as a form-feed.
    Put the backslashes back in every string of a decoded JSON value."""
    if isinstance(value, str):
        for bad, good in _CTRL_FIX.items():
            value = value.replace(bad, good)
        value = _NL_FIX.sub(lambda m: "\\n", value)
        # "$f\\(x\\)$": escaped parentheses inside maths are literal parentheses (KaTeX rejects the escapes)
        return re.sub(r"\\([()])", r"\1", value) if "$" in value else value
    if isinstance(value, list):
        return [repair_latex(v) for v in value]
    if isinstance(value, dict):
        return {k: repair_latex(v) for k, v in value.items()}
    return value


class OllamaProvider(Provider):
    name = "ollama"
    verify_quizzes = True
    per_section = True  # an 8B model writes one focused section far more reliably than a 12-section document

    # ---- plumbing -----------------------------------------------------------------------------
    def _open(self, path: str, payload: dict | None = None):
        url = config.OLLAMA_HOST.rstrip("/") + path
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read().decode()).get("error", "")
            except Exception:  # noqa: BLE001
                pass
            if exc.code == 404 and "not found" in detail.lower():
                missing = (payload or {}).get("model") or config.model("ollama")
                raise ProviderError(f"The model '{missing}' is not installed. Run: ollama pull {missing}") from exc
            raise ProviderError(f"The local model server returned an error ({exc.code}): {detail or exc.reason}") from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            raise ProviderError(f"Cannot reach Ollama at {config.OLLAMA_HOST}. Start it with `ollama serve` (or the Ollama app) and try again.") from exc

    def _lines(self, path: str, payload: dict) -> Iterator[dict]:
        with self._open(path, payload) as resp:
            for raw in resp:
                raw = raw.strip()
                if not raw:
                    continue
                chunk = json.loads(raw)
                if chunk.get("error"):
                    raise ProviderError(f"The local model reported an error: {chunk['error']}")
                yield chunk

    def _options(self, temperature: float, num_predict: int) -> dict:
        return {"temperature": temperature, "num_ctx": config.NUM_CTX, "num_predict": num_predict}

    # ---- which model does which job ------------------------------------------------------------
    _tags: tuple[float, set[str]] = (0.0, set())

    def installed(self) -> set[str]:
        """Names of the models Ollama has (cached for 20 seconds)."""
        now = time.time()
        if now - self._tags[0] > 20:
            with self._open("/api/tags") as resp:
                names = {m["name"] for m in json.load(resp).get("models", [])}
            self._tags = (now, names)
        return self._tags[1]

    @staticmethod
    def _has(names: set[str], model: str) -> bool:
        return model in names or f"{model}:latest" in names or (":" not in model and any(n.split(":")[0] == model for n in names))

    def resolve(self, role: str) -> str:
        """The model to use for a job. A model you chose yourself (TEACHER_MODEL_<ROLE> ...) is used as is; a built-in default that is not
        installed falls back to the everyday model, and then to anything installed, so a missing download never stops the app."""
        want = config.role_model(role, "ollama")
        if not want:
            return config.model("ollama")
        try:
            names = self.installed()
        except ProviderError:
            return want
        if self._has(names, want) or config.is_pinned(role):
            return want
        for alt in (config.model("ollama"), "gemma4:e4b", "llama3.1:8b"):
            if alt and self._has(names, alt):
                return alt
        usable = sorted(n for n in names if not re.search(r"embed|whisper|router|rerank", n))
        return usable[0] if usable else want

    @staticmethod
    def _think(model: str):
        """Reasoning models spend tokens 'thinking' before answering. gpt-oss cannot switch it off (low is the cheapest); others are told not to."""
        if "gpt-oss" in model:
            return "low"
        if re.search(r"gemma4|qwen3|qwen35|deepseek-r1", model):
            return False
        return None

    def _payload(self, model: str, messages: list[dict], num_predict: int, temperature: float, **extra) -> dict:
        payload = {"model": model, "keep_alive": "30m", "messages": messages, "options": self._options(temperature, num_predict + (1500 if "gpt-oss" in model else 0)), **extra}
        think = self._think(model)
        if think is not None:
            payload["think"] = think
        if model != config.model("ollama"):
            payload["keep_alive"] = "5m"  # specialists make room again soon after the everyday model is wanted
        return payload

    def load(self, model: str) -> None:
        """Ask Ollama to load a model into memory and keep it there (no prompt, no tokens generated)."""
        with self._open("/api/generate", {"model": model, "keep_alive": "30m"}) as resp:
            resp.read()

    # ---- Provider interface -------------------------------------------------------------------
    def health(self) -> dict:
        try:
            with self._open("/api/tags") as resp:
                names = {m["name"] for m in json.load(resp).get("models", [])}
            self._tags = (time.time(), names)
        except ProviderError as exc:
            return {"ready": False, "problem": str(exc)}
        for role in ("lesson", "chat"):
            model = self.resolve(role)
            if not self._has(names, model):
                return {"ready": False, "problem": f"The model '{model}' is not installed. Run: ollama pull {model}"}
        return {"ready": True, "problem": None}

    def roles(self) -> dict:
        """-> {role: {"model": str, "installed": bool, "wanted": str}} for the admin health page."""
        names = self.installed()
        out = {}
        for role in config.MODEL_ROLES:
            wanted, used = config.role_model(role, "ollama"), self.resolve(role)
            out[role] = {"model": used, "wanted": wanted, "installed": self._has(names, used)}
        return out

    def stream_text(self, system: str, user: str, effort: str, role: str = "lesson", should_stop=None) -> Iterator[str]:
        payload = self._payload(self.resolve(role), [{"role": "system", "content": system}, {"role": "user", "content": user}], 3000 if role == "figure" else 1800, 0.6, stream=True)
        if role == "figure" and "gpt-oss" in payload["model"]:
            payload["think"] = "medium"  # drawing needs a little planning: where things go, what the axes are
        t0 = time.time()
        for chunk in self._lines("/api/chat", payload):
            if should_stop and should_stop():  # closing the connection makes Ollama stop generating
                raise Preempted()
            piece = chunk.get("message", {}).get("content")
            if piece:
                yield piece
            if chunk.get("done"):
                usage.record_call("text", payload["model"], chunk.get("prompt_eval_count", 0), chunk.get("eval_count", 0), int((time.time() - t0) * 1000))

    def structured(self, system: str, user: str, schema: dict, effort: str, max_tokens: int = 4000, role: str = "quiz") -> dict:
        model = self.resolve(role)
        for attempt in range(2):  # a longer-winded model can run out of room mid-answer: ask again with twice the room
            payload = self._payload(model, [{"role": "system", "content": system + JSON_HINT}, {"role": "user", "content": user}], max_tokens, 0.1, stream=False, format=schema)
            t0 = time.time()
            with self._open("/api/chat", payload) as resp:
                body = json.load(resp)
            if body.get("error"):
                raise ProviderError(f"The local model reported an error: {body['error']}")
            usage.record_call("structured", payload["model"], body.get("prompt_eval_count", 0), body.get("eval_count", 0), int((time.time() - t0) * 1000))
            try:
                return repair_latex(json.loads(body["message"]["content"]))
            except json.JSONDecodeError:
                if attempt == 1 or body.get("done_reason") != "length":
                    raise
                max_tokens = min(max_tokens * 2, 8000)
        raise ProviderError("The local model gave an answer I could not read.")

    def agent(self, system_blocks: list[dict], history: list[dict], tools: list[dict], run_tool: ToolRunner, model: str | None = None) -> Iterator[dict]:
        model = model or self.resolve("chat")
        system = "\n\n".join(b["text"] for b in system_blocks) + LOCAL_HINT
        msgs: list[dict] = [{"role": "system", "content": system}, *history]
        tool_defs = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}} for t in tools]
        seen: set[str] = set()
        for turn in range(MAX_TURNS):
            text, calls = "", []
            payload = self._payload(model, msgs, 1500, 0.2, stream=True)
            t0 = time.time()
            if turn < MAX_TURNS - 1:  # the last turn must answer in words, not call yet another tool
                payload["tools"] = tool_defs
            for attempt in range(3):
                try:
                    for chunk in self._lines("/api/chat", payload):
                        msg = chunk.get("message", {})
                        if msg.get("content"):
                            text += msg["content"]
                            yield {"type": "text", "delta": msg["content"]}
                        calls.extend(msg.get("tool_calls") or [])
                        if chunk.get("done"):
                            usage.record_call("chat", model, chunk.get("prompt_eval_count", 0), chunk.get("eval_count", 0), int((time.time() - t0) * 1000))
                    break
                except ProviderError as exc:
                    # Maths written with a bare backslash (\frac) inside a tool call is not valid JSON and Ollama rejects the whole reply:
                    # ask again with a reminder, then once without tools, so the student always gets an answer.
                    if "error parsing tool call" not in str(exc) or text or attempt == 2:
                        raise
                    if attempt == 0:
                        payload["messages"] = [*payload["messages"], {"role": "system", "content": TOOL_ESCAPE_NOTE}]
                    else:
                        payload.pop("tools", None)
                    calls = []
            if not calls:
                return
            msgs.append({"role": "assistant", "content": text, "tool_calls": calls})
            for call in calls:
                fn = call.get("function", {})
                name, args = fn.get("name", ""), fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = None
                key = f"{name}:{json.dumps(args, sort_keys=True, default=str)}"
                yield {"type": "tool", "name": name}
                if key in seen:  # small models sometimes repeat the same call forever
                    result = "error: you already did this; continue with your explanation in words."
                else:
                    seen.add(key)
                    result, _ = run_tool(name, args)
                msgs.append({"role": "tool", "tool_name": name, "content": result})
            yield {"type": "_tools_ran"}

    def vision(self, system: str, user: str, images_b64: list[str]) -> str:
        payload = self._payload(self.resolve("vision"), [{"role": "system", "content": system}, {"role": "user", "content": user, "images": images_b64}], 1200, 0.1, stream=False)
        with self._open("/api/chat", payload) as resp:
            body = json.load(resp)
        if body.get("error"):
            raise ProviderError(f"The image model reported an error: {body['error']}")
        return body["message"]["content"].strip()

    def friendly_error(self, exc: Exception) -> str:
        if isinstance(exc, (json.JSONDecodeError, KeyError)):
            return "The local model gave an answer I could not read. Please try again."
        return super().friendly_error(exc)
