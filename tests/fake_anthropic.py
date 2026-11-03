"""A tiny fake of the Anthropic Messages API (streaming + non-streaming) used to exercise the real SDK code path offline."""
import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
REQUESTS: list[dict] = []

LESSON = "".join(
    f"=== SECTION: {k} | {t} ===\n[DISPLAY]\nBody of {t} with $a = v/t$.\n[SPEECH]\nSpoken words for {t}.\n\n"
    for k, t in [("hook", "Why care"), ("idea", "Big idea"), ("how", "How"), ("example", "Example")]
) + "=== END ===\n"


def sse(events):
    for ev in events:
        yield f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n"


def message_start():
    return {"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant", "model": "fake", "content": [],
                                                 "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}}


def text_events(chunks, stop="end_turn", start_index=0):
    evs = [{"type": "content_block_start", "index": start_index, "content_block": {"type": "text", "text": ""}}]
    evs += [{"type": "content_block_delta", "index": start_index, "delta": {"type": "text_delta", "text": c}} for c in chunks]
    evs.append({"type": "content_block_stop", "index": start_index})
    return evs


def finish(stop):
    return [{"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": 5}}, {"type": "message_stop"}]


def tool_events(index, tool_id, name, args):
    raw = json.dumps(args)
    return [
        {"type": "content_block_start", "index": index, "content_block": {"type": "tool_use", "id": tool_id, "name": name, "input": {}}},
        {"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": raw[:10]}},
        {"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": raw[10:]}},
        {"type": "content_block_stop", "index": index},
    ]


@app.post("/v1/messages")
async def messages(req: Request):
    body = await req.json()
    REQUESTS.append(body)
    msgs = body["messages"]
    last = msgs[-1]
    is_tool_result_turn = isinstance(last["content"], list) and any(b.get("type") == "tool_result" for b in last["content"])
    wants_json = "format" in (body.get("output_config") or {})

    if wants_json:
        schema_props = body["output_config"]["format"]["schema"]["properties"]
        if "questions" in schema_props:
            payload = {"questions": [{"question": "Q1?", "options": ["a", "b", "c", "d"], "answer_index": 2, "tests": "concept", "hint": "h",
                                      "explanation": "e", "wrong_option_notes": ["1", "2", "3", "4"], "misconception": "m"}]}
        else:
            payload = {"score": 72, "strengths": ["s"], "gaps": ["g"], "misconceptions": ["Thinks speed is acceleration"], "next_step": "n", "spoken_feedback": "Well done."}
        return JSONResponse({"id": "msg_j", "type": "message", "role": "assistant", "model": "fake", "stop_reason": "end_turn", "stop_sequence": None,
                             "content": [{"type": "text", "text": json.dumps(payload)}], "usage": {"input_tokens": 1, "output_tokens": 1}})

    if not body.get("stream"):
        return JSONResponse({"error": {"type": "invalid_request_error", "message": "fake supports streaming only"}}, status_code=400)

    if "=== SECTION:" in body["system"] if isinstance(body["system"], str) else False:  # lesson request
        chunks = [LESSON[i:i + 40] for i in range(0, len(LESSON), 40)]
        evs = [message_start()] + text_events(chunks) + finish("end_turn")
    elif is_tool_result_turn:
        evs = [message_start()] + text_events(["The answer is ", "96.04 joules."]) + finish("end_turn")
    else:
        evs = ([message_start()] + text_events(["Let me work that out. "]) +
               tool_events(1, "toolu_calc", "calculator", {"expression": "0.5 * 2 * 9.8 ** 2"}) +
               tool_events(2, "toolu_board", "show_on_board", {"title": "KE", "markdown": "$$KE = \\frac12 m v^2$$"}) + finish("tool_use"))
    return StreamingResponse(sse(evs), media_type="text/event-stream")
