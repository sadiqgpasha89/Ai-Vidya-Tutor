// Teacher worksheet maker: pick topics and question types, get a printable question paper and an answer key.
import { api, get, del, sse } from './api.js';
import { t } from './i18n.js';
import { md, esc } from './render.js';
import { $, $$, toast, confirmDialog, promptDialog, fmtDate, download } from './ui.js';
import { state } from './state.js';

const KINDS = [['mcq', 'ws.k.mcq', 'Multiple choice', 1, 5], ['short', 'ws.k.short', 'Short answer', 2, 3], ['long', 'ws.k.long', 'Long answer', 5, 1], ['case', 'ws.k.case', 'Case-based', 4, 0], ['numeric', 'ws.k.numeric', 'Numerical', 2, 0]];
const KIND_LABEL = Object.fromEntries(KINDS.map(([k, key, d]) => [k, [key, d]]));
const LETTERS = 'ABCDEFGH';
const kindName = (k) => t(...KIND_LABEL[k]);

export async function route(view, rest) {
  return rest ? renderSheet(view, rest) : renderList(view);
}

/* ============================================================ list + builder ============================================================ */
async function renderList(view) {
  const { items } = await get('/api/worksheets');
  view.innerHTML = `<div class="row"><h1 style="margin:0">📄 ${t('ws.heading', 'Worksheets')}</h1><span class="spacer"></span><button class="btn primary" id="new">＋ ${t('ws.new', 'New worksheet')}</button></div>
    <p class="muted">${t('ws.help', 'Choose topics and the kinds of questions you want. AIVidya writes a question paper with an answer key and marking scheme that you can print or download. Questions you have approved in the question bank are used first.')}</p>
    <div id="builder"></div>
    ${items.length ? `<div class="list">${items.map((w) => `<a class="card pad row link" href="#/teach/worksheets/${w.id}"><div style="flex:1"><b>${esc(w.title)}</b><div class="muted small">${w.questions} ${t('ws.questions', 'questions')} · ${w.total_marks} ${t('coach.marksword', 'marks')} · ${fmtDate(w.created_at)}</div><div class="muted small">${esc(w.topics.join(' · '))}</div></div></a>`).join('')}</div>`
      : `<p class="muted" id="none">${t('ws.none', 'No worksheets yet.')}</p>`}`;
  $('#new', view).onclick = () => { $('#new', view).hidden = true; builder($('#builder', view)); };
  if (!items.length) { $('#new', view).hidden = true; builder($('#builder', view)); }
}

function builder(box) {
  const picked = new Map(); // topic id -> title, kept while the subject or class is changed
  const subjects = state.meta.subjects, langs = state.meta.languages || [{ id: 'en', name: 'English' }];
  box.innerHTML = `<section class="card pad"><h2>${t('ws.topics', '1. Topics')}</h2>
      <div class="row"><select id="sub" aria-label="${t('tests.subject', 'Subject')}">${subjects.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join('')}</select>
        <select id="gr" aria-label="${t('common.grade', 'Grade')}">${state.meta.grades.map((g) => `<option value="${g}" ${g === 9 ? 'selected' : ''}>${t('common.grade', 'Grade')} ${g}</option>`).join('')}</select></div>
      <div id="chapters" class="ws-chapters" aria-live="polite"></div>
      <div id="chosen" class="row" style="flex-wrap:wrap"></div>
      <h2>${t('ws.types', '2. Questions')}</h2>
      <table class="tt"><tr><th>${t('ws.type', 'Type')}</th><th>${t('ws.count', 'How many')}</th><th>${t('ws.marks', 'Marks each')}</th></tr>
        ${KINDS.map(([k, key, d, marks, count]) => `<tr><td>${t(key, d)}</td><td><input type="number" min="0" max="20" value="${count}" data-n="${k}" aria-label="${t(key, d)}: ${t('ws.count', 'How many')}"></td><td><input type="number" min="1" max="10" value="${marks}" data-m="${k}" aria-label="${t(key, d)}: ${t('ws.marks', 'Marks each')}"></td></tr>`).join('')}</table>
      <p class="muted small" id="sum"></p>
      <h2>${t('ws.options', '3. Options')}</h2>
      <div class="grid2"><div class="field"><label for="ti">${t('note.title', 'Title')}</label><input id="ti" type="text" maxlength="120" placeholder="${t('ws.title.ph', 'e.g. Motion: weekly practice')}"></div>
        <div class="field"><label for="df">${t('ws.difficulty', 'Difficulty')}</label><select id="df"><option value="easy">${t('ws.d.easy', 'Easier')}</option><option value="standard" selected>${t('ws.d.standard', 'Standard')}</option><option value="hard">${t('ws.d.hard', 'Harder')}</option></select></div>
        <div class="field"><label for="lg">${t('ws.language', 'Language')}</label><select id="lg">${langs.map((l) => `<option value="${l.id}">${esc(l.name)}</option>`).join('')}</select></div>
        <div class="field"><label for="bd">${t('profile.board', 'Board')}</label><select id="bd">${state.meta.boards.map((b) => `<option>${b}</option>`).join('')}</select></div></div>
      <div class="field"><label for="nt">${t('ws.note', 'Anything else? (optional)')}</label><input id="nt" type="text" maxlength="500" placeholder="${t('ws.note.ph', 'e.g. include numericals with units; avoid diagrams')}"></div>
      <p class="error" id="err" role="alert" hidden></p><p id="prog" class="muted" role="status"></p>
      <div class="row"><button class="btn primary" id="make">${t('ws.make', 'Make the worksheet')}</button></div></section>`;
  const paintChosen = () => { $('#chosen', box).innerHTML = picked.size ? [...picked].map(([id, title]) => `<button class="chip on" data-x="${esc(id)}" title="${t('ws.remove', 'Remove')}">${esc(title)} ✕</button>`).join('') : `<span class="muted small">${t('ws.notopics', 'Tick the topics below.')}</span>`;
    $$('[data-x]', box).forEach((b) => (b.onclick = () => { picked.delete(b.dataset.x); paintChosen(); loadChapters(); })); };
  const sum = () => { const rows = KINDS.map(([k]) => [+$(`[data-n="${k}"]`, box).value || 0, +$(`[data-m="${k}"]`, box).value || 1]); const n = rows.reduce((a, r) => a + r[0], 0), m = rows.reduce((a, r) => a + r[0] * r[1], 0);
    $('#sum', box).textContent = t('ws.sum', '{n} questions · {m} marks · about {x} minutes', { n, m, x: Math.max(10, Math.round(m * 1.5)) }); };
  $$('input[data-n], input[data-m]', box).forEach((i) => (i.oninput = sum));
  const loadChapters = async () => {
    const el = $('#chapters', box); el.innerHTML = `<p class="muted small">…</p>`;
    try {
      const { chapters } = await get(`/api/curriculum?subject=${$('#sub', box).value}&grade=${$('#gr', box).value}`);
      el.innerHTML = chapters.map((c) => `<details><summary>${esc(c.title)}</summary><div class="ws-subs">${c.subtopics.map((s) => `<label class="check"><input type="checkbox" data-t="${esc(s.id)}" data-title="${esc(s.title)}" ${picked.has(s.id) ? 'checked' : ''}> ${esc(s.title)}</label>`).join('')}</div></details>`).join('') || `<p class="muted small">${t('ws.nochapters', 'No chapters for this subject and grade.')}</p>`;
      $$('[data-t]', el).forEach((cb) => (cb.onchange = () => { if (cb.checked) { if (picked.size >= 12) { cb.checked = false; toast(t('ws.max', 'Up to 12 topics.')); return; } picked.set(cb.dataset.t, cb.dataset.title); } else picked.delete(cb.dataset.t); paintChosen(); }));
    } catch (e) { el.innerHTML = `<p class="error">${esc(e.message)}</p>`; }
  };
  $('#sub', box).onchange = loadChapters; $('#gr', box).onchange = loadChapters;
  paintChosen(); sum(); loadChapters();
  $('#make', box).onclick = async (e) => {
    const err = $('#err', box); err.hidden = true;
    const items = KINDS.map(([k]) => ({ kind: k, count: +$(`[data-n="${k}"]`, box).value || 0, marks: +$(`[data-m="${k}"]`, box).value || 0 })).filter((x) => x.count > 0);
    if (!picked.size) { err.textContent = t('ws.pick.topics', 'Tick at least one topic.'); err.hidden = false; return; }
    if (!items.length) { err.textContent = t('ws.pick.types', 'Choose at least one question.'); err.hidden = false; return; }
    const btn = e.currentTarget; btn.disabled = true;
    const body = { topics: [...picked.keys()], items, title: $('#ti', box).value, difficulty: $('#df', box).value, language: $('#lg', box).value, board: $('#bd', box).value, note: $('#nt', box).value };
    try {
      for await (const ev of sse('/api/worksheets/make', body)) {
        if (ev.type === 'queue') $('#prog', box).textContent = ev.ahead ? t('queue.ahead', '{n} ahead of you…', { n: ev.ahead }) : '';
        else if (ev.type === 'progress') $('#prog', box).textContent = t('ws.progress', 'Writing part {i} of {n}… this takes about a minute in all.', { i: ev.step + 1, n: ev.of });
        else if (ev.type === 'error') throw new Error(ev.message);
        else if (ev.type === 'done') { location.hash = `#/teach/worksheets/${ev.id}`; return; }
      }
    } catch (er) { err.textContent = er.message; err.hidden = false; $('#prog', box).textContent = ''; btn.disabled = false; }
  };
}

/* ============================================================ one worksheet ============================================================ */
function numbered(sheet) { let n = 0; return sheet.sections.map((s) => ({ ...s, questions: s.questions.map((q) => ({ ...q, no: ++n })) })); }

const paperHtml = (sheet, key, editable) => {
  const secs = numbered(sheet), title = esc(sheet.title);
  return `<article class="ws-paper"><header><h2>${title}</h2>
    <div class="ws-meta"><span>${esc(sheet.board)}</span><span>${t('ws.maxmarks', 'Maximum marks')}: <b>${sheet.total_marks}</b></span><span>${t('ws.time', 'Time')}: <b>${sheet.minutes}</b> ${t('ws.min', 'min')}</span></div>
    ${key ? `<p><b>${t('ws.answerkey', 'Answer key and marking scheme')}</b></p>` : `<div class="ws-meta"><span>${t('ws.name', 'Name')}: ____________________</span><span>${t('ws.class', 'Class')}: ________</span><span>${t('ws.date', 'Date')}: ____________</span></div>
    <p class="small">${t('ws.instr', 'Answer all questions. Write the marks for each part clearly.')}${sheet.note ? ' ' + esc(sheet.note) : ''}</p>`}</header>
    ${secs.map((s) => `<section class="ws-sec"><h3>${t('ws.section', 'Section')} ${s.name}: ${kindName(s.kind)} <span class="muted small">(${s.marks} ${s.marks === 1 ? t('ws.mark', 'mark') : t('coach.marksword', 'marks')} ${t('ws.each', 'each')})</span></h3>
      ${s.questions.map((q) => `<div class="ws-q" data-q="${q.id}"><div class="row"><b>${q.no}.</b><div class="prose" style="flex:1">${md(q.question)}</div><span class="muted small">[${q.marks}]</span>${editable ? `<button class="btn sm no-print" data-swap="${q.id}" title="${t('ws.swap', 'Replace this question')}">↻</button>` : ''}</div>
        ${!key && q.options?.length ? `<ol class="ws-opts" type="A">${q.options.map((o) => `<li><div class="prose">${md(o)}</div></li>`).join('')}</ol>` : ''}
        ${key ? `<div class="ws-ans"><b>${t('ws.answer', 'Answer')}:</b> ${q.kind === 'mcq' && q.options?.length ? `${LETTERS[q.answer_index]}. ${md(q.options[q.answer_index] ?? '').replace(/<\/?p>/g, '')}` : md(q.answer || '')}
          ${q.marking_scheme ? `<div class="small"><b>${t('coach.scheme', 'Marking scheme')}:</b>${md(String(q.marking_scheme).replace(/\n/g, '\n\n'))}</div>` : ''}</div>` : ''}</div>`).join('')}</section>`).join('')}</article>`;
};

async function renderSheet(view, id) {
  let sheet;
  try { sheet = await get(`/api/worksheets/${id}`); } catch (e) { view.innerHTML = `<div class="banner" role="alert">${esc(e.message)}</div><p><a class="btn" href="#/teach/worksheets">${t('common.back', 'Back')}</a></p>`; return; }
  let tab = 'paper';
  const draw = () => {
    view.innerHTML = `<div class="crumbs no-print"><a href="#/teach/worksheets">📄 ${t('ws.heading', 'Worksheets')}</a> › ${esc(sheet.title)}</div>
      <div class="tabs no-print"><button class="tab" role="tab" aria-selected="${tab === 'paper'}" data-tab="paper">${t('ws.paper', 'Question paper')}</button><button class="tab" role="tab" aria-selected="${tab === 'key'}" data-tab="key">${t('ws.key', 'Answer key')}</button></div>
      <div class="row no-print" style="flex-wrap:wrap;margin-top:10px"><button class="btn" id="print">🖨️ ${t('common.print', 'Print')}</button><button class="btn" id="md">⬇️ ${t('ws.download', 'Download')}</button><button class="btn" id="ren">✏️</button><button class="btn danger" id="del" aria-label="${t('common.delete', 'Delete')}">🗑️</button></div>
      ${tab === 'paper' ? `<p class="muted small no-print">${t('ws.swap.help', 'Not happy with a question? Tap ↻ to replace it with a new one.')}</p>` : ''}
      <div class="card pad">${paperHtml(sheet, tab === 'key', tab === 'paper')}</div>`;
    $$('[data-tab]', view).forEach((b) => (b.onclick = () => { tab = b.dataset.tab; draw(); }));
    $('#print', view).onclick = () => window.print();
    $('#md', view).onclick = () => download(`${sheet.title.replace(/[^\w\-]+/g, '_') || 'worksheet'}.md`, toMarkdown(sheet), 'text/markdown');
    $('#ren', view).onclick = async () => { const v = await promptDialog(t('note.title', 'Title'), { value: sheet.title }); if (v && v.trim()) { await api(`/api/worksheets/${id}`, { title: v }, 'PUT'); sheet.title = v.trim(); draw(); } };
    $('#del', view).onclick = async () => { if (await confirmDialog(t('ws.del', 'Delete this worksheet?'), { danger: true })) { await del(`/api/worksheets/${id}`); location.hash = '#/teach/worksheets'; } };
    $$('[data-swap]', view).forEach((b) => (b.onclick = async () => {
      b.disabled = true; b.textContent = '…';
      try { const r = await api(`/api/worksheets/${id}/replace`, { question_id: b.dataset.swap }); for (const s of sheet.sections) { const i = s.questions.findIndex((q) => q.id === b.dataset.swap); if (i >= 0) s.questions[i] = r.question; } draw(); }
      catch (e) { toast(e.message); b.disabled = false; b.textContent = '↻'; }
    }));
  };
  draw();
}

function toMarkdown(sheet) {
  const out = [`# ${sheet.title}`, `${sheet.board} · ${sheet.total_marks} marks · ${sheet.minutes} min`, ''];
  const key = [`## Answer key`, ''];
  for (const s of numbered(sheet)) {
    out.push(`## Section ${s.name}: ${kindName(s.kind)} (${s.marks} each)`, '');
    for (const q of s.questions) {
      out.push(`${q.no}. ${q.question} [${q.marks}]`);
      (q.options || []).forEach((o, i) => out.push(`   - ${LETTERS[i]}. ${o}`));
      out.push('');
      key.push(`${q.no}. ${q.kind === 'mcq' && q.options?.length ? `${LETTERS[q.answer_index]}. ${q.options[q.answer_index] ?? ''}` : q.answer || ''}`);
      if (q.marking_scheme) key.push(`   Marking scheme: ${String(q.marking_scheme).replace(/\n/g, '; ')}`);
    }
  }
  return [...out, '', ...key].join('\n');
}
