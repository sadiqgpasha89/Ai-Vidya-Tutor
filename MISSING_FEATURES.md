> **Update:** this was the gap list written before the second build. Every item has since been addressed or consciously limited; see **[FEATURE_STATUS.md](FEATURE_STATUS.md)** for the item-by-item result.

# AIVidya – Missing Features & Known Gaps

An honest inventory of what the app does **not** do yet, based on the current code (not on the README's aspirations).
Priority: **P0** = needed before real students use it, **P1** = big learning or product value, **P2** = nice to have.
Effort: **S** (hours), **M** (days), **L** (weeks).

## What exists today (for context)

Subject → chapter → subtopic browsing (838 subtopics, Grades 7–12, 5 subjects) · 12-section streamed lessons with voice + transcript ·
tutor chat with tools (calculator, board, find_topics, student profile, learning signals) · hands-free voice conversation ·
MCQ quiz · teach-back grading · Leitner revision schedule · streak · 3 levels · 8 languages · Ollama (default) and Anthropic providers.

---

## 0. Things that are built but NOT verified

These exist in code but have never been exercised on a real device or API. Treat them as unproven.

| Gap | Why it matters | Pri | Effort |
|---|---|---|---|
| Real speech output on a real device | The dev browser had no voices; only the "silent failure" guard and sentence queue were tested | P0 | S |
| Speech recognition and hands-free mode | Needs Chrome/Edge with a microphone; never run | P0 | S |
| Anthropic provider against the live API | Only tested against a fake server (no API key was available) | P1 | S |
| Indian-language lessons (Telugu, Tamil, Kannada, Marathi, Bengali) | Llama 3.1 doesn't officially support them; quality unmeasured | P1 | M |
| Mobile layout on real phones | Checked only in browser emulation at 375 px | P1 | S |
| Accuracy of lessons across the 838 subtopics | Only a handful were generated and read | P0 | L |

## 1. Content accuracy & trust (biggest risk)

| Missing | Notes | Pri | Effort |
|---|---|---|---|
| Grounding in real textbooks (NCERT) via retrieval | Lessons come from model memory only; no source passages, no citations | P0 | L |
| Teacher/expert review workflow | No review queue, approve/reject, or "verified" badge on lessons | P0 | M |
| "Report a mistake" button for students | No way to flag a wrong lesson, quiz question or chat answer | P0 | S |
| Regenerate / edit a lesson or section | Cached lessons can only be changed by deleting files by hand | P1 | S |
| Automated fact-check pass | A second model (or calculator/sympy) cross-checking lessons and quiz keys; today only local quizzes get a weak verification | P1 | M |
| Symbolic maths checking (sympy) | Calculator is numeric only; can't verify algebra, derivatives, factorisation | P1 | M |
| Pre-generation / cache warm-up script | First student on each topic waits ~1 minute; no batch job for a whole syllabus | P1 | S |
| Lesson versioning | Switching model or prompt silently starts a new cache; old lessons aren't tracked or comparable | P2 | S |
| AI-content disclaimer in the UI | Nothing tells students/parents that content is AI-generated and may contain errors | P0 | S |
| Evaluation harness | No golden Q&A set, no regression tests for answer quality or scope-guard behaviour | P1 | M |

## 2. Curriculum

| Missing | Notes | Pri | Effort |
|---|---|---|---|
| Official syllabus mapping | Outline is NCERT-*style*, hand-written, not an official mapping; no chapter numbers, units, or marks weightage | P1 | M |
| State-board and ICSE syllabi | Board is a label only; content is identical for CBSE/ICSE/State | P1 | L |
| Learning objectives per chapter/subtopic | None stored; the tutor can't tell what "done" means | P1 | M |
| Prerequisite graph | Only linear previous/next within a grade; no "you need X before Y" across chapters or grades | P1 | M |
| Placement / diagnostic test | New students pick a grade; nothing checks whether they are actually ready | P1 | M |
| Other subjects (English, Hindi, Social Science, EVS) | Only 5 subjects | P2 | L |
| Class 11–12 streams | Computer Science vs Informatics Practices, Biology-without-Maths, Commerce maths not distinguished | P2 | M |
| Competitive-exam tracks (JEE, NEET, olympiads, CUET) | Only a "Challenge" level and an exam-tips section | P2 | L |
| Curriculum editor (admin UI) | Curriculum is edited by changing text files | P2 | M |

## 3. Learning experience

| Missing | Notes | Pri | Effort |
|---|---|---|---|
| **Chat and board history is not saved** | Reloading or leaving a lesson loses the whole conversation and board | P0 | S |
| Resume position in a lesson | No "continue from section 5" | P1 | S |
| Practice problems with step-by-step checking | Quiz is MCQ only; no numeric, short-answer, or multi-step problems; no hints ladder | P1 | L |
| Question bank / previous-year and board-style papers | None | P1 | L |
| Timed tests and mock exams | None | P2 | M |
| Mistake notebook | Wrong quiz answers are not stored for later review; only a "misconception" note is saved | P1 | S |
| Real revision sessions | Due topics appear as links; there are no flashcards or quick-recall drills for them | P1 | M |
| Adaptive difficulty | Level is chosen once; quizzes don't get harder or easier based on results | P1 | M |
| Proper learner model | Mastery is a simple moving average per subtopic; no per-concept tracking, no forgetting estimate beyond fixed intervals | P2 | L |
| Concise lesson mode | Every lesson is 12 sections (~10+ minutes); no 5-minute summary or "just the formula" mode | P1 | S |
| Notes / bookmarks / highlights | Can't save or print notes, formula sheets or the board | P1 | M |
| Study plan, goals, exam countdown | None | P2 | M |
| Motivation features beyond the streak | No badges, XP, levels, or (privacy-safe) class challenges | P2 | M |
| Oral viva (spoken back-and-forth assessment) | Teach-back is one-shot; no spoken Q&A examination | P2 | M |
| Feedback on lessons | No thumbs up/down or "too easy / too hard" per section | P1 | S |
| Semantic search | Search matches words in titles only ("why is the sky blue" won't find Scattering of light) | P2 | M |

## 4. Rich content & interactivity

| Missing | Notes | Pri | Effort |
|---|---|---|---|
| Diagrams in lessons | Lessons are text + LaTeX; only the chat can draw SVG, and only when the model chooses to | P1 | M |
| Interactive simulations / graphs | No projectile, circuit, graph-plotter or titration widgets | P1 | L |
| In-browser code runner | Computers lessons show code but students can't run or edit it | P1 | M |
| Photo / image input | Can't photograph a homework problem or a diagram and ask about it | P1 | M |
| Textbook / PDF upload | Can't ask questions about the student's own textbook pages | P2 | M |
| Videos / animations | None | P2 | L |
| Chemistry tools (equation balancer, periodic table, 3D molecules) | None | P2 | M |

## 5. Voice

| Missing | Notes | Pri | Effort |
|---|---|---|---|
| Offline / private speech recognition | Uses the browser's Web Speech API: Chrome/Edge only, audio goes to Google. Whisper (local) not integrated | P1 | M |
| Consistent, high-quality text-to-speech | Voice quality and Indian-language availability depend on the user's device; no server-side TTS (e.g. Piper, AI4Bharat Indic TTS) | P1 | M |
| Word-level highlighting | Highlight is per sentence only | P2 | S |
| Better spoken maths and chemistry | Equation-to-speech is a rough regex; chemical formulas, units and Indian-language numerals aren't handled | P2 | M |
| Voice interruption (barge-in) | Student must tap the mic; the app can't detect speech while AIVidya is talking | P2 | M |
| Downloadable lesson audio | No MP3/offline listening | P2 | M |
| Voice-picker per language | One voice choice stored for all languages | P2 | S |
| Noise / accent handling | No confidence display, no "did you mean…" correction of recognised text | P2 | S |

## 6. Tutor agent

| Missing | Notes | Pri | Effort |
|---|---|---|---|
| Stop-generating button | A long answer or lesson can't be cancelled from the UI | P1 | S |
| Regenerate a reply or section | Not available | P1 | S |
| Memory across sessions | Only a few "learning signals" are stored; no summary of what the student knows or how they like to learn | P1 | M |
| More tools | No Python runner, graph plotter, unit converter, web or textbook search | P1 | M |
| Checking the student's own work | Can't ask "check my solution" with structured step feedback | P1 | M |
| Smarter model routing | One model for everything; no automatic escalation to a stronger model for hard maths/physics questions | P1 | M |
| Safer small-model behaviour | Llama 8B still mentions the board without using it, repeats tools, or answers conceptual questions wrongly | P1 | M |
| Moderation layer | Scope and safety rely only on the prompt; no separate input/output safety check | P0 | M |
| Distress / wellbeing handling | Prompt-level only; no escalation path or resources list | P1 | S |
| Cross-topic questions | Off-topic redirect works, but "go to that topic and bring this question with you" doesn't | P2 | S |

## 7. Accounts, privacy & safety (required for children)

| Missing | Notes | Pri | Effort |
|---|---|---|---|
| Authentication | Student ID is a random value in the browser; no login, passwords, or recovery. Anyone with the ID can read the progress | P0 | M |
| Parental consent and age gate | Required for minors under India's DPDP Act 2023 and similar rules | P0 | M |
| Data export and deletion | No "delete my data" or "download my data" | P0 | S |
| Multiple students on one device | One profile per browser; no switcher | P1 | S |
| Cross-device sync | Progress is tied to one browser's stored ID | P1 | M |
| Rate limiting, abuse protection, request size limits | None; any client can hammer the model | P0 | S |
| Privacy notice and terms | None in the app | P0 | S |
| Audit log | No record of who did what | P2 | S |

## 8. Teachers, parents & schools

| Missing | Notes | Pri | Effort |
|---|---|---|---|
| Teacher dashboard | No class roster, progress heatmap, or weak-topic report | P1 | L |
| Assignments | A teacher can't assign a topic, quiz or deadline | P1 | M |
| Parent view and reports | None | P1 | M |
| Reminders and notifications | No email / WhatsApp / push for revision or streaks | P1 | M |
| Multi-school / multi-tenant support | Single global database | P2 | L |
| Analytics | No usage, learning-outcome, or cost tracking | P1 | M |

## 9. Accessibility & localisation

| Missing | Notes | Pri | Effort |
|---|---|---|---|
| Translated interface | Buttons, menus and messages are English only, even when the lesson is in Hindi or Telugu | P1 | M |
| Accessibility audit | Basic ARIA and keyboard use only; no screen-reader testing, colour-contrast check, or focus-trap in modals | P1 | M |
| Display preferences | No font-size control, dyslexia-friendly font, high-contrast mode, or manual light/dark toggle (follows the system only) | P2 | S |
| Reduced-data / low-bandwidth mode | Page loads libraries from CDNs | P2 | M |
| Onboarding tour | None | P2 | S |

## 10. Platform & engineering

| Missing | Notes | Pri | Effort |
|---|---|---|---|
| Truly offline operation | Despite the local model, the page loads marked, KaTeX and DOMPurify from public CDNs; vendor them | P1 | S |
| Installable app (PWA) and offline lessons | No manifest, service worker, or offline cache | P2 | M |
| Native mobile apps | None | P2 | L |
| Concurrency and scaling for a classroom | Ollama serves one request at a time; no queue, no position-in-line message, no multi-GPU or batching plan. A whole class opening new lessons would wait minutes | P0 (for classrooms) | M |
| Model warm-up at startup | The first request after idle loads the model (seconds to minutes) | P1 | S |
| Frontend tests | UI was checked manually in a browser; no unit or end-to-end tests | P1 | M |
| CI, linting, type-checking | None configured | P1 | S |
| Docker / one-command install | Needs Python venv + Ollama set up by hand | P1 | S |
| Production serving guide | Runs the plain dev-style uvicorn command; no HTTPS, reverse proxy, or process manager | P1 | S |
| Database migrations and backups | SQLite schema created on the fly; no migrations, no backup | P1 | S |
| Logging, tracing, health dashboard | Minimal; health is a one-time toast at page load | P1 | S |
| Health indicator in the UI | If Ollama stops mid-session the student sees an error only when asking | P2 | S |
| Config validation | Bad `.env` values fail late with generic messages | P2 | S |

---

## Suggested order of work

1. **Before any student uses it (P0):** AI-content disclaimer, report-a-mistake button, persisted chat history, authentication + parental consent + data deletion, rate limiting, moderation layer, real-device voice testing, and a reviewed set of lessons for at least one grade and subject.
2. **Next (P1):** textbook grounding (RAG), teacher review queue, practice problems with step checking, mistake notebook and real revision drills, translated UI, vendored libraries for offline use, classroom concurrency (queue + warm-up), teacher dashboard.
3. **Later (P2):** simulations, local Whisper/Indic TTS, native apps, competitive-exam tracks, gamification.
