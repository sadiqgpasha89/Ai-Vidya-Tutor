"""Server-side voice: Piper text-to-speech and Whisper speech-to-text."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import config, curriculum, lesson, voice
from ..deps import ai_student, current_user
from .learn import _topic

router = APIRouter(prefix="/api/voice")


@router.get("/info")
def info(user: dict = Depends(current_user)):
    return {"tts": {"enabled": config.TTS == "piper", "languages": voice.tts_languages(), "installed": [l for l in voice.tts_languages() if voice.installed(l)]},
            "stt": {"enabled": voice.stt_available(), "model": config.WHISPER_MODEL}}


class TtsIn(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    language: str | None = None


@router.post("/tts")
def tts(body: TtsIn, student: dict = Depends(ai_student)):
    lang = body.language or student["language"]
    try:
        with voice.gate():
            wav, dur = voice.synthesize(body.text, lang)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:  # noqa: BLE001
        raise HTTPException(503, "The server voice is not ready yet (the voice file may still be downloading). Try again in a minute.")
    timings = voice.word_timings(body.text, dur)
    return Response(wav, media_type="audio/wav", headers={"X-Duration": f"{dur:.3f}", "X-Words": __import__("base64").b64encode(__import__("json").dumps(timings).encode()).decode(), "Cache-Control": "private, max-age=86400"})


@router.get("/lesson-audio")
def lesson_audio(subtopic_id: str, student: dict = Depends(ai_student)):
    """The whole lesson as one downloadable WAV (listen offline)."""
    _topic(subtopic_id, student)
    v = lesson.active_version(subtopic_id, lesson.variant(student["language"], student["level"], student["board"]))
    if not v:
        raise HTTPException(404, "Open the lesson once first so it can be written")
    if config.TTS != "piper" or student["language"] not in voice.tts_languages():
        raise HTTPException(400, "Downloadable audio is not available for this language yet")
    parts = []
    with voice.gate():
        for s in v["sections"]:
            wav, _ = voice.synthesize(s["speech"], student["language"])
            parts.append(wav)
    t = curriculum.get_subtopic(subtopic_id)
    return Response(voice.wav_concat(parts), media_type="audio/wav", headers={"Content-Disposition": f'attachment; filename="{t["title"][:40].replace(" ", "-")}.wav"'})


@router.post("/stt")
async def stt(request: Request, language: str | None = None, student: dict = Depends(ai_student)):
    """Body: raw audio (webm/ogg/wav/mp4). Private speech recognition by Whisper on this server."""
    if not voice.stt_available():
        raise HTTPException(503, "Private voice input is not installed on this server")
    data = await request.body()
    if not data or len(data) > 12 * 1024 * 1024:
        raise HTTPException(400, "Send a short audio recording (under 12 MB)")
    lang = language if language in config.LANGUAGES else student["language"]
    import anyio

    def run():
        with voice.gate():
            return voice.transcribe(data, lang)

    try:
        return await anyio.to_thread.run_sync(run)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
