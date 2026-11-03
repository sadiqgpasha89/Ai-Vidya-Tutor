// Assessments and revision tools opened from a lesson: quiz, practice, teach-back, viva, flashcards, check-my-work, reports.
import { api, get } from './api.js';
import { t } from './i18n.js';
import { md, esc } from './render.js';
import { speaker, listener, sttEngine } from './voice.js';
import { $, $$, openModal, toast, ring } from './ui.js';
import { state, refreshProgress, langInfo } from './state.js';
import { speakOpts, speakText, caption, rewardToast } from './lesson.js';
const rich = (s) => md(String(s ?? '')).replace(/^\s*<p>([\s\S]*)<\/p>\s*$/, '$1'); // marked answers may contain $maths$ and **bold**

const say = (text) => { if (!speaker.supported) return; speaker.begin(speakOpts({ onSentence: caption, onIdle: () => ($('#caption').hidden = true) })); speaker.push(speakText(text)); speaker.end(); };
const wait = (lines = 2) => `<div class="skeleton"></div>${lines > 1 ? '<div class="skeleton" style="width:70%"></div>' : ''}`;

function dictate(btn, target) { // fill a textarea by voice (browser or private recognition)
  if (listener.active) return listener.stop();
  const base = target.value ? `${target.value.trim()} ` : ''; const lang = langInfo(state.profile.language); btn.textContent = `⏹ ${t('common.stop', 'Stop')}`;
  listener.start({ lang: lang.speech, langCode: lang.id, onInterim: (tx) => { target.value = base + tx; }, onFinal: ({ text }) => { target.value = base + text; }, onEnd: () => { btn.textContent = `🎤 ${t('teach.speak', 'Speak instead')}`; }, onError: (er) => { btn.textContent = `🎤 ${t('teach.speak', 'Speak instead')}`; toast(`${t('chat.voiceprob', 'Voice input problem')}: ${er}`); } });
}

/* ============================================================ quiz ============================================================ */
export async function openQuiz(ctx) {
  speaker.stop();
  const m = openModal(`<p class="muted">${t('quiz.preparing', 'AIVidya is preparing questions just for you…')}</p>${wait()}`, { title: `📝 ${t('quiz.title', 'Quick quiz')}`, onClose: () => speaker.stop() });
  let quiz;
  try { quiz = await api('/api/quiz', { subtopic_id: ctx.topic.id, n: 5 }); } catch (e) { m.el.innerHTML = `<p>${esc(e.message)}</p>`; return; }
  const qs = quiz.questions; let i = 0, correct = 0; const missed = []; const L = ['A', 'B', 'C', 'D'];
  const body = () => $('.qbody', m.el); m.el.innerHTML = '<div class="qbody"></div>';
  const show = () => {
    const q = qs[i];
    body().innerHTML = `<h3>${t('quiz.q', 'Question')} ${i + 1} ${t('common.of', 'of')} ${qs.length}</h3><div class="progress-dots">${qs.map((_, k) => `<i class="${k < i ? 'done' : ''}"></i>`).join('')}</div><span class="chip">${esc(q.tests.replace('-', ' '))}</span>
      <div class="prose qtext">${md(q.question)}</div><div id="opts" role="group" aria-label="${t('quiz.options', 'Answer options')}">${q.options.map((o, k) => `<button class="q-opt" data-k="${k}"><b>${L[k]}</b><span class="prose">${md(o)}</span></button>`).join('')}</div>
      <div class="row"><button class="btn sm" id="hint">💡 ${t('quiz.hint', 'Hint')}</button>${speaker.supported ? `<button class="btn sm" id="read">🔊 ${t('quiz.read', 'Read aloud')}</button>` : ''}<button class="btn sm ghost" id="rep">⚑ ${t('lesson.report', 'Report a mistake')}</button></div><div id="fb" aria-live="polite"></div>`;
    $('#hint', body()).onclick = () => { $('#fb', body()).innerHTML = `<div class="explain">💡 ${md(q.hint)}</div>`; };
    $('#read', body())?.addEventListener('click', () => say(`${q.question}. ${q.options.map((o, k) => `${L[k]}. ${o}`).join('. ')}`));
    $('#rep', body()).onclick = () => reportDialog('quiz', ctx.topic.id, q.question);
    $$('.q-opt', body()).forEach((b) => (b.onclick = () => answer(+b.dataset.k))); $('.q-opt', body()).focus();
  };
  const answer = (k) => {
    const q = qs[i], ok = k === q.answer_index;
    $$('.q-opt', body()).forEach((b, idx) => { b.disabled = true; if (idx === q.answer_index) b.classList.add('right'); else if (idx === k) b.classList.add('wrong'); });
    if (ok) correct++; else missed.push({ question: q.question, options: q.options, chosen: q.options[k], correct: q.options[q.answer_index], explanation: q.explanation, concept: q.misconception || '' });
    $('#fb', body()).innerHTML = `<div class="explain"><b>${ok ? `✅ ${t('quiz.right', 'Correct!')}` : `❌ ${t('quiz.wrong', 'Not quite.')}`}</b>${!ok && q.wrong_option_notes[k] ? `<p>${md(q.wrong_option_notes[k])}</p>` : ''}<div class="prose">${md(q.explanation)}</div></div>
      <div class="row" style="margin-top:12px"><span class="spacer"></span>${speaker.supported ? `<button class="btn sm" id="read2">🔊 ${t('quiz.listen', 'Listen')}</button>` : ''}<button class="btn primary" id="nextq">${i + 1 < qs.length ? t('quiz.next', 'Next question →') : t('quiz.result', 'See my result')}</button></div>`;
    $('#read2', body())?.addEventListener('click', () => say(q.explanation));
    $('#nextq', body()).onclick = () => { speaker.stop(); if (++i < qs.length) show(); else finish(); }; $('#nextq', body()).focus();
  };
  const finish = async () => {
    let r = null; try { r = await api('/api/quiz/result', { subtopic_id: ctx.topic.id, correct, total: qs.length, missed }); } catch { /* offline */ }
    refreshProgress(); const pct = Math.round(100 * correct / qs.length); if (r) rewardToast(r.reward);
    const msg = pct >= 80 ? t('quiz.great', 'Excellent! You have a strong grip on this.') : pct >= 50 ? t('quiz.good', 'Good effort! A little more practice will make it solid.') : t('quiz.low', "This topic needs another look — that is perfectly okay. Let's fix it together.");
    body().innerHTML = `<h3>${t('quiz.yourresult', 'Your result')}</h3><div class="row" style="gap:20px;margin:14px 0">${ring(pct, `${correct}/${qs.length}`)}<div><b>${msg}</b><p class="muted">${r ? `${t('quiz.mastery', 'Mastery of this topic')}: <b>${Math.round(r.mastery * 100)}%</b>. ` : ''}${r ? `+${r.reward.points} XP. ` : ''}${t('quiz.reminder', "AIVidya will remind you to revise this at the right time.")}</p>${missed.length ? `<p class="small">${t('quiz.saved', 'Your mistakes were saved in your Mistakes notebook.')}</p>` : ''}</div></div>
      <div class="row"><button class="btn primary" id="discuss">💬 ${missed.length ? t('quiz.discuss', 'Discuss my mistakes') : t('quiz.followup', 'Ask a follow-up')}</button><button class="btn" id="again">🔄 ${t('quiz.again', 'Another quiz')}</button><button class="btn ghost" id="close2">${t('common.close', 'Close')}</button></div>`;
    $('#close2', body()).onclick = m.close; $('#again', body()).onclick = () => { m.close(); openQuiz(ctx); };
    $('#discuss', body()).onclick = async () => { m.close(); const { ask } = await import('./chat.js'); if (missed.length) ask(t('quiz.discussq', 'In the quiz I got these wrong: {list}. Please help me understand where my thinking went wrong.', { list: missed.map((x) => x.question).join(' | ') })); else $('#q').focus(); };
  };
  show();
}

/* ============================================================ practice ============================================================ */
export async function openPractice(ctx, difficulty = '') {
  speaker.stop(); const m = openModal(`<p class="muted">${t('practice.preparing', 'Writing a problem for you…')}</p>${wait()}`, { title: `🧮 ${t('practice.title', 'Practice problem')}`, wide: true });
  let p; try { p = await api('/api/practice/new', { subtopic_id: ctx.topic.id, difficulty }); } catch (e) { m.el.innerHTML = `<p>${esc(e.message)}</p>`; return; }
  let hintLevel = 0;
  m.el.innerHTML = `<span class="chip">${t('practice.level', 'Level')}: ${t('practice.' + p.difficulty, p.difficulty)}</span> ${p.concept ? `<span class="chip">${esc(p.concept)}</span>` : ''}
    <div class="prose qtext">${md(p.question)}</div>
    <div class="field"><label for="pa">${t('practice.answer', 'Your final answer')}${p.unit ? ` (${esc(p.unit)})` : ''}</label><input id="pa" type="text" autocomplete="off" autofocus></div>
    <div class="field"><label for="ps">${t('practice.steps', 'Your working (optional, but you get better feedback)')}</label><textarea id="ps" rows="4"></textarea></div>
    <div class="row"><button class="btn primary" id="pc">${t('practice.check', 'Check')}</button><button class="btn" id="ph">💡 ${t('quiz.hint', 'Hint')} (<span id="hl">${p.hints}</span>)</button><button class="btn ghost" id="pr">${t('practice.giveup', 'Show solution')}</button></div><div id="pout" aria-live="polite"></div>`;
  const out = $('#pout', m.el);
  $('#ph', m.el).onclick = async () => { if (hintLevel >= p.hints) return toast(t('practice.nohint', 'No more hints — try checking your answer.')); const h = await get(`/api/practice/${p.id}/hint?level=${hintLevel++}`); $('#hl', m.el).textContent = Math.max(0, p.hints - hintLevel); out.insertAdjacentHTML('beforeend', `<div class="explain">💡 ${hintLevel}. ${md(h.hint)}</div>`); };
  const check = async (reveal) => {
    out.insertAdjacentHTML('beforeend', `<p class="muted" id="chk">${t('practice.checking', 'Checking…')}</p>`);
    try {
      const r = await api(`/api/practice/${p.id}/check`, { answer: $('#pa', m.el).value, steps: $('#ps', m.el).value, reveal }); $('#chk', m.el)?.remove();
      let html = `<div class="explain ${r.correct ? 'good' : 'bad'}"><b>${r.correct ? `✅ ${t('quiz.right', 'Correct!')}` : `❌ ${t('quiz.wrong', 'Not quite.')}`}</b> ${md(r.feedback)}`;
      if (r.steps_feedback?.length) html += `<ul class="stepfb">${r.steps_feedback.map((s) => `<li class="${s.verdict}"><span>${s.verdict === 'correct' ? '✓' : s.verdict === 'error' ? '✗' : '?'}</span> ${rich(s.text)} <i class="muted">${rich(s.comment)}</i></li>`).join('')}</ul>`;
      if (r.revealed) html += `<h4>${t('practice.solution', 'Worked solution')}</h4><ol>${r.steps.map((s) => `<li>${md(s).replace(/<\/?p>/g, '')}</li>`).join('')}</ol><p><b>${t('practice.finalans', 'Answer')}:</b> ${esc(r.answer)}</p>`;
      out.insertAdjacentHTML('beforeend', `${html}</div>`);
      if (r.reward) { rewardToast(r.reward); out.insertAdjacentHTML('beforeend', `<p class="muted">+${r.reward.points} XP</p>`); }
      if (r.revealed) { out.insertAdjacentHTML('beforeend', `<div class="row"><button class="btn primary" id="pn">${t('practice.another', 'Another problem')}</button></div>`); $('#pn', m.el).onclick = () => { m.close(); openPractice(ctx); }; refreshProgress(); }
    } catch (e) { $('#chk', m.el)?.remove(); toast(e.message); }
  };
  $('#pc', m.el).onclick = () => check(false); $('#pr', m.el).onclick = () => check(true);
}

/* ============================================================ teach-back ============================================================ */
export function openTeachback(ctx) {
  speaker.stop();
  const m = openModal(`<p class="muted">${t('teach.help', 'The best way to learn is to teach. Explain {t} in your own words, as if you are teaching a younger friend. AIVidya will give honest feedback.', { t: `<b>${esc(ctx.topic.title)}</b>` })}</p>
    <div class="field"><label for="tb">${t('teach.yours', 'Your explanation')}</label><textarea id="tb" placeholder="${t('teach.ph', 'Start with the main idea, then give an example…')}"></textarea></div>
    <div class="row">${sttEngine() ? `<button class="btn" id="tb-mic">🎤 ${t('teach.speak', 'Speak instead')}</button>` : ''}<span class="spacer"></span><button class="btn primary" id="tb-go">${t('teach.go', 'Get feedback')}</button></div><div id="tb-out" aria-live="polite"></div>`, { title: `🗣️ ${t('lesson.teach', 'Teach it back')}`, onClose: () => { speaker.stop(); listener.abort(); } });
  const ta = $('#tb', m.el); $('#tb-mic', m.el)?.addEventListener('click', (e) => dictate(e.currentTarget, ta));
  $('#tb-go', m.el).onclick = async (e) => {
    const text = ta.value.trim(); if (text.length < 10) return toast(t('teach.short', 'Write a few more words first — at least a sentence.'));
    e.currentTarget.disabled = true; $('#tb-out', m.el).innerHTML = `<p class="muted">${t('teach.reading', 'AIVidya is reading your explanation…')}</p>`;
    try {
      const r = await api('/api/teachback', { subtopic_id: ctx.topic.id, explanation: text }); refreshProgress(); rewardToast(r.reward);
      const list = (a) => (a?.length ? `<ul class="feedback-list">${a.map((x) => `<li>${md(x).replace(/<\/?p>/g, '')}</li>`).join('')}</ul>` : '');
      $('#tb-out', m.el).innerHTML = `<hr><div class="row" style="gap:20px">${ring(r.score, `${r.score}%`)}<div style="flex:1"><b>${esc(r.spoken_feedback)}</b></div></div>
        ${r.strengths?.length ? `<h3>👍 ${t('teach.right', 'What you got right')}</h3>${list(r.strengths)}` : ''}${r.gaps?.length ? `<h3>🧩 ${t('teach.add', 'What to add')}</h3>${list(r.gaps)}` : ''}${r.misconceptions?.length ? `<h3>⚠️ ${t('teach.fix', "Let's fix these")}</h3>${list(r.misconceptions)}` : ''}
        <div class="explain"><b>${t('teach.next', 'Next step')}:</b> ${esc(r.next_step)}</div><p class="small muted">🤖 ${t('teach.ai', 'Marked by AI — it can be wrong. Ask your teacher if unsure.')}</p>
        <div class="row"><button class="btn" id="tb-again">${t('common.tryagain', 'Try again')}</button><button class="btn ghost" id="tb-close">${t('common.close', 'Close')}</button></div>`;
      $('#tb-again', m.el).onclick = () => { $('#tb-out', m.el).innerHTML = ''; $('#tb-go', m.el).disabled = false; ta.focus(); }; $('#tb-close', m.el).onclick = m.close; say(r.spoken_feedback);
    } catch (er) { $('#tb-out', m.el).innerHTML = `<div class="banner">${esc(er.message)}</div>`; $('#tb-go', m.el).disabled = false; }
  };
}

/* ============================================================ oral viva ============================================================ */
export async function openViva(ctx) {
  speaker.stop(); const m = openModal(`<p class="muted">${t('viva.start', 'Your examiner is getting ready…')}</p>${wait()}`, { title: `🎤 ${t('lesson.viva', 'Oral viva')}`, wide: true, onClose: () => { speaker.stop(); listener.abort(); } });
  let v; try { v = await api('/api/viva/start', { subtopic_id: ctx.topic.id }); } catch (e) { m.el.innerHTML = `<p>${esc(e.message)}</p>`; return; }
  const render = (q, n, total, fb) => {
    m.el.innerHTML = `<p class="muted small">${t('quiz.q', 'Question')} ${n} ${t('common.of', 'of')} ${total}</p>${fb ? `<div class="explain">${esc(fb)}</div>` : ''}<div class="prose qtext">${md(q)}</div>
      <div class="field"><label for="va">${t('viva.answer', 'Your answer — speak or type')}</label><textarea id="va" rows="3" autofocus></textarea></div>
      <div class="row">${sttEngine() ? `<button class="btn" id="vm">🎤 ${t('teach.speak', 'Speak instead')}</button>` : ''}<button class="btn" id="vr">🔊 ${t('quiz.read', 'Read aloud')}</button><span class="spacer"></span><button class="btn primary" id="vs">${t('viva.submit', 'Answer')}</button></div>`;
    say((fb ? `${fb} ` : '') + q);
    $('#vr', m.el).onclick = () => say(q); $('#vm', m.el)?.addEventListener('click', (e) => dictate(e.currentTarget, $('#va', m.el)));
    $('#vs', m.el).onclick = async (e) => {
      const text = $('#va', m.el).value.trim(); if (!text) return toast(t('viva.empty', 'Say or type your answer first.')); e.currentTarget.disabled = true; speaker.stop(); listener.abort();
      try {
        const r = await api(`/api/viva/${v.id}/answer`, { answer: text });
        if (r.finished) { rewardToast(r.reward); refreshProgress(); m.el.innerHTML = `<div class="row" style="gap:20px">${ring(r.percent, `${r.percent}%`)}<div><b>${esc(r.feedback)}</b><p>${esc(r.summary)}</p><p class="muted small">+${r.reward.points} XP · 🤖 ${t('teach.ai', 'Marked by AI — it can be wrong. Ask your teacher if unsure.')}</p></div></div><div class="row"><button class="btn primary" id="vd">${t('common.close', 'Close')}</button></div>`; $('#vd', m.el).onclick = m.close; say(`${r.feedback} ${r.summary}`); }
        else render(r.question, r.number, r.total, r.feedback);
      } catch (er) { toast(er.message); e.currentTarget.disabled = false; }
    };
  };
  render(v.question, v.number, v.total, v.greeting);
}

/* ============================================================ flashcards (from a lesson) ============================================================ */
export async function openFlashcards(ctx) {
  const m = openModal(`<p class="muted">${t('cards.making', 'Making flashcards…')}</p>${wait()}`, { title: `🃏 ${t('lesson.cards', 'Flashcards')}` });
  try {
    const { cards } = await api('/api/flashcards/generate', { subtopic_id: ctx.topic.id });
    m.el.innerHTML = `<p class="muted">${cards.length} ${t('cards.ready', 'cards are ready and added to your revision.')}</p><div class="cards-preview">${cards.map((c) => `<details class="card-mini"><summary>${md(c.front).replace(/<\/?p>/g, '')}</summary><div class="prose">${md(c.back)}</div></details>`).join('')}</div><div class="row end"><a class="btn primary" href="#/revise" id="gor">${t('cards.revise', 'Revise now')}</a></div>`;
    $('#gor', m.el).onclick = m.close;
  } catch (e) { m.el.innerHTML = `<p>${esc(e.message)}</p>`; }
}

/* ============================================================ check my working ============================================================ */
export function openCheckWork(ctx, problem = '') {
  const m = openModal(`<div class="field"><label for="cw-p">${t('work.problem', 'The problem')}</label><textarea id="cw-p" rows="2">${esc(problem)}</textarea></div>
    <div class="field"><label for="cw-s">${t('work.steps', 'Your working, one step per line')}</label><textarea id="cw-s" rows="6" placeholder="${t('work.ph', 'Step 1: …\nStep 2: …')}"></textarea></div>
    <div class="row">${sttEngine() ? `<button class="btn" id="cw-m">🎤 ${t('teach.speak', 'Speak instead')}</button>` : ''}<span class="spacer"></span><button class="btn primary" id="cw-go">${t('work.go', 'Check my steps')}</button></div><div id="cw-out" aria-live="polite"></div>`, { title: `✅ ${t('lesson.work', 'Check my working')}`, wide: true, onClose: () => listener.abort() });
  $('#cw-m', m.el)?.addEventListener('click', (e) => dictate(e.currentTarget, $('#cw-s', m.el)));
  $('#cw-go', m.el).onclick = async (e) => {
    const p = $('#cw-p', m.el).value.trim(), s = $('#cw-s', m.el).value.trim(); if (p.length < 3 || s.length < 3) return toast(t('work.need', 'Write the problem and at least one step.'));
    e.currentTarget.disabled = true; $('#cw-out', m.el).innerHTML = `<p class="muted">${t('practice.checking', 'Checking…')}</p>`;
    try {
      const r = await api('/api/check-work', { subtopic_id: ctx.topic.id, problem: p, steps: s });
      $('#cw-out', m.el).innerHTML = `<ul class="stepfb">${r.steps.map((x) => `<li class="${x.verdict}"><span>${x.verdict === 'correct' ? '✓' : x.verdict === 'error' ? '✗' : '?'}</span> ${rich(x.text)}${x.comment ? ` <i class="muted">${rich(x.comment)}</i>` : ''}</li>`).join('')}</ul>
        <div class="explain ${r.final_answer_correct === false ? 'bad' : r.final_answer_correct ? 'good' : ''}"><b>${r.final_answer_correct === true ? `✅ ${t('work.finalok', 'Final answer is right')}` : r.final_answer_correct === false ? `❌ ${t('work.finalbad', 'Final answer is not right yet')}` : t('work.nofinal', 'No final answer yet')}</b><p>${rich(r.overall)}</p><p><b>${t('teach.next', 'Next step')}:</b> ${rich(r.suggestion)}</p></div><p class="small muted">🤖 ${t('teach.ai', 'Marked by AI — it can be wrong. Ask your teacher if unsure.')}</p>`;
    } catch (er) { $('#cw-out', m.el).innerHTML = `<div class="banner">${esc(er.message)}</div>`; } finally { e.currentTarget.disabled = false; }
  };
}

/* ============================================================ report a mistake ============================================================ */
export function reportDialog(kind, subtopicId, ref) {
  const m = openModal(`<p class="muted">${t('report.help', 'Found something wrong or confusing? Tell us — a teacher will check it.')}</p>${ref ? `<blockquote class="small">${esc(ref.slice(0, 200))}</blockquote>` : ''}<div class="field"><label for="rp">${t('report.what', 'What is wrong?')}</label><textarea id="rp" rows="3" autofocus></textarea></div><div class="row end"><button class="btn primary" id="rg">${t('report.send', 'Send report')}</button></div>`, { title: `⚑ ${t('lesson.report', 'Report a mistake')}` });
  $('#rg', m.el).onclick = async () => { const msg = $('#rp', m.el).value.trim(); if (msg.length < 3) return; try { const r = await api('/api/report', { kind, subtopic_id: subtopicId || '', ref: ref || '', message: msg }); m.close(); toast(r.message); } catch (e) { toast(e.message); } };
}
