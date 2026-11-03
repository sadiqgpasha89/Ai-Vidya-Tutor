// Doubt inbox. Students send a doubt to their class teacher and follow the conversation; teachers answer from an inbox.
import { api, get } from './api.js';
import { t } from './i18n.js';
import { md, esc } from './render.js';
import { $, $$, openModal, toast, timeAgo } from './ui.js';
import { state } from './state.js';

const STATUS = { open: ['doubt.s.open', 'Waiting for the teacher'], answered: ['doubt.s.answered', 'Answered'], resolved: ['doubt.s.resolved', 'Cleared'] };
const chip = (s, role) => `<span class="chip ${s === 'resolved' ? 'ok' : (s === 'open') === (role !== 'student') ? 'warn' : ''}">${t(...STATUS[s])}</span>`;
const plain = (s) => esc(s).replace(/\n/g, '<br>');

/* ============================================================ the student's side ============================================================ */
export async function route(view, rest) {
  if (rest) return renderThread(view, rest, 'student');
  const { items } = await get('/api/doubts');
  view.innerHTML = `<div class="crumbs"><a href="#/">${t('nav.home', 'Home')}</a> › 🙋 ${t('doubt.heading', 'Ask my teacher')}</div>
    <div class="row"><h1 style="margin:0">🙋 ${t('doubt.heading', 'Ask my teacher')}</h1><span class="spacer"></span><button class="btn primary" id="new">＋ ${t('doubt.new', 'New doubt')}</button></div>
    <p class="muted">${t('doubt.help', 'AIVidya can answer most doubts straight away. For the ones you want your own teacher to look at, send them here. Your teacher replies in this page and you get a notification.')}</p>
    ${items.length ? `<div class="list">${items.map((d) => `<a class="card pad row link" href="#/doubts/${d.id}"><div style="flex:1"><b>${esc(d.question)}</b><div class="muted small">${esc(d.class_name)}${d.topic ? ` · ${esc(d.topic)}` : ''} · ${timeAgo(d.updated_at)}</div>${d.last ? `<div class="small">${esc(d.last)}</div>` : ''}</div>${d.new ? `<span class="chip warn">${t('doubt.new.reply', 'New reply')}</span>` : chip(d.status, 'student')}</a>`).join('')}</div>`
    : `<p class="muted">${t('doubt.none', 'No doubts sent yet.')}</p>`}`;
  $('#new', view).onclick = () => askTeacher({}, () => route(view, ''));
}

/** The dialog for sending a doubt. `ctx`: { topic, question, aiAnswer } when it is opened from the chat. */
export async function askTeacher(ctx = {}, done) {
  let classes = [];
  try { classes = (await get('/api/me/assignments')).classes || []; } catch { /* shown below as "no class" */ }
  const m = openModal(classes.length ? `<div class="field"><label for="dq">${t('doubt.q', 'Your doubt')}</label><textarea id="dq" rows="4" maxlength="4000" autofocus>${esc(ctx.question || '')}</textarea></div>
      ${classes.length > 1 ? `<div class="field"><label for="dc">${t('doubt.class', 'Which class?')}</label><select id="dc">${classes.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('')}</select></div>` : ''}
      ${ctx.topic ? `<p class="muted small">${t('doubt.topic', 'About')}: <b>${esc(ctx.topic.title)}</b></p>` : ''}
      ${ctx.aiAnswer ? `<label class="check"><input type="checkbox" id="dai" checked> ${t('doubt.attach', 'Show my teacher what AIVidya answered')}</label>` : ''}
      <p class="error" id="de" role="alert" hidden></p><div class="row end"><button class="btn primary" id="dgo">${t('doubt.send', 'Send to my teacher')}</button></div>`
    : `<p>${t('doubt.noclass', 'You are not in a class yet. Ask your teacher for the class code and enter it here.')}</p><div class="field"><label for="cc">${t('doubt.code', 'Class code')}</label><input id="cc" type="text" autocapitalize="characters" maxlength="10" autofocus></div>
      <p class="error" id="de" role="alert" hidden></p><div class="row end"><button class="btn primary" id="join">${t('cls.join', 'Join class')}</button></div>`, { title: `🙋 ${t('doubt.heading', 'Ask my teacher')}` });
  const fail = (er) => { const x = $('#de', m.el); x.textContent = er.message; x.hidden = false; };
  $('#join', m.el)?.addEventListener('click', async () => { try { await api('/api/classes/join', { code: $('#cc', m.el).value, nickname: state.user?.display_name || 'Student', share_leaderboard: false }); m.close(); askTeacher(ctx, done); } catch (er) { fail(er); } });
  $('#dgo', m.el)?.addEventListener('click', async (e) => {
    e.currentTarget.disabled = true;
    try {
      const r = await api('/api/doubts', { class_id: $('#dc', m.el)?.value || classes[0].id, question: $('#dq', m.el).value, subtopic_id: ctx.topic?.id || '', ai_answer: $('#dai', m.el)?.checked ? ctx.aiAnswer.slice(0, 4000) : '' });
      m.close(); toast(t('doubt.sent', 'Sent to your teacher ✓')); if (done) done(r); else location.hash = `#/doubts/${r.id}`;
    } catch (er) { fail(er); e.currentTarget.disabled = false; }
  });
}

/* ============================================================ the conversation (both sides) ============================================================ */
async function renderThread(view, id, role) {
  let d;
  try { d = await get(`/api/doubts/${id}`); } catch (e) { view.innerHTML = `<div class="banner" role="alert">${esc(e.message)}</div>`; return; }
  const teacher = role !== 'student', back = teacher ? '#/teach/doubts' : '#/doubts';
  const bubble = (who, name, body, at) => `<div class="bubble ${who}"><div class="small muted">${esc(name)} · ${timeAgo(at)}</div><div>${plain(body)}</div></div>`;
  view.innerHTML = `<div class="crumbs"><a href="#/">${t('nav.home', 'Home')}</a> › <a href="${back}">🙋 ${teacher ? t('doubt.inbox', 'Doubts') : t('doubt.heading', 'Ask my teacher')}</a></div>
    <div class="row"><h1 style="margin:0">${esc(d.question)}</h1><span class="spacer"></span>${chip(d.status, role)}</div>
    <p class="muted small">${teacher ? `${esc(d.student)} · ` : ''}${esc(d.class_name)}${d.topic ? ` · ${d.subtopic_id && !d.subtopic_id.startsWith('my-') ? `<a href="#/learn/${esc(d.subtopic_id)}">${esc(d.topic)}</a>` : esc(d.topic)}` : ''}</p>
    <section class="card pad doubt-thread">${bubble('student', teacher ? d.student : t('doubt.you', 'You'), d.question_full, d.created_at)}
      ${d.ai_answer ? `<details class="ai-said"><summary>🤖 ${t('doubt.aisaid', 'What AIVidya answered (not checked by a teacher)')}</summary><div class="prose">${md(d.ai_answer)}</div></details>` : ''}
      ${d.messages.map((m) => bubble(m.role, m.role === 'teacher' ? (m.author || t('doubt.teacher', 'Teacher')) : (teacher ? d.student : t('doubt.you', 'You')), m.body, m.created_at)).join('')}</section>
    <section class="card pad"><div class="field"><label for="rb">${teacher ? t('doubt.reply', 'Your reply') : d.status === 'answered' ? t('doubt.followup', 'Still unsure? Ask more') : t('doubt.add', 'Add something')}</label><textarea id="rb" rows="3" maxlength="4000"></textarea></div>
      <p class="error" id="re" role="alert" hidden></p>
      <div class="row"><button class="btn primary" id="send">${teacher ? t('doubt.sendreply', 'Send reply') : t('doubt.sendmore', 'Send')}</button><span class="spacer"></span>
        ${d.status === 'resolved' ? `<button class="btn" id="reopen">${t('doubt.reopen', 'Reopen')}</button>` : `<button class="btn" id="clear">${teacher ? t('doubt.clear.t', 'Mark as cleared') : `✅ ${t('doubt.clear.s', 'Got it, clear this doubt')}`}</button>`}</div></section>`;
  const fail = (er) => { const x = $('#re', view); x.textContent = er.message; x.hidden = false; };
  $('#send', view).onclick = async (e) => { const body = $('#rb', view).value.trim(); if (!body) return; e.currentTarget.disabled = true; try { await api(`/api/doubts/${id}/reply`, { body }); renderThread(view, id, role); } catch (er) { fail(er); e.currentTarget.disabled = false; } };
  $('#clear', view)?.addEventListener('click', async () => { await api(`/api/doubts/${id}/resolve`, { resolved: true }); toast(t('doubt.cleared', 'Cleared ✓')); location.hash = back; });
  $('#reopen', view)?.addEventListener('click', async () => { await api(`/api/doubts/${id}/resolve`, { resolved: false }); renderThread(view, id, role); });
}

/* ============================================================ the teacher's inbox ============================================================ */
export async function renderInbox(view, id) {
  if (id) return renderThread(view, id, 'teacher');
  const q = new URLSearchParams(location.hash.split('?')[1] || ''), tab = q.get('s') || 'open', cls = q.get('c') || '';
  const [{ items, waiting }, { items: classes }] = await Promise.all([get(`/api/doubts?status=${tab}${cls ? `&class_id=${encodeURIComponent(cls)}` : ''}`), get('/api/classes')]);
  const link = (s, c) => `#/teach/doubts?s=${s}${c ? `&c=${encodeURIComponent(c)}` : ''}`;
  view.innerHTML = `<div class="row"><h1 style="margin:0">🙋 ${t('doubt.inbox', 'Doubts')} ${waiting ? `<span class="chip warn">${waiting}</span>` : ''}</h1></div>
    <p class="muted">${t('doubt.inbox.help', 'Doubts students send you from their classes. Answer here; they are notified. If AIVidya had already answered, you can see what it said.')}</p>
    <div class="tabs">${['open', 'answered', 'resolved'].map((s) => `<a class="tab" role="tab" aria-selected="${s === tab}" href="${link(s, cls)}">${t(...STATUS[s])}</a>`).join('')}</div>
    ${classes.length > 1 ? `<div class="field" style="margin-top:10px"><label for="cf">${t('doubt.class', 'Which class?')}</label><select id="cf"><option value="">${t('lib.any', 'Any')}</option>${classes.map((c) => `<option value="${esc(c.id)}" ${c.id === cls ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select></div>` : ''}
    ${items.length ? `<div class="list">${items.map((d) => `<a class="card pad row link" href="#/teach/doubts/${d.id}"><div style="flex:1"><b>${esc(d.question)}</b><div class="muted small">${esc(d.student)} · ${esc(d.class_name)}${d.topic ? ` · ${esc(d.topic)}` : ''} · ${timeAgo(d.updated_at)}</div></div>${d.new ? `<span class="chip warn">${t('doubt.new.badge', 'New')}</span>` : ''}</a>`).join('')}</div>`
    : `<p class="muted">${tab === 'open' ? t('doubt.empty.open', 'Nothing is waiting for you. 🎉') : t('doubt.empty', 'Nothing here.')}</p>`}`;
  $('#cf', view)?.addEventListener('change', (e) => { location.hash = link(tab, e.target.value); });
}
