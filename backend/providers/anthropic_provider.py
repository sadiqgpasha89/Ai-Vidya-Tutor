"""Claude via the Anthropic API."""
from __future__ import annotations

import json
from typing import Iterator

import anthropic

import time

from .. import config, usage
from . import Provider, ProviderError, ToolRunner

MAX_TURNS = 6  # model calls per student message (tool loop guard)

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # Resolves ANTHROPIC_API_KEY (or an `ant auth login` profile) from the environment.
        _client = anthropic.Anthropic(max_retries=3)
    return _client


def _media_type(b64: str) -> str:
    head = b64[:12]
    return "image/png" if head.startswith("iVBOR") else "image/webp" if head.startswith("UklGR") else "image/gif" if head.startswith("R0lGOD") else "image/jpeg"


class AnthropicProvider(Provider):
    name = "anthropic"

    def health(self) -> dict:
        try:
            c = client()
            ok = bool(c.api_key or c.auth_token)
        except Exception:  # noqa: BLE001
            ok = False
        return {"ready": ok, "problem": None if ok else "Set ANTHROPIC_API_KEY (or switch to the local model with TEACHER_PROVIDER=ollama)."}

    def stream_text(self, system: str, user: str, effort: str, role: str = "lesson", should_stop=None) -> Iterator[str]:
        with client().messages.stream(
            model=config.model("anthropic"), max_tokens=32000, system=system,
            messages=[{"role": "user", "content": user}], output_config={"effort": effort},
        ) as stream:
            yield from stream.text_stream
            final = stream.get_final_message()
        if final.stop_reason == "refusal":
            raise ProviderError("The model declined to write this lesson.")

    def structured(self, system: str, user: str, schema: dict, effort: str, max_tokens: int = 4000, role: str = "quiz") -> dict:
        t0 = time.time()
        resp = client().messages.create(
            model=config.structured_model("anthropic"), max_tokens=12000, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        )
        usage.record_call("structured", config.structured_model("anthropic"), resp.usage.input_tokens, resp.usage.output_tokens, int((time.time() - t0) * 1000))
        if resp.stop_reason == "refusal":
            raise ProviderError("The model declined this request.")
        return json.loads(next((b.text for b in resp.content if b.type == "text"), ""))

    def agent(self, system_blocks: list[dict], history: list[dict], tools: list[dict], run_tool: ToolRunner, model: str | None = None) -> Iterator[dict]:
        model = model or config.model("anthropic")
        msgs: list[dict] = list(history)
        bad_json = 0
        for _ in range(MAX_TURNS):
            try:
                t0 = time.time()
                with client().messages.stream(
                    model=model,
                    max_tokens=16000,  # thinking tokens count toward this cap
                    system=system_blocks, tools=tools, messages=msgs,
                    output_config={"effort": config.EFFORT_CHAT},
                ) as stream:
                    for event in stream:
                        if event.type == "text":
                            yield {"type": "text", "delta": event.text}
                        elif event.type == "content_block_start" and event.content_block.type == "tool_use":
                            yield {"type": "tool", "name": event.content_block.name}
                    final = stream.get_final_message()
                usage.record_call("chat", model, final.usage.input_tokens, final.usage.output_tokens, int((time.time() - t0) * 1000))
                bad_json = 0
            except ValueError:
                # Tool input JSON that could not be parsed at all (eager input streaming): re-issue the turn.
                bad_json += 1
                if bad_json > 2:
                    raise
                continue

            if final.stop_reason == "refusal":
                yield {"type": "text", "delta": "I can't help with that one, but I'm happy to help with this topic. What would you like to know?"}
                return
            if final.stop_reason == "pause_turn":
                msgs.append({"role": "assistant", "content": final.content})
                continue
            tool_uses = [b for b in final.content if b.type == "tool_use"]
            if final.stop_reason == "max_tokens" and tool_uses:
                yield {"type": "text", "delta": "\n\n(That answer got too long - ask me to continue and I will.)"}
                return
            if not tool_uses:
                if final.stop_reason == "max_tokens":
                    yield {"type": "text", "delta": "\n\n(Ask me to continue and I will.)"}
                return
            results = []
            for block in tool_uses:
                text, is_error = run_tool(block.name, block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": text, "is_error": is_error})
            yield {"type": "_tools_ran"}
            # Append the assistant turn untouched (thinking blocks included), then all tool results in one user turn.
            msgs.append({"role": "assistant", "content": final.content})
            msgs.append({"role": "user", "content": results})

    def vision(self, system: str, user: str, images_b64: list[str]) -> str:
        blocks = [{"type": "image", "source": {"type": "base64", "media_type": _media_type(b), "data": b}} for b in images_b64]
        resp = client().messages.create(model=config.model("anthropic"), max_tokens=2000, system=system,
                                        messages=[{"role": "user", "content": [*blocks, {"type": "text", "text": user}]}])
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def friendly_error(self, exc: Exception) -> str:
        if isinstance(exc, ProviderError):
            return str(exc)
        if isinstance(exc, anthropic.AuthenticationError):
            return "The AI teacher is not connected yet: the server needs a valid ANTHROPIC_API_KEY."
        if isinstance(exc, anthropic.PermissionDeniedError):
            return "The API key does not have permission to use this model."
        if isinstance(exc, anthropic.NotFoundError):
            return "The configured AI model was not found. Check TEACHER_MODEL."
        if isinstance(exc, anthropic.RateLimitError):
            return "The teacher is a bit busy right now. Please try again in a few seconds."
        if isinstance(exc, anthropic.APIConnectionError):
            return "Could not reach the AI service. Please check the internet connection."
        if isinstance(exc, anthropic.APIStatusError):
            return f"The AI service returned an error ({exc.status_code}). Please try again."
        if isinstance(exc, anthropic.AnthropicError):
            return "The AI teacher is not connected yet: the server needs a valid ANTHROPIC_API_KEY."
        return super().friendly_error(exc)
