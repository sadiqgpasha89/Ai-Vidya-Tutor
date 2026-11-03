# Deploying AIVidya

## 1. Pick a setup

| Setup | Good for | How |
|---|---|---|
| **One computer** (laptop/desktop) | one family or a tutor | `./install.sh` then `./run.sh`; add `TEACHER_AUTH=off` in `.env` to skip sign-in |
| **School server** | a class or a whole school | Docker Compose (below) behind HTTPS |
| **Claude API instead of a local GPU** | no GPU available | `TEACHER_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=…` |

## 2. Docker Compose (recommended for schools)

```bash
cp .env.example .env            # set TEACHER_ADMIN_USER / TEACHER_ADMIN_PASSWORD, TEACHER_COOKIE_SECURE=1
docker compose up -d --build
docker compose exec ollama ollama pull gemma4:e4b          # everyday model: lessons, chat, summaries, quizzes, photos
docker compose exec ollama ollama pull gpt-oss:20b          # pictures, fact-checking, answer-key tie-breaks (needs ~14 GB GPU memory; skip on small GPUs)
docker compose exec ollama ollama pull nomic-embed-text      # meaning-based search + textbook retrieval
```
GPU: uncomment the `deploy:` block in `docker-compose.yml` (NVIDIA container toolkit required). Open `http://server:8000`.
**Code sandbox:** on a normal Linux host (`systemd` install) AIVidya runs student/model code inside bubblewrap (no network, no access to your data).
Inside a Docker container bubblewrap cannot start (tested, even with `seccomp=unconfined`/`SYS_ADMIN`), so AIVidya detects this and uses its **restricted mode**:
code is limited by an allow-list (no `os`, files, sockets, `eval`…), a 6 s CPU / 1 GB limit and a timeout, but without kernel isolation. The mode in use is shown in
*Admin → System health* and at `/api/meta`. If you want kernel isolation inside containers, use a runtime such as gVisor, or install without Docker.

## 3. HTTPS and a reverse proxy (required when students sign in over a network)

Caddy (automatic certificates):
```
vidya.myschool.in {
    encode gzip
    reverse_proxy 127.0.0.1:8000 { flush_interval -1 }      # -1 keeps Server-Sent Events (lessons, chat) streaming
}
```
nginx: `proxy_buffering off; proxy_read_timeout 600s; proxy_http_version 1.1;` on the `/api/` location.
Then set `TEACHER_COOKIE_SECURE=1`. Never expose Ollama's port (11434) to the network.

## 4. Without Docker: systemd

```ini
# /etc/systemd/system/vidya.service
[Unit]
Description=AIVidya AI teacher
After=network.target ollama.service
[Service]
User=vidya
WorkingDirectory=/opt/vidya
EnvironmentFile=/opt/vidya/.env
ExecStart=/opt/vidya/.venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000 --proxy-headers
Restart=on-failure
[Install]
WantedBy=multi-user.target
```
Run **one** worker. The model queue, rate limits and the single SQLite writer live in the process; scale by giving the model server more GPU, or by pointing several apps at different databases (one per school), not by adding workers.

## 5. Capacity planning (single local GPU)

* A local 8B model answers one request at a time. AIVidya queues requests fairly: chat first, then quizzes, then lesson writing; lessons are written section by section so chat can jump in between sections. Students see "N ahead of you" while waiting.
* Lessons are written **once** and cached for everyone: run `python scripts/pregenerate.py --grade 9 --resume` overnight before term starts, then review them in *Review lessons*.
* Typical RTX 4090 numbers with Gemma 4 e4b: first lesson section ~10 s, full lesson ~1½ min, chat answer 5–12 s, quiz ~45–60 s (five questions, each answer key double-checked), lesson pictures ~20 s each (gpt-oss, drawn in the background and kept). Switching between Gemma and gpt-oss costs ~10 s of loading; on a GPU under 16 GB set `TEACHER_MODEL_FIGURE=gemma4:e4b` (and `_FACTCHECK`, `_STRONG`) to keep everything on one model. A class of 30 asking questions at once will feel it; use `TEACHER_CONCURRENCY=2` with `OLLAMA_NUM_PARALLEL=2` if VRAM allows, or the Claude API.

## 6. First-day checklist

1. Create the admin (`TEACHER_ADMIN_USER/PASSWORD`, or `python scripts/create_admin.py name`), sign in, change the password.
2. Fill in contact details in **Privacy notice** and **Terms** (`backend/legal.py`) with your legal advisor. They are templates.
3. *Admin → Users*: create a school (gives a school code), make teachers.
4. *Teach → Library*: upload the textbook chapters you are licensed to use so answers cite them.
5. Pre-generate and **review** lessons for the grades you teach. Unreviewed lessons are labelled "AI-written".
6. Open **Voice check** on a student device. Choose *private voice input* in Settings → Voice if the browsers do not support recognition.
7. **Set up email (SMTP) before opening sign-ups. Everyone depends on it.** People create accounts with an email address and a 6-digit code sent to that address, and sign in the same way each time (a password is optional, and "Keep me signed in on this device" lasts `TEACHER_REMEMBER_DAYS`, default 30). With no email working, nobody without a password can sign in. Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` and `SMTP_SECURITY` (see `.env.example`; Gmail, Outlook, SES and school mail servers all work). Without `SMTP_HOST` no email is sent and each code is written to the server log, so only the person running the server can read it. Web push and WhatsApp are optional; in-app reminders work out of the box.

## 7. Backups, upgrades, monitoring

* Automatic daily backups to `data/backups/` (`TEACHER_BACKUP_HOURS`); manual: *Admin → Health → Back up now* or `python scripts/backup.py`. **Also copy `data/` off the machine.** Restore: stop the app, copy a backup over `data/teacher.db`, start.
* Upgrade: `git pull && docker compose up -d --build`. Database migrations run automatically at start and are append-only.
* Prometheus: scrape `/metrics` (localhost, or send `Authorization: Bearer $TEACHER_METRICS_TOKEN`). Logs: `TEACHER_LOG_JSON=1`. Health: `/api/health`.
* After changing the model or prompts, run `python evals/run.py --repeat 3` and compare with the previous run.

## 8. Security notes

* Passwords are scrypt-hashed; sessions are random tokens stored hashed, in HttpOnly SameSite cookies. Five wrong passwords in a row lock a username for ten minutes; sign-in and AI calls are rate limited.
* The strict Content-Security-Policy forbids inline scripts and third-party code; all libraries are vendored (`scripts/vendor.sh`).
* Student/model code runs in a bubblewrap sandbox on a plain Linux host (no network, no access to app data, 6 s CPU / 1 GB limits). In Docker it falls back to a weaker restricted mode (see §2).
* Children's accounts need parent consent; parents see progress, never chat transcripts. A distress message triggers help-line numbers and an alert (without the message) to linked parents. All of this is disclosed in the privacy notice.
* Not included: single sign-on, e-mail verification (no e-mail is required to sign up), CAPTCHA. For a public internet service add them at the proxy.

## Languages

The language button (top-right) offers 20 languages and changes the interface, the lessons/answers and the voice together.

| What | How it is done | Download |
|---|---|---|
| Interface | `frontend/locales/<code>.json`, machine-translated with TranslateGemma (Gemma 4 for Odia) by `scripts/translate_ui.py`; **have a native speaker review them** | `ollama pull translategemma:4b` |
| Lessons, answers, quizzes | Gemma 4 writes them directly in the language (Odia is marked beta); section titles and safety messages are in `backend/server_text.json` | — |
| Voice (text to speech) | Piper voices for 16 languages (~65 MB each, downloaded by `scripts/pull_voices.py`); Tamil, Gujarati, Kannada, Odia from Meta MMS, converted once by `scripts/export_mms.py` (**CC-BY-NC licence: non-commercial/school use only**) | `data/voices/` |
| Speech recognition | Whisper `large-v3-turbo` (private, on the server). Whisper has no Odia: it guesses | first use, ~1.6 GB |
| Right-to-left | Arabic and Urdu switch the page direction | — |

Fonts: the browser needs a font for each script (most systems have them; on a bare Linux install add `fonts-noto`).
Distress detection uses word lists for English and Hindi (including romanised Hindi) and, for every other language, a quick yes/no check by the model on each message (about a second). Add phrases in `backend/moderation.py` for your community.
