// The lesson page: streamed sections with voice + word-highlighted transcript, objectives, highlights, feedback, extras.
import { api, get, sse, blob } from './api.js';
import { t } from './i18n.js';
import { md, esc, toSpeakable } from './render.js';
import { speaker, listener, supportsBrowserTTS, splitSentences, pickVoice, listVoices, ttsEngineFor, serverVoice } from './voice.js';
import { $, $$, toast, openModal, download } from './ui.js';
import { state, subjectInfo, speechLang, langInfo, saveLast, saveSettings, refreshProgress } from './state.js';
import { mountChat, leaveChat, ask } from './chat.js';
import { openQuiz, openTeachback, openPractice, openViva, openFlashcards, reportDialog, openCheckWork } from './assess.js';
import { setLeave } from './app.js';
import { prepare as prepareNotes, savedNotes } from './studynotes.js';

const EMOJI = { hook: '🎯', idea: '💡', how: '⚙️', example: '✏️', edge: '🧐', proscons: '⚖️', uses: '🌍', mistakes: '⚠️', tryit: '🔬', exam: '📝', connect: '🔗', recap: '✅' };
export const L = { ctx: null }; // the current lesson, shared with chat.js / assess.js

export const wordsLang = () => state.profile.language;
export const speakText = (s) => toSpeakable(s, state.profile.language);

export function speakOpts(extra = {}) {
  const lang = langInfo(state.profile.language), uri = state.settings.voiceByLang[lang.id] || '';
  return {
    lang: lang.speech, langCode: lang.id, rate: state.settings.rate, voiceURI: uri, engine: ttsEngineFor(lang.id, lang.speech, uri), ...extra,
    onBlocked: () => toast(t('voice.blocked', 'Your browser blocked sound. Tap ▶ to allow it.')),
    onFail: (why, fellBack) => {
      if (fellBack) return toast(t('voice.fellback', 'The server voice is not ready, so I switched to your device voice.'));
      const c = L.ctx; if (c) { c.userStopped = true; markPlaying(-1); setPlayLabel(t('lesson.listen', '▶ Listen to the lesson')); $('#caption').hidden = true; }
      if (why !== 'blocked') toast(t('voice.notworking', 'Voice playback is not working on this device. You can still read everything here.'), 6000);
    },
  };
}
export function warnIfNoVoice() {
  const c = L.ctx; if (!c || c.warnedVoice) return;
  const lang = langInfo(state.profile.language);
  if (supportsBrowserTTS && listVoices().length && !pickVoice(lang.speech, state.settings.voiceByLang[lang.id]) && !serverVoice.tts.includes(lang.id)) {
    c.warnedVoice = true; toast(t('voice.novoice', 'No {lang} voice found on this device — the default voice will be used. A server voice is not available for this language yet.', { lang: lang.name }), 6000);
  }
}
export function caption(text) { const bar = $('#caption'); if (!state.settings.captions || !text) { bar.hidden = true; return; } $('#caption-text').textContent = text; bar.hidden = false; }

export function leaveLesson() {
  const c = L.ctx; if (!c) return;
  c.alive = false; c.abort?.abort(); c.observer?.disconnect(); leaveChat(); speaker.stop(true); listener.abort(); $('#caption').hidden = true; L.ctx = null;
}

/* ============================================================ page ============================================================ */
export async function renderLesson(view, topicId) {
  leaveLesson();
  const topic = await get(`/api/topic/${topicId}`);
  const subj = subjectInfo(topic.subject);
  const params = new URLSearchParams((location.hash.split('?')[1] || ''));
  const ctx = L.ctx = { alive: true, topic, subj, sections: [], filled: 0, done: false, playingIdx: -1, chain: false, waiting: -1, userStopped: false, highlights: [], resumeAt: 0, mode: 'full', pendingQuestion: params.get('q') };
  setLeave(leaveLesson);
  saveLast(topic); document.title = `${topic.title} – AIVidya`;
  const showMath = ['maths', 'physics', 'chemistry'].includes(topic.subject);
  view.style.setProperty('--accent', subj.color);
  view.innerHTML = `
    <div class="crumbs"><a href="#/">${t('nav.home', 'Home')}</a> › ${topic.custom ? `<a href="#/mytopics">${t('mt.heading', 'My topics')}</a>` : `<a href="#/subject/${topic.subject}/${topic.grade}">${esc(topic.subject_name)} · ${t('common.grade', 'Grade')} ${topic.grade}</a> › ${esc(topic.chapter)}`}</div>
    <div class="mobile-tabs"><button class="btn" data-m="lesson" aria-pressed="true">📖 ${t('lesson.tab', 'Lesson')}</button><button class="btn" data-m="ask" aria-pressed="false">💬 ${t('chat.tab', 'Ask AIVidya')}</button></div>
    <div class="lesson-layout" data-mobile="lesson" style="--accent:${subj.color}">
      <div class="lesson-col">
        <div class="lesson-head"><div class="row"><span class="chip subj" style="border-left:6px solid ${subj.color}">${subj.icon} ${esc(topic.subject_name)} · ${t('common.grade', 'Grade')} ${topic.grade}</span>
          <span id="ver" class="chip ai" title="${t('lesson.ai', 'Written by AI. Always check with your teacher or textbook.')}">🤖 ${t('lesson.aibadge', 'AI-written')}</span><span class="spacer"></span>
          <button class="icon-btn small" id="bookmark" aria-pressed="${topic.bookmarked}" aria-label="${t('lesson.bookmark', 'Bookmark')}" title="${t('lesson.bookmark', 'Bookmark')}">${topic.bookmarked ? '⭐' : '☆'}</button>
          <button class="icon-btn small" id="report" aria-label="${t('lesson.report', 'Report a mistake')}" title="${t('lesson.report', 'Report a mistake')}">⚑</button></div>
          <h1>${esc(topic.title)}</h1><p class="muted">${topic.custom ? `💡 ${t('mt.yours', 'A topic you added. Only you can see this lesson.')}` : `${t('lesson.chapter', 'Chapter')}: ${esc(topic.chapter)}`}</p>
          <div id="flagged" class="banner warn" hidden>⚠️ ${t('lesson.flagged', 'An automatic check found something that may be wrong in this lesson. A teacher will review it — double-check key facts.')}</div>
          <div id="prereq"></div><details id="objectives" class="objectives" hidden></details><div id="media"></div></div>
        <div class="modes" role="group" aria-label="${t('lesson.mode', 'Lesson length')}">
          <button class="chip mode" data-mode="full" aria-pressed="true">${t('mode.full', 'Full lesson')}</button><button class="chip mode" data-mode="quick" aria-pressed="false">⚡ ${t('mode.quick', 'Quick (5 min)')}</button><button class="chip mode" data-mode="cheat" aria-pressed="false">📄 ${t('mode.cheat', 'Cheat sheet')}</button></div>
        <div class="notes-bar row"><button class="btn" id="notes-btn" disabled title="${t('notes.wait', 'Available when the lesson has been written')}">📝 ${t('notes.prepare', 'Prepare notes')}</button><span class="muted small" id="notes-hint">${t('notes.hint', 'Short bullet points with diagrams, saved for you to download.')}</span></div>
        <div class="player card" role="group" aria-label="${t('lesson.audio', 'Lesson audio controls')}">
          <button class="btn primary" id="play">${t('lesson.listen', '▶ Listen to the lesson')}</button>
          <button class="icon-btn small" id="prev-sec" aria-label="${t('lesson.prev', 'Previous section')}" title="${t('lesson.prev', 'Previous section')}">⏮</button>
          <button class="icon-btn small" id="next-sec" aria-label="${t('lesson.next', 'Next section')}" title="${t('lesson.next', 'Next section')}">⏭</button>
          <label class="small">${t('lesson.speed', 'Speed')} <select id="rate" aria-label="${t('lesson.speed', 'Speed')}">${[0.75, 1, 1.25, 1.5].map((r) => `<option value="${r}" ${r === state.settings.rate ? 'selected' : ''}>${r}×</option>`).join('')}</select></label>
          <label class="small"><input type="checkbox" id="autoplay" ${state.settings.autoplay && !state.prefs.dataSaver ? 'checked' : ''}> ${t('lesson.autoplay', 'Auto-play')}</label>
          <label class="small"><input type="checkbox" id="captions" ${state.settings.captions ? 'checked' : ''}> ${t('lesson.captions', 'Captions')}</label>
          <span class="spacer"></span><span id="lesson-status" class="muted small" role="status">${t('lesson.preparing', 'Preparing your lesson…')}</span><button class="btn sm danger" id="stop-gen" hidden>⏹ ${t('common.stop', 'Stop')}</button>
        </div>
        <div id="lesson-error"></div>
        <div class="sections" id="sections"></div><div class="sections" id="quick" hidden></div><div id="cheat" class="card prose" hidden></div>
        <aside id="dyk" class="card dyk" hidden aria-labelledby="dyk-h"></aside>
        <div class="card lesson-extras" id="extras" hidden>
          <h2 class="small-title">${t('lesson.practice', 'Practise & check yourself')}</h2>
          <div class="row"><button class="btn primary" id="quiz-btn">📝 ${t('lesson.quiz', 'Quiz me')}</button><button class="btn" id="practice-btn">🧮 ${t('lesson.practiceBtn', 'Practice problem')}</button>
            <button class="btn" id="teach-btn">🗣️ ${t('lesson.teach', 'Teach it back')}</button><button class="btn" id="viva-btn">🎤 ${t('lesson.viva', 'Oral viva')}</button>
            ${showMath ? `<button class="btn" id="work-btn">✅ ${t('lesson.work', 'Check my working')}</button>` : ''}<button class="btn" id="cards-btn">🃏 ${t('lesson.cards', 'Flashcards')}</button>
            ${topic.custom ? '' : `<a class="btn" id="test-btn" href="#/tests/new/${topic.id}">⏱️ ${t('lesson.test', 'Test me')}</a>`}</div>
          <h2 class="small-title">${t('lesson.more', 'More ways to learn this')}</h2>
          <div class="row"><button class="btn" id="diagram-btn">🖼️ ${t('lesson.diagram', 'Draw a diagram')}</button><button class="btn" id="exam-btn">🎯 ${t('lesson.examfocus', 'Exam focus')}</button>
            <button class="btn" id="audio-btn">⬇️ ${t('lesson.audiodl', 'Download audio')}</button><button class="btn" id="note-btn">📓 ${t('lesson.note', 'Add a note')}</button><a class="btn" href="#/tools">🧰 ${t('nav.tools', 'Tools & simulations')}</a></div>
          <div id="extra-out"></div><div id="sim-slot"></div>
        </div>
        <div class="lesson-actions card" id="actions" hidden><button class="btn primary" id="done-btn">✅ ${t('lesson.done', 'I understood this')}</button><span class="spacer"></span>
          ${topic.prev ? `<a class="btn" href="#/learn/${topic.prev.id}">← ${esc(topic.prev.title)}</a>` : ''}${topic.next ? `<a class="btn" href="#/learn/${topic.next.id}">${t('lesson.nexttopic', 'Next')}: ${esc(topic.next.title)} →</a>` : ''}</div>
      </div>
      <aside class="side card" id="side" aria-label="${t('chat.tab', 'Ask AIVidya')}"></aside>
    </div><div class="sel-bar" id="selbar" hidden role="toolbar" aria-label="Selection"><button data-a="hl">🖍 ${t('hl.highlight', 'Highlight')}</button><button data-a="note">📓 ${t('hl.note', 'Save to notes')}</button><button data-a="ask">💬 ${t('hl.ask', 'Ask about this')}</button></div>`;
  wire(view);
  mountChat($('#side', view), ctx);
  renderPrereq(topic); renderObjectives(topic); renderMedia(topic);
  loadLesson();
}

function renderPrereq(topic) {
  const weak = topic.prerequisites.filter((p) => p.subtopics && p.subtopics.every((id) => (state.progress[id]?.retention ?? state.progress[id]?.mastery ?? 0) < 0.55)).slice(0, 2);
  if (weak.length) $('#prereq').innerHTML = `<div class="banner info">💡 ${t('lesson.prereq', 'This builds on')} ${weak.map((p) => `<a href="#/learn/${p.id}">${esc(p.title)}${p.grade ? ` (${t('common.grade', 'Grade')} ${p.grade})` : ''}</a>`).join(', ')}. ${t('lesson.prereq2', 'A quick refresher first will make this easier.')}</div>`;
}
async function renderObjectives(topic) {
  const el = $('#objectives'); let o = topic.objectives;
  const fill = (d) => { el.innerHTML = `<summary>🎯 ${t('lesson.objectives', 'What you will learn')}</summary><ul>${d.objectives.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>${d.key_terms?.length ? `<p class="small"><b>${t('lesson.terms', 'Key terms')}:</b> ${d.key_terms.map(esc).join(' · ')}</p>` : ''}`; el.hidden = false; };
  if (o) return fill(o);
  try { fill(await get(`/api/topic/${topic.id}/objectives`)); } catch { /* optional */ }
}
function renderMedia(topic) {
  if (!topic.media?.length) return;
  $('#media').innerHTML = `<div class="media-list">${topic.media.map((m) => {
    const yt = /^https:\/\/(?:www\.)?(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]{11})/.exec(m.url);
    return yt && !state.prefs.dataSaver ? `<figure><iframe src="https://www.youtube-nocookie.com/embed/${yt[1]}" title="${esc(m.title || 'Video')}" loading="lazy" allowfullscreen referrerpolicy="no-referrer"></iframe><figcaption>${esc(m.title || '')}</figcaption></figure>`
      : `<a class="chip" href="${esc(m.url)}" target="_blank" rel="noopener noreferrer">${m.kind === 'video' ? '🎬' : '🔗'} ${esc(m.title || m.url)}</a>`;
  }).join('')}</div>`;
}

function wire(view) {
  const c = L.ctx;
  $$('.mobile-tabs [data-m]', view).forEach((b) => (b.onclick = () => { $('.lesson-layout', view).dataset.mobile = b.dataset.m; $$('.mobile-tabs [data-m]', view).forEach((x) => x.setAttribute('aria-pressed', x === b)); if (b.dataset.m === 'ask') requestAnimationFrame(() => { dispatchEvent(new Event('resize')); $('.side', view).scrollIntoView({ block: 'start' }); }); }));
  $('#play', view).onclick = onPlayClick; $('#prev-sec', view).onclick = () => jump(-1); $('#next-sec', view).onclick = () => jump(1);
  $('#rate', view).onchange = (e) => { state.settings.rate = +e.target.value; saveSettings(); };
  $('#autoplay', view).onchange = (e) => { state.settings.autoplay = e.target.checked; saveSettings(); };
  $('#captions', view).onchange = (e) => { state.settings.captions = e.target.checked; saveSettings(); if (!e.target.checked) $('#caption').hidden = true; };
  $('#stop-gen', view).onclick = () => { c.abort?.abort(); $('#stop-gen').hidden = true; $('#lesson-status').textContent = t('lesson.stopped', 'Stopped. Reload to continue writing.'); };
  $('#caption-stop').onclick = () => { c.userStopped = true; speaker.stop(); };
  $('#sections', view).addEventListener('click', onSectionClick); $('#quick', view).addEventListener('click', onSectionClick);
  $$('.mode', view).forEach((b) => (b.onclick = () => setMode(b.dataset.mode)));
  $('#bookmark', view).onclick = async (e) => { const r = await api('/api/bookmarks/toggle', { subtopic_id: c.topic.id }); e.currentTarget.textContent = r.bookmarked ? '⭐' : '☆'; e.currentTarget.setAttribute('aria-pressed', r.bookmarked); refreshProgress(); };
  $('#report', view).onclick = () => reportDialog('lesson', c.topic.id, '');
  $('#notes-btn', view).onclick = () => prepareNotes(c.topic, false, markNotes);
  $('#quiz-btn', view).onclick = () => openQuiz(c); $('#practice-btn', view).onclick = () => openPractice(c); $('#teach-btn', view).onclick = () => openTeachback(c);
  $('#viva-btn', view).onclick = () => openViva(c); $('#cards-btn', view).onclick = () => openFlashcards(c); $('#work-btn', view)?.addEventListener('click', () => openCheckWork(c));
  $('#done-btn', view).onclick = markDone;
  $('#diagram-btn', view).onclick = () => extra('diagram'); $('#exam-btn', view).onclick = () => extra('exam'); $('#audio-btn', view).onclick = downloadAudio;
  $('#note-btn', view).onclick = () => noteDialog('');
  document.addEventListener('selectionchange', onSelection);
  c.cleanupSel = () => document.removeEventListener('selectionchange', onSelection);
  $('#selbar', view).onmousedown = (e) => e.preventDefault();
  $('#selbar', view).onclick = onSelAction;
}

/* ============================================================ streaming ============================================================ */
async function loadLesson() {
  const my = L.ctx; my.abort = new AbortController();
  $('#lesson-error').innerHTML = ''; $('#stop-gen').hidden = false;
  const collected = [];
  try {
    const stream = navigator.onLine === false ? offlineEvents(my.topic.id) : openLesson(my.topic.id, my.abort.signal);
    for await (const ev of withOfflineFallback(stream, my.topic.id)) {
      if (!my.alive) return;
      if (ev.type === 'section' || ev.type === 'version') collected.push(ev);
      if (ev.type === 'resume') my.resumeAt = ev.section || 0;
      else if (ev.type === 'queue') $('#lesson-status').textContent = ev.ahead > 0 ? t('queue.wait', 'Waiting in line — {n} ahead of you…', { n: ev.ahead }) : t('lesson.preparing', 'Preparing your lesson…');
      else if (ev.type === 'section_start') ensureCard(ev.index, ev.kind, ev.title);
      else if (ev.type === 'section') fillSection(ev);
      else if (ev.type === 'status') $('#lesson-status').textContent = ev.message;
      else if (ev.type === 'version') showVersion(ev);
      else if (ev.type === 'done') { my.done = true; $('#lesson-status').textContent = ev.offline ? t('lesson.offline', 'Offline copy ✓') : ev.cached ? t('lesson.ready', 'Ready ✓') : t('lesson.saved', 'Lesson ready ✓'); if (!ev.offline && !ev.local) saveOffline(my.topic.id, collected); onLessonComplete(); }
      else if (ev.type === 'error') throw new Error(ev.message);
    }
    if (my.alive && !my.done && my.sections.length === 0) throw new Error(t('lesson.ended', 'The lesson stream ended unexpectedly.'));
  } catch (err) {
    if (!my.alive || err.name === 'AbortError') return;
    showLessonError(err.message);
  } finally { if (my.alive) { $('#stop-gen').hidden = true; $('#extras').hidden = $('#actions').hidden = my.sections.length === 0; } }
}

// ---- offline copies of lessons you have opened (Cache API; newest 40 are kept) ----------------------------------------------
const OFFLINE = 'vidya-lessons-v1', KEEP_LESSONS = 150;
async function saveOffline(id, events) {
  try {
    if (!events.some((e) => e.type === 'section') || !('caches' in window)) return;
    const c = await caches.open(OFFLINE); await c.put(`/offline/lesson/${id}`, new Response(JSON.stringify({ at: Date.now(), events }), { headers: { 'Content-Type': 'application/json' } }));
    const keys = await c.keys(); if (keys.length > KEEP_LESSONS) await c.delete(keys[0]);
  } catch { /* storage full or blocked: the saved copy is a bonus */ }
}
async function readOffline(id) {
  try { const hit = 'caches' in window ? await (await caches.open(OFFLINE)).match(`/offline/lesson/${id}`) : null; return hit ? await hit.json() : null; } catch { return null; }
}
async function* offlineEvents(id) {
  const copy = await readOffline(id);
  if (!copy) throw new Error(t('lesson.nooffline', 'You are offline and this lesson was not opened before.'));
  for (const ev of copy.events) yield ev;
  yield { type: 'done', cached: true, offline: true };
}
// A lesson opened before is kept on this device. Opening it again asks the server only "is it still the same version?" (no model, a few milliseconds)
// and shows the saved copy at once; anything new or changed is streamed as usual.
async function* openLesson(id, signal) {
  const copy = await readOffline(id);
  const have = copy?.events.find((e) => e.type === 'version')?.version?.id;
  if (copy && have) {
    let check;
    try { check = await get(`/api/lesson/check?subtopic_id=${encodeURIComponent(id)}`); } catch (err) { if (err.status) throw err; check = null; }
    if (!check) { yield* offlineEvents(id); return; } // the server cannot be reached: the saved copy is the best there is
    if (check.version?.version?.id === have) {
      yield { type: 'resume', section: check.resume || 0 };
      yield check.version; // fresh review status and warning flag
      for (const ev of copy.events) if (ev.type === 'section') yield ev;
      yield { type: 'done', cached: true, local: true };
      return;
    }
    yield* sse('/api/lesson/stream', { subtopic_id: id, tracked: true }, signal);
    return;
  }
  yield* sse('/api/lesson/stream', { subtopic_id: id }, signal);
}
async function* withOfflineFallback(stream, id) { // network died before the first byte: use the saved copy
  let started = false;
  try { for await (const ev of stream) { started = true; yield ev; } } catch (err) { if (started || err.name === 'AbortError' || err.status) throw err; yield* offlineEvents(id); }
}

function showVersion(ev) {
  const v = ev.version, el = $('#ver'); if (!v) return;
  const approved = v.status === 'approved';
  el.className = `chip ${approved ? 'ok' : 'ai'}`;
  el.textContent = approved ? `✅ ${t('lesson.reviewed', 'Reviewed by')} ${v.reviewer || t('role.teacher', 'Teacher')}` : v.source === 'teacher' ? `✏️ ${t('lesson.teachermade', 'Edited by a teacher')}` : `🤖 ${t('lesson.aibadge', 'AI-written')}`;
  el.title = `${t('lesson.version', 'Version')} ${v.version} · ${v.model || ''}`;
  $('#flagged').hidden = !ev.flagged;
  L.ctx.sources = ev.sources || [];
}

function showLessonError(message) {
  $('#lesson-status').textContent = ''; $$('.section.pending').forEach((el) => el.remove());
  $('#lesson-error').innerHTML = `<div class="banner" role="alert"><b>${t('lesson.failed', "Couldn't load the lesson.")}</b> ${esc(message)}<div style="margin-top:8px"><button class="btn sm" id="retry">↻ ${t('common.retry', 'Try again')}</button></div></div>`;
  $('#retry').onclick = () => { const c = L.ctx; c.sections = []; c.filled = 0; $('#sections').innerHTML = ''; $('#lesson-status').textContent = t('lesson.preparing', 'Preparing your lesson…'); loadLesson(); };
}

function ensureCard(i, kind, title) {
  let el = document.getElementById(`sec-${i}`); if (el) return el;
  el = document.createElement('article'); el.className = 'card section pending'; el.id = `sec-${i}`; el.dataset.i = i; el.dataset.kind = kind;
  el.innerHTML = `<div class="section-head"><span class="section-emoji" aria-hidden="true">${EMOJI[kind] || '📘'}</span><h2>${esc(title)}</h2></div><div class="skeleton" style="width:90%"></div><div class="skeleton" style="width:75%"></div>`;
  $('#sections').append(el); $('#lesson-status').textContent = t('lesson.writing', 'AIVidya is writing: {title}…', { title });
  return el;
}

function fillSection(s) {
  const c = L.ctx, i = c.filled++;
  c.sections[i] = { ...s, speak: speakText(s.speech) };
  const el = ensureCard(i, s.kind, s.title); el.dataset.kind = s.kind; el.classList.remove('pending');
  const sentences = splitSentences(c.sections[i].speak);
  el.innerHTML = `
    <div class="section-head"><span class="section-emoji" aria-hidden="true">${EMOJI[s.kind] || '📘'}</span><h2>${esc(s.title)}</h2>
      <div class="section-tools"><button class="icon-btn small" data-act="listen" aria-label="${t('lesson.listenpart', 'Listen to this part')}" title="${t('lesson.listenpart', 'Listen to this part')}">🔊</button>
        <button class="icon-btn small" data-act="explain" aria-label="${t('lesson.explain', 'Explain this differently')}" title="${t('lesson.explain', 'Explain this differently')}">💬</button>
        <button class="icon-btn small" data-act="rewrite" aria-label="${t('lesson.rewrite', 'Rewrite this part another way')}" title="${t('lesson.rewrite', 'Rewrite this part another way')}">🔄</button></div></div>
    <div class="prose">${md(s.display)}</div>
    <details class="transcript"><summary>📜 ${t('lesson.transcript', 'Transcript — what AIVidya says')}</summary><p>${sentences.map((tx, k) => `<span class="s" data-k="${k}">${tx.split(/(\s+)/).map((w) => (w.trim() ? `<span class="w">${esc(w)}</span>` : w)).join('')} </span>`).join('')}</p></details>
    <div class="fb" role="group" aria-label="${t('fb.label', 'Was this part helpful?')}"><span class="muted small">${t('fb.label', 'Was this part helpful?')}</span>
      <button class="chip tiny" data-fb="1">👍</button><button class="chip tiny" data-fb="-1" data-tag="confusing">😕 ${t('fb.confusing', 'Confusing')}</button><button class="chip tiny" data-fb="-1" data-tag="too_hard">${t('fb.hard', 'Too hard')}</button><button class="chip tiny" data-fb="-1" data-tag="too_easy">${t('fb.easy', 'Too easy')}</button><button class="chip tiny" data-fb="-1" data-tag="wrong">⚠️ ${t('fb.wrong', 'Wrong')}</button></div>`;
  applyHighlights(el, i); observe(el);
  if (i === 0) {
    $('#extras').hidden = $('#actions').hidden = false;
    if (c.resumeAt > 0) toast(t('lesson.resume', 'Welcome back — continuing from part {n}.', { n: c.resumeAt + 1 }), 4000);
    else if ((speaker.supported) && state.settings.autoplay && !state.prefs.dataSaver && !c.userStopped && !c.pendingQuestion) { warnIfNoVoice(); playSection(0, true); }
  }
  if (c.resumeAt > 0 && i === c.resumeAt) setTimeout(() => el.scrollIntoView({ block: 'start', behavior: 'smooth' }), 150);
  if (c.waiting === i) { c.waiting = -1; playSection(i, true); }
}

function markNotes(n) { // the button shows whether notes are already saved
  const b = $('#notes-btn'); if (!b) return;
  b.textContent = n ? `📝 ${t('notes.open', 'My notes')}` : `📝 ${t('notes.prepare', 'Prepare notes')}`;
  $('#notes-hint').textContent = n ? t('notes.saved', 'Saved. Open them to read, download or print.') : t('notes.hint', 'Short bullet points with diagrams, saved for you to download.');
}

function onLessonComplete() {
  const c = L.ctx; renderSims(c.topic);
  $('#notes-btn').disabled = false; $('#notes-btn').title = ''; savedNotes(c.topic.id).then(markNotes).catch(() => {});
  if (c.mode === 'quick') loadQuick();
  loadFigures('full'); loadDidYouKnow();
  if (c.pendingQuestion) { const q = c.pendingQuestion; c.pendingQuestion = null; setTimeout(() => ask(q), 400); }
  if ((c.sources || []).length) $('#lesson-status').textContent += ` · 📚 ${c.sources.map((s) => `${s.title} p.${s.page}`).join(', ')}`;
}

function observe(el) { // remember how far the student got (for "resume")
  const c = L.ctx; if (!('IntersectionObserver' in window)) return;
  c.observer ||= new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting && e.intersectionRatio > 0.5) { const i = +e.target.dataset.i; if (i > (c.lastPos ?? -1)) { c.lastPos = i; clearTimeout(c.posT); c.posT = setTimeout(() => api('/api/lesson/position', { subtopic_id: c.topic.id, section: i }).catch(() => {}), 1500); } }
  }, { threshold: [0.5] });
  c.observer.observe(el);
}

/* ============================================================ modes ============================================================ */
async function setMode(mode) {
  const c = L.ctx; c.mode = mode; speaker.stop(); c.playingIdx = -1; setPlayLabel(t('lesson.listen', '▶ Listen to the lesson'));
  $$('.mode').forEach((b) => b.setAttribute('aria-pressed', b.dataset.mode === mode));
  $('#sections').hidden = mode !== 'full'; $('#quick').hidden = mode !== 'quick'; $('#cheat').hidden = mode !== 'cheat'; $('#dyk').hidden = mode === 'cheat' || !c.dyk;
  if (mode === 'quick') loadQuick();
  if (mode === 'cheat' && !$('#cheat').dataset.loaded) {
    $('#cheat').innerHTML = `<p class="muted">${t('lesson.cheatwait', 'Writing your one-page cheat sheet…')}</p>`;
    try { const r = await api('/api/lesson/cheatsheet', { subtopic_id: c.topic.id }); $('#cheat').innerHTML = `<div class="row"><h2 style="margin:0">📄 ${esc(c.topic.title)}</h2><span class="spacer"></span><button class="btn sm" id="cheat-note">📓 ${t('hl.note', 'Save to notes')}</button><button class="btn sm" onclick="window.print()">🖨️ ${t('common.print', 'Print')}</button></div>${md(r.markdown)}`; $('#cheat').dataset.loaded = '1'; $('#cheat-note').onclick = async () => { await api('/api/notes', { subtopic_id: c.topic.id, title: `${c.topic.title} — cheat sheet`, body: r.markdown }); toast(t('note.saved', 'Saved to your notes')); }; }
    catch (er) { $('#cheat').innerHTML = `<div class="banner" role="alert">${esc(er.message)}<div style="margin-top:8px"><button class="btn sm" id="cheat-retry">↻ ${t('common.retry', 'Try again')}</button></div></div>`; $('#cheat-retry').onclick = () => { $('#cheat').dataset.loaded = ''; setMode('cheat'); }; }
  }
}

// ---- the 5-minute summary: a few short parts, written from the finished lesson, with their own audio -------------------------
async function loadQuick() {
  const c = L.ctx, box = $('#quick'); if (c.quick || c.quickBusy) return;
  if (!c.done) { box.innerHTML = `<div class="card"><p class="muted">⏳ ${t('quick.wait', 'The summary is made from the full lesson. It will appear as soon as the lesson has been written.')}</p></div>`; return; }
  c.quickBusy = true; box.innerHTML = `<div class="card"><p class="muted">⚡ ${t('quick.writing', 'Writing your 5-minute summary…')}</p><div class="skeleton" style="width:90%"></div><div class="skeleton" style="width:70%"></div></div>`;
  try {
    const r = await api('/api/lesson/quick', { subtopic_id: c.topic.id });
    if (!c.alive) return;
    c.quick = r.sections.map((p) => ({ ...p, kind: 'quick', speak: speakText(p.speech) }));
    box.innerHTML = c.quick.map((p, i) => `<article class="card section" id="qsec-${i}" data-i="${i}" data-kind="quick"><div class="section-head"><span class="section-emoji" aria-hidden="true">${['💡', '⚙️', '✏️', '⚠️', '✅', '📌'][i] || '📘'}</span><h2>${esc(p.title)}</h2>
      <div class="section-tools"><button class="icon-btn small" data-act="listen" aria-label="${t('lesson.listenpart', 'Listen to this part')}" title="${t('lesson.listenpart', 'Listen to this part')}">🔊</button></div></div>
      <div class="prose">${md(p.display)}</div>
      <details class="transcript"><summary>📜 ${t('lesson.transcript', 'Transcript — what AIVidya says')}</summary><p>${splitSentences(p.speak).map((tx, k) => `<span class="s" data-k="${k}">${tx.split(/(\s+)/).map((w) => (w.trim() ? `<span class="w">${esc(w)}</span>` : w)).join('')} </span>`).join('')}</p></details></article>`).join('');
    if (c.mode === 'quick' && state.settings.autoplay && !state.prefs.dataSaver && speaker.supported && !c.userStopped) playSection(0, true);
    loadFigures('quick');
  } catch (er) {
    box.innerHTML = `<div class="banner" role="alert"><b>${t('quick.failed', "Couldn't write the summary.")}</b> ${esc(er.message)}<div style="margin-top:8px"><button class="btn sm" id="quick-retry">↻ ${t('common.retry', 'Try again')}</button></div></div>`;
    $('#quick-retry').onclick = () => { c.quickBusy = false; loadQuick(); };
  } finally { c.quickBusy = false; }
}

// ---- "Did you know?": three curiosity-sparking facts, each hidden behind a teaser until the student taps it ------------------------------
async function loadDidYouKnow() {
  const c = L.ctx; if (!c || c.dykStarted || navigator.onLine === false) return; c.dykStarted = true;
  try {
    const r = await api('/api/lesson/didyouknow', { subtopic_id: c.topic.id });
    if (!c.alive || !r.facts?.length) return;
    c.dyk = r.facts; const box = $('#dyk');
    box.innerHTML = `<h2 id="dyk-h" class="small-title">💡 ${t('dyk.title', 'Did you know?')}</h2>
      ${r.facts.map((f) => `<details class="dyk-item"><summary><span aria-hidden="true">${esc(f.emoji)}</span> ${esc(f.teaser)} <span class="dyk-tap muted small">${t('dyk.tap', 'Tap to find out')}</span></summary><p>${esc(f.fact)}</p></details>`).join('')}
      <p class="muted small">🤖 ${t('dyk.note', 'Written by AI. Surprising facts are worth checking in your textbook or with your teacher.')}</p>`;
    box.hidden = c.mode === 'cheat';
  } catch { c.dykStarted = false; /* a bonus: try again next time the lesson opens */ }
}

// ---- pictures: a concept diagram for every part of the lesson, made once by the model and kept ---------------------------------
const FIG_MAX_WAIT = 6;
async function loadFigures(mode = 'full') {
  const c = L.ctx; if (!c || navigator.onLine === false) return;
  c.figures ||= {}; if (c.figures[mode]) return; c.figures[mode] = true;
  const parts = mode === 'quick' ? c.quick || [] : c.sections, pre = mode === 'quick' ? 'qsec-' : 'sec-';
  const kinds = state.meta.picture_kinds || [];
  let have = {}; try { have = (await api('/api/lesson/figures', { subtopic_id: c.topic.id, mode })).figures || {}; } catch { /* draw them one by one below */ }
  const show = (slot, f) => { slot.className = 'lesson-figure'; slot.innerHTML = `<img alt="${esc(t('lesson.diagram.alt', 'Diagram of'))} ${esc(f.caption)}" src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(f.svg)}"><figcaption class="muted small">🤖 ${t('lesson.diagram.made', 'Made by AI from this part of the lesson — check it against your textbook.')}</figcaption>`; };
  const draw = async (slot, i) => {
    slot.className = 'lesson-figure pending'; slot.innerHTML = `<p class="muted small">🎨 ${t('fig.drawing', 'Drawing a picture for this part…')}</p>`;
    try {
      let r = await api('/api/lesson/figure', { subtopic_id: c.topic.id, section: i, mode });
      for (let tries = 0; r.figure?.retry && tries < FIG_MAX_WAIT && c.alive; tries++) { // the model was needed for something you asked: try again in a moment
        await new Promise((ok) => setTimeout(ok, 12000)); r = await api('/api/lesson/figure', { subtopic_id: c.topic.id, section: i, mode });
      }
      if (!c.alive) return;
      if (r.figure?.svg) return show(slot, r.figure);
      if (!r.figure) return slot.remove(); // this part has nothing to draw
    } catch { /* fall through to the retry button */ }
    if (!c.alive) return;
    slot.className = 'lesson-figure failed';
    slot.innerHTML = `<p class="muted small">🖼️ ${t('fig.failed', "Couldn't draw the picture for this part.")} <button class="btn sm" type="button">↻ ${t('common.retry', 'Try again')}</button></p>`;
    $('button', slot).onclick = () => draw(slot, i);
  };
  for (const [i, s] of parts.entries()) {
    if (!c.alive) return; if (!s || (mode === 'full' && !kinds.includes(s.kind))) continue;
    const el = document.getElementById(`${pre}${i}`); if (!el || el.querySelector('figure')) continue;
    const slot = document.createElement('figure'); $('.prose', el).after(slot);
    if (have[i]?.svg) { show(slot, have[i]); continue; }
    await draw(slot, i);
  }
}

/* ============================================================ audio ============================================================ */
const setPlayLabel = (text) => { const b = $('#play'); if (b) b.textContent = text; };
const list = () => (L.ctx.mode === 'quick' ? L.ctx.quick || [] : L.ctx.sections);
const pre = () => (L.ctx.mode === 'quick' ? 'qsec-' : 'sec-');
function markPlaying(i) {
  $$('.section.playing').forEach((e) => e.classList.remove('playing')); $$('.transcript .s.on, .transcript .w.on').forEach((e) => e.classList.remove('on'));
  L.ctx.playingIdx = i;
  if (i >= 0) { const el = document.getElementById(`${pre()}${i}`); el?.classList.add('playing'); if (!state.prefs.dataSaver) el?.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
}
export function playSection(i, chain) {
  const c = L.ctx; if (!c) return;
  if (!speaker.supported) { toast(t('voice.none', 'This device has no voice. Install the server voice (see the README) or use a browser with speech support. You can read everything here.'), 6000); return; }
  const sec = list()[i];
  if (!sec) { if (!c.done && c.mode === 'full') { c.waiting = i; setPlayLabel(t('lesson.waiting', '⏳ Waiting for AIVidya…')); } return; }
  c.chain = chain; c.userStopped = false; c.waiting = -1; c.startedAt = performance.now(); listener.abort();
  markPlaying(i); setPlayLabel(t('lesson.pause', '⏸ Pause'));
  speaker.begin(speakOpts({
    onSentence: (text, k) => { caption(text); $$('.transcript .s.on').forEach((e) => e.classList.remove('on')); $(`#${pre()}${i} .transcript .s[data-k="${k}"]`)?.classList.add('on'); },
    onWord: (w, k) => { $$('.transcript .w.on').forEach((e) => e.classList.remove('on')); $$(`#${pre()}${i} .transcript .s[data-k="${k}"] .w`)[w]?.classList.add('on'); },
    onIdle: () => {
      if (L.ctx !== c) return; $('#caption').hidden = true;
      if (chain && i + 1 < list().length) setTimeout(() => L.ctx === c && !c.userStopped && playSection(i + 1, true), 350);
      else if (chain && !c.done && c.mode === 'full') { c.waiting = i + 1; setPlayLabel(t('lesson.waiting', '⏳ Waiting for AIVidya…')); }
      else { markPlaying(-1); setPlayLabel(chain ? t('lesson.again', '↺ Listen again') : t('lesson.listen', '▶ Listen to the lesson')); if (chain) toast(t('lesson.finished', 'Lesson finished! Try the quiz to lock it in 🔒'), 5000); }
    },
    onStop: () => { if (L.ctx === c) { markPlaying(-1); setPlayLabel(t('lesson.listen', '▶ Listen to the lesson')); $('#caption').hidden = true; } },
  }));
  speaker.push(sec.speak); speaker.end();
}
function onPlayClick() {
  const c = L.ctx; if (!list().length) { toast(t('lesson.notyet', 'The lesson is still being written. It will play as soon as the first part is ready.'), 4000); return; }
  if (speaker.paused) { speaker.resume(); setPlayLabel(t('lesson.pause', '⏸ Pause')); return; }
  if (speaker.speaking && c.playingIdx >= 0) { speaker.pause(); setPlayLabel(t('lesson.resume', '▶ Resume')); return; }
  warnIfNoVoice(); playSection(c.playingIdx >= 0 ? c.playingIdx : (c.mode === 'full' ? Math.max(0, c.resumeAt) : 0), true);
}
function jump(delta) { // ⏮ restarts the part you are in (or goes to the one before if it just began); ⏭ goes to the next part
  const c = L.ctx, n = list().length;
  if (!n) { toast(t('lesson.notyet', 'The lesson is still being written. It will play as soon as the first part is ready.'), 4000); return; }
  const at = c.playingIdx;
  if (delta < 0 && at >= 0 && performance.now() - (c.startedAt || 0) > 4000) return playSection(at, true);
  if (delta > 0 && at >= n - 1) { toast(t('lesson.last', 'That is the last part.'), 2500); return; }
  const to = at < 0 ? (delta > 0 ? 0 : 0) : Math.max(0, Math.min(n - 1, at + delta));
  playSection(to, true);
}

async function onSectionClick(e) {
  const c = L.ctx;
  const fb = e.target.closest('[data-fb]');
  if (fb) { const i = +fb.closest('.section').dataset.i; await api('/api/lesson/feedback', { subtopic_id: c.topic.id, section: i, rating: +fb.dataset.fb, tag: fb.dataset.tag || (+fb.dataset.fb > 0 ? 'great' : '') }); fb.closest('.fb').innerHTML = `<span class="muted small">${t('fb.thanks', 'Thanks — this helps teachers improve the lesson.')}</span>`; return; }
  const btn = e.target.closest('[data-act]'); if (!btn) return;
  const i = +btn.closest('.section').dataset.i, sec = list()[i];
  if (btn.dataset.act === 'listen') { warnIfNoVoice(); (speaker.speaking && c.playingIdx === i) ? speaker.stop() : playSection(i, false); }
  if (btn.dataset.act === 'explain') { $('.lesson-layout').dataset.mobile = 'ask'; $$('.mobile-tabs [data-m]').forEach((x) => x.setAttribute('aria-pressed', x.dataset.m === 'ask')); ask(t('lesson.explainq', 'Please explain the part titled “{title}” again in a different way, with a new analogy.', { title: sec.title })); }
  if (btn.dataset.act === 'rewrite') {
    btn.disabled = true; const prose = $('.prose', btn.closest('.section')); prose.style.opacity = 0.5;
    try {
      const r = await api('/api/lesson/rewrite', { subtopic_id: c.topic.id, section: i, guidance: '' });
      prose.innerHTML = md(r.display) + `<p class="muted small">🔄 ${t('lesson.rewritten', 'Rewritten just for you (not saved to the shared lesson).')}</p>`; sec.speak = speakText(r.speech);
    } catch (er) { toast(er.message); } finally { btn.disabled = false; prose.style.opacity = 1; }
  }
}

/* ============================================================ selection: highlight / note / ask ============================================================ */
let selText = '', selSection = 0;
function onSelection() {
  const bar = $('#selbar'); if (!bar) return;
  const sel = window.getSelection(); const txt = sel?.toString().trim() || '';
  const prose = sel?.anchorNode?.parentElement?.closest('.section .prose');
  if (!txt || txt.length < 3 || txt.length > 400 || !prose) { bar.hidden = true; return; }
  selText = txt; selSection = +prose.closest('.section').dataset.i;
  const r = sel.getRangeAt(0).getBoundingClientRect();
  bar.style.top = `${Math.max(70, r.top - 46)}px`; bar.style.left = `${Math.max(8, Math.min(window.innerWidth - 300, r.left))}px`; bar.hidden = false;
}
async function onSelAction(e) {
  const a = e.target.closest('[data-a]')?.dataset.a; const c = L.ctx; if (!a) return;
  if (a === 'hl') { const r = await api('/api/highlights', { subtopic_id: c.topic.id, section: selSection, text: selText }); applyHighlight(document.getElementById(`sec-${selSection}`), selText, r.id); toast(t('hl.saved', 'Highlighted')); }
  if (a === 'note') { await api('/api/notes', { subtopic_id: c.topic.id, title: c.topic.title, body: `> ${selText}` }); toast(t('note.saved', 'Saved to your notes')); }
  if (a === 'ask') ask(t('hl.askq', 'Can you explain this part more simply: “{text}”', { text: selText }));
  window.getSelection().removeAllRanges(); $('#selbar').hidden = true;
}
async function applyHighlights(el, i) {
  const c = L.ctx; // one request for the whole lesson (it used to be one per section, all sent at once)
  c.hlLoading ||= get(`/api/highlights?subtopic_id=${c.topic.id}`).then((r) => r.items, () => []);
  c.highlights = await c.hlLoading; if (!c.alive) return;
  c.highlights.filter((h) => h.section_index === i).forEach((h) => applyHighlight(el, h.text, h.id));
}
function applyHighlight(sectionEl, text, id) {
  if (!sectionEl) return; const root = $('.prose', sectionEl); if (!root) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const at = n.nodeValue.indexOf(text.slice(0, 60)); if (at < 0 || n.parentElement.closest('mark, .katex')) continue;
    const len = Math.min(text.length, n.nodeValue.length - at); const r = document.createRange(); r.setStart(n, at); r.setEnd(n, at + len);
    const mark = document.createElement('mark'); mark.dataset.id = id; mark.title = t('hl.remove', 'Click to remove highlight');
    mark.onclick = async () => { await api(`/api/highlights/${id}`, undefined, 'DELETE'); mark.replaceWith(...mark.childNodes); };
    try { r.surroundContents(mark); } catch { /* selection crossed elements */ } return;
  }
}

/* ============================================================ extras ============================================================ */
async function extra(kind) {
  const c = L.ctx, out = $('#extra-out'); out.innerHTML = `<p class="muted">${t('common.loading', 'Loading…')}</p>`;
  try {
    if (kind === 'diagram') {
      const what = ''; const r = await api('/api/lesson/diagram', { subtopic_id: c.topic.id, what });
      out.innerHTML = `<div class="card diagram"><img alt="${t('lesson.diagram.alt', 'Diagram of')} ${esc(c.topic.title)}" src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(r.svg)}"><p class="muted small">🤖 ${t('lesson.diagram.ai', 'Drawn by AI — check the labels against your textbook.')}</p></div>`;
    } else {
      const r = await api('/api/lesson/exam-focus', { subtopic_id: c.topic.id });
      out.innerHTML = `<div class="card prose"><h3>🎯 ${esc(state.meta.goals.find((g) => g.id === r.goal)?.label || '')}</h3>${md(r.markdown)}</div>`;
    }
  } catch (er) { out.innerHTML = `<div class="banner">${esc(er.message)}</div>`; }
}
async function downloadAudio() {
  const c = L.ctx; toast(t('lesson.audiowait', 'Preparing the audio — this can take a minute…'), 6000);
  try { const res = await blob(`/api/voice/lesson-audio?subtopic_id=${c.topic.id}`); download(`${c.topic.title}.wav`, await res.blob()); } catch (er) { toast(er.message); }
}
export function noteDialog(prefill) {
  const c = L.ctx; const m = openModal(`<div class="field"><label for="nt">${t('note.title', 'Title')}</label><input id="nt" type="text" value="${esc(c.topic.title)}"></div><div class="field"><label for="nb">${t('note.body', 'Note')}</label><textarea id="nb" autofocus>${esc(prefill)}</textarea></div><div class="row end"><button class="btn primary" id="ns">${t('common.save', 'Save')}</button></div>`, { title: t('lesson.note', 'Add a note') });
  $('#ns', m.el).onclick = async () => { await api('/api/notes', { subtopic_id: c.topic.id, title: $('#nt', m.el).value, body: $('#nb', m.el).value }); m.close(); toast(t('note.saved', 'Saved to your notes')); };
}
async function markDone() {
  const btn = $('#done-btn'); btn.disabled = true;
  try { const r = await api('/api/lesson/complete', { subtopic_id: L.ctx.topic.id }); await refreshProgress(); btn.textContent = `✅ ${t('lesson.marked', 'Marked as understood')}`; toast(t('lesson.done.toast', 'Great! +{xp} XP. I will remind you to revise this soon 🔁', { xp: r.reward.points })); rewardToast(r.reward); }
  catch (e) { btn.disabled = false; toast(e.message); }
}
export function rewardToast(reward) { (reward?.new_badges || []).forEach((b) => toast(`${b.icon} ${t('badge.new', 'New badge')}: ${b.name}`, 5000)); }

/* ============================================================ simulations & code runner (loaded on demand) ============================================================ */
async function renderSims(topic) {
  const mod = await import('./tools.js'); const list = mod.simsFor(topic);
  const slot = $('#sim-slot'); if (!slot || (!list.length && topic.subject !== 'computers')) return;
  slot.innerHTML = `<h2 class="small-title">🧪 ${t('lesson.try', 'Try it yourself')}</h2><div class="row">${list.map((s) => `<button class="btn" data-sim="${s.id}">${s.icon} ${esc(s.title)}</button>`).join('')}${topic.subject === 'computers' ? `<button class="btn" data-sim="__code">💻 ${t('code.open', 'Write and run code')}</button>` : ''}</div><div id="sim-host"></div>`;
  $$('[data-sim]', slot).forEach((b) => (b.onclick = () => (b.dataset.sim === '__code' ? mod.mountCodeRunner($('#sim-host')) : mod.mountSim(b.dataset.sim, $('#sim-host')))));
}
