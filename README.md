# AIVidya — a voice-enabled AI teacher for Grades 7–12

AIVidya teaches **Physics, Chemistry, Biology, Maths, Computers, English, Social Science and Commerce** (NCERT/CBSE-style, with an ICSE overlay)
in simple words, by **voice and transcript**, in **20 languages** chosen from the button in the top-right corner: the ten most spoken in India (Hindi, Bengali, Marathi, Telugu, Tamil, Gujarati, Urdu, Kannada, Odia, Malayalam) and ten international ones (English, Chinese, Spanish, French, Arabic, Portuguese, Russian, Indonesian, German, Japanese). One choice changes the app, the lessons and answers, and the voice.
It runs on **your own computer with local models (Gemma 4 and gpt-oss via Ollama)** — no API key needed — or on Claude.

* **Students** browse topics → lessons, listen, ask doubts by voice/text/photo, quiz themselves, practise, take timed tests, revise on a schedule, earn XP.
* **Parents** approve children's accounts and see progress. **Teachers** run classes, assign work, review and correct the AI's lessons. **Admins** have their own console (`#/admin`) to manage people, schools, the topic list and curriculum, every lesson and student-added topic, write lessons in bulk, send announcements, and look after backups and system health.
* Everything the AI writes is labelled, reviewable and correctable. See **[FEATURE_STATUS.md](FEATURE_STATUS.md)** for exactly what is done, partly done or limited — and **read it before putting this in front of children.**

## Quick start

```bash
./install.sh            # Python env, offline libraries, Ollama models, first admin   (or:)
./scripts/pull_models.sh   # gemma4:e4b (everyday), gpt-oss:20b (pictures, fact-checks), translategemma:4b (translating the app), nomic-embed-text (search); --small skips gpt-oss
.venv/bin/python scripts/pull_voices.py   # the 16 Piper voices + speech recognition (Whisper large-v3-turbo); Tamil/Gujarati/Kannada/Odia voices: scripts/export_mms.py
./run.sh                # http://127.0.0.1:8000
```
Just trying it? `TEACHER_MOCK=1 ./run.sh` (sample content, no model) or `TEACHER_AUTH=off ./run.sh` (no sign-in, one person).
Docker: `docker compose up -d --build` (see **[docs/DEPLOY.md](docs/DEPLOY.md)** for HTTPS, GPU, backups, capacity planning and a first-day checklist).
Use **Chrome or Edge** for browser voice input; or choose *private voice input* (Whisper on the server) in Settings → Voice. Run **Voice check** (`#/voicecheck`) on a new device.

## What it does

| Area | Features |
|---|---|
| Topics | topic lists by class, board, stream and **level** (Foundation adds the earlier lessons you build on; Challenge adds olympiad-style extensions), and **My topics**: students add anything they are curious about and the local model writes a private lesson on it |
| Lessons | 12-part lessons (why it matters → idea → how it works → worked example → **edge cases** → **advantages & limits** → **where it is used** → common mistakes → try-it → exam corner → connections → recap), spoken sentence by sentence with word highlighting and a transcript; Quick mode, cheat sheet, diagrams, exam-focus briefing, objectives, prerequisites, bookmarks, highlights, notes, resume, offline copy, downloadable audio |
| Tutor | streaming answers read aloud, hands-free mode, photo of homework, board with formulas/graphs/diagrams, SymPy algebra, sandboxed Python, unit conversion, textbook citations, **stays on topic**, safe with distress and unsafe requests, remembers how you learn, stop/regenerate |
| Practice | adaptive quizzes (wrong answers explained), practice problems with hints and step-by-step feedback, "check my working", teach-it-back, oral viva, flashcards (SM-2), mistakes notebook, placement check, timed tests and CBSE-pattern papers, question bank |
| Daily habit | **Daily 5** (five questions a day from what you are about to forget or got wrong; feeds the streak), **Answer coach** (write a 2/3/5-mark answer, see where each mark came from and what was missing), **Ask my teacher** (send a doubt to your class teacher, with the AI's answer attached if you wish) |
| Progress | Bayesian knowledge tracing with a forgetting curve, daily plan with exam countdown, XP/levels/badges, streaks, opt-in class leaderboard |
| Tools | 12 simulations (graphs, projectile, motion, Ohm's law, waves, optics, pH, …), periodic table, equation balancer, 3D molecules, Python/HTML runner |
| Schools | **doubt inbox** and **worksheet maker** (question paper plus answer key, printable), accounts and roles, parental consent, classes, assignments, mastery heat-maps, review queue, reports, library of textbooks, curriculum editor, analytics, audit log, backups |
| Platform | offline libraries (strict CSP), installable PWA, accessibility (axe-clean, dyslexia font, high contrast, text size), 20 languages (interface, lessons, voice), Prometheus metrics, CI, Docker |

## Configuration

Everything is optional; see **[.env.example](.env.example)**. The most useful settings:

| Setting | Meaning |
|---|---|
| `TEACHER_PROVIDER` / `TEACHER_MODEL` | `ollama` (default) or `anthropic` + `claude-opus-5-5`. `TEACHER_MODEL` pins one model for all everyday jobs |
| `TEACHER_MODEL_<JOB>` | choose the model per job: `LESSON`, `CHAT`, `SUMMARY`, `CHEATSHEET`, `QUIZ`, `VISION`, `FIGURE`, `FACTCHECK`, `STRONG`. Defaults: `gemma4:e4b` for everyday jobs, `gpt-oss:20b` for pictures and fact-checks (`STRONG`, off by default, sends hard chat questions to a bigger model) |
| `TEACHER_AUTH=off` | single-person mode without accounts |
| `TEACHER_ADMIN_USER/PASSWORD` | creates the first administrator |
| `TEACHER_COOKIE_SECURE=1` | when served over HTTPS |
| `TEACHER_STT=whisper`, `TEACHER_TTS=piper` | private server voice (default on if installed) |

## Using a small local model well

Each job has its own local model: **Gemma 4 (e4b)** writes lessons, answers questions, makes summaries/cheat sheets/quizzes and reads photos; **gpt-oss 20b** draws the lesson pictures, double-checks the lesson's facts and breaks ties on practice answers (it loads only when needed and then makes room again; set `TEACHER_MODEL_STRONG` to also send hard chat questions to it). On an RTX 4090 a lesson starts showing in ≈10 s and takes ≈1½ min to finish, chat answers take 5–12 s. AIVidya is built for models of this size: lessons are written one section per call and cached; quiz keys are double-checked; the calculator echoes expressions; a scope guard keeps it on topic; the board is written if the reply promised one.
It still **makes mistakes** (wrong reasoning; lessons in the less common languages read less naturally than English). Measured on this machine, e.g. it once answered 48 m instead of 24 m. Treat every lesson as a draft until a teacher reviews it, and for maths-heavy or regional-language use set a stronger model (`TEACHER_QUIZ_MODEL`, `TEACHER_STRONG_MODEL`) or use Claude.
Measure before you trust: `python evals/run.py --repeat 3`.

## Project layout

```
backend/            FastAPI app (routes/, providers/ for Ollama & Claude), agent loop (tutor.py), tools, learner model, exams, voice, RAG
backend/curriculum_data/   the syllabus as plain text (+ boards/icse.txt overlay, prereqs.txt)
frontend/           vanilla ES modules, no build step; vendor/ is downloaded by scripts/vendor.sh; locales/ are translations
evals/              behaviour tests for the tutor against golden questions
scripts/            vendor, pregenerate, backup, create_admin, live_smoke, i18n_extract/build_locales
tests/              pytest (backend, with fake Ollama/Anthropic servers) and tests/js (Node unit tests)
docs/DEPLOY.md      production guide      mobile/  Capacitor wrapper scaffold      FEATURE_STATUS.md  honest status
```

## Develop & test

```bash
pip install -r requirements-dev.txt -r requirements-voice.txt
ruff check backend tests scripts evals && python -m pytest        # 100+ backend tests, fully offline
npm test                                                           # front-end unit tests
python scripts/live_smoke.py                                       # against your real model
python evals/run.py --repeat 3                                     # tutor behaviour quality
python scripts/i18n_extract.py                                     # translation coverage
```

## Privacy & safety in one paragraph

With the local model, lessons and chats never leave your machine (browser speech recognition may send audio to the browser vendor unless you pick private voice input). Children under 18 need a parent's approval; parents see progress, not chat transcripts; a distress message shows help-line numbers and alerts linked parents without the message. Student/model code runs in a no-network sandbox. Users can download or erase all their data. The privacy notice and terms (`backend/legal.py`) are **templates for your lawyer to finish**.
