"""A tiny fake of Ollama's /api/tags and /api/chat, to exercise OllamaProvider deterministically."""
import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
REQUESTS: list[dict] = []
# Raw JSON text on purpose: "\f" and "\t" are VALID JSON escapes, so a small model's "\frac" / "\times" silently decode to control characters.
QUIZ_RAW = ('{"questions": ['
            '{"question": "Compute $\\frac{1}{2} \\times 4$", "options": ["a) 1", "b) 2", "c) 4", "d) 8"], "answer_index": 1, "tests": "concept", "hint": "h", "explanation": "e", "wrong_option_notes": ["", "", "", ""], "misconception": "m"},'
            '{"question": "Second", "options": ["w", "x", "y", "z"], "answer_index": 2, "tests": "concept", "hint": "h", "explanation": "e", "wrong_option_notes": ["", "", "", ""], "misconception": "m"},'
            '{"question": "Third (wrong key)", "options": ["w", "x", "y", "z"], "answer_index": 0, "tests": "concept", "hint": "h", "explanation": "e", "wrong_option_notes": ["", "", "", ""], "misconception": "m"}]}')


def lines(items):
    for it in items:
        yield json.dumps(it) + "\n"


@app.get("/api/tags")
def tags():
    return {"models": [{"name": "llama3.1:8b"}]}


@app.post("/api/chat")
async def chat(req: Request):
    body = await req.json()
    REQUESTS.append(body)
    if body["model"] == "missing-model":
        return JSONResponse({"error": "model 'missing-model' not found"}, status_code=404)
    last = body["messages"][-1]
    schema = body.get("format")
    if schema:
        if "working" in schema["properties"]:  # verifier: always claims option 2 is right
            content = '{"working": "I solved it.", "answer_index": 2}'
            if "Compute" in last["content"]:
                content = '{"working": "half of 4 is 2", "answer_index": 1}'
        elif "questions" in schema["properties"]:
            content = QUIZ_RAW
        else:
            content = '{"score": 64, "strengths": ["s"], "gaps": ["g"], "misconceptions": [], "next_step": "n", "spoken_feedback": "Good try."}'
        return {"message": {"role": "assistant", "content": content}, "done": True}
    if "ONE section" in body["messages"][0]["content"]:
        return StreamingResponse(lines([{"message": {"content": "[DISPLAY]\nBody with $a=b$.\n"}, "done": False},
                                        {"message": {"content": "[SPEECH]\nSpoken words."}, "done": False}, {"message": {}, "done": True}]),
                                 media_type="application/x-ndjson")
    if "BACKSLASH-FAIL" in str(body["messages"][-1].get("content", "")) + str(body["messages"][-2:]) and not any("JSON: write every backslash" in str(m.get("content")) for m in body["messages"]) and body.get("tools"):
        return StreamingResponse(lines([{"error": "error parsing tool call: raw='{\"markdown\":\"\\frac\"}', err=invalid character 'p' in string escape code"}]), media_type="application/x-ndjson")
    if last["role"] == "tool":
        return StreamingResponse(lines([{"message": {"content": "It is 96.04 "}, "done": False}, {"message": {"content": "joules."}, "done": False}, {"message": {}, "done": True}]),
                                 media_type="application/x-ndjson")
    return StreamingResponse(lines([
        {"message": {"content": "Let me work that out. "}, "done": False},
        {"message": {"tool_calls": [{"function": {"name": "calculator", "arguments": {"expression": "0.5 * 2 * 9.8 ** 2"}}},
                                    {"function": {"name": "show_on_board", "arguments": {"title": "KE", "markdown": "$$KE=\\frac12 mv^2$$"}}}]}, "done": False},
        {"message": {}, "done": True}]), media_type="application/x-ndjson")
