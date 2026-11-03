"""Server-side voice: Piper text-to-speech (consistent quality on every device) and Whisper speech-to-text (private, works in any browser)."""
from __future__ import annotations

import hashlib
import json
import io
import re
import threading
import time
import urllib.request
import wave
from pathlib import Path

from . import config
from .logs import get

log = get("voice")
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
# language -> Piper voice (path on Hugging Face). 16 of the 20 languages have one.
PIPER_VOICES = {
    "en": "en/en_GB/cori/medium/en_GB-cori-medium",
    "hi": "hi/hi_IN/priyamvada/medium/hi_IN-priyamvada-medium",
    "bn": "bn/bn_BD/google/medium/bn_BD-google-medium",
    "mr": "mr/mr_IN/google/medium/mr_IN-google-medium",
    "te": "te/te_IN/maya/medium/te_IN-maya-medium",
    "ur": "ur/ur_PK/fasih/medium/ur_PK-fasih-medium",
    "ml": "ml/ml_IN/meera/medium/ml_IN-meera-medium",
    "zh": "zh/zh_CN/huayan/medium/zh_CN-huayan-medium",
    "es": "es/es_ES/davefx/medium/es_ES-davefx-medium",
    "fr": "fr/fr_FR/siwis/medium/fr_FR-siwis-medium",
    "ar": "ar/ar_JO/kareem/medium/ar_JO-kareem-medium",
    "pt": "pt/pt_BR/faber/medium/pt_BR-faber-medium",
    "ru": "ru/ru_RU/irina/medium/ru_RU-irina-medium",
    "id": "id/id_ID/news_tts/medium/id_ID-news_tts-medium",
    "de": "de/de_DE/thorsten/medium/de_DE-thorsten-medium",
    "ja": "ja/ja_JP/hi_fi_captain/medium/ja_JP-hi_fi_captain-medium",
}
# Tamil, Gujarati, Kannada and Odia have no Piper voice. Meta's MMS voices (CC-BY-NC 4.0: free for non-commercial / school use) cover them;
# `scripts/export_mms.py` converts them once to ONNX so they run here without PyTorch. Until that has been run the browser's own voice is used.
MMS_VOICES = {"ta": "tam", "gu": "guj", "kn": "kan", "or": "ory"}
WHISPER_LANG = {"en": "en", "hi": "hi", "bn": "bn", "mr": "mr", "te": "te", "ta": "ta", "gu": "gu", "ur": "ur", "kn": "kn", "or": None, "ml": "ml",
                "zh": "zh", "es": "es", "fr": "fr", "ar": "ar", "pt": "pt", "ru": "ru", "id": "id", "de": "de", "ja": "ja"}  # Whisper has no Odia: it listens and guesses
CACHE = config.DATA_DIR / "tts_cache"
CACHE_LIMIT = 400 * 1024 * 1024
_voices: dict[str, object] = {}
_vlock = threading.Lock()
_gate = threading.BoundedSemaphore(2)  # speech work runs on the CPU: it must not queue behind lessons being written by the model


def gate():
    """Context manager limiting how many speech jobs run at once."""
    return _gate


_whisper = None
_wlock = threading.Lock()


# ---- text to speech ----------------------------------------------------------------------------
def tts_languages() -> list[str]:
    if config.TTS != "piper":
        return []
    return [*PIPER_VOICES, *[l for l in MMS_VOICES if installed(l)]]


def _voice_files(lang: str) -> tuple[Path, Path]:
    rel = PIPER_VOICES[lang]
    base = config.VOICES_DIR / Path(rel).name
    return base.with_suffix(".onnx"), Path(str(base) + ".onnx.json")


def _mms_files(lang: str) -> tuple[Path, Path]:
    return config.VOICES_DIR / f"mms-{MMS_VOICES[lang]}.onnx", config.VOICES_DIR / f"mms-{MMS_VOICES[lang]}.json"


def installed(lang: str) -> bool:
    if lang in MMS_VOICES:
        return all(p.exists() for p in _mms_files(lang))
    if lang not in PIPER_VOICES:
        return False
    onnx, js = _voice_files(lang)
    return onnx.exists() and js.exists()


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
    tmp.replace(dest)


def install_voice(lang: str) -> None:
    """Download a Piper voice (one-off, 20-80 MB)."""
    if lang not in PIPER_VOICES:
        raise ValueError("No server voice for this language")
    config.VOICES_DIR.mkdir(parents=True, exist_ok=True)
    onnx, js = _voice_files(lang)
    rel = PIPER_VOICES[lang]
    if not js.exists():
        _download(f"{HF}/{rel}.onnx.json", js)
    if not onnx.exists():
        _download(f"{HF}/{rel}.onnx", onnx)


def _load(lang: str):
    with _vlock:
        if lang not in _voices:
            from piper import PiperVoice
            if not installed(lang):
                install_voice(lang)
            onnx, js = _voice_files(lang)
            _voices[lang] = PiperVoice.load(str(onnx), str(js))
        return _voices[lang]


class _Mms:
    """A Meta MMS voice converted to ONNX (see scripts/export_mms.py): characters in, 16 kHz audio out."""

    def __init__(self, onnx: Path, meta: Path) -> None:
        import onnxruntime as ort
        m = json.loads(meta.read_text(encoding="utf-8"))
        self.sess = ort.InferenceSession(str(onnx), providers=["CPUExecutionProvider"])
        self.vocab, self.rate = m["vocab"], int(m["sampling_rate"])
        self.blank, self.lower = m.get("blank_id"), bool(m.get("lowercase"))

    def wav(self, text: str) -> bytes:
        import numpy as np
        text = text.lower() if self.lower else text
        ids = [self.vocab[c] for c in text if c in self.vocab]
        if not ids:
            raise ValueError("Nothing this voice can say")
        if self.blank is not None:  # VITS expects a blank between characters
            ids = [x for i in ids for x in (self.blank, i)] + [self.blank]
        x = np.array([ids], dtype=np.int64)
        audio = self.sess.run(None, {"input_ids": x, "attention_mask": np.ones_like(x)})[0].reshape(-1)
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.rate)
            w.writeframes(pcm)
        return buf.getvalue()


def _load_mms(lang: str) -> _Mms:
    with _vlock:
        if lang not in _voices:
            onnx, meta = _mms_files(lang)
            _voices[lang] = _Mms(onnx, meta)
        return _voices[lang]  # type: ignore[return-value]


def _clean_for_speech(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"[*_`#>|]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:1200]


def synthesize(text: str, lang: str) -> tuple[bytes, float]:
    """-> (wav bytes, duration seconds). Cached on disk by text + voice."""
    if config.TTS != "piper" or not (lang in PIPER_VOICES or installed(lang)):
        raise ValueError("Server voice not available for this language")
    text = _clean_for_speech(text)
    if not text:
        raise ValueError("Nothing to say")
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{PIPER_VOICES.get(lang) or MMS_VOICES[lang]}|{text}".encode()).hexdigest()[:40]
    path = CACHE / f"{key}.wav"
    if path.exists():
        path.touch()
        data = path.read_bytes()
    else:
        if lang in MMS_VOICES:
            data = _load_mms(lang).wav(text)
        else:
            voice = _load(lang)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wav:
                voice.synthesize_wav(text, wav)
            data = buf.getvalue()
        path.write_bytes(data)
        _prune()
    with wave.open(io.BytesIO(data)) as w:
        return data, w.getnframes() / float(w.getframerate())


def _prune() -> None:
    files = sorted(CACHE.glob("*.wav"), key=lambda p: p.stat().st_mtime)
    total = sum(f.stat().st_size for f in files)
    while files and total > CACHE_LIMIT:
        f = files.pop(0)
        total -= f.stat().st_size
        f.unlink(missing_ok=True)


def word_timings(text: str, duration: float) -> list[dict]:
    """Estimate when each word starts, proportional to its length (Piper gives no word timestamps)."""
    words = re.findall(r"\S+", _clean_for_speech(text))
    weights = [len(w) + 1.5 for w in words]
    total = sum(weights) or 1.0
    t, out = 0.0, []
    for w, wt in zip(words, weights):
        out.append({"w": w, "t": round(t, 3)})
        t += duration * wt / total
    return out


def wav_concat(parts: list[bytes]) -> bytes:
    """Join WAV files with identical format into one (for the downloadable lesson audio)."""
    out = io.BytesIO()
    params = None
    with wave.open(out, "wb") as dst:
        for blob in parts:
            with wave.open(io.BytesIO(blob)) as src:
                if params is None:
                    params = src.getparams()
                    dst.setparams(params)
                dst.writeframes(src.readframes(src.getnframes()))
                dst.writeframes(b"\x00\x00" * int(src.getframerate() * 0.35))  # short pause between sections
    return out.getvalue()


# ---- speech to text ----------------------------------------------------------------------------
def stt_available() -> bool:
    if config.STT != "whisper":
        return False
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _model():
    global _whisper
    with _wlock:
        if _whisper is None:
            from faster_whisper import WhisperModel
            try:
                _whisper = WhisperModel(config.WHISPER_MODEL, device="cuda", compute_type="float16")
                log.info("whisper loaded on GPU")
            except Exception:  # noqa: BLE001 - no CUDA libraries: run on CPU
                _whisper = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
                log.info("whisper loaded on CPU")
        return _whisper


def _decode(audio: bytes):
    """Any browser recording (webm/ogg/mp4/wav) -> 16 kHz mono float32, via ffmpeg."""
    import subprocess

    import numpy as np
    proc = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", "16000", "pipe:1"],
                          input=audio, capture_output=True, timeout=60)
    if proc.returncode != 0 or not proc.stdout:
        raise ValueError("Could not read that audio recording")
    return np.frombuffer(proc.stdout, dtype=np.float32)


def transcribe(audio: bytes, lang: str) -> dict:
    """-> {"text", "language", "confidence"}. `audio` is any container ffmpeg can read (webm, ogg, wav, mp4)."""
    t0 = time.time()
    samples = _decode(audio)
    if len(samples) < 1600:  # shorter than 0.1 s
        return {"text": "", "language": lang, "confidence": 0.0}
    segments, info = _model().transcribe(samples, language=WHISPER_LANG.get(lang), vad_filter=True, beam_size=1, condition_on_previous_text=False)
    segs = list(segments)
    text = " ".join(s.text.strip() for s in segs).strip()
    conf = round(sum(min(1.0, max(0.0, 1 + s.avg_logprob / 2)) for s in segs) / len(segs), 2) if segs else 0.0
    log.info(f"transcribed {len(audio) // 1024} KB in {time.time() - t0:.1f}s")
    return {"text": text, "language": info.language, "confidence": conf}
