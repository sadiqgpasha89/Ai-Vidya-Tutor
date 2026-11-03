// The administrator's console: its own pages and its own navigation, separate from the learner and teacher screens.
// (Text here is English: the console is for the people who run the service.)
import { api, get, put, del } from './api.js';
import { md, esc } from './render.js';
import { $, $$, toast, openModal, confirmDialog, promptDialog, fmtDate, fmtDateTime, timeAgo, barChart, debounce } from './ui.js';
import { state } from './state.js';

const qs = () => new URLSearchParams(location.hash.split('?')[1] || '');
const setQs = (patch) => { const p = qs(); for (const [k, v] of Object.entries(patch)) (v === '' || v == null ? p.delete(k) : p.set(k, v)); const path = location.hash.split('?')[0]; location.hash = `${path}${p.toString() ? `?${p}` : ''}`; };
const isAdmin = () => state.user.role === 'admin';
const head = (title, extra = '', sub = '') => `<div class="row adm-head"><div><h1 style="margin:0">${title}</h1>${sub ? `<p class="muted small" style="margin:2px 0 0">${sub}</p>` : ''}</div><span class="spacer"></span>${extra}</div>`;
const fail = (e) => toast(e.message || 'Something went wrong');
const mb = (b) => `${(b / 1048576).toFixed(b > 1048576 * 10 ? 0 : 1)} MB`;
const stat = (label, value, href, tone = '') => `<${href ? `a href="${href}"` : 'div'} class="card pad stat adm-stat ${tone}"><div class="muted small">${esc(label)}</div><b>${value}</b></${href ? 'a' : 'div'}>`;
const chip = (text, cls = '') => `<span class="chip ${cls}">${esc(text)}</span>`;
const statusChip = (s) => chip(s, s === 'approved' ? 'ok' : s === 'rejected' ? 'bad' : 'warn');
const pager = (total, offset, limit) => (total > limit ? `<div class="row adm-pager"><button class="btn sm" data-pg="${Math.max(0, offset - limit)}" ${offset <= 0 ? 'disabled' : ''}>← Previous</button><span class="muted small">${offset + 1}–${Math.min(offset + limit, total)} of ${total}</span><button class="btn sm" data-pg="${offset + limit}" ${offset + limit >= total ? 'disabled' : ''}>Next →</button></div>` : `<p class="muted small">${total} found</p>`);
const wirePager = (root) => $$('[data-pg]', root).forEach((b) => (b.onclick = () => setQs({ o: +b.dataset.pg || '' })));

const NAV = [
  ['Overview', [['', '🏠', 'Overview', 'admin']]],
  ['People', [['users', '👥', 'Users', 'school'], ['schools', '🏫', 'Schools', 'school']]],
  ['Topics and content', [['topics', '🧭', 'Topics and curriculum', 'school'], ['lessons', '📚', 'Lessons', 'admin'], ['custom', '💡', 'Student topics', 'admin']]],
  ['Run', [['jobs', '⚙️', 'Write lessons in bulk', 'admin'], ['announce', '📣', 'Announcements', 'admin']]],
  ['Insight', [['analytics', '📊', 'Analytics', 'admin'], ['audit', '🧾', 'Audit log', 'admin']]],
  ['System', [['system', '🩺', 'System and health', 'admin']]],
];
const LINKS = [['#/teach/review', 'Review queue'], ['#/teach/reports', 'Reports from students'], ['#/teach/bank', 'Question bank'], ['#/teach/library', 'Textbook library']];

let timer = null;
const stopTimer = () => { clearInterval(timer); timer = null; };

export async function route(view, rest) {
  stopTimer();
  const [page = '', id = ''] = rest.split('/');
  const scope = isAdmin() ? 'admin' : 'school';
  const allowed = NAV.flatMap(([, items]) => items).filter(([, , , need]) => need === 'school' || isAdmin());
  const current = allowed.find(([p]) => p === page) || allowed[0];
  view.innerHTML = `<div class="admin-shell"><nav class="admin-nav card" aria-label="Administration">
      <p class="admin-brand">🛠️ Admin console</p>
      ${NAV.map(([group, items]) => { const shown = items.filter(([, , , need]) => need === 'school' || scope === 'admin'); return shown.length ? `<p class="admin-group">${group}</p>${shown.map(([p, icon, label]) => `<a href="#/admin${p ? `/${p}` : ''}" ${p === current[0] ? 'aria-current="page"' : ''}>${icon} ${label}</a>`).join('')}` : ''; }).join('')}
      ${isAdmin() ? `<p class="admin-group">Also</p>${LINKS.map(([h, l]) => `<a href="${h}">${l}</a>`).join('')}` : ''}</nav>
    <section class="admin-main" id="admin-main" aria-live="polite"><p class="muted">Loading…</p></section></div>`;
  const main = $('#admin-main', view);
  const pages = { '': overview, users: id ? userDetail : users, schools, topics, lessons: id ? lessonDetail : lessons, custom, jobs, announce, analytics, audit, system };
  try { await (pages[current[0]] || overview)(main, id); } catch (e) { main.innerHTML = `<div class="banner" role="alert">${esc(e.message)}</div>`; }
}

/* ------------------------------------------------------------------ overview */
async function overview(m) {
  const o = await get('/api/admin/overview');
  const u = o.users, c = o.content, a = o.attention;
  const bar = `<div class="adm-bar" role="img" aria-label="${c.coverage}% of topics have a lesson"><i style="width:${c.coverage}%"></i></div>`;
  m.innerHTML = `${head('Overview', `<button class="btn" id="bk">💾 Back up now</button>`, `${u.total} people · ${c.topics_with_lesson} of ${c.topics} topics have a lesson`)}
    ${Object.values({ r: a.reports_open, d: a.drafts, f: a.flagged, g: a.guardrail_blocks_7d }).some(Boolean) ? `<section class="card pad"><h2 style="margin-top:0">Needs attention</h2><div class="adm-grid">
      ${a.reports_open ? stat('Open reports from students', a.reports_open, '#/teach/reports', 'warn') : ''}${a.drafts ? stat('Lessons waiting for review', a.drafts, '#/admin/lessons?status=draft', 'warn') : ''}
      ${a.flagged ? stat('Lessons the automatic check flagged', a.flagged, '#/admin/lessons?flagged=1', 'bad') : ''}${a.guardrail_blocks_7d ? stat('Messages the guardrails stopped (7 days)', a.guardrail_blocks_7d, '#/admin/audit?q=moderation_', '') : ''}</div></section>` : '<div class="banner ok">Nothing needs attention right now. ✅</div>'}
    <h2>People</h2><div class="adm-grid">${stat('Students', u.by_role.student || 0, '#/admin/users?role=student')}${stat('Teachers', u.by_role.teacher || 0, '#/admin/users?role=teacher')}${stat('Parents', u.by_role.parent || 0, '#/admin/users?role=parent')}
      ${stat('Administrators', (u.by_role.admin || 0) + (u.by_role.school_admin || 0), '#/admin/users?role=admin')}${stat('New this week', u.new_7d, '#/admin/users')}${stat('Active this week', u.active_7d, '#/admin/analytics')}
      ${stat('Awaiting parent approval', u.pending_consent, '#/admin/users?status=pending_consent')}${stat('Without a confirmed email', u.without_email, '#/admin/users?status=no_email')}${stat('Disabled', u.disabled, '#/admin/users?status=disabled')}</div>
    <h2>Content</h2><section class="card pad"><div class="row"><b>${c.coverage}% of topics have a lesson</b><span class="spacer"></span><a class="btn sm" href="#/admin/jobs">Write more lessons</a></div>${bar}</section>
    <div class="adm-grid">${stat('Lesson versions', c.versions, '#/admin/lessons')}${stat('Approved (in use)', c.by_status.approved || 0, '#/admin/lessons?status=approved')}${stat('Drafts (in use)', c.by_status.draft || 0, '#/admin/lessons?status=draft')}
      ${stat('Pictures made', c.extras.pic || 0)}${stat('Did-you-know sets', c.extras.dyk || 0)}${stat('5-minute summaries', c.extras.quick || 0)}${stat('Study notes saved', c.study_notes)}
      ${stat('Topics students added', c.custom_topics, '#/admin/custom')}${stat('Questions in the bank', c.questions, '#/teach/bank')}${stat('Textbooks in the library', c.library_docs, '#/teach/library')}${stat('Curriculum edits', c.curriculum_edits, '#/admin/topics')}</div>
    <h2>Right now</h2><div class="adm-grid">${stat('Model queue', `${o.queue.running}/${o.queue.limit} running · ${o.queue.waiting} waiting`, '#/admin/system')}${stat('Bulk jobs running', o.jobs_running, '#/admin/jobs')}</div>`;
  $('#bk', m).onclick = async () => { try { const r = await api('/api/admin/backup', {}); toast(`✓ ${r.file} (${mb(r.bytes)})`); } catch (e) { fail(e); } };
}

/* ------------------------------------------------------------------ users */
const ROLES = ['student', 'parent', 'teacher', 'school_admin', 'admin'];
async function users(m) {
  const p = qs(), q = p.get('q') || '', role = p.get('role') || '', status = p.get('status') || '', offset = +(p.get('o') || 0), limit = 50;
  const [r, schools] = await Promise.all([get(`/api/admin/users?q=${encodeURIComponent(q)}&role=${role}&status=${status}&offset=${offset}&limit=${limit}`), get('/api/admin/schools')]);
  const school = Object.fromEntries(schools.items.map((s) => [s.id, s.name]));
  m.innerHTML = `${head('Users', isAdmin() ? '<button class="btn primary" id="new">＋ New person</button>' : '')}
    <div class="row adm-filters"><input id="q" type="search" placeholder="Search name, username or email" value="${esc(q)}" aria-label="Search people"><select id="role" aria-label="Role"><option value="">All roles</option>${ROLES.map((x) => `<option ${x === role ? 'selected' : ''}>${x}</option>`).join('')}</select>
      <select id="status" aria-label="Status">${[['', 'Any status'], ['active', 'Active'], ['disabled', 'Disabled'], ['no_email', 'No confirmed email'], ['pending_consent', 'Awaiting parent approval']].map(([v, l]) => `<option value="${v}" ${v === status ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
    ${pager(r.total, offset, limit)}
    <div class="table-wrap"><table class="tt"><tr><th>Username</th><th>Name</th><th>Role</th><th>School</th><th>Email</th><th>Last sign-in</th><th>Status</th><th></th></tr>
    ${r.items.map((u) => `<tr><td><a href="#/admin/users/${u.id}">${esc(u.username)}</a></td><td>${esc(u.display_name)}</td><td>${esc(u.role)}</td><td>${esc(school[u.school_id] || '—')}</td><td class="small">${u.email ? `${esc(u.email)} ${u.email_verified ? '✓' : '(not confirmed)'}` : '—'}</td>
      <td>${u.last_login ? timeAgo(u.last_login) : '—'}</td><td>${u.disabled ? chip('disabled', 'bad') : u.consent === 'pending' ? chip('awaiting parent', 'warn') : chip('active', 'ok')}</td><td><a class="btn sm" href="#/admin/users/${u.id}">Open</a></td></tr>`).join('') || '<tr><td colspan="8" class="muted">Nobody matches.</td></tr>'}</table></div>`;
  wirePager(m);
  $('#q', m).oninput = debounce((e) => setQs({ q: e.target.value, o: '' }), 400);
  $('#role', m).onchange = (e) => setQs({ role: e.target.value, o: '' }); $('#status', m).onchange = (e) => setQs({ status: e.target.value, o: '' });
  $('#new', m)?.addEventListener('click', () => newPerson(schools.items));
}

function newPerson(schools) {
  const d = openModal(`<div class="field"><label for="nr">Role</label><select id="nr">${ROLES.map((x) => `<option>${x}</option>`).join('')}</select></div>
    <div class="field"><label for="nn">Name</label><input id="nn" type="text" maxlength="40" autofocus></div><div class="field"><label for="nu">Username</label><input id="nu" type="text" autocapitalize="none"></div>
    <div class="field"><label for="ne">Email (optional; counts as confirmed)</label><input id="ne" type="email"></div><div class="field" id="ng"><label for="nc">Class (students)</label><select id="nc">${[7, 8, 9, 10, 11, 12].map((g) => `<option ${g === 9 ? 'selected' : ''}>${g}</option>`).join('')}</select></div>
    <div class="field"><label for="ns">School</label><select id="ns"><option value="">None</option>${schools.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join('')}</select></div>
    <div class="field"><label for="np">Password (leave empty to make one up)</label><input id="np" type="text" autocomplete="off"></div><p class="error" id="ne2" role="alert" hidden></p>
    <div class="row end"><button class="btn primary" id="go">Create</button></div>`, { title: 'New person' });
  $('#nr', d.el).onchange = (e) => { $('#ng', d.el).hidden = e.target.value !== 'student'; };
  $('#go', d.el).onclick = async () => {
    try {
      const r = await api('/api/admin/users', { role: $('#nr', d.el).value, display_name: $('#nn', d.el).value, username: $('#nu', d.el).value, email: $('#ne', d.el).value, grade: +$('#nc', d.el).value, school_id: $('#ns', d.el).value || null, password: $('#np', d.el).value });
      d.close();
      if (r.password) openModal(`<p>Account created. Give this password to the person; it is shown <b>only now</b>:</p><div class="code-box" aria-label="Password">${esc(r.password)}</div>`, { title: 'Password' });
      else toast('Account created');
      location.hash = `#/admin/users/${r.id}`;
    } catch (e) { const x = $('#ne2', d.el); x.textContent = e.message; x.hidden = false; }
  };
}

async function userDetail(m, id) {
  const [u, schools] = await Promise.all([get(`/api/admin/users/${id}`), get('/api/admin/schools')]);
  const L = u.learning, me = u.id === state.user.id, canEdit = isAdmin();
  m.innerHTML = `${head(`${esc(u.display_name)} <small class="muted">@${esc(u.username)}</small>`, `<a class="btn" href="#/admin/users">← All users</a>`, `${esc(u.role)}${u.school ? ` · ${esc(u.school.name)}` : ''} · joined ${fmtDate(u.created_at)} · last sign-in ${u.last_login ? timeAgo(u.last_login) : 'never'}`)}
    <div class="adm-grid">${stat('Status', u.disabled ? 'Disabled' : 'Active', '', u.disabled ? 'bad' : '')}${stat('Email', u.email ? `${esc(u.email)} ${u.email_verified ? '✓' : '(not confirmed)'}` : 'none')}${stat('Signed in on', `${u.sessions} device${u.sessions === 1 ? '' : 's'}`)}${u.consent !== 'na' ? stat('Parent consent', esc(u.consent), '', u.consent === 'pending' ? 'warn' : '') : ''}</div>
    ${canEdit ? `<section class="card pad"><h2 style="margin-top:0">Manage</h2><div class="row adm-filters"><label>Name <input id="dn" value="${esc(u.display_name)}" maxlength="40"></label>
      <label>Role <select id="rl">${ROLES.map((x) => `<option ${x === u.role ? 'selected' : ''}>${x}</option>`).join('')}</select></label>
      <label>School <select id="sc"><option value="">None</option>${schools.items.map((s) => `<option value="${s.id}" ${s.id === u.school_id ? 'selected' : ''}>${esc(s.name)}</option>`).join('')}</select></label><button class="btn primary" id="save">Save</button></div>
      <div class="row" style="margin-top:10px"><button class="btn" id="pw">🔑 Reset password</button><button class="btn" id="so">⏏ Sign out everywhere</button><button class="btn ${u.disabled ? '' : 'danger'}" id="dis" ${me ? 'disabled' : ''}>${u.disabled ? 'Enable account' : 'Disable account'}</button><span class="spacer"></span><button class="btn danger" id="rm" ${me ? 'disabled' : ''}>🗑 Delete account</button></div></section>` : ''}
    ${L ? `<section class="card pad"><h2 style="margin-top:0">Learning</h2><div class="adm-grid">${stat('Grade', u.profile?.grade ?? '—')}${stat('Topics started', L.topics_started)}${stat('Topics completed', L.topics_completed)}${stat('XP', L.xp)}${stat('Day streak', L.streak)}${stat('Own topics', L.custom_topics)}${stat('Study notes', L.study_notes)}</div>
      ${L.classes.length ? `<p class="small">Classes: ${L.classes.map((c) => esc(c.name)).join(', ')}</p>` : ''}${L.parents.length ? `<p class="small">Parents: ${L.parents.map((p) => `<a href="#/admin/users/${p.id}">${esc(p.name)}</a>`).join(', ')}</p>` : ''}</section>` : ''}
    ${u.children?.length ? `<section class="card pad"><h2 style="margin-top:0">Children</h2><p>${u.children.map((c) => `<a href="#/admin/users/${c.id}">${esc(c.display_name)}</a>`).join(', ')}</p></section>` : ''}
    ${u.classes_taught?.length ? `<section class="card pad"><h2 style="margin-top:0">Classes taught</h2><p>${u.classes_taught.map((c) => `${esc(c.name)} (class ${c.grade ?? '—'})`).join(', ')}</p></section>` : ''}
    <section class="card pad"><h2 style="margin-top:0">Recent activity</h2><table class="tt">${u.recent_activity.map((a) => `<tr><td>${fmtDateTime(a.ts)}</td><td>${esc(a.action)}</td><td class="small">${esc(a.target || '')}</td></tr>`).join('') || '<tr><td class="muted">Nothing recorded.</td></tr>'}</table></section>`;
  if (!canEdit) return;
  const reload = () => userDetail(m, id);
  const patch = (extra = {}) => put(`/api/admin/users/${id}`, { role: $('#rl', m).value, school_id: $('#sc', m).value || null, display_name: $('#dn', m).value, ...extra });
  $('#save', m).onclick = () => patch().then(() => { toast('Saved'); reload(); }).catch(fail);
  $('#dis', m).onclick = async () => { if (u.disabled || await confirmDialog(`Disable ${u.username}? They are signed out at once and cannot sign in.`, { danger: true, yes: 'Disable' })) patch({ disabled: !u.disabled }).then(reload).catch(fail); };
  $('#so', m).onclick = () => api(`/api/admin/users/${id}/signout`, {}).then((r) => toast(`Signed out of ${r.sessions} device${r.sessions === 1 ? '' : 's'}`)).then(reload).catch(fail);
  $('#pw', m).onclick = async () => {
    const typed = await promptDialog('New password (leave empty to make one up)', { ok: 'Reset' }); if (typed === null) return;
    try { const r = await api(`/api/admin/users/${id}/password`, { new_password: typed }); openModal(r.password ? `<p>The new password (shown <b>only now</b>):</p><div class="code-box" aria-label="Password">${esc(r.password)}</div>` : '<p>The password has been changed and the person is signed out everywhere.</p>', { title: 'Password reset' }); } catch (e) { fail(e); }
  };
  $('#rm', m).onclick = async () => {
    if (!(await confirmDialog(`Delete ${u.username} and everything they have made? This cannot be undone.`, { danger: true, yes: 'Delete forever' }))) return;
    const typed = await promptDialog(`Type the username (${u.username}) to confirm`, { ok: 'Delete' }); if (typed !== u.username) return toast('That did not match: nothing was deleted');
    del(`/api/admin/users/${id}`).then(() => { toast('Deleted'); location.hash = '#/admin/users'; }).catch(fail);
  };
}

/* ------------------------------------------------------------------ schools */
async function schools(m) {
  const { items } = await get('/api/admin/schools');
  m.innerHTML = `${head('Schools', isAdmin() ? '<button class="btn primary" id="new">＋ New school</button>' : '')}<p class="muted">People join a school by typing its code when they sign up.</p>
    <div class="table-wrap"><table class="tt"><tr><th>School</th><th>Join code</th><th>People</th><th>Classes</th><th>Created</th>${isAdmin() ? '<th></th>' : ''}</tr>
    ${items.map((s) => `<tr data-id="${s.id}"><td><b>${esc(s.name)}</b></td><td><code>${esc(s.code)}</code></td><td><a href="#/admin/users?q=">${s.people}</a></td><td>${s.classes}</td><td>${fmtDate(s.created_at)}</td>${isAdmin() ? '<td><button class="btn sm" data-rn>Rename</button> <button class="btn sm" data-code>New code</button> <button class="btn sm danger" data-rm>Delete</button></td>' : ''}</tr>`).join('') || '<tr><td colspan="6" class="muted">No schools yet.</td></tr>'}</table></div>`;
  $('#new', m)?.addEventListener('click', async () => { const name = await promptDialog('School name', { ok: 'Create' }); if (name) api('/api/admin/schools', { name }).then((r) => { toast(`Created. Join code: ${r.code}`, 8000); schools(m); }).catch(fail); });
  $$('tr[data-id]', m).forEach((tr) => {
    const id = tr.dataset.id, s = items.find((x) => x.id === id);
    $('[data-rn]', tr)?.addEventListener('click', async () => { const name = await promptDialog('School name', { value: s.name }); if (name) put(`/api/admin/schools/${id}`, { name }).then(() => schools(m)).catch(fail); });
    $('[data-code]', tr)?.addEventListener('click', async () => { if (await confirmDialog('Make a new join code? The old code stops working.', { yes: 'New code' })) api(`/api/admin/schools/${id}/code`, {}).then((r) => { toast(`New code: ${r.code}`, 8000); schools(m); }).catch(fail); });
    $('[data-rm]', tr)?.addEventListener('click', async () => { if (await confirmDialog(`Delete ${s.name}?`, { danger: true, yes: 'Delete' })) del(`/api/admin/schools/${id}`).then(() => schools(m)).catch(fail); });
  });
}

/* ------------------------------------------------------------------ topics and curriculum */
async function topics(m) {
  const p = qs(), subject = p.get('s') || 'physics', grade = +(p.get('g') || 9), showHidden = p.get('h') !== '0';
  const r = await get(`/api/admin/curriculum?subject=${subject}&grade=${grade}`);
  const origin = { syllabus: ['Syllabus', ''], board: ['Board', 'ai'], level: ['Challenge', 'ai'], added: ['Added by you', 'ok'] };
  m.innerHTML = `${head('Topics and curriculum', `<button class="btn" id="undo" ${r.edits ? '' : 'disabled'}>↶ Undo last edit (${r.edits})</button><button class="btn primary" id="addc">＋ Chapter</button>`, 'Edits are layered on top of the syllabus files, which are never changed. Every edit is logged.')}
    <div class="row adm-filters"><select id="cs" aria-label="Subject">${state.meta.subjects.map((s) => `<option value="${s.id}" ${s.id === subject ? 'selected' : ''}>${esc(s.name)}</option>`).join('')}</select>
      <select id="cg" aria-label="Class">${state.meta.grades.map((g) => `<option ${g === grade ? 'selected' : ''}>${g}</option>`).join('')}</select><label class="check"><input type="checkbox" id="hid" ${showHidden ? 'checked' : ''}> Show hidden items</label>
      ${isAdmin() ? '<button class="btn" id="bulk">⚙️ Write all lessons for this class</button>' : ''}</div>
    ${r.chapters.filter((c) => showHidden || !c.hidden).map((c) => `<section class="card pad ${c.hidden ? 'adm-dim' : ''}" data-id="${c.id}"><div class="row"><b>${c.number ? `${c.number}. ` : ''}${esc(c.title)}</b>${chip(...origin[c.origin])}${c.board ? chip(c.board.replace('not-', 'not ')) : ''}${c.hidden ? chip('hidden from students', 'bad') : ''}<span class="spacer"></span>
      <button class="btn sm" data-rn>✏️ Rename</button><button class="btn sm" data-as>＋ Topic</button><button class="btn sm" data-hide>${c.hidden ? '👁 Show' : '🙈 Hide'}</button>${isAdmin() ? '<button class="btn sm" data-wr>⚙️ Write lessons</button>' : ''}</div>
      <ul class="plain adm-topics">${c.subtopics.map((s) => `<li class="row ${s.hidden ? 'adm-dim' : ''}" data-sid="${s.id}"><span>${esc(s.title)}</span>${s.hidden ? chip('hidden', 'bad') : ''}${s.lessons ? chip('lesson written', 'ok') : chip('no lesson yet')}<span class="spacer"></span>
        ${s.hidden ? '<button class="btn sm" data-us>Show</button>' : `<a class="btn sm" href="#/learn/${s.id}">Open</a>${isAdmin() ? `<a class="btn sm" href="#/admin/lessons?q=${encodeURIComponent(s.id)}">Versions</a><button class="btn sm" data-cl title="Delete its pictures, summaries and facts (made again when needed), or the whole lesson">Clear…</button>` : ''}<button class="icon-btn small" data-rs aria-label="Rename topic">✏️</button><button class="icon-btn small" data-hs aria-label="Hide topic">🙈</button>`}</li>`).join('')}</ul></section>`).join('') || '<p class="muted">Nothing here.</p>'}`;
  const edit = (body) => api('/api/admin/curriculum/edit', body).then(() => { state.curriculumCache = {}; topics(m); }).catch(fail);
  const goto = (s, g, h) => { location.hash = `#/admin/topics?s=${s}&g=${g}&h=${h ? 1 : 0}`; };
  $('#cs', m).onchange = (e) => goto(e.target.value, grade, showHidden); $('#cg', m).onchange = (e) => goto(subject, e.target.value, showHidden); $('#hid', m).onchange = (e) => goto(subject, grade, e.target.checked);
  $('#undo', m).onclick = async () => { if (await confirmDialog('Take back the most recent edit?', { yes: 'Undo' })) api('/api/admin/curriculum/undo', {}).then((x) => { toast(`Undone: ${x.undone.op}`); state.curriculumCache = {}; topics(m); }).catch(fail); };
  $('#addc', m).onclick = async () => { const title = await promptDialog('Chapter title'); if (!title) return; const subs = await promptDialog('Topics in it, separated by ;'); edit({ op: 'add_chapter', subject, grade, title, subtopics: (subs || '').split(';').map((x) => x.trim()).filter(Boolean) }); };
  $('#bulk', m)?.addEventListener('click', () => bulkDialog({ subject, grade }));
  $$('section[data-id]', m).forEach((sec) => {
    const id = sec.dataset.id, c = r.chapters.find((x) => x.id === id);
    $('[data-rn]', sec).onclick = async () => { const v = await promptDialog('Chapter title', { value: c.title }); if (v) edit({ op: 'rename_chapter', id, title: v }); };
    $('[data-as]', sec).onclick = async () => { const v = await promptDialog('Topic title'); if (v) edit({ op: 'add_subtopic', chapter: id, title: v }); };
    $('[data-hide]', sec).onclick = async () => { if (c.hidden || await confirmDialog('Hide this chapter from students?', { danger: true, yes: 'Hide' })) edit({ op: 'hide_chapter', id, hidden: !c.hidden }); };
    $('[data-wr]', sec)?.addEventListener('click', () => bulkDialog({ subject, grade, chapter: c }));
    $$('li[data-sid]', sec).forEach((li) => {
      const sid = li.dataset.sid, s = c.subtopics.find((x) => x.id === sid);
      $('[data-rs]', li)?.addEventListener('click', async () => { const v = await promptDialog('Topic title', { value: s.title }); if (v) edit({ op: 'rename_subtopic', id: sid, title: v }); });
      $('[data-hs]', li)?.addEventListener('click', async () => { if (await confirmDialog('Hide this topic from students?', { danger: true, yes: 'Hide' })) edit({ op: 'hide_subtopic', id: sid }); });
      $('[data-us]', li)?.addEventListener('click', () => edit({ op: 'unhide_subtopic', id: sid }));
      $('[data-cl]', li)?.addEventListener('click', () => clearDialog(sid, s.title, () => topics(m)));
    });
  });
}

function clearDialog(sid, title, done) {
  const d = openModal(`<p>What should be cleared for <b>${esc(title)}</b>?</p>
    <div class="col"><button class="btn" id="c1">🖼 Pictures, facts, summaries and cheat sheets</button><p class="muted small" style="margin:0 0 8px">They are made again, quietly, the next time they are needed. The lesson stays.</p>
    <button class="btn danger" id="c2">📚 The lesson as well</button><p class="muted small" style="margin:0">Every version of the lesson is deleted, along with students' saved notes for it. It is written again the next time a student opens the topic.</p></div>`, { title: 'Clear a topic' });
  const go = (what) => api(`/api/admin/topics/${encodeURIComponent(sid)}/clear`, { what }).then((r) => { d.close(); toast(`Cleared ${r.extras} extras${r.lessons ? `, ${r.lessons} lesson version(s)` : ''}`); done(); }).catch(fail);
  $('#c1', d.el).onclick = () => go('extras');
  $('#c2', d.el).onclick = async () => { if (await confirmDialog('Delete every version of this lesson?', { danger: true, yes: 'Delete lesson' })) go('lessons'); };
}

function bulkDialog({ subject, grade, chapter }) {
  const d = openModal(`<p>Write the lessons for <b>${esc(chapter ? chapter.title : `all of class ${grade}`)}</b> now, one after another in the background. Lessons already written are skipped.</p>
    <div class="row adm-filters"><label>Language <select id="bl">${state.meta.languages.map((l) => `<option value="${l.id}">${esc(l.name)}</option>`).join('')}</select></label>
    <label>Level <select id="bv">${state.meta.levels.map((l) => `<option value="${l.id}" ${l.id === 'standard' ? 'selected' : ''}>${esc(l.label)}</option>`).join('')}</select></label><label>Board <select id="bb">${state.meta.boards.map((b) => `<option>${esc(b)}</option>`).join('')}</select></label></div>
    <label class="check"><input type="checkbox" id="bx"> Also make pictures, facts, summary and cheat sheet</label><label class="check"><input type="checkbox" id="bf"> Write them again even if they exist</label>
    <p class="error" id="be" role="alert" hidden></p><div class="row end"><button class="btn primary" id="go">Start</button></div>`, { title: 'Write lessons in bulk' });
  $('#go', d.el).onclick = async () => {
    try { const j = await api('/api/admin/jobs', { subject, grade, chapter_id: chapter?.id || null, language: $('#bl', d.el).value, level: $('#bv', d.el).value, board: $('#bb', d.el).value, extras: $('#bx', d.el).checked, force: $('#bf', d.el).checked }); d.close(); toast(`Started: ${j.total} topics`); location.hash = '#/admin/jobs'; }
    catch (e) { const x = $('#be', d.el); x.textContent = e.message; x.hidden = false; }
  };
}

/* ------------------------------------------------------------------ lessons */
async function lessons(m) {
  const p = qs(), status = p.get('status') || '', q = p.get('q') || '', subject = p.get('s') || '', grade = p.get('g') || '', flagged = p.get('flagged') === '1', offset = +(p.get('o') || 0), limit = 50;
  const query = new URLSearchParams({ offset, limit }); for (const [k, v] of Object.entries({ status, q, subject, grade })) if (v) query.set(k, v); if (flagged) query.set('flagged', 'true');
  const r = await get(`/api/admin/lessons?${query}`);
  m.innerHTML = `${head('Lessons', '', 'Every version of every lesson that has been written. Students see the one marked “in use”.')}
    <div class="row adm-filters"><input id="q" type="search" placeholder="Search topic or chapter" value="${esc(q)}" aria-label="Search lessons"><select id="st" aria-label="Status">${[['', 'Any status'], ['draft', 'Draft'], ['approved', 'Approved'], ['rejected', 'Rejected']].map(([v, l]) => `<option value="${v}" ${v === status ? 'selected' : ''}>${l}</option>`).join('')}</select>
      <select id="sj" aria-label="Subject"><option value="">All subjects</option>${state.meta.subjects.map((s) => `<option value="${s.id}" ${s.id === subject ? 'selected' : ''}>${esc(s.name)}</option>`).join('')}</select>
      <select id="gr" aria-label="Class"><option value="">All classes</option>${state.meta.grades.map((g) => `<option ${String(g) === grade ? 'selected' : ''}>${g}</option>`).join('')}</select><label class="check"><input type="checkbox" id="fl" ${flagged ? 'checked' : ''}> Flagged only</label></div>
    ${pager(r.total, offset, limit)}<div class="table-wrap"><table class="tt"><tr><th>Topic</th><th>Class</th><th>Language · level</th><th>Version</th><th>Status</th><th>Check</th><th>Written</th><th></th></tr>
    ${r.items.map((l) => `<tr><td><a href="#/admin/lessons/${l.id}">${esc(l.title)}</a><div class="muted small">${esc(l.subject_name || '')} · ${esc(l.chapter || '')}</div></td><td>${l.grade ?? '—'}</td><td class="small">${esc(l.variant)}</td><td>v${l.version} ${l.active ? chip('in use', 'ok') : ''} ${l.source === 'teacher' ? chip('teacher', 'ai') : ''}</td><td>${statusChip(l.status)}</td>
      <td>${l.issues == null ? '—' : l.high_issues ? chip(`${l.high_issues} serious`, 'bad') : chip(`${l.issues} minor`, l.issues ? 'warn' : 'ok')}</td><td class="small">${fmtDate(l.created_at)}</td><td><a class="btn sm" href="#/admin/lessons/${l.id}">Open</a></td></tr>`).join('') || '<tr><td colspan="8" class="muted">No lessons match.</td></tr>'}</table></div>`;
  wirePager(m);
  $('#q', m).oninput = debounce((e) => setQs({ q: e.target.value, o: '' }), 400);
  $('#st', m).onchange = (e) => setQs({ status: e.target.value, o: '' }); $('#sj', m).onchange = (e) => setQs({ s: e.target.value, o: '' }); $('#gr', m).onchange = (e) => setQs({ g: e.target.value, o: '' }); $('#fl', m).onchange = (e) => setQs({ flagged: e.target.checked ? '1' : '', o: '' });
}

async function lessonDetail(m, id) {
  const v = await get(`/api/admin/lessons/${id}`);
  const others = (await get(`/api/review/topic/${encodeURIComponent(v.subtopic_id)}?variant=${encodeURIComponent(v.variant)}`).catch(() => ({ versions: [] }))).versions;
  const issues = v.factcheck?.issues || [];
  m.innerHTML = `${head(esc(v.title || v.subtopic_id), '<a class="btn" href="#/admin/lessons">← All lessons</a>', `${esc(v.subject_name || '')} · class ${v.grade ?? '—'} · ${esc(v.variant)} · version ${v.version} · written ${fmtDate(v.created_at)} by ${esc(v.model || v.source)}`)}
    <section class="card pad"><div class="row">${statusChip(v.status)}${v.is_active ? chip('in use', 'ok') : chip('not shown to students')}<span class="spacer"></span>
      <button class="btn ok" data-s="approved">✅ Approve</button><button class="btn" data-s="draft">Back to draft</button><button class="btn danger" data-s="rejected">Reject</button>${v.is_active ? '' : '<button class="btn" id="act">Show this version</button>'}
      <a class="btn" href="#/learn/${v.subtopic_id}">Open as a student</a><button class="btn danger" id="del">🗑 Delete version</button></div>${v.review_note ? `<p class="small">Review note: ${esc(v.review_note)}</p>` : ''}</section>
    ${others.length > 1 ? `<section class="card pad"><b>Versions of this lesson</b><div class="row" style="flex-wrap:wrap;margin-top:6px">${others.map((o) => `<a class="chip ${o.id === v.id ? 'ok' : ''}" href="#/admin/lessons/${o.id}">v${o.version} · ${esc(o.status)}${o.is_active ? ' · in use' : ''}</a>`).join('')}</div></section>` : ''}
    ${issues.length ? `<section class="card pad"><b>Automatic fact-check (${issues.length})</b><ul>${issues.map((i) => `<li>${chip(i.severity, i.severity === 'high' ? 'bad' : 'warn')} <b>${esc(i.title || '')}</b> ${esc(i.claim || '')}: ${esc(i.problem || '')}</li>`).join('')}</ul></section>` : ''}
    ${v.sections.map((s) => `<section class="card pad"><div class="row"><b>${esc(s.title)}</b>${chip(s.kind)}</div><div class="prose">${md(s.display)}</div><details><summary class="small muted">What is read aloud</summary><p class="small">${esc(s.speech)}</p></details></section>`).join('')}`;
  $$('[data-s]', m).forEach((b) => (b.onclick = async () => {
    const note = b.dataset.s === 'draft' ? '' : await promptDialog(`Note for the record (optional)`, { ok: b.dataset.s === 'approved' ? 'Approve' : 'Reject' }); if (note === null) return;
    api(`/api/admin/lessons/${id}/status`, { status: b.dataset.s, note: note || '' }).then(() => { toast('Saved'); lessonDetail(m, id); }).catch(fail);
  }));
  $('#act', m)?.addEventListener('click', () => api(`/api/admin/lessons/${id}/activate`, {}).then(() => { toast('Students now see this version'); lessonDetail(m, id); }).catch(fail));
  $('#del', m).onclick = async () => { if (await confirmDialog('Delete this version, with the pictures and summaries made from it?', { danger: true, yes: 'Delete' })) del(`/api/admin/lessons/${id}`).then(() => { toast('Deleted'); location.hash = '#/admin/lessons'; }).catch(fail); };
}

/* ------------------------------------------------------------------ topics students added */
async function custom(m) {
  const p = qs(), q = p.get('q') || '', offset = +(p.get('o') || 0), limit = 50;
  const r = await get(`/api/admin/custom-topics?q=${encodeURIComponent(q)}&offset=${offset}&limit=${limit}`);
  m.innerHTML = `${head('Student topics', '', 'Topics students typed in themselves. Only the student can open the lesson; you can see the title so unsuitable ones can be removed.')}
    <input id="q" type="search" placeholder="Search topic or student" value="${esc(q)}" aria-label="Search">${pager(r.total, offset, limit)}
    <div class="table-wrap"><table class="tt"><tr><th>Topic</th><th>Student</th><th>Class</th><th>Subject</th><th>Lesson</th><th>Added</th><th></th></tr>
    ${r.items.map((t) => `<tr data-id="${t.id}"><td><b>${esc(t.title)}</b>${t.details ? `<div class="muted small">${esc(t.details)}</div>` : ''}</td><td>${esc(t.display_name || '—')} <span class="muted small">@${esc(t.username || '')}</span></td><td>${t.grade}</td><td>${esc(t.subject)}</td><td>${t.lessons ? 'written' : '—'}</td><td class="small">${fmtDate(t.created_at)}</td><td><button class="btn sm danger" data-rm>Remove</button></td></tr>`).join('') || '<tr><td colspan="7" class="muted">None.</td></tr>'}</table></div>`;
  wirePager(m); $('#q', m).oninput = debounce((e) => setQs({ q: e.target.value, o: '' }), 400);
  $$('tr[data-id]', m).forEach((tr) => ($('[data-rm]', tr).onclick = async () => { if (await confirmDialog('Remove this topic and its lesson, notes and chat? The student is not told.', { danger: true, yes: 'Remove' })) del(`/api/admin/custom-topics/${tr.dataset.id}`).then(() => custom(m)).catch(fail); }));
}

/* ------------------------------------------------------------------ bulk jobs */
async function jobs(m) {
  const { items } = await get('/api/admin/jobs');
  const active = items.some((j) => ['queued', 'running'].includes(j.status));
  m.innerHTML = `${head('Write lessons in bulk', '<a class="btn primary" href="#/admin/topics">Choose a chapter or class</a>', 'Lessons are written one at a time in the background, behind any student who is waiting. The list is forgotten when the server restarts; the lessons themselves are kept.')}
    ${items.length ? items.map((j) => { const pct = Math.round(100 * (j.done + j.skipped + j.failed) / j.total); return `<section class="card pad" data-id="${j.id}"><div class="row"><b>${esc(j.title)}</b>${chip(j.status, j.status === 'done' ? 'ok' : j.status === 'failed' ? 'bad' : j.status === 'cancelled' ? '' : 'warn')}<span class="spacer"></span>${['queued', 'running'].includes(j.status) ? '<button class="btn sm danger" data-cancel>Stop</button>' : ''}</div>
      <div class="adm-bar" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><i style="width:${pct}%"></i></div>
      <p class="small muted">${j.done} written · ${j.skipped} already there · ${j.failed} failed · ${j.total} topics${j.current ? ` · now: ${esc(j.current)}` : ''}${j.extras ? ' · with pictures and summaries' : ''} · started ${timeAgo(j.created_at)}</p>${j.errors.length ? `<details><summary class="small">Problems (${j.errors.length})</summary><ul class="small">${j.errors.map((e) => `<li>${esc(e)}</li>`).join('')}</ul></details>` : ''}</section>`; }).join('') : '<p class="muted">No jobs yet. Open <a href="#/admin/topics">Topics and curriculum</a> and press “Write lessons” on a chapter, or “Write all lessons for this class”.</p>'}`;
  $$('section[data-id]', m).forEach((s) => $('[data-cancel]', s)?.addEventListener('click', () => api(`/api/admin/jobs/${s.dataset.id}/cancel`, {}).then(() => jobs(m)).catch(fail)));
  if (active) timer = setInterval(() => { if (!m.isConnected || !location.hash.startsWith('#/admin/jobs')) return stopTimer(); jobs(m); }, 3000);
}

/* ------------------------------------------------------------------ announcements */
async function announce(m) {
  const { items } = await get('/api/admin/schools');
  m.innerHTML = `${head('Announcements', '', 'A notice that appears under the 🔔 bell of everyone in the audience. Nothing is emailed.')}
    <form class="card pad" id="f" novalidate><div class="field"><label for="at">Title</label><input id="at" maxlength="120" required></div><div class="field"><label for="ab">Message (optional)</label><textarea id="ab" rows="4" maxlength="600"></textarea></div>
      <div class="row adm-filters"><label>Send to <select id="aa"><option value="all">Everyone</option><option value="students">All students</option><option value="parents">All parents</option><option value="teachers">All teachers</option><option value="school">One school</option></select></label>
      <label id="sw" hidden>School <select id="as">${items.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join('')}</select></label></div>
      <div class="field"><label for="al">Link (optional: #/… inside the app, or https://…)</label><input id="al" maxlength="200" placeholder="#/"></div><p class="error" id="er" role="alert" hidden></p><div class="row end"><button class="btn primary" type="submit">Send</button></div></form>`;
  $('#aa', m).onchange = (e) => { $('#sw', m).hidden = e.target.value !== 'school'; };
  $('#f', m).onsubmit = async (e) => {
    e.preventDefault(); const aud = $('#aa', m).value, label = $('#aa', m).selectedOptions[0].textContent;
    if (!(await confirmDialog(`Send this notice to ${label.toLowerCase()}?`, { yes: 'Send' }))) return;
    try { const r = await api('/api/admin/announce', { title: $('#at', m).value, body: $('#ab', m).value, audience: aud, school_id: aud === 'school' ? $('#as', m).value : null, link: $('#al', m).value }); toast(`Sent to ${r.recipients} ${r.recipients === 1 ? 'person' : 'people'}`); $('#f', m).reset(); $('#sw', m).hidden = true; $('#er', m).hidden = true; }
    catch (er) { $('#er', m).textContent = er.message; $('#er', m).hidden = false; }
  };
}

/* ------------------------------------------------------------------ analytics and audit */
async function analytics(m) {
  const days = +(qs().get('d') || 14), a = await get(`/api/admin/analytics?days=${days}`);
  const byDay = {}; a.model_by_day.forEach((r) => { byDay[r.day] ||= { calls: 0, tin: 0, tout: 0, ms: 0, n: 0, errors: 0 }; const x = byDay[r.day]; x.calls += r.calls; x.tin += r.tin || 0; x.tout += r.tout || 0; x.ms += (r.ms || 0) * r.calls; x.n += r.calls; x.errors += r.errors || 0; });
  const rows = Object.entries(byDay).map(([day, v]) => ({ day, ...v }));
  m.innerHTML = `${head('Analytics', `<select id="dd" aria-label="Days">${[7, 14, 30, 90].map((d) => `<option ${d === days ? 'selected' : ''}>${d}</option>`).join('')}</select>`)}
    <div class="adm-grid">${[['Active (7 days)', a.active_7d], ['Active (30 days)', a.active_30d], ['Lessons written', a.lessons.generated], ['Lessons approved', a.lessons.approved], ['Awaiting review', a.lessons.drafts], ['Open reports', a.reports_open], ['Average mastery', `${Math.round(a.learning.avg_mastery * 100)}%`], ['Average test score', a.learning.avg_test_percent != null ? `${a.learning.avg_test_percent}%` : '—'], ['Topics completed', a.learning.topics_completed], ['Tokens used', ((a.tokens.input || 0) + (a.tokens.output || 0)).toLocaleString()], ['👍 / 👎 on answers', `${a.feedback.up} / ${a.feedback.down}`]].map(([l, v]) => stat(l, v)).join('')}</div>
    <div class="grid2"><section class="card pad"><h2>Active people per day</h2>${a.active_by_day.length ? barChart(a.active_by_day, { label: (r) => r.day, value: (r) => r.users }) : '<p class="muted">—</p>'}</section><section class="card pad"><h2>Model calls per day</h2>${rows.length ? barChart(rows, { label: (r) => r.day, value: (r) => r.calls, color: '#16a34a' }) : '<p class="muted">—</p>'}</section></div>
    <section class="card pad"><h2>Model usage</h2><div class="table-wrap"><table class="tt"><tr><th>Day</th><th>Calls</th><th>Tokens in</th><th>Tokens out</th><th>Avg latency</th><th>Errors</th></tr>${rows.map((r) => `<tr><td>${esc(r.day)}</td><td>${r.calls}</td><td>${r.tin.toLocaleString()}</td><td>${r.tout.toLocaleString()}</td><td>${Math.round(r.ms / (r.n || 1))} ms</td><td>${r.errors}</td></tr>`).join('')}</table></div></section>`;
  $('#dd', m).onchange = (e) => setQs({ d: e.target.value });
}

async function audit(m) {
  const action = qs().get('a') || '', q = qs().get('q') || '';
  const [{ items }, acts] = await Promise.all([get(`/api/admin/audit?q=${encodeURIComponent(q)}${action ? `&action=${encodeURIComponent(action)}` : ''}`), get('/api/admin/audit/actions')]);
  m.innerHTML = `${head('Audit log', '', 'Who did what, newest first. Passwords and messages are never recorded here.')}
    <div class="row adm-filters"><select id="af" aria-label="Action"><option value="">Every action</option>${acts.items.map((a) => `<option ${a === action ? 'selected' : ''}>${esc(a)}</option>`).join('')}</select><input id="aq" type="search" placeholder="Search target or detail" value="${esc(q)}" aria-label="Search"></div>
    <div class="table-wrap"><table class="tt"><tr><th>Time</th><th>Action</th><th>Actor</th><th>Target</th><th>Detail</th><th>IP</th></tr>${items.map((a) => `<tr><td>${fmtDateTime(a.ts)}</td><td>${esc(a.action)}</td><td class="small">${esc(a.actor_id || '—')}</td><td class="small">${esc(a.target || '')}</td><td class="small">${esc(a.detail || '')}</td><td class="small">${esc(a.ip || '')}</td></tr>`).join('') || '<tr><td colspan="6" class="muted">Nothing recorded.</td></tr>'}</table></div>`;
  $('#af', m).onchange = (e) => setQs({ a: e.target.value }); $('#aq', m).onchange = (e) => setQs({ q: e.target.value });
}

/* ------------------------------------------------------------------ system */
async function system(m) {
  const [h, s] = await Promise.all([get('/api/admin/health'), get('/api/admin/system')]);
  const cfg = s.settings, st = s.storage;
  m.innerHTML = `${head('System and health', '<button class="btn primary" id="bk">💾 Back up now</button>')}
    <div class="adm-grid">${stat('Model', `${esc(h.model.name)} ${chip(h.model.ready ? 'ready' : h.model.problem || 'not ready', h.model.ready ? 'ok' : 'bad')}`)}${stat('Model queue', `${h.queue.running}/${h.queue.limit} running · ${h.queue.waiting} waiting`)}
      ${stat('Voice', `speech: ${esc(h.voice.tts_languages.join(', ') || 'off')} · listening: ${h.voice.stt ? 'on' : 'off'}`)}${stat('Email', s.channels.email ? '✓ set up' : 'not set up (sign-up codes go to the server log)', '', s.channels.email ? '' : 'warn')}
      ${stat('Web push', s.channels.push ? '✓ set up' : 'off')}${stat('WhatsApp', s.channels.whatsapp ? '✓ set up' : 'off')}${stat('Database', `${mb(st.db_bytes)} · schema v${h.schema}`)}${stat('Voice cache', `${mb(st.tts_cache_bytes)} · ${st.tts_cache_files} files`)}
      ${stat('Signed-in sessions', s.sessions.active)}${stat('Waiting email codes', s.sessions.pending_codes)}</div>
    <h2>Settings in force</h2><p class="muted small">Set with environment variables or the .env file, then restart. They are shown here, not changed here.</p>
    <div class="table-wrap"><table class="tt">${[['Accounts', s.app.auth === 'on' ? 'on (passwords)' : 'off (single person)'], ['Model provider', `${s.app.provider}${s.app.mock ? ' (demo mode)' : ''}`], ['Model calls at once', s.app.concurrency], ['Background preparation', s.app.prefetch ? 'on' : 'off'], ['Sign out after (idle)', `${cfg.idle_minutes} minutes`], ['Sign-in lasts', `${cfg.session_days} days`], ['"Keep me signed in" lasts', `${cfg.remember_days} days`], ['Email code lifetime', `${cfg.otp_minutes} minutes`], ['Wait between codes', `${cfg.otp_resend_seconds} seconds`], ['AI requests per person per minute', cfg.rate_ai_per_minute], ['Sign-in attempts per address per minute', cfg.rate_auth_per_minute], ['Languages', cfg.languages], ['Backups kept', cfg.backup_keep]].map(([k, v]) => `<tr><td>${k}</td><td>${esc(String(v))}</td></tr>`).join('')}</table></div>
    <h2>Backups</h2><div class="table-wrap"><table class="tt"><tr><th>File</th><th>Size</th><th>Made</th><th></th></tr>${st.backups.map((b) => `<tr data-n="${esc(b.name)}"><td><code>${esc(b.name)}</code></td><td>${mb(b.bytes)}</td><td>${fmtDateTime(b.at)}</td><td><a class="btn sm" href="/api/admin/backups/${encodeURIComponent(b.name)}" download>⬇ Download</a> <button class="btn sm danger" data-rm>Delete</button></td></tr>`).join('') || '<tr><td colspan="4" class="muted">No backups yet.</td></tr>'}</table></div>
    <h2>Housekeeping</h2><div class="row" style="flex-wrap:wrap">${[['sessions', 'Remove expired sign-ins'], ['codes', 'Remove expired email codes'], ['tts_cache', 'Empty the voice cache'], ['audit_90d', 'Delete audit entries older than 90 days']].map(([k, l]) => `<button class="btn" data-purge="${k}">${l}</button>`).join('')}</div>
    <details><summary>Live counters</summary><pre class="small">${esc(JSON.stringify(h.metrics, null, 1))}</pre></details><p class="muted small">Prometheus: <code>/metrics</code></p>`;
  $('#bk', m).onclick = () => api('/api/admin/backup', {}).then((r) => { toast(`✓ ${r.file} (${mb(r.bytes)})`); system(m); }).catch(fail);
  $$('tr[data-n]', m).forEach((tr) => $('[data-rm]', tr).addEventListener('click', async () => { if (await confirmDialog(`Delete ${tr.dataset.n}?`, { danger: true, yes: 'Delete' })) del(`/api/admin/backups/${encodeURIComponent(tr.dataset.n)}`).then(() => system(m)).catch(fail); }));
  $$('[data-purge]', m).forEach((b) => (b.onclick = async () => { if (b.dataset.purge !== 'tts_cache' && b.dataset.purge !== 'audit_90d' || await confirmDialog(`${b.textContent}?`, { yes: 'Yes' })) api('/api/admin/system/purge', { what: b.dataset.purge }).then((r) => { toast(`Removed ${r.removed}`); system(m); }).catch(fail); }));
}
