// Answer-writing coach: write a 2, 3 or 5 mark answer and get it marked against a board-style marking scheme.
import { api, get } from './api.js';
import { t } from './i18n.js';
import { md, esc } from './render.js';
import { $, $$, debounce, fmtDate, ring } from './ui.js';
import { state, refreshProgress } from './state.js';
import { rewardToast } from './lesson.js';

const SIZES = { 2: ['coach.m2', 'Short answer · about 30–60 words'], 3: ['coach.m3', 'Explain · about 60–100 words'], 5: ['coach.m5', 'Long answer · about 120–200 words'] };
const crumbs = (extra = '') => `<div class="crumbs"><a href="#/">${t('nav.home', 'Home')}</a> › <a href="#/coach">✍️ ${t('coach.heading', 'Answer coach')}</a>${extra}</div>`;
const rich = (s) => md(String(s ?? '')).replace(/^\s*<p>([\s\S]*)<\/p>\s*$/, '$1'); // model text may hold $maths$ and **bold**
const wordCount = (s) => (s.trim().match(/\S+/g) || []).length;

export async function route(view, rest) {
  if (/^\d+$/.test(rest)) return renderAttempt(view, +rest);
  return renderStart(view);
}

async function renderStart(view) {
  const { items } = await get('/api/coach');
  let topic = state.last ? { id: state.last.id, title: state.last.title } : null, marks = 3;
  view.innerHTML = `${crumbs()}<h1>✍️ ${t('coach.heading', 'Answer coach')}</h1>
    <p class="muted">${t('coach.help', 'Board exams give marks for points, not for length. Write an answer the way you would in the exam, and see exactly where each mark came from and what was missing.')}</p>
    <section class="card pad"><h2>${t('coach.new', 'Practise an answer')}</h2>
      <div class="field"><span class="label">${t('coach.marks', 'How many marks?')}</span><div class="choice-row" id="marks">${[2, 3, 5].map((m) => `<button type="button" class="choice" data-v="${m}" aria-pressed="${m === marks}">${m}</button>`).join('')}</div><small class="muted" id="msize"></small></div>
      <div class="field"><label for="tq">${t('coach.topic', 'Topic')}</label><div id="chosen" class="row"></div><input id="tq" type="search" placeholder="${t('search.placeholder', 'Search any topic or ask a question…')}" autocomplete="off"><div id="tr" class="topic-pills"></div></div>
      <details class="more"><summary>${t('coach.own', 'I have my own question')}</summary><div class="field"><label for="own">${t('coach.own.label', 'Paste a question from your textbook or an old paper')}</label><textarea id="own" rows="3" maxlength="1500"></textarea></div></details>
      <p class="error" id="err" role="alert" hidden></p>
      <button class="btn primary" id="go">${t('coach.give', 'Give me a question')}</button></section>
    <h2 class="section-title">${t('coach.history', 'My answers')}</h2>
    ${items.length ? `<div class="list">${items.map((h) => `<a class="card pad row link" href="#/coach/${h.id}"><div style="flex:1"><b>${esc(h.topic)}</b> <span class="muted small">${h.marks} ${t('coach.marksword', 'marks')} · ${fmtDate(h.created_at)}</span><div class="muted small">${esc(h.question)}</div></div>
      ${h.submitted_at ? `<span class="chip ${h.awarded >= h.marks * 0.7 ? 'ok' : h.awarded < h.marks * 0.4 ? 'warn' : ''}">${h.awarded}/${h.marks}</span>` : `<span class="chip">${t('coach.unfinished', 'not finished')}</span>`}</a>`).join('')}</div>` : `<p class="muted">${t('coach.nohistory', 'Nothing yet. Your answers and marks will be kept here.')}</p>`}`;
  const paintMarks = () => { $$('#marks .choice', view).forEach((b) => b.setAttribute('aria-pressed', +b.dataset.v === marks)); $('#msize', view).textContent = t(SIZES[marks][0], SIZES[marks][1]); };
  $$('#marks .choice', view).forEach((b) => (b.onclick = () => { marks = +b.dataset.v; paintMarks(); }));
  const paintTopic = () => { $('#chosen', view).innerHTML = topic ? `<span class="chip on">${esc(topic.title)}</span>` : `<span class="muted small">${t('coach.picktopic', 'Search and pick a topic below.')}</span>`; };
  paintMarks(); paintTopic();
  $('#tq', view).oninput = debounce(async (e) => {
    const q = e.target.value.trim(); if (q.length < 2) return;
    const r = await get(`/api/search?q=${encodeURIComponent(q)}`);
    $('#tr', view).innerHTML = r.results.filter((x) => !String(x.id).startsWith('my-')).slice(0, 6).map((x) => `<button class="chip" data-id="${esc(x.id)}" data-t="${esc(x.title)}">${esc(x.subject_name)} G${x.grade}: ${esc(x.title)}</button>`).join('');
    $$('#tr [data-id]', view).forEach((b) => (b.onclick = () => { topic = { id: b.dataset.id, title: b.dataset.t }; paintTopic(); $('#tr', view).innerHTML = ''; }));
  }, 300);
  $('#go', view).onclick = async (e) => {
    const err = $('#err', view); err.hidden = true;
    if (!topic) { err.textContent = t('coach.picktopic.first', 'Pick a topic first.'); err.hidden = false; return; }
    e.currentTarget.disabled = true; e.currentTarget.textContent = t('coach.preparing', 'Preparing your question…');
    try { const a = await api('/api/coach/start', { subtopic_id: topic.id, marks, question: $('#own', view).value }); location.hash = `#/coach/${a.id}`; }
    catch (er) { err.textContent = er.message; err.hidden = false; e.currentTarget.disabled = false; e.currentTarget.textContent = t('coach.give', 'Give me a question'); }
  };
}

async function renderAttempt(view, id) {
  let a;
  try { a = await get(`/api/coach/${id}`); } catch (e) { view.innerHTML = `${crumbs()}<div class="banner" role="alert">${esc(e.message)}</div>`; return; }
  if (a.submitted) return showResult(view, a);
  const [lo, hi] = a.words;
  view.innerHTML = `${crumbs(` › ${esc(a.topic)}`)}<h1>✍️ ${esc(a.topic)}</h1>
    <section class="card pad"><div class="row"><span class="chip">${a.marks} ${t('coach.marksword', 'marks')}</span><span class="spacer"></span><span class="muted small">${t('coach.length', 'Aim for about {lo}–{hi} words', { lo, hi })}</span></div>
      <div class="prose qtext">${md(a.question)}</div>
      <div class="field"><label for="ans">${t('coach.yours', 'Your answer')}</label><textarea id="ans" rows="${a.marks >= 5 ? 12 : 7}" maxlength="4000" autofocus></textarea><small class="muted" id="wc"></small></div>
      <p class="error" id="err" role="alert" hidden></p>
      <div class="row"><button class="btn primary" id="send">${t('coach.mark', 'Mark my answer')}</button><a class="btn ghost" href="#/coach">${t('common.back', 'Back')}</a></div></section>`;
  const ta = $('#ans', view), count = () => { const n = wordCount(ta.value); $('#wc', view).textContent = `${n} ${t('coach.words', 'words')}`; $('#wc', view).className = n >= lo * 0.6 && n <= hi * 2 ? 'muted' : n ? 'warn-text' : 'muted'; };
  ta.oninput = count; count();
  $('#send', view).onclick = async (e) => {
    const err = $('#err', view); err.hidden = true; const btn = e.currentTarget; btn.disabled = true; btn.textContent = t('coach.marking', 'Marking… this takes a few seconds');
    try { const r = await api(`/api/coach/${id}/submit`, { answer: ta.value }); refreshProgress(); showResult(view, r); rewardToast(r.reward); }
    catch (er) { err.textContent = er.message; err.hidden = false; btn.disabled = false; btn.textContent = t('coach.mark', 'Mark my answer'); }
  };
}

function showResult(view, r) {
  const pct = Math.round((100 * r.awarded) / r.marks);
  const icon = (p) => (p.got >= p.max ? '✅' : p.got > 0 ? '🟡' : '❌');
  view.innerHTML = `${crumbs(` › ${esc(r.topic || '')}`)}<h1>✍️ ${esc(r.topic || t('coach.heading', 'Answer coach'))}</h1>
    <section class="card pad"><div class="row" style="gap:20px">${ring(pct, `${r.awarded}/${r.marks}`)}<div style="flex:1"><b>${rich(r.feedback)}</b>${r.reward?.points ? `<p class="muted small">+${r.reward.points} XP</p>` : ''}</div></div>
      <h3>${t('coach.question', 'Question')}</h3><div class="prose">${md(r.question)}</div>
      <h3>${t('coach.where', 'Where your marks came from')}</h3>
      <table class="tt"><tr><th></th><th>${t('coach.point', 'Point')}</th><th>${t('coach.got', 'Marks')}</th></tr>${r.points.map((p) => `<tr><td>${icon(p)}</td><td>${rich(p.point)}<div class="muted small">${rich(p.comment)}</div></td><td>${p.got}/${p.max}</td></tr>`).join('')}</table>
      ${r.missing.length ? `<h3>${t('coach.missing', 'What was missing')}</h3><ul>${r.missing.map((m) => `<li>${rich(m)}</li>`).join('')}</ul>` : ''}
      ${r.tips.length ? `<h3>💡 ${t('coach.tips', 'Exam tips for this answer')}</h3><ul>${r.tips.map((m) => `<li>${rich(m)}</li>`).join('')}</ul>` : ''}
      <details><summary>${t('coach.yours', 'Your answer')} (${r.word_count || wordCount(r.answer)} ${t('coach.words', 'words')})</summary><div class="prose">${md(r.answer)}</div></details>
      <details open><summary>${t('coach.model', 'A model answer')}</summary><div class="prose">${md(r.model_answer || '')}</div></details>
      <details><summary>${t('coach.scheme', 'Marking scheme')}</summary><div class="prose">${md(String(r.scheme || '').replace(/\n/g, '\n\n'))}</div></details>
      <div class="row" style="margin-top:14px"><button class="btn primary" id="retry">🔄 ${t('coach.retry', 'Write it again')}</button><button class="btn" id="newq">${t('coach.another', 'Another question on this topic')}</button><a class="btn ghost" href="#/learn/${esc(r.subtopic_id)}">${t('coach.lesson', 'Back to the lesson')}</a></div></section>`;
  const go = async (body) => { try { const a = await api('/api/coach/start', body); location.hash = `#/coach/${a.id}`; } catch (e) { $('#retry', view).insertAdjacentHTML('afterend', `<span class="error">${esc(e.message)}</span>`); } };
  $('#retry', view).onclick = () => go({ marks: r.marks, retry_of: r.id });
  $('#newq', view).onclick = () => go({ subtopic_id: r.subtopic_id, marks: r.marks });
}
