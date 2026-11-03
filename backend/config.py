"""Runtime configuration, read from the environment (and a local .env). `validate()` reports every problem at startup."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()
_problems: list[str] = []


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _int(name: str, default: int, lo: int = 0, hi: int = 10**9) -> int:
    raw = _env(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        _problems.append(f"{name}='{raw}' is not a whole number")
        return default
    if not lo <= value <= hi:
        _problems.append(f"{name}={value} must be between {lo} and {hi}")
        return default
    return value


def _flag(name: str, default: bool = False) -> bool:
    raw = _env(name)
    return default if raw == "" else raw.lower() in ("1", "true", "yes", "on")


DATA_DIR = Path(_env("TEACHER_DATA_DIR") or ROOT / "data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---- model provider ----------------------------------------------------------------------------
PROVIDER = _env("TEACHER_PROVIDER", "ollama").lower()
if PROVIDER not in ("ollama", "anthropic"):
    _problems.append(f"TEACHER_PROVIDER='{PROVIDER}' must be 'ollama' or 'anthropic'")
OLLAMA_HOST = _env("OLLAMA_HOST", "http://127.0.0.1:11434")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = "http://" + OLLAMA_HOST
NUM_CTX = _int("TEACHER_NUM_CTX", 12288, 2048, 262144)
MOCK = _flag("TEACHER_MOCK")
WARMUP = _flag("TEACHER_WARMUP", default=not MOCK)
# Model calls running at once. A single local GPU does one at a time well; Claude can take many.
# Quiet background preparation while the model is idle (pictures, facts and summaries of lessons just written; the next topic's lesson).
PREFETCH = _flag("TEACHER_PREFETCH", default=True)
CONCURRENCY = _int("TEACHER_CONCURRENCY", 1 if PROVIDER == "ollama" else 4, 1, 64)

_DEFAULT_MODELS = {"ollama": "gemma4:e4b", "anthropic": "claude-opus-5-5"}
# Which local model does which job. Everyday work (writing lessons, chatting, summaries, cheat sheets, quizzes, reading photos) runs on one
# fast model that stays loaded; the specialists load on demand: gpt-oss:20b draws diagrams, double-checks facts and handles hard maths.
MODEL_ROLES = ("lesson", "chat", "summary", "cheatsheet", "quiz", "vision", "figure", "factcheck", "strong")
_EVERYDAY = ("lesson", "chat", "summary", "cheatsheet", "quiz", "vision")
_SPECIALIST_DEFAULTS = {"figure": "gpt-oss:20b", "factcheck": "gpt-oss:20b", "strong": "gpt-oss:20b"}
_LEGACY_ENV = {"quiz": "TEACHER_QUIZ_MODEL", "factcheck": "TEACHER_QUIZ_MODEL", "strong": "TEACHER_STRONG_MODEL", "vision": "TEACHER_VISION_MODEL"}


def role_model(role: str, provider: str | None = None) -> str:
    """The model configured for a job. TEACHER_MODEL_<ROLE> (e.g. TEACHER_MODEL_FIGURE) wins, then the older TEACHER_QUIZ_MODEL /
    TEACHER_STRONG_MODEL / TEACHER_VISION_MODEL, then TEACHER_MODEL for everyday jobs, then the built-in default."""
    prov = provider or PROVIDER
    specific = _env(f"TEACHER_MODEL_{role.upper()}") or _env(_LEGACY_ENV.get(role, "-"))
    if specific:
        return specific
    if prov == "anthropic":
        return _env("TEACHER_MODEL") or _DEFAULT_MODELS["anthropic"]
    if role in _EVERYDAY:
        return _env("TEACHER_MODEL") or _DEFAULT_MODELS["ollama"]
    return _SPECIALIST_DEFAULTS.get(role, "")


def is_pinned(role: str) -> bool:
    """True when the operator chose this job's model explicitly (then a missing model is an error, not something to quietly replace)."""
    return bool(_env(f"TEACHER_MODEL_{role.upper()}") or _env(_LEGACY_ENV.get(role, "-")) or (role in _EVERYDAY and _env("TEACHER_MODEL")))


def model(provider: str | None = None) -> str:
    """The everyday model (lessons, chat). TEACHER_MODEL overrides the per-provider default (e.g. llama3.1:8b, or claude-sonnet-5-5)."""
    return role_model("lesson", provider)


def structured_model(provider: str | None = None) -> str:
    """Quizzes, grading, other structured answers."""
    return role_model("quiz", provider)


def strong_model() -> str:
    """A bigger model the tutor escalates hard maths/physics chat questions to. Off unless you set TEACHER_MODEL_STRONG: Gemma answers these correctly
    on its own, and swapping to a 20B model costs 30-40 s on a 16 GB GPU. (gpt-oss still breaks ties when two checks of a practice answer disagree.)"""
    return role_model("strong") if is_pinned("strong") else ""


def vision_model() -> str:
    return role_model("vision")


EMBED_MODEL = _env("TEACHER_EMBED_MODEL", "nomic-embed-text")
VERIFY_CHAT = _flag("TEACHER_VERIFY_CHAT")  # second-model check of numeric/maths chat answers (slower)
WEB_SEARCH = _flag("TEACHER_WEB_SEARCH")  # lets the tutor search the web (off by default: privacy)


def model_slug() -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", f"{PROVIDER}-{model()}")


# Anthropic only: reasoning depth per workload.
EFFORT_LESSON = _env("TEACHER_EFFORT_LESSON", "medium")
EFFORT_CHAT = _env("TEACHER_EFFORT_CHAT", "low")
EFFORT_QUIZ = _env("TEACHER_EFFORT_QUIZ", "medium")
for _name, _val in (("TEACHER_EFFORT_LESSON", EFFORT_LESSON), ("TEACHER_EFFORT_CHAT", EFFORT_CHAT), ("TEACHER_EFFORT_QUIZ", EFFORT_QUIZ)):
    if _val not in ("low", "medium", "high", "xhigh", "max"):
        _problems.append(f"{_name}='{_val}' must be low, medium, high, xhigh or max")

# ---- accounts & security -----------------------------------------------------------------------
AUTH = _env("TEACHER_AUTH", "on").lower()  # "on": accounts with passwords; "off": single-device anonymous profiles
if AUTH not in ("on", "off"):
    _problems.append(f"TEACHER_AUTH='{AUTH}' must be 'on' or 'off'")
SESSION_DAYS = _int("TEACHER_SESSION_DAYS", 30, 1, 365)
REMEMBER_DAYS = _int("TEACHER_REMEMBER_DAYS", 30, 1, 365)  # "keep me signed in on this device": no idle sign-out, and the sign-in lasts this long
IDLE_MINUTES = _int("TEACHER_IDLE_MINUTES", 120, 1, 1440)  # a signed-in session with no requests for this long is signed out
COOKIE_SECURE = _flag("TEACHER_COOKIE_SECURE")  # set when served over HTTPS
ADMIN_USER = _env("TEACHER_ADMIN_USER")
ADMIN_PASSWORD = _env("TEACHER_ADMIN_PASSWORD")
ADULT_AGE = 18  # under this age, parental consent is required (India DPDP Act 2023: a "child" is under 18)
NOTICE_VERSION = "2026-11-01"
RATE_AI = _int("TEACHER_RATE_AI", 40, 1, 100000)  # AI requests per user per minute
RATE_AUTH = _int("TEACHER_RATE_AUTH", 12, 1, 100000)  # sign-in / sign-up attempts per IP per minute
RATE_GENERAL = _int("TEACHER_RATE_GENERAL", 900, 1, 1000000)  # all API requests per IP per minute
MAX_BODY = _int("TEACHER_MAX_BODY_MB", 1, 1, 100) * 1024 * 1024
MAX_UPLOAD = _int("TEACHER_MAX_UPLOAD_MB", 25, 1, 500) * 1024 * 1024

# ---- notifications -----------------------------------------------------------------------------
SMTP_HOST, SMTP_PORT = _env("SMTP_HOST"), _int("SMTP_PORT", 587, 1, 65535)
SMTP_USER, SMTP_PASSWORD, SMTP_FROM = _env("SMTP_USER"), _env("SMTP_PASSWORD"), _env("SMTP_FROM", "aividya@localhost")
SMTP_SECURITY = _env("SMTP_SECURITY", "starttls").lower()  # starttls (port 587), ssl (port 465) or none (a local mail relay)
# Email codes (one-time passwords) for signing up and resetting a password
OTP_MINUTES = _int("TEACHER_OTP_MINUTES", 10, 1, 60)
OTP_RESEND_SECONDS = _int("TEACHER_OTP_RESEND_SECONDS", 60, 0, 600)
VAPID_PUBLIC, VAPID_PRIVATE, VAPID_SUBJECT = _env("VAPID_PUBLIC_KEY"), _env("VAPID_PRIVATE_KEY"), _env("VAPID_SUBJECT", "mailto:admin@localhost")
WHATSAPP_TOKEN, WHATSAPP_PHONE_ID = _env("WHATSAPP_TOKEN"), _env("WHATSAPP_PHONE_ID")
REMINDERS = _flag("TEACHER_REMINDERS", default=not MOCK)

# ---- voice -------------------------------------------------------------------------------------
TTS = _env("TEACHER_TTS", "piper").lower()  # "piper" (server voices) or "off"
STT = _env("TEACHER_STT", "whisper").lower()  # "whisper" (private speech recognition) or "off"
WHISPER_MODEL = _env("TEACHER_WHISPER_MODEL", "large-v3-turbo")
VOICES_DIR = Path(_env("TEACHER_VOICES_DIR") or DATA_DIR / "voices")

# ---- operations --------------------------------------------------------------------------------
METRICS_TOKEN = _env("TEACHER_METRICS_TOKEN")  # bearer token for /metrics from non-local scrapers
LOG_LEVEL = _env("TEACHER_LOG_LEVEL", "INFO").upper()
LOG_JSON = _flag("TEACHER_LOG_JSON")
BACKUP_HOURS = _int("TEACHER_BACKUP_HOURS", 24, 0, 24 * 90)  # 0 = no automatic backups
BACKUP_KEEP = _int("TEACHER_BACKUP_KEEP", 7, 1, 365)

# The 20 languages offered: the ten most spoken in India and the ten most spoken around the world (English is the default and counts as one of the latter).
# `speech` is the BCP-47 tag used by the browser's speech synthesis / recognition; `scripts` the writing systems a lesson in that language may use
# (plus Latin letters for technical terms); `rtl` marks right-to-left languages; `group` is how the picker lists them.
SCRIPTS = {"latin": "A-Za-z", "deva": "\u0900-\u0963\u0966-\u097f", "beng": "\u0980-\u09ff", "guru": "\u0a00-\u0a7f", "gujr": "\u0a80-\u0aff", "orya": "\u0b00-\u0b7f", "taml": "\u0b80-\u0bff",
           "telu": "\u0c00-\u0c7f", "knda": "\u0c80-\u0cff", "mlym": "\u0d00-\u0d7f", "arab": "\u0600-\u06ff\u0750-\u077f", "cyrl": "\u0400-\u04ff", "han": "\u4e00-\u9fff",
           "kana": "\u3040-\u30ff"}
LANGUAGES = {
    "en": {"name": "English", "native": "English", "speech": "en-IN", "group": "world", "scripts": ["latin"]},
    "hi": {"name": "Hindi", "native": "हिन्दी", "speech": "hi-IN", "group": "india", "scripts": ["deva"]},
    "bn": {"name": "Bengali", "native": "বাংলা", "speech": "bn-IN", "group": "india", "scripts": ["beng"]},
    "mr": {"name": "Marathi", "native": "मराठी", "speech": "mr-IN", "group": "india", "scripts": ["deva"]},
    "te": {"name": "Telugu", "native": "తెలుగు", "speech": "te-IN", "group": "india", "scripts": ["telu"]},
    "ta": {"name": "Tamil", "native": "தமிழ்", "speech": "ta-IN", "group": "india", "scripts": ["taml"]},
    "gu": {"name": "Gujarati", "native": "ગુજરાતી", "speech": "gu-IN", "group": "india", "scripts": ["gujr"]},
    "ur": {"name": "Urdu", "native": "اردو", "speech": "ur-IN", "group": "india", "scripts": ["arab"], "rtl": True},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ", "speech": "kn-IN", "group": "india", "scripts": ["knda"]},
    "or": {"name": "Odia", "native": "ଓଡ଼ିଆ", "speech": "or-IN", "group": "india", "scripts": ["orya"]},
    "ml": {"name": "Malayalam", "native": "മലയാളം", "speech": "ml-IN", "group": "india", "scripts": ["mlym"]},
    "zh": {"name": "Chinese (Mandarin)", "native": "中文", "speech": "zh-CN", "group": "world", "scripts": ["han"]},
    "es": {"name": "Spanish", "native": "Español", "speech": "es-ES", "group": "world", "scripts": ["latin"]},
    "fr": {"name": "French", "native": "Français", "speech": "fr-FR", "group": "world", "scripts": ["latin"]},
    "ar": {"name": "Arabic", "native": "العربية", "speech": "ar-SA", "group": "world", "scripts": ["arab"], "rtl": True},
    "pt": {"name": "Portuguese", "native": "Português", "speech": "pt-BR", "group": "world", "scripts": ["latin"]},
    "ru": {"name": "Russian", "native": "Русский", "speech": "ru-RU", "group": "world", "scripts": ["cyrl"]},
    "id": {"name": "Indonesian", "native": "Bahasa Indonesia", "speech": "id-ID", "group": "world", "scripts": ["latin"]},
    "de": {"name": "German", "native": "Deutsch", "speech": "de-DE", "group": "world", "scripts": ["latin"]},
    "ja": {"name": "Japanese", "native": "日本語", "speech": "ja-JP", "group": "world", "scripts": ["han", "kana"]},
}
LOCAL_LANGS = set(LANGUAGES) - {"or"}  # Gemma 4 writes all of these well enough to teach; Odia is the weakest, so it is marked beta in the picker

LEVELS = {
    "foundation": "Foundation - take it slow, more analogies, minimal maths",
    "standard": "Standard - board-exam level",
    "challenge": "Challenge - deeper reasoning, olympiad / JEE / NEET flavour",
}
GRADES = [7, 8, 9, 10, 11, 12]
BOARDS = ["CBSE", "ICSE", "State Board"]
GOALS = {
    "boards": "School & board exams", "jee": "JEE (Main/Advanced)", "neet": "NEET", "olympiad": "Olympiads", "cuet": "CUET",
}
STREAMS = {
    "pcm": "Science - Physics, Chemistry, Maths", "pcb": "Science - Physics, Chemistry, Biology", "pcmb": "Science - PCM + Biology",
    "commerce": "Commerce", "humanities": "Humanities / Arts",
}
TRACKS = {"cs": "Computer Science", "ip": "Informatics Practices"}  # Grades 11-12 computers
ROLES = ("student", "parent", "teacher", "school_admin", "admin")


def validate() -> list[str]:
    """Every configuration problem found, as readable sentences (empty list = fine)."""
    problems = list(_problems)
    if AUTH == "on" and COOKIE_SECURE is False and _env("TEACHER_PUBLIC") == "1":
        problems.append("TEACHER_PUBLIC=1 but TEACHER_COOKIE_SECURE is off: serve over HTTPS and set TEACHER_COOKIE_SECURE=1")
    if PROVIDER == "anthropic" and not MOCK and not (_env("ANTHROPIC_API_KEY") or _env("ANTHROPIC_AUTH_TOKEN")):
        problems.append("TEACHER_PROVIDER=anthropic needs ANTHROPIC_API_KEY (or run `ant auth login`)")
    if SMTP_SECURITY not in ("starttls", "ssl", "none"):
        problems.append(f"SMTP_SECURITY='{SMTP_SECURITY}' must be starttls, ssl or none")
    if bool(VAPID_PUBLIC) != bool(VAPID_PRIVATE):
        problems.append("Set both VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY, or neither")
    if bool(WHATSAPP_TOKEN) != bool(WHATSAPP_PHONE_ID):
        problems.append("Set both WHATSAPP_TOKEN and WHATSAPP_PHONE_ID, or neither")
    if bool(ADMIN_USER) != bool(ADMIN_PASSWORD):
        problems.append("Set both TEACHER_ADMIN_USER and TEACHER_ADMIN_PASSWORD, or neither")
    if ADMIN_PASSWORD and len(ADMIN_PASSWORD) < 8:
        problems.append("TEACHER_ADMIN_PASSWORD must be at least 8 characters")
    return problems
