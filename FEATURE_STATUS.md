# Feature status — every item from MISSING_FEATURES.md

✅ built and exercised · 🟡 built but partly verified, or deliberately limited · ⛔ cannot be done from code alone (reason given)
"Exercised" means a test, a real-model run, or a check in the browser. Counts at the bottom.

## 0. Built but unverified (the original worry list)

| Item | | What was done / what is still open |
|---|---|---|
| Real speech output | 🟡 | New **Voice check** page (`#/voicecheck`) tests device voices, server voice, microphone, both recognisers and barge-in on any device. Server voice verified end-to-end (Piper wrote audio, Whisper transcribed it back correctly on the GPU). **Open:** nobody has listened on real speakers/phones; the test browser has no voices. |
| Speech recognition & hands-free | 🟡 | Private recognition (Whisper) verified with synthesised speech; the recording/silence-detection/hands-free loop is code-reviewed but **never run with a real microphone**. |
| Anthropic provider on the live API | 🟡 | `scripts/live_smoke.py` runs the whole stack against a real model (run against local Llama: see below). Claude path tested only against a fake server (no API key here). |
| Indian-language lessons | 🟡 | Hindi and Hinglish lessons generate correctly (a bug where speech came out in English was found and fixed). **Quality with Llama 3.1 8B is weak** (wrong terms, drift); Telugu/Tamil/Kannada/Marathi/Bengali are unsupported by that model and labelled *experimental*. Use a larger model, and native-speaker review. |
| Mobile on real phones | 🟡 | Responsive layout checked in emulation at 375 px; installable PWA; Capacitor project scaffolded (`mobile/`) but not built (needs Android SDK / Xcode). |
| Accuracy across all topics | ⛔ | Needs subject experts. What exists to make that practical: automatic fact-check on every lesson, teacher review queue with approve/edit/reject, bulk `scripts/pregenerate.py`, and a behaviour eval suite. |

## 1. Content accuracy & trust

| Item | | Notes |
|---|---|---|
| Textbook grounding (RAG) | ✅ | PDF/text ingest → chunks → local embeddings (nomic-embed-text) → cited passages in lessons and chat; keyword fallback. Verified with the real embedding model. **NCERT text is not bundled** (copyright): upload your licensed copies in *Teach → Library*. |
| Teacher/expert review workflow | ✅ | Versioned lessons (draft → approved/rejected), editor with preview, history, "Reviewed by" badge for students. |
| "Report a mistake" | ✅ | On lessons, chat answers and quiz questions; teachers resolve in *Reports*. |
| Regenerate / edit lessons | ✅ | Per-section rewrite, whole-lesson regenerate, teacher edit → new approved version. Students can also rewrite a section for themselves. |
| Automated fact-check | ✅ | Deterministic arithmetic checker + model review per section, shown to reviewers; students see a warning when a high-severity issue is unreviewed. Local quizzes also verify keys. |
| Symbolic maths (SymPy) | ✅ | `algebra` tool (solve, factor, diff, integrate, limit, equality…) in the sandbox; expression whitelist; verified. |
| Pre-generation script | ✅ | `scripts/pregenerate.py` (filters, resume, dry run, extras). |
| Lesson versioning | ✅ | Every generation/edit is a version with model, source, status, reviewer. |
| AI-content disclaimer | ✅ | Badge on every lesson, footer on every page, labels on AI-marked results, in the privacy notice and terms. |
| Evaluation harness | ✅ | `evals/run.py` + 18 golden cases (numeric, concept, scope, injection, safety), `--repeat`, JSON report, CI-gateable. First real run exposed that Llama stayed on topic 1/3 times → fixed (see scope guard), now 3/3. |

## 2. Curriculum

| Item | | Notes |
|---|---|---|
| Official syllabus mapping | 🟡 | 9 subjects, 362 chapters, 1,254 topics with chapter numbers; still an NCERT-*style* outline written by the developer, no marks weightage. Admin editor lets a school correct it. |
| State-board & ICSE syllabi | 🟡 | Board overlay mechanism + an ICSE overlay for Grade 9–10 Physics/Chemistry/Biology; lessons are board-aware (separate cache). **No State-board outlines shipped** (they differ by state). |
| Learning objectives | ✅ | Generated per topic, cached, shown on the lesson page and used by the tutor. |
| Prerequisite graph | ✅ | ~100 cross-chapter/cross-grade links, validated by a test; lesson page suggests a refresher when prerequisites are weak. |
| Placement / diagnostic test | ✅ | Per subject; results seed the learner model and recommend where to start. |
| Other subjects | ✅ | English, Hindi, Social Science, Commerce (outlines). |
| Class 11–12 streams | ✅ | PCM/PCB/PCMB/Commerce/Humanities and CS vs IP tracks. |
| Competitive-exam tracks | 🟡 | Goal (boards/JEE/NEET/Olympiad/CUET) drives an "Exam focus" briefing, exam-style papers and tutor framing. No dedicated JEE/NEET question banks or full-length mocks are bundled. |
| Curriculum editor | ✅ | Add/rename/hide chapters and topics, audit-logged, base files untouched. |

## 3. Learning experience

| Item | | Notes |
|---|---|---|
| Chat & board history saved | ✅ | Reloads restore the conversation and boards (browser-verified). |
| Resume position | ✅ | |
| Practice with step checking | ✅ | Generated numeric/short problems, 3-level hint ladder, step-by-step feedback, reveal; exact numeric check in code. |
| Question bank / past papers | 🟡 | Bank with import (CSV/JSON), approval, reuse in papers. **No previous-year papers are shipped** (rights); teachers import theirs. |
| Timed tests & mock exams | ✅ | Unit 10 / Half 30 / CBSE-pattern 80-mark papers, server-enforced timer, auto + AI marking, late flag. |
| Mistake notebook | ✅ | |
| Real revision sessions | ✅ | SM-2 flashcards (generated per topic) + due topics + mistakes retry. |
| Adaptive difficulty | ✅ | Quiz and practice difficulty follow the learner model (bug found while writing this audit: quizzes were not adaptive; fixed). |
| Proper learner model | ✅ | Bayesian knowledge tracing + forgetting curve per topic; revision dates from predicted recall. Per-*concept* tracking is approximated by misconception signals, not a full concept graph. |
| Concise lesson mode | ✅ | Quick (5 parts) and one-page Cheat sheet. |
| Notes / bookmarks / highlights | ✅ | Highlight any text, save board/cheat sheet to notes, export Markdown, print. |
| Study plan / exam countdown | ✅ | Daily plan, pace check against exam date. |
| Motivation beyond streak | ✅ | XP, levels, 12 badges, daily goal, opt-in nickname-only class leaderboard. |
| Oral viva | ✅ | Spoken Q&A with scoring and summary. |
| Lesson feedback | ✅ | Per-section helpful/confusing/too hard/too easy/wrong. |
| Semantic search | ✅ | Embedding search across grades with a boost for the student's grade (verified on 5 real queries: 4 good, "why is the sky blue" still misses). |

## 4. Rich content

| Item | | Notes |
|---|---|---|
| Diagrams in lessons | ✅ | On-demand AI-drawn SVG (sanitised), plus tutor board diagrams and graphs. Quality depends on the model. |
| Simulations & graphs | ✅ | 12 tools: function grapher, projectile, motion graphs, Ohm's law, pendulum+waves, lenses/mirrors, pH, periodic table, equation balancer, 3D molecules, number systems, logic gates, unit converter. |
| In-browser code runner | ✅ | Python (Pyodide in a worker, 10 s kill) and an HTML preview, verified under the CSP. |
| Photo input | ✅ | Photo → local vision model → transcription → tutor. Verified: it read a worksheet and the tutor caught the wrong answer. |
| Textbook/PDF upload | ✅ | Students' own uploads (private) and a shared library. |
| Videos / animations | 🟡 | Teachers attach YouTube/video links per topic (embedded privacy-friendly); the simulations are the animations. **No videos are shipped.** |
| Chemistry tools | ✅ | Balancer (exact rational maths), 118-element table, 11 rotatable 3D molecules. |

## 5. Voice

| Item | | Notes |
|---|---|---|
| Private recognition | ✅ | Whisper on the server (GPU/CPU); selectable per user. |
| Consistent TTS | 🟡 | Piper server voices for English, Hindi, Telugu, Marathi, Bengali (voices download on first use). **None exist yet for Tamil and Kannada** — device voices are used there. |
| Word-level highlighting | ✅ | Browser voices use real word events; server voices use estimated timings. |
| Spoken maths & chemistry | ✅ | Units, formulae (H₂SO₄), operators; operator words in 7 languages (non-English ones are best-effort, need native review). |
| Barge-in | 🟡 | Voice-activity detection with echo cancellation; **untested with a real microphone**; headphones advised. |
| Downloadable audio | ✅ | Whole lesson as WAV (languages with a server voice). |
| Voice per language | ✅ | |
| Noise/accent handling | ✅ | Confidence shown; low confidence asks "Did you say…?" with alternatives. |

## 6. Tutor agent

| Item | | Notes |
|---|---|---|
| Stop generating | ✅ | Cancels the model call server-side. |
| Regenerate | ✅ | |
| Memory across sessions | ✅ | Summarised notes (no names/addresses), refreshed every 8 messages. |
| More tools | ✅ | SymPy algebra, sandboxed Python, graph plotting, unit conversion, textbook search, check-my-work, prerequisites, optional web search (off by default). |
| Checking the student's work | ✅ | Modal + tool. |
| Model routing | ✅ | Optional stronger model for hard maths/science (`TEACHER_STRONG_MODEL`). |
| Safer small-model behaviour | 🟡 | Fixes: promised-board writer, trimmed tool menus, calculator echo/guards, scope guard, optional verify pass. **Wrong reasoning still happens** (e.g. 48 m vs 24 m earlier); measured by the evals. |
| Moderation layer | 🟡 | Rule-based input/output filters + scope guard that don't depend on the tutor model. **No separate LLM safety classifier**; rules can be evaded by novel phrasing. |
| Distress handling | ✅ | Help-lines (Tele-MANAS 14416, CHILDLINE 1098), alert to linked parent without content. |
| Cross-topic questions | ✅ | Chips open the other topic and carry the question. |

## 7. Accounts, privacy & safety

| Item | | Notes |
|---|---|---|
| Authentication | ✅ | Scrypt passwords, hashed session tokens, lockout, roles, sign-up and password reset by emailed 6-digit code (below). `TEACHER_AUTH=off` for single-person use. |
| Parental consent & age gate | ✅ | Under 18 → pending until a parent enters the child's code; revocable. Template wording needs legal review. |
| Data export & deletion | ✅ | Self-service and by parent; erasure verified by test. |
| Several students per device | 🟡 | Sign out / sign in; no fast user switcher. |
| Cross-device sync | ✅ | Server accounts. |
| Rate limiting & limits | ✅ | Per-user AI, per-IP auth/general, body-size caps, security headers, strict CSP. |
| Privacy notice & terms | 🟡 | Written and shown (templates). **A lawyer must review and add the operator's details.** |
| Audit log | ✅ | |

## 8. Teachers, parents, schools

| Item | | Notes |
|---|---|---|
| Teacher dashboard | ✅ | Classes, rosters, mastery heat-map by chapter, hard-topics list, student overviews. |
| Assignments | ✅ | Lessons, quizzes, practice, with due dates; auto-ticked on completion. |
| Parent view & reports | ✅ | Weekly summary, per-subject progress, printable. |
| Reminders & notifications | 🟡 | In-app: tested. **E-mail, web push and WhatsApp are implemented but could not be tested live** (no SMTP/keys). |
| Multi-school | 🟡 | Schools, school codes, school-admin role, class scoping; not a hard multi-tenant split of content. |
| Analytics | ✅ | Usage, tokens, latency, learning outcomes, reports. |

## 9. Accessibility & localisation

| Item | | Notes |
|---|---|---|
| Translated interface | 🟡 | 143 of 742 strings (navigation, buttons, core flows) in Hindi, Telugu, Tamil, Kannada, Marathi, Bengali; the rest falls back to English. Written by the developer: **needs native review.** `scripts/i18n_extract.py` reports gaps. |
| Accessibility audit | ✅ | axe-core: 0 violations (WCAG 2.1 A/AA + best practice) on 6 key pages in light, dark and high-contrast themes at 130% text; modal focus-trap, labelled controls, live regions. **No screen-reader or user testing.** |
| Display preferences | ✅ | Light/dark/high-contrast, text size, dyslexia-friendly font, line spacing. |
| Reduced-data mode | 🟡 | Data-saver switch (no autoplay/animation), vendored libraries, gzip; no image/low-bandwidth variant of lessons. |
| Onboarding tour | ✅ | |

## 10. Platform & engineering

| Item | | Notes |
|---|---|---|
| Fully offline libraries | ✅ | All libraries vendored (`scripts/vendor.sh`); CSP forbids third-party code. |
| PWA & offline lessons | ✅ | Installable; lessons you opened are cached for offline reading; shell cached. |
| Native mobile apps | 🟡 | Capacitor scaffold only; not built or published. |
| Classroom concurrency | ✅ | Priority queue (chat > quiz > lessons), "N ahead of you", lessons yield between sections. A single GPU is still the limit. |
| Model warm-up | ✅ | |
| Front-end tests | 🟡 | 6 Node unit-test groups (found 3 real bugs) + extensive manual browser checks; **no automated end-to-end browser suite**. |
| CI, lint, types | 🟡 | GitHub Actions workflow + ruff (clean). **Never run on GitHub**; no static type checker. |
| Docker / one-command install | 🟡 | Image **builds (1.7 GB) and serves the app** (health, vendored libraries, voice and sandbox checked in the running container). Inside Docker the strong bubblewrap sandbox cannot start, so a weaker restricted mode is used (documented). `install.sh` not run on a clean machine. |
| Production guide | ✅ | `docs/DEPLOY.md`. |
| Migrations & backups | ✅ | Versioned migrations, online backups, retention. |
| Logging & metrics | ✅ | Structured logs with request ids, Prometheus `/metrics`, admin health. |
| Health indicator in UI | ✅ | |
| Config validation | ✅ | |

## Fixes after first real use (2026-11-01)

The first real session on the user's machine found that lessons, chat, cheat sheet and listening all stalled. What was wrong and what changed:

| Problem | Cause | Fix |
|---|---|---|
| Lesson stuck on "Waiting in line — 2 ahead of you", chat and cheat sheet never answered | With one model lane (the Ollama default) several endpoints took a model slot and then asked for a second one inside it (objectives, cheat sheet, diagram, exam focus, flashcards), so they waited for themselves for 15 minutes and blocked everyone behind them. The automated tests used the demo model, which never reaches that code | Removed the nested slots; the slot is now re-entrant per thread; two regression tests run with one lane |
| Listening cut out while a lesson was being written | Speech (Piper, on the CPU) queued behind the model | Speech has its own small gate and never waits for the model |
| Skip buttons did nothing / felt dead | They had nothing to skip to while the lesson was stuck; no feedback either | ⏮ restarts the current part (or goes back if it just began), ⏭ goes forward, a message explains when the lesson is not ready or it is the last part |
| Quick (5 min) was only the lesson with some parts hidden | — | A real summary: five short parts written from the finished lesson, with their own text, transcript and audio |
| No pictures in lessons | — | "The big idea", "How it works" and "Worked example" each get a picture, drawn once by gpt-oss and kept; "Draw a diagram" uses the same drawer |
| Quality of Llama 3.1 8B (wrong analogy for acceleration, wrong Hindi term) | small model | **One model per job**: gemma4:e4b for everyday work, gpt-oss:20b for pictures, fact-checks and answer-key tie-breaks (hard chat questions go to it only if `TEACHER_MODEL_STRONG` is set); a missing model falls back to an installed one; `./scripts/pull_models.sh` downloads them |
| Wrong answer key on a practice problem (a right answer was marked wrong) | key was never checked | Each numeric problem is solved independently; two solves that agree override a wrong key |
| "Who won the 2011 World Cup" got answered | the on-topic guard skipped any question containing a digit | Only real maths (operators, units, "find/solve") skips the guard |
| Wrong-script words in Hindi speech (a Bengali word) | model slip | Non-English sections are checked and rewritten once if they contain another Indian script |
| Fact-check cried wolf ("high" for unit choices) and thrashed the GPU (12 model loads) | — | Stricter severity rule; one call per lesson |
| First-run settings dialog and tour overlapped | — | The tour waits until the dialog is closed |

Measured after the change (RTX 4090 laptop, 16 GB, one student): chat answers 5–12 s; lesson first part ≈10 s, complete ≈1½ min; quiz ≈45–60 s; 18/18 behaviour checks pass (was 16/18 on Llama). While a second program (another server, a smoke test) shares the same GPU, everything is several times slower: the queue is per server, not per GPU.

## Menu, languages and subjects (2026-11-01, second round)

| Request | What was done | Honest status |
|---|---|---|
| Keep the app in English; remove the Hindi subject | English is the default everywhere; the Hindi subject and its syllabus file are gone (8 subjects remain); Hinglish removed (existing profiles moved to English by a migration) | ✅ |
| Menu under a hamburger (☰), expandable | Drawer from the left with groups that open and close (Subjects, Practice, My progress, Tools, Help; Teaching/Administration for staff); the group you are in opens itself; keyboard, Escape, focus trap; RTL-aware | ✅ clicked through; axe-core 0 violations with the menu and picker open |
| Language picker top-right, 10 Indian + 10 international, for UI and voice | One button; the choice sets the app text, the lessons/answers/quizzes and the voice together (and is saved to the student's profile). Indian: Hindi, Bengali, Marathi, Telugu, Tamil, Gujarati, Urdu, Kannada, Odia, Malayalam. International: English, Chinese, Spanish, French, Arabic, Portuguese, Russian, Indonesian, German, Japanese | ✅ built and used; quality varies by language, see below |
| Download local models for these languages | `translategemma:4b` (translates the interface, 55 languages); `gemma4:e4b` (writes lessons in the language; also translates Odia); 16 Piper voices; MMS voices for Tamil, Gujarati, Kannada, Odia converted to ONNX; Whisper `large-v3-turbo` for speech recognition | ✅ all downloaded and used on this machine |

What was measured: every language's voice was tested by translating a sentence, speaking it, and transcribing the audio with Whisper large-v3-turbo. Similarity to the text: Spanish 0.92, French 0.94, Arabic 0.95, Portuguese 0.90, Russian 0.90, Indonesian 0.92, German 0.92, Chinese 0.80, Urdu 0.85, Hindi 0.91, Tamil 0.86, Kannada 0.87, Telugu 0.92, Bengali 0.74, Gujarati 0.69; Japanese was fluent after installing `pyopenjtalk-plus`. Malayalam scored 0.26 because the machine translation of the test sentence contained a stray word; Odia cannot be scored (Whisper has no Odia) but its audio matched Odia word-for-word when read as sounds.

Limits: the interface translations are **machine-made and unreviewed**; lessons in less common languages read less naturally than English (Gemma writes them directly); subject and topic names in the syllabus stay English; the MMS voices are **CC-BY-NC** (non-commercial use); fonts for every script must exist on the device; distress detection for languages other than English/Hindi relies on a model check, not word lists; Arabic and Urdu switch to right-to-left but were only checked briefly.

## Topics by class and level; topics students add (2026-11-01, third round)

| Request | What was done | Honest status |
|---|---|---|
| Topics according to the student's curriculum, not the same for every class and level | Class-wise lists already existed (e.g. Physics: 5 chapters in Class 7 up to 12 in Class 12; the check is in the tests). New: the **level** now changes the list. *Standard* = the plain syllabus for the class and board. *Foundation* adds "Build your foundation": earlier-class chapters this class builds on (from the prerequisite graph). *Challenge* adds "Challenge extensions" beyond the syllabus (olympiad / JEE / NEET foundation / programming contests) | ✅ built and clicked through. The Challenge chapters are **AI drafts, not checked by a teacher** (Maths and Computers for Classes 8-12, Science for 11-12 from the local model; Class 9-10 science hand-written because the model's drafts reached university level). Teachers can hide or rename them in the curriculum editor. State-board syllabi are still not included: only CBSE and a small ICSE overlay |
| Students add topics; the local model writes the explanation | "My topics" on the home page, in the menu and on its own page: type a topic (and optionally details and a subject), the model writes the same 12-part lesson with voice, summary, cheat sheet, pictures, quiz and chat. Moderated (unsafe topics refused), limited to 40 per student, can be removed (the lesson, notes and chat go with it) | ✅ built; a lesson on "How do black holes form?" was written in 77 s |
| Privacy of those topics (you chose: private to the student) | Only the owner can open one (other students get "Unknown topic"); they never appear in the teacher's review queue, class reports or parent reports; they are exported and erased with the account | ✅ tested |

Limits: a topic the student types is only as good as the model's knowledge of it (there is no textbook to ground it, so facts are unchecked unless the automatic fact-check flags them); "Test me" is not offered on own topics.

## Auto sign-off and lesson pictures

| Ask | What exists now |
|---|---|
| Sign out after 120 minutes of inactivity | Enforced on the server (a session with no requests for `TEACHER_IDLE_MINUTES`, default 120, is deleted and the next request gets a 401 with the reason) and in the browser (`frontend/idle.js`: keyboard, mouse, touch and scroll activity, shared between tabs; signs out through the server and shows "You were signed out after 120 minutes of inactivity"). While the student is active but not asking for anything (reading), the page pings `/api/auth/ping` every few minutes so the server does not count them as away. A laptop that sleeps past the limit is signed out on wake-up. Does not apply in single-person mode (`TEACHER_AUTH=off`). Verified in the browser with the limit set to 2 minutes. |
| Pictures in each lesson's explanation (every topic) | **Every** section of the full lesson (all 12) and every part of the 5-minute summary gets a concept diagram, drawn after the lesson is written: concept map for the big idea and uses, steps for how it works / examples / the activity, a cycle for repeating processes, side-by-side columns for edge cases, advantages vs limitations and mistakes. The everyday model writes a short description (layout, labels, notes) and `backend/diagrams.py` draws it, so text never overlaps. Safety nets: maths markup in labels (`$..$`, `\frac`, `**`) is written out as plain symbols; if the model's description is unusable twice, a plain diagram is built from the section's own bold terms and bullets; if the picture request itself fails, the page shows "Couldn't draw the picture for this part. ↻ Try again" instead of silently showing nothing. Shown in the lesson's language (right-to-left for Arabic and Urdu). Pictures are kept, so reopening is instant. Checked on a fresh maths lesson: 12/12 diagrams, and 5 of 5 parts of the summary. |
| "Prepare notes" button: short, bullet-point notes with diagrams, saved, downloadable | A **📝 Prepare notes** button under the lesson modes (enabled once the lesson is written). It makes 4–7 note sections (2–6 one-line bullets each, key terms in bold, formulas rendered), a one-line summary, a "Remember" box and a diagram per section (about 30 s). The notes are **saved per student in the app's SQLite database** (table `study_notes`; MongoDB is not used), so they are there next time (the button then reads "My notes"), listed on the Notes page under "Study notes you prepared", exported and erased with the account, and deleted with a student's own topic. Buttons: **Download (web page)** (one self-contained HTML file with the diagrams embedded), **Download (Markdown)** (diagrams embedded as images), **Print / save as PDF**, **Prepare again**, **Delete**. Notes are private to the student. |

Limits: a diagram or note is only as correct as the model's reading of the lesson, so each says "Made by AI … check it against your textbook". Free-hand drawing by the larger model was tried first and dropped: its pictures had wrong arrows and overlapping labels. No diagrams in the cheat sheet. Physics-style pictures (ray diagrams, circuits, free-body diagrams) and graphs are not produced by this; the separate "Draw a diagram" button and the grapher still handle those. The print layout (print / save as PDF) is built with print-only styles and was not checked in a real print dialog. Notes are written in the student's lesson language; their quality in less common languages is lower, as for lessons. Setting the model to write notes needs the lesson first (open the full lesson).

## Curiosity facts, chat layout, guardrails, streak chip

| Ask | What exists now |
|---|---|
| "Did you know?" for every explainer | A **💡 Did you know?** card under every full lesson and every 5-minute summary (not the cheat sheet): 3 curiosity facts, each shown as a teaser question the student taps to reveal. Written by the everyday model from the finished lesson (true, well-established, not already in the lesson, no invented figures), made once per lesson and kept, screened by the output guardrail, shown in the lesson's language. Also added to the prepared study notes (and their downloads) when the facts exist. Marked "Written by AI". |
| Chat window fits the screen; bigger text box | The chat panel now measures the room left on the screen (on load, on scroll and on resize) so the whole panel, including the text box, stays inside the window on any laptop height; on phones it uses the dynamic viewport height. The text box is on its own full-width row, 72 px tall (grows to 180 px), with the camera, microphone and Send buttons below it. Before: 158 × 47 px and the bottom of the panel could fall below the window. |
| Input guardrails | Every message is checked before the tutor sees it: (1) word lists for prohibited requests - weapons/explosives, drugs and alcohol, hacking and phishing, fraud and forged documents, violence and bullying, hate, privacy invasion, piracy, gambling, sexual content, exam cheating - in English, Hindi (Devanagari and Roman letters), with spaced-out ("b o m b"), number-swapped ("b0mb"), full-width and zero-width tricks undone; (2) prompt-injection patterns (ignore/forget/override instructions, reveal or translate the prompt, "you are now…", DAN/developer mode, pretend/roleplay, fake system or XML tags, long encoded blobs); (3) a model reading in any language (ok / prohibited / injection / distress, about 0.2 s) for what word lists miss; (4) distress still gets the helpline reply. Distress aside, a refused message gets one polite boilerplate reply ("I'm sorry, but I can't help with that request. I'm AIVidya, your study assistant…") in the student's language and never reaches the tutor model. The same check covers Teach-it-back, Check my working, Oral viva, practice steps, "explain another way" guidance and My topics. |
| Answer only on the topic | Questions outside the lesson/subject still get the redirect, now worded as the same polite boilerplate with the topic name. The tutor prompt also forbids other personas, "modes", and revealing its instructions, and treats lesson text, textbook passages, photos and messages as data. |
| Output guardrails | The tutor's reply is checked as it is written, shown a sentence at a time: unsafe content (instructions for weapons/drugs/hacking/forgery, sexual content, hate, self-harm encouragement) or a leak of the tutor's own instructions stops the answer mid-way and replaces it with a polite refusal, so flagged text is not shown. The saved chat history holds the replacement, not the bad text. Did-you-know facts go through the same check. |
| 🔥 icon "not clicking" | It is the daily study streak (days in a row you opened a lesson, asked a doubt, took a quiz or revised). It was only a label. It is now a button: tap it for the count, what counts, the last 14 days, and a link to "My progress". It is shown for students even at 0 days and on phones (before: hidden at 0 and hidden on narrow screens). |

Limits: the word lists are strongest in English and Hindi; other languages rely on the model reading (29 of 30 test messages in eight languages were classified right; the one miss is now also on the word list). A determined attacker may find wording that gets through - that is why the tutor prompt and the output check are separate layers. Output checks are word-based (no second model call), so subtle harm in a reply that uses no listed phrase is not caught. A false positive blocks a student with a polite message; words like "explosive" or "hack" in a normal science question pass (tested).

## Speed: keep what is made, prepare the rest in the quiet

| What | How it works now |
|---|---|
| Generated topics are stored locally and never made twice | Lessons, pictures, curiosity facts, summaries, cheat sheets, learning goals and study notes were already kept in the local SQLite database, once for everyone with the same language, level and board. New: the **browser also keeps a copy of every lesson it has opened** (newest 150, in the browser's own storage). Opening one again asks the server only "is it still the same version?" (`/api/lesson/check`: no model, ~30 ms), shows the saved copy at once and refreshes its review status; if the lesson changed it is streamed again. The same saved copy works offline. Pictures that already exist arrive in one request (`/api/lesson/figures`) instead of one per section. |
| A written lesson no longer waits for the model | Opening a lesson that is already written used to queue behind any lesson being written (up to 10 s). It is now served straight from the database. The model queue also wakes a waiting request the instant its turn comes (it used to look every 0.7 s). |
| Things are ready before the student asks | After a lesson is written, the server quietly makes its 12 pictures, curiosity facts, 5-minute summary and cheat sheet; when a student opens a topic it writes **the next topic in their syllabus** ahead of time (at most 3 ahead). A job starts only after the model has been idle for a few seconds (3 s for pictures and facts, 6 s for a lesson ahead), a student always goes first, jobs using the everyday model run together, and the automatic fact-check (which swaps the big model in and evicts the everyday one) runs last, after 25 s of quiet. Switch off with `TEACHER_PREFETCH=0`. |
| One maker per item | If the page and the warm-up ask for the same picture, summary or cheat sheet at once, one makes it and the other waits for it. |
| Fewer requests on open | The per-section "highlights" request (12 at once) is now one; the learning-goals request jumps ahead of lesson writing in the queue; vendored libraries, fonts and icons are cached for a week; the page's own modules are downloaded in parallel (`modulepreload`) instead of one after another. |
| Write lessons overnight | `python scripts/pregenerate.py --subject maths --grade 9 --extras` writes every missing lesson (and with `--extras` its pictures, facts, summary and cheat sheet) into the same database; safe to stop and run again; `--dry-run` lists what is missing. |

Measured on this machine (gemma4:e4b on an RTX 4090 laptop, lesson of 12 sections, another student chatting meanwhile), before → after:

| | before | after |
|---|---|---|
| Open an already-written lesson while another lesson is being written | 0.7 – 10.5 s | 0.03 s |
| Open an already-written lesson (nothing else running) | 0.27 s | 0.14 s (saved copy) |
| First section of a lesson being written | 6.7 s (18 s once warm-up ran, before the fix below) | 4.2 s |
| Chat answer starts while a lesson is being written | 7.1 s | 0.9 s |
| 12 pictures of a lesson already opened once | 12 requests, ~0.4 s | 1 request, ~0.02 s |
| Pictures, facts, summary and cheat sheet of a new lesson | made when the student scrolls or taps (about 40 s of drawing in the lesson page) | ready about 70 s after the lesson, without the student asking |

Limits: the first time anyone opens a topic nobody has opened before (and that was not written ahead or by the script) it is still written by the model - about 90 s for 12 sections on this machine, with the first section after 4 s; a single local model serves one request at a time (Ollama runs one slot here), so that time cannot be shortened by running things in parallel. Writing the next topic ahead can be wasted work if the student never opens it (capped at 3). The browser's saved copy is per device.

## Daily 5, answer coach, doubt inbox, worksheet maker

| Feature | What exists now |
|---|---|
| **Daily 5** (students: `#/daily`, a card on the home page) | Five multiple-choice questions a day, made the first time they are needed and kept. Chosen in this order: topics **due for revision**, questions from the **mistakes notebook** (up to two, asked again), topics whose **recall is fading**, then whatever was **studied last**; approved question-bank questions are used before new ones are written (one model call for the missing ones, each checked by a second solve). Needs something studied first (otherwise says so). Marking is on the **server**: the key and the explanation reach the browser only after the answer, an answer is final, a reload resumes at the next question. Finishing updates the learner model per topic, puts wrong answers in the mistakes notebook (marking a mistake fixed when it is now right), gives XP (4 per right answer, +10 for finishing, +5 for all five), counts for the streak, and awards two new badges (☀️ Daily starter, 📅 Daily habit: 7 days). Explanations are made from the marking scheme with the "1 mark for" wording removed. The home card reads a small status (no model work) and, when today's set does not exist, **writes it in the background** once the model is idle, so it is usually ready when tapped. |
| **Answer coach** (`#/coach`) | The student picks a topic and 2, 3 or 5 marks and gets a written-answer question (an approved bank question first, else a new one; or **their own** question pasted from a textbook, for which the model writes a model answer and scheme). They write the answer (word counter against a suggested range) and are marked against the scheme: **marks are added up from the points of the scheme** (each point shows marks got/max and a comment), plus what was missing, up to three exam-technique tips and a locally computed length tip, then the model answer and the marking scheme. The question and scheme stay on the server until the answer is in. Marks feed the learner model and, below 50%, the mistakes notebook; XP, and a badge (✍️ Answer ace) for full marks. "Write it again" repeats the question; history of attempts is kept. Free-text answers and own questions pass the same input guardrails as the chat. |
| **Doubt inbox** (students `#/doubts`; teachers `#/teach/doubts`) | A student in a class sends a doubt to that class's teacher, optionally about a topic and optionally with what AIVidya answered (a "🙋 Ask my teacher" button on every tutor answer; the teacher sees it labelled as not checked by a teacher). The teacher gets a notification and an inbox (Waiting / Answered / Cleared, filter by class); replies notify the student; either side can add to the thread and either can clear it; a follow-up puts it back in the teacher's queue. Limits: 5 open doubts per student; messages from students go through the word-list guardrails. Visible only to the student and to teachers who manage that class (school admins of the school, administrators). A student with no class can join one from the dialog. |
| **Worksheet maker** (teachers `#/teach/worksheets`) | Pick up to 12 topics (subject, grade, chapters), the number and marks of each type (multiple choice, short, long, case-based, numerical; up to 40 questions), difficulty (easier / standard / harder), language, board, and an optional instruction. Written one section at a time with a progress line (about a minute for a full sheet); approved bank questions are used first and new ones are added to the bank as **unapproved**. The sheet is shown as a **question paper** (name/class/date lines, marks, time) and an **answer key with marking scheme**; both print cleanly (browser print), download as Markdown, can be renamed and deleted, and any question can be swapped for a new one (↻). Private to the teacher who made it. |
| Privacy | All four are included in "download my data" and erased with the account (a student's doubts and their messages, daily sets, written answers; a teacher's worksheets). |

Verified: 16 new tests (`tests/test_study_features.py`: hidden key and server marking, resume, no double award, mistake round-trip, scheme-based marks, privacy between students and teachers, limits, guardrails, input checks, worksheet make/replace/rename/delete, export and erasure) and the whole of each feature in the browser with the real model (Daily 5 with five newly written physics questions, finishing and badges; the coach marking a half-complete answer 1/3 with the missing points, tips and a model answer; a doubt sent by a student, seen and answered by the teacher with the notification; a two-section worksheet written, its answer key, and a question replaced). **Not verified:** print output on paper or as PDF (the page hides everything except the sheet when printing, but no printer dialog was opened); the "Ask my teacher" button inside the tutor chat (the code is a few lines; the dialog it opens was tested from the doubts page); the full-length 80-mark sheet time; Daily 5 and coach marking quality in languages other than English.

Fixes found on the way: the model repeating a textbook question when asked to replace one (it is now told which questions are on the sheet and tries twice); explanations showing "1 mark for ..." wording; formulas in coach feedback showing as raw LaTeX.

## Simpler sign-in (email code, short sign-up, remember this device)

| Ask | What exists now |
|---|---|
| Sign in without a password | **Sign in** now asks for one thing: the email address (or username). "Email me a code" sends a 6-digit code (`/api/auth/code/start`, `/code/verify`); entering it signs the person in. The answer to "send a code" is the same whether or not the account exists (the mail is sent in the background so timing does not reveal it); disabled accounts and accounts with no verified email get nothing. Same rules as every code: works once, 10 minutes, 5 wrong tries kill it, 60 s between codes, 5 an hour, and 8 wrong tries in 10 minutes lock that address for 10 minutes. The password form is still there under "Use a password instead", and its page offers the code instead ("Forgot it, or no password yet?"), so the separate forgot-password screen is gone from the app (its server routes remain). |
| Shorter sign-up | Three steps instead of one long form plus a code: **1.** email address, **2.** the code, **3.** "Almost done": I am a (student/parent/teacher), first name, year of birth, grade (students), terms. Board and school code are under "More options" (board can be changed later in Settings). No username and no password to invent: the username is made from the email (`meera.rao@...` becomes `meera.rao`, with digits added if taken) and is only a handle. The step-2 proof is a short-lived ticket (30 minutes, single use) so a mistake on the form (for example a wrong year of birth) can be corrected without another code. |
| Passwords are optional | Accounts made this way have no password. Settings → Account → "Set a password (optional)" adds one (nothing to type as the old password); after that "Change password" needs the old one as before. Deleting such an account needs only typing DELETE. Changing the email on a passwordless account needs a code to the new address but no password (a stolen sign-in could therefore change it; the same sign-in could already do anything else). Accounts that already have a password work unchanged, and administrator and bulk-created accounts are unaffected. |
| Fewer sign-ins on your own device | "Keep me signed in on this device for 30 days" (sign-in and the last sign-up step; the choice is remembered in the browser, off by default). A remembered sign-in lasts `TEACHER_REMEMBER_DAYS` (default 30) and is **not** ended by the 120-minute idle limit; sessions without it behave exactly as before (shared computers). Stored per session (migration v11); the page learns it from `/api/auth/me` (`remembered`) and stops its idle watcher. Signing out, "sign out everywhere", a password change and disabling the account still end it. |

Verified: 12 new tests in `tests/test_login_codes.py` plus the rewritten sign-up tests (46 auth tests in all; full suite green), and in the browser: email → code → "Almost done" → parent code for a child, sign-in by code (wrong code shows "4 tries left", right code signs in), sign-in on an account with no password, Settings showing "Set a password (optional)" with no old-password box. **Not verified:** delivery through a real mail provider (codes still go to the server log until SMTP is set up), and the password sign-in page in the browser (covered by the API tests). A handful of the 14 new interface strings fall back to English in Malayalam, Urdu, Bengali, Kannada, Odia and Tamil because the translation tool's output failed its checks; re-run `scripts/translate_ui.py` later.

## Sign-up with email codes (recovery codes removed) - first version; the steps and sign-in were then simplified, see above

| Ask | What exists now |
|---|---|
| Sign-up asks for username and email, and the email gets an OTP | Step 1: the form (role, name, **username, email address**, password, year of birth, class and board, terms). The server checks everything (username and email free, password strong enough, age rules) and emails a **6-digit code**; nothing is created yet. Step 2: the code screen ("Check your email"): enter the code and the account is made and signed in; children under 18 then see their parent code as before. The code works once, for 10 minutes; 5 wrong tries kill it; a new one can be asked for after 60 s and at most 5 times an hour; "Wrong email? Go back" returns to the form with what was typed. Codes are stored hashed with a salt, compared in constant time, and never sent back to the browser. One account per email address. |
| Recovery codes replaced | There are no recovery codes any more (nothing to save or lose). **Forgot your password?** takes a username or email, emails a 6-digit code, and the code plus a new password resets it (all sessions are signed out). The page says the same thing whether or not the account exists. Sign-in also accepts the email address. |
| Accounts made before this change | They have no email. When they sign in the home page asks them to add one (also in Settings → Account): enter the address, confirm the code, done. Changing an existing email needs the password. Until an account has a verified email its password can only be reset by a teacher, parent or admin. Accounts made by the admin script have no email either. |
| How the email is sent | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_SECURITY` (starttls / ssl / none). With no `SMTP_HOST` nothing is emailed and the code is written to the server log, and the code screen says so ("Ask the person who runs AIVidya for your code") - fine on your own computer, **not acceptable for a school: set up SMTP before opening sign-ups**. If the mail server refuses, the person sees "We could not send the email" and no code is left behind. |

Verified: 30+ automated tests (sign-up, wrong/expired/reused/farmed codes, duplicates and races, reset, adding an email, real SMTP delivery to a local test mail server) and the whole flow in the browser (sign-up, code, parent code for a child, wrong-email-go-back, forgot-password, sign-in by email, adding an email to an old account). **Not verified:** delivery through a real mail provider (Gmail, Outlook, SES...), and spam-folder behaviour; the email text is plain English only (the screens are translated, the email is not).

## Name: AIVidya

The product is called **AIVidya** everywhere a person can read it: page title and header, home-screen app name, every screen, the tutor introducing itself and refusing politely, emails (subject "Your AIVidya code"), sign-up terms, study notes and downloads (`aividya-my-data.zip`), documents and the README, in all 20 languages (the name is kept exactly as `AIVidya` in Latin letters, never translated or transliterated: the translation script now protects it and rejects any translation that changes it). Text the app wrote earlier (old tutor replies, cached lessons, notices) is renamed once by a database migration. `tests/test_brand.py` fails if the old short name creeps back into any file or translation. Left as they were on purpose, because they are never read by people and changing them would sign everyone out or lose saved data: the sign-in cookie (`vidya_session`), browser storage keys, internal logger and metric names, the `/opt/vidya` and `vidya.service` deployment examples, and the mobile app id `in.vidya.teacher`. Note: audio already made for lessons says the old name until it is made again; about 20 interface strings in Malayalam, Kannada, Urdu and Bengali could not be re-translated this time and show in English (with the new name) until the translation script is run again.

## Administrator console (separate admin module)

A separate area at **`#/admin`** with its own navigation, its own code (`backend/routes/admin.py`, `backend/admin_service.py`, `backend/jobs.py`, `frontend/admin.js`) and its own tests (`tests/test_admin.py`). Sign in as an administrator and the menu shows "🛠️ Admin console". The first administrator is made with `TEACHER_ADMIN_USER` / `TEACHER_ADMIN_PASSWORD` or `python scripts/create_admin.py`. The console is in English. Everything an administrator changes is written to the audit log.

| Section | What an administrator can do |
|---|---|
| Overview | People by role, new and active this week, who is waiting for parent approval or has no confirmed email; how many of the ~1450 topics have a lesson (with a coverage bar); lessons in use by status; pictures, fact sets, summaries, notes, questions and textbooks made; and a **Needs attention** list (open reports, lessons waiting for review, lessons the automatic check flagged, messages the guardrails stopped) linking to the place to fix each. One-click backup. |
| Users | Search and filter (role, status, no confirmed email, awaiting parent approval), 50 per page. **Create** a person (any role, class, school; email counts as confirmed; password made up and shown once if left empty). **Open** a person: profile, school, devices signed in, learning summary (topics, XP, streak, own topics, notes, classes, parents), children or classes taught, recent activity. **Change** name, role, school; **disable/enable**; **reset password**; **sign out everywhere**; **delete** (type the username to confirm). You cannot demote, disable or delete yourself. |
| Schools | List with people and class counts; create, rename, **new join code**, delete (refused while people or classes belong to it). |
| Topics and curriculum | The whole syllabus for any subject and class, **hidden items included**, each chapter marked Syllabus / Board / Challenge / Added by you, each topic showing whether a lesson exists. Add, rename, **hide and show again** chapters and topics, **undo the last edit**, see the edit log. Per topic: open it as a student, see all its lesson versions, **clear** its pictures/summaries/facts or the lesson itself. Per chapter or class: **write all the lessons now**. (A school administrator can use this section and Users and Schools for their own school; nothing else.) |
| Lessons | Every version of every lesson: search, filter by status, subject, class, "flagged by the automatic check". Open one to read it all (what is shown and what is read aloud), see the fact-check findings and the other versions; **approve, reject, back to draft, show this version to students, delete** (its pictures and notes go with it; the newest version takes over). |
| Student topics | Every topic a student typed in, with the student, class and whether a lesson was written; remove unsuitable ones. (The lessons themselves stay private to the student and are never listed with the others.) |
| Write lessons in bulk | Start a background job for a chapter or a whole class (any language, level, board; optionally with pictures, facts, summary and cheat sheet; optionally rewriting what exists). Progress bar, what is being written now, failures, **stop**. Jobs run one at a time behind any waiting student. The list is forgotten on restart; the lessons are kept and a repeated job skips them. |
| Announcements | Send a notice to the 🔔 of everyone, all students, parents or teachers, or one school (up to 5000 people; not emailed; optional link). Disabled accounts are skipped. |
| Analytics and Audit log | The earlier analytics (activity, model use, learning) and audit trail, moved here; the audit log can be filtered by action and searched. |
| System and health | Model and queue state, voice, which of email, push and WhatsApp are set up (a warning if email is not, since sign-up codes then go to the server log), database and voice-cache size, sessions and waiting codes, the **settings in force** (read-only: set with environment variables), **backups** (list, make, download, delete) and **housekeeping** (remove expired sign-ins and codes, empty the voice cache, delete audit entries older than 90 days). |

Also reachable from the console menu: the teachers' review queue, student reports, question bank and textbook library (existing pages that administrators can use).

Verified: 14 automated admin tests (who may get in; every action above, including that a school administrator sees only their school, that hiding and un-hiding a topic restores its position, that deleting a lesson version promotes the newest and removes what was made from it, that backups cannot be read from outside their folder) and, in the browser with the real model, the overview, every page, and a bulk job that wrote a real two-lesson chapter. **Not done / limits:** the console is English only; editing the text of a lesson is still done by teachers in the review pages, not here; settings cannot be changed from the console (they come from the environment); announcements are in-app only; the job list is not kept across restarts; there is no separate admin sign-in or two-step sign-in for administrators.

## Verification run (this machine, Llama 3.1 8B on an RTX 4090, 2026-11-01)

| Check | Result |
|---|---|
| Backend tests (`pytest`, fake model servers) | 97 passed |
| Front-end unit tests (`node --test`) | 6 groups passed; they found and fixed 3 bugs (unary minus precedence, units rewriting inside maths speech, prototype names in the expression evaluator) |
| Lint (`ruff`) | clean |
| Live smoke test against real Llama (`scripts/live_smoke.py`) | 7/7: lesson (12 sections, 65 s), numeric chat, stays on topic, quiz, teach-back, flashcards + cheat-sheet + diagram. Its automatic fact-check flagged the Llama-written lesson for a human to review, as designed. |
| Behaviour evals (`evals/run.py --repeat 2`, 18 cases) | 16/18 (89%): safety 3/3, injection 1/1, concept 2/2, numeric 9/10, scope 1/2. The two near-misses are non-deterministic (1 of 2 runs passed): a sum of an AP, and one off-topic redirect. |
| Browser (in-app Chromium, strict CSP) | sign-up as a child → parent approval → home; 28 student pages and 11 staff/admin pages render with no JavaScript errors; chat + board survive reload; quiz; balancer solves KMnO₄ + HCl; Python runs in the worker; Hindi interface; offline lesson fallback |
| Accessibility (axe-core) | 0 violations on 6 pages × light/dark/high-contrast |
| Docker | image builds and serves (see Docker row) |
| Photo input | worksheet photo read by the local vision model; tutor spotted the wrong answer |
| Semantic search / textbook retrieval | real embedding model; 4 of 5 sample queries good; page-level citations correct |

**Not verified anywhere:** real speakers/microphones/phones, the Claude API, e-mail/push/WhatsApp delivery, GitHub CI, the mobile builds, screen readers, and the correctness of lesson content across the syllabus.

**Totals:** 73 items fully built, 24 built-but-limited or only partly verified, 1 impossible from code alone.
