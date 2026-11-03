// Student study pages: revise (flashcards), mistakes notebook, notes, plan, achievements, tests & papers, assignments.
import { api, get, put, del } from './api.js';
import { t } from './i18n.js';
import { md, esc } from './render.js';
import { $, $$, toast, openModal, confirmDialog, ring, fmtDate, fmtDateTime, download } from './ui.js';
import { state, subjectInfo, refreshProgress, whyText } from './state.js';
import { taskHref } from './home.js';
import { speaker } from './voice.js';
import { speakOpts, speakText } from './lesson.js';
import { openSettings } from './settings.js';

export async function route(view, name, rest) {
  const pages = { revise: renderRevise, mistakes: renderMistakes, notes: renderNotes, plan: renderPlan, me: renderMe, tests: renderTests, assignments: renderAssignments };
  return pages[name](view, rest);
}
const head = (title, extra = '') => `<div class="crumbs"><a href="#/">${t('nav.home', 'Home')}</a> › ${esc(title)}</div><div class="row"><h1 style="margin:0">${title}</h1><span class="spacer"></span>${extra}</div>`;
const topicTitle = (id) => id;

/* ============================================================ revise ============================================================ */
async function renderRevise(view) {
  const r = await get('/api/revision');
  view.innerHTML = `${head(`🔁 ${t('nav.revise', 'Revise')}`)}
    <p class="muted">${t('rev.help', 'Short, spaced practice beats cramming. Cards and topics appear exactly when you are about to forget them.')}</p>
    <div class="grid2"><section class="card pad"><h2>🃏 ${t('rev.cards', 'Flashcards')} <span class="chip">${r.cards.length}</span></h2><div id="drill">${r.cards.length ? `<button class="btn primary" id="start">${t('rev.start', 'Start revising')}</button>` : `<p class="muted">${t('rev.nocards', 'No cards due. Open a lesson and tap “Flashcards” to create some.')}</p>`}</div>
      <p class="muted small">${t('rev.reviewed', 'Reviewed so far')}: ${r.counts.reviewed}</p></section>
    <section class="card pad"><h2>📚 ${t('rev.topics', 'Topics due')} <span class="chip">${r.topics.length}</span></h2>${r.topics.length ? `<div class="topic-pills">${r.topics.map((x) => `<a class="topic-pill" href="#/learn/${x.id}" style="--accent:${subjectInfo(x.subject).color}"><b>${esc(x.title)}</b><span class="muted small">${esc(x.subject_name)} · ${esc(x.chapter)}</span></a>`).join('')}</div>` : `<p class="muted">${t('rev.notopics', 'Nothing is due right now. 🎉')}</p>`}
      ${r.mistakes ? `<p><a class="btn" href="#/mistakes">🛠️ ${t('rev.mistakes', 'Fix {n} past mistakes', { n: r.mistakes })}</a></p>` : ''}</section></div>`;
  $('#start', view)?.addEventListener('click', () => drill(view, r.cards));
}
function drill(view, cards) {
  let i = 0, done = 0; const box = $('#drill', view);
  const show = () => {
    if (i >= cards.length) { box.innerHTML = `<p><b>🎉 ${t('rev.done', 'Done!')}</b> ${done} ${t('rev.cardsreviewed', 'cards reviewed.')}</p>`; refreshProgress(); return; }
    const c = cards[i];
    box.innerHTML = `<p class="muted small">${i + 1}/${cards.length}</p><div class="flash" tabindex="0" aria-live="polite"><div class="prose">${md(c.front)}</div><div id="back" hidden><hr><div class="prose">${md(c.back)}</div></div></div>
      <div class="row"><button class="btn" id="show">${t('rev.show', 'Show answer')}</button><button class="btn sm" id="say">🔊</button></div><div class="row" id="grades" hidden>
      ${[[0, 'rev.again', 'Again', 'danger'], [1, 'rev.hard', 'Hard', ''], [2, 'rev.good', 'Good', 'primary'], [3, 'rev.easy', 'Easy', '']].map(([g, k, d, cls]) => `<button class="btn ${cls}" data-g="${g}">${t(k, d)}</button>`).join('')}</div>`;
    const reveal = () => { $('#back', box).hidden = false; $('#grades', box).hidden = false; $('#show', box).hidden = true; $('[data-g="2"]', box).focus(); };
    $('#show', box).onclick = reveal; $('.flash', box).onkeydown = (e) => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); reveal(); } };
    $('#say', box).onclick = () => { speaker.begin(speakOpts()); speaker.push(speakText(c.front + '. ' + ($('#back', box).hidden ? '' : c.back))); speaker.end(); };
    $$('[data-g]', box).forEach((b) => (b.onclick = async () => { const r = await api(`/api/flashcards/${c.id}/review`, { grade: +b.dataset.g }); toast(t('rev.next', 'See it again in {d} day(s)', { d: r.interval_days || '<1' })); done++; i++; show(); }));
  };
  show();
}

/* ============================================================ mistakes ============================================================ */
async function renderMistakes(view, rest) {
  const all = rest === 'all'; const { items } = await get(`/api/mistakes${all ? '?all=true' : ''}`);
  view.innerHTML = `${head(`🛠️ ${t('nav.mistakes', 'Mistakes notebook')}`, `<a class="btn sm" href="#/mistakes${all ? '' : '/all'}">${all ? t('mist.open', 'Only open') : t('mist.all', 'Include fixed')}</a>`)}
    <p class="muted">${t('mist.help', 'Every wrong answer lands here. Try each again — when you get it right, mark it fixed.')}</p>
    ${items.length ? items.map((m) => `<article class="card pad mistake" data-id="${m.id}"><div class="row"><span class="chip">${esc(m.subject_name || '')} · ${esc(m.topic || '')}</span><span class="chip">${esc(m.source)}</span>${m.times_wrong > 1 ? `<span class="chip warn">×${m.times_wrong}</span>` : ''}${m.resolved_at ? `<span class="chip ok">✓ ${t('mist.fixed', 'fixed')}</span>` : ''}<span class="spacer"></span><a class="small" href="#/learn/${m.subtopic_id}">${t('mist.review', 'Review lesson')}</a></div>
      <div class="prose qtext">${md(m.question)}</div>
      ${m.options.length ? `<div class="opts">${m.options.map((o, k) => `<button class="q-opt small" data-o="${esc(o)}"><b>${'ABCD'[k]}</b><span class="prose">${md(o)}</span></button>`).join('')}</div>` : ''}
      <details><summary>${t('mist.show', 'Show answer')}</summary><p><b>${t('mist.yours', 'You answered')}:</b> ${esc(m.chosen)}</p><p><b>${t('mist.correct', 'Correct')}:</b> ${esc(m.correct)}</p><div class="prose">${md(m.explanation || '')}</div></details>
      ${m.resolved_at ? '' : `<button class="btn sm" data-fix>✅ ${t('mist.markfixed', 'I can do this now')}</button>`}</article>`).join('') : `<p class="empty">🎉 ${t('mist.none', 'No open mistakes. Keep going!')}</p>`}`;
  $$('.mistake', view).forEach((card) => {
    const id = card.dataset.id; const m = items.find((x) => x.id == id);
    $$('.q-opt', card).forEach((b) => (b.onclick = async () => { const ok = b.dataset.o === m.correct; b.classList.add(ok ? 'right' : 'wrong'); if (ok) { await api(`/api/mistakes/${id}/resolve`, {}); toast(t('mist.yes', 'Correct! Marked as fixed.')); card.querySelector('[data-fix]')?.remove(); refreshProgress(); } else toast(t('mist.no', 'Not yet — look at the explanation and try again.')); }));
    card.querySelector('[data-fix]')?.addEventListener('click', async () => { await api(`/api/mistakes/${id}/resolve`, {}); card.remove(); refreshProgress(); });
  });
}

/* ============================================================ notes ============================================================ */
async function renderNotes(view) {
  const [{ items, bookmarks }, prepared] = await Promise.all([get('/api/notes'), get('/api/lesson-notes').catch(() => ({ items: [] }))]);
  view.innerHTML = `${head(`📓 ${t('nav.notes', 'My notes')}`, `<button class="btn sm" id="new">＋ ${t('notes.new', 'New note')}</button><a class="btn sm" href="/api/notes/export.md" download>⬇️ ${t('notes.export', 'Download')}</a><button class="btn sm" onclick="window.print()">🖨️ ${t('common.print', 'Print')}</button>`)}
    ${prepared.items.length ? `<h2 class="small-title">📝 ${t('notes.prepared', 'Study notes you prepared')}</h2><div class="topic-pills">${prepared.items.map((n) => `<button class="topic-pill" data-prep="${esc(n.subtopic_id)}" data-title="${esc(n.topic)}"><b>${esc(n.topic)}</b><span class="muted small">${esc(n.subject_name)} · ${t('common.grade', 'Grade')} ${n.grade} · ${fmtDate(n.updated_at)}</span></button>`).join('')}</div>` : ''}
    ${bookmarks.length ? `<h2 class="small-title">⭐ ${t('notes.bookmarks', 'Bookmarked topics')}</h2><div class="topic-pills">${bookmarks.map((b) => `<a class="topic-pill" href="#/learn/${b.id}"><b>${esc(b.title)}</b><span class="muted small">${esc(b.subject_name)} · ${t('common.grade', 'Grade')} ${b.grade}</span></a>`).join('')}</div>` : ''}
    <div id="notes">${items.length ? items.map((n) => `<article class="card pad note" data-id="${n.id}"><div class="row"><h3 style="margin:0">${esc(n.title || t('notes.untitled', 'Note'))}</h3><span class="spacer"></span><span class="muted small">${n.topic ? esc(n.topic) + ' · ' : ''}${fmtDate(n.updated_at)}</span><button class="icon-btn small" data-e aria-label="${t('common.edit', 'Edit')}">✏️</button><button class="icon-btn small" data-d aria-label="${t('common.delete', 'Delete')}">🗑️</button></div><div class="prose">${md(n.body)}</div></article>`).join('') : `<p class="empty">${t('notes.none', 'No notes yet. Highlight text in a lesson, or save a board from the chat.')}</p>`}</div>`;
  const edit = (n) => { const m = openModal(`<div class="field"><label for="t">${t('note.title', 'Title')}</label><input id="t" type="text" value="${esc(n?.title || '')}"></div><div class="field"><label for="b">${t('note.body', 'Note')} <span class="muted small">(Markdown / $math$)</span></label><textarea id="b" rows="8">${esc(n?.body || '')}</textarea></div><div class="row end"><button class="btn primary" id="s">${t('common.save', 'Save')}</button></div>`, { title: t('notes.edit', 'Note'), wide: true });
    $('#s', m.el).onclick = async () => { const body = { subtopic_id: n?.subtopic_id || null, title: $('#t', m.el).value, body: $('#b', m.el).value }; n ? await put(`/api/notes/${n.id}`, body) : await api('/api/notes', body); m.close(); renderNotes(view); }; };
  $('#new', view).onclick = () => edit(null);
  $$('[data-prep]', view).forEach((b) => (b.onclick = async () => { const { prepare } = await import('./studynotes.js'); prepare({ id: b.dataset.prep, title: b.dataset.title }, false, () => renderNotes(view)); }));
  $$('.note', view).forEach((el) => { const n = items.find((x) => x.id == el.dataset.id); $('[data-e]', el).onclick = () => edit(n); $('[data-d]', el).onclick = async () => { if (await confirmDialog(t('notes.del', 'Delete this note?'), { danger: true })) { await del(`/api/notes/${n.id}`); renderNotes(view); } }; });
}

/* ============================================================ plan ============================================================ */
async function renderPlan(view) {
  const p = await get('/api/me/plan'); const K = { learn: ['📖', 'plan.learn', 'Learn'], revise: ['🔁', 'plan.revise', 'Revise'], strengthen: ['💪', 'plan.strengthen', 'Strengthen'], cards: ['🃏', 'plan.cards', 'Flashcards'], mistakes: ['🛠️', 'plan.mistakes', 'Fix mistakes'] };
  view.innerHTML = `${head(`🗓️ ${t('nav.plan', 'My plan')}`, `<button class="btn sm" id="edit">⚙️ ${t('plan.edit', 'Goals & exam date')}</button>`)}
    <div class="grid2"><section class="card pad"><h2>${t('home.today', "Today's plan")} <span class="muted small">≈ ${p.tasks.reduce((a, k) => a + k.minutes, 0)} ${t('common.min', 'min')}</span></h2>
      ${p.tasks.length ? `<ol class="plan">${p.tasks.map((k) => `<li><a href="${taskHref(k)}"><span>${K[k.kind][0]}</span><div><b>${esc(k.topic ? k.topic.title : t(K[k.kind][1], K[k.kind][2]))}</b><div class="muted small">${esc(whyText(k.why))}${k.topic ? ` · ${esc(k.topic.subject_name)}` : ''} · ${k.minutes} ${t('common.min', 'min')}</div></div></a></li>`).join('')}</ol>` : `<p class="empty">🎉 ${t('plan.alldone', 'You are all caught up!')}</p>`}</section>
    <section class="card pad"><h2>${t('plan.syllabus', 'Your syllabus')}</h2><div class="row" style="gap:18px">${ring(Math.round(100 * p.done / Math.max(1, p.total)), `${p.done}/${p.total}`)}<div><p>${p.done} ${t('common.of', 'of')} ${p.total} ${t('plan.topics', 'topics done')}</p>
      ${p.days_left != null ? (p.days_left > 0 ? `<p>📅 <b>${p.days_left}</b> ${t('plan.daysleft', 'days to your exam')} · ${t('plan.pace', 'aim for')} <b>${p.topics_per_week}</b> ${t('plan.perweek', 'new topics a week')}</p><p class="${p.on_track ? 'ok' : 'warn'}-text">${p.on_track ? `✅ ${t('plan.ontrack', 'You are on track with your daily time.')}` : `⚠️ ${t('plan.behind', 'At your current daily time you may not finish — try adding minutes in Settings.')}`}</p>` : `<p>${t('plan.exampassed', 'Your exam date has passed — update it in Settings.')}</p>`) : `<p class="muted">${t('plan.noexam', 'Add your exam date to get a pace.')}</p>`}</div></div></section></div>`;
  $('#edit', view).onclick = () => openSettings('profile');
}

/* ============================================================ me: achievements ============================================================ */
async function renderMe(view) {
  const [prog, act, cls] = await Promise.all([get('/api/me/progress'), get('/api/me/activity'), get('/api/me/assignments')]); const c = prog.card;
  const days = new Set(act.days), cells = [];
  for (let i = 34; i >= 0; i--) { const d = new Date(Date.now() - i * 864e5); const k = d.toISOString().slice(0, 10); cells.push(`<i class="${days.has(k) ? 'on' : ''}" title="${k}"></i>`); }
  view.innerHTML = `${head(`🏅 ${t('nav.me', 'Me')}`)}
    <section class="hero card pad"><div class="row" style="gap:22px">${ring(Math.round(100 * c.level.into / c.level.needed), `L${c.level.level}`)}<div><h2 style="margin:0">${t('home.level', 'Level')} ${c.level.level} · ${c.xp} XP</h2><p class="muted">${c.level.needed - c.level.into} XP ${t('me.tonext', 'to the next level')} · 🔥 ${c.streak} ${t('me.streak', 'day streak')}</p>
      <div class="bar" style="max-width:320px"><i style="width:${Math.min(100, Math.round(100 * c.today_xp / c.daily_goal))}%"></i></div><span class="muted small">${t('me.today', 'Today')}: ${c.today_xp}/${c.daily_goal} XP</span></div></div></section>
    <h2 class="section-title">${t('me.badges', 'Badges')}</h2><div class="badges">${c.all_badges.map((b) => { const got = c.badges.some((x) => x.id === b.id); return `<div class="badge-tile ${got ? 'got' : ''}" title="${esc(b.about)}"><span aria-hidden="true">${b.icon}</span><b>${esc(b.name)}</b><small class="muted">${esc(b.about)}</small></div>`; }).join('')}</div>
    <h2 class="section-title">${t('me.calendar', 'Your last 5 weeks')}</h2><div class="cal" role="img" aria-label="Activity calendar">${cells.join('')}</div>
    ${cls.classes.length ? `<h2 class="section-title">🏆 ${t('me.leaderboard', 'Class leaderboard (weekly XP)')}</h2><div id="lb"></div>` : `<p class="muted"><a href="#/assignments">${t('me.joinclass', 'Join a class')}</a> ${t('me.joinclass2', 'to see assignments and the friendly leaderboard.')}</p>`}`;
  const lb = $('#lb', view); if (lb) { const parts = await Promise.all(cls.classes.map((k) => get(`/api/classes/${k.id}/leaderboard`).then((r) => ({ k, r })))); lb.innerHTML = parts.map(({ k, r }) => `<section class="card pad"><h3>${esc(k.name)}</h3>${r.rows.length ? `<ol class="lb">${r.rows.map((x) => `<li class="${x.me ? 'me' : ''}"><b>${x.rank}</b> ${esc(x.nickname)} <span class="spacer"></span>${x.xp} XP</li>`).join('')}</ol>` : `<p class="muted">${t('lb.empty', 'Nobody has opted in yet. Opt in from Assignments.')}</p>`}<p class="muted small">${t('lb.note', 'Only students who opt in appear, with nicknames.')}</p></section>`).join(''); }
}

/* ============================================================ assignments & classes ============================================================ */
async function renderAssignments(view) {
  const { items, classes } = await get('/api/me/assignments');
  view.innerHTML = `${head(`📝 ${t('nav.assignments', 'Assignments')}`, `<button class="btn sm" id="join">＋ ${t('cls.join', 'Join a class')}</button>`)}
    ${classes.length ? `<p class="muted">${t('cls.in', 'Your classes')}: ${classes.map((k) => `<span class="chip">${esc(k.name)}</span>`).join(' ')}</p>` : ''}
    ${items.length ? `<div class="list">${items.map((a) => `<article class="card pad row ${a.overdue ? 'overdue' : ''}"><div style="flex:1"><b>${esc(a.title)}</b><div class="muted small">${esc(a.class_name)} · ${esc(a.kind)}${a.topic ? ` · ${esc(a.topic)}` : ''}${a.due_at ? ` · ${t('home.due', 'due')} ${fmtDate(a.due_at)}` : ''}</div>${a.note ? `<div class="small">${esc(a.note)}</div>` : ''}</div>
      ${a.status === 'done' ? `<span class="chip ok">✓ ${t('asg.done', 'Done')}${a.score != null ? ` · ${Math.round(a.score)}%` : ''}</span>` : `<a class="btn primary" href="${a.kind === 'test' ? `#/tests/new/${a.subtopic_id || ''}?asg=${a.id}` : `#/learn/${a.subtopic_id}`}">${t('asg.open', 'Open')}</a>`}</article>`).join('')}</div>` : `<p class="empty">${t('asg.none', 'No assignments yet. Join your class with the code from your teacher.')}</p>`}`;
  $('#join', view).onclick = () => {
    const m = openModal(`<div class="field"><label for="jc">${t('cls.code', 'Class code')}</label><input id="jc" type="text" autocapitalize="characters" maxlength="8" autofocus></div><div class="field"><label for="jn">${t('cls.nick', 'Nickname for the leaderboard (not your real name)')}</label><input id="jn" type="text" maxlength="20" value="${esc(state.user.display_name.slice(0, 1))}…"></div>
      <label class="check"><input type="checkbox" id="jl"> ${t('cls.opt', 'Show me on my class leaderboard (nickname and weekly XP only)')}</label><p class="error" id="je" hidden></p><div class="row end"><button class="btn primary" id="jg">${t('cls.joinbtn', 'Join')}</button></div>`, { title: t('cls.join', 'Join a class') });
    $('#jg', m.el).onclick = async () => { try { await api('/api/classes/join', { code: $('#jc', m.el).value, nickname: $('#jn', m.el).value, share_leaderboard: $('#jl', m.el).checked }); m.close(); renderAssignments(view); } catch (e) { const x = $('#je', m.el); x.textContent = e.message; x.hidden = false; } };
  };
}

/* ============================================================ tests & papers ============================================================ */
async function renderTests(view, rest) {
  if (rest.startsWith('new')) return newTest(view, rest.split('/')[1] || '');
  const [{ items }, presets] = await Promise.all([get('/api/tests'), get('/api/tests/presets')]);
  view.innerHTML = `${head(`📝 ${t('nav.tests', 'Tests')}`, `<a class="btn primary sm" href="#/tests/new">＋ ${t('tests.new', 'New test')}</a>`)}
    <p class="muted">${t('tests.help', 'Practise like the real exam: timed papers with sections and marks. Marked instantly, with a list of what to fix.')}</p>
    ${items.length ? `<div class="list">${items.map((x) => `<article class="card pad row"><div style="flex:1"><b>${esc(x.title)}</b><div class="muted small">${fmtDateTime(x.created_at)} · ${x.duration_min ? `${x.duration_min} ${t('common.min', 'min')}` : t('tests.untimed', 'untimed')}</div></div>
      ${x.submitted_at ? `<span class="chip ${x.percent >= 60 ? 'ok' : 'warn'}">${x.score}/${x.out_of} · ${x.percent}%</span><a class="btn sm" href="#/test/${x.id}">${t('tests.review', 'Review')}</a>` : `<a class="btn primary sm" href="#/test/${x.id}">${t('tests.resume', 'Continue')}</a>`}</article>`).join('')}</div>` : `<p class="empty">${t('tests.none', 'No tests yet.')}</p>`}
    <h2 class="section-title">${t('tests.types', 'Paper types')}</h2><div class="topic-pills">${Object.values(presets).map((p) => `<span class="topic-pill"><b>${esc(p.title)}</b><span class="muted small">${p.marks} ${t('tests.marks', 'marks')} · ${p.questions} ${t('tests.q', 'questions')} · ${p.minutes} ${t('common.min', 'min')}</span></span>`).join('')}</div>`;
}
async function newTest(view, ids) {
  const preselected = new Set(ids.split('?')[0].split(',').filter(Boolean)); const asg = new URLSearchParams(location.hash.split('?')[1] || '').get('asg');
  const subjects = state.meta.subjects.filter((s) => s.grades.includes(state.profile.grade)); const presets = await get('/api/tests/presets');
  view.innerHTML = `${head(`＋ ${t('tests.new', 'New test')}`)}<div class="card pad"><div class="field"><span class="label">${t('tests.type', 'Paper type')}</span><div class="choice-row" id="pt">${Object.entries(presets).map(([k, p], i) => `<button type="button" class="choice" data-v="${k}" aria-pressed="${i === 0}">${esc(p.title)} <small>${p.marks}m · ${p.minutes}′</small></button>`).join('')}</div></div>
    <div class="field"><label for="sj">${t('tests.subject', 'Subject')}</label><select id="sj">${subjects.map((s) => `<option value="${s.id}">${s.icon} ${esc(s.name)}</option>`).join('')}</select></div><div id="chs" class="checks"></div>
    <p class="error" id="te" hidden></p><button class="btn primary" id="go">${t('tests.create', 'Create my test')}</button></div>`;
  const choice = $('#pt', view); $$('.choice', choice).forEach((b) => (b.onclick = () => $$('.choice', choice).forEach((x) => x.setAttribute('aria-pressed', x === b))));
  const load = async () => { const ch = await (await import('./state.js')).loadCurriculum($('#sj', view).value, state.profile.grade); $('#chs', view).innerHTML = ch.map((c) => `<label class="check"><input type="checkbox" value="${c.subtopics[0].id}" ${preselected.has(c.subtopics[0].id) || [...preselected].some((p) => c.subtopics.some((s) => s.id === p)) ? 'checked' : ''}> <b>${c.number}.</b> ${esc(c.title)}</label>`).join(''); };
  if (preselected.size) { const first = [...preselected][0]; const sub = state.meta.subjects.find((s) => first.startsWith(s.id.slice(0, 3))); if (sub) $('#sj', view).value = sub.id; }
  $('#sj', view).onchange = load; await load();
  $('#go', view).onclick = async (e) => {
    const sel = $$('#chs input:checked', view).map((x) => x.value); if (!sel.length) { const x = $('#te', view); x.textContent = t('tests.pick', 'Pick at least one chapter.'); x.hidden = false; return; }
    e.currentTarget.disabled = true; e.currentTarget.textContent = t('tests.setting', 'Setting your paper… this can take a minute');
    try { const r = await api('/api/tests', { subtopic_ids: sel, preset: $('.choice[aria-pressed="true"]', choice).dataset.v, assignment_id: asg || null }); sessionStorage.setItem(`vidya.test.${r.id}`, JSON.stringify(r)); location.hash = `#/test/${r.id}`; }
    catch (er) { const x = $('#te', view); x.textContent = er.message; x.hidden = false; e.currentTarget.disabled = false; e.currentTarget.textContent = t('tests.create', 'Create my test'); }
  };
}

export async function renderTest(view, id) {
  let timer = null; const clear = () => clearInterval(timer);
  const { setLeave } = await import('./app.js'); setLeave(clear);
  let result = null; try { result = await get(`/api/tests/${id}/result`); } catch { /* not submitted yet */ }
  if (result) return showResult(view, result);
  const b = await api(`/api/tests/${id}/begin`, {}); const paper = b.paper; const answers = {}; let left = b.remaining_seconds; const timed = b.minutes > 0;
  const q = (x, n) => `<article class="card pad tq" data-id="${x.id}"><div class="row"><b>${n}.</b><span class="spacer"></span><span class="chip">${x.marks} ${x.marks > 1 ? t('tests.marks', 'marks') : t('tests.mark', 'mark')}</span></div><div class="prose qtext">${md(x.question)}</div>
    ${x.kind === 'mcq' ? `<div class="opts">${x.options.map((o, k) => `<label class="q-opt"><input type="radio" name="q${x.id}" value="${k}"><b>${'ABCD'[k]}</b><span class="prose">${md(o)}</span></label>`).join('')}</div>` : x.kind === 'numeric' ? `<input type="text" class="ans" aria-label="${t('practice.answer', 'Your final answer')}" placeholder="${t('practice.answer', 'Your final answer')}">` : `<textarea class="ans" rows="${x.marks >= 4 ? 7 : 3}" aria-label="${t('tests.yourans', 'Your answer')}"></textarea>`}</article>`;
  let n = 0;
  view.innerHTML = `<div class="test-head card"><div><b>${esc(paper.title)}</b><div class="muted small">${paper.total_marks} ${t('tests.marks', 'marks')}</div></div><span class="spacer"></span>${timed ? `<span class="timer" id="timer" role="timer" aria-live="off">--:--</span>` : ''}<button class="btn primary" id="submit">${t('tests.submit', 'Submit')}</button></div>
    ${paper.sections.map((s) => `<h2 class="section-title">${t('tests.section', 'Section')} ${s.name} <span class="muted small">(${s.marks} ${t('tests.marks', 'marks')} ${t('tests.each', 'each')})</span></h2>${s.questions.map((x) => q(x, ++n)).join('')}`).join('')}<div class="row end"><button class="btn primary" id="submit2">${t('tests.submit', 'Submit')}</button></div>`;
  const collect = () => { $$('.tq', view).forEach((el) => { const qid = el.dataset.id; const r = $('input[type=radio]:checked', el); answers[qid] = r ? r.value : ($('.ans', el)?.value || ''); }); return answers; };
  const submit = async (auto) => {
    clear(); const btns = $$('#submit, #submit2', view); btns.forEach((x) => (x.disabled = true));
    if (!auto && !(await confirmDialog(t('tests.confirm', 'Submit your test now?')))) { btns.forEach((x) => (x.disabled = false)); if (timed) timer = setInterval(tick, 1000); return; }
    toast(t('tests.marking', 'Marking your paper…'), 6000);
    try { const r = await api(`/api/tests/${id}/submit`, { answers: collect() }); refreshProgress(); showResult(view, r); } catch (e) { toast(e.message); btns.forEach((x) => (x.disabled = false)); }
  };
  $$('#submit, #submit2', view).forEach((x) => (x.onclick = () => submit(false)));
  const tick = () => { left--; const el = $('#timer', view); if (!el) return clear(); el.textContent = `${String(Math.floor(Math.max(0, left) / 60)).padStart(2, '0')}:${String(Math.max(0, left) % 60).padStart(2, '0')}`; el.classList.toggle('low', left < 300); if (left <= 0) { toast(t('tests.timeup', "Time's up — submitting."), 5000); submit(true); } };
  if (timed) { timer = setInterval(tick, 1000); tick(); }
}
function showResult(view, r) {
  view.innerHTML = `${head(`📊 ${t('tests.result', 'Result')}`)}<section class="hero card pad"><div class="row" style="gap:22px">${ring(r.percent, `${r.percent}%`)}<div><h2 style="margin:0">${r.score} / ${r.out_of} ${t('tests.marks', 'marks')}</h2>${r.late ? `<p class="warn-text">⏱️ ${t('tests.late', 'Submitted after the time limit.')}</p>` : ''}${r.reward ? `<p class="muted">+${r.reward.points} XP</p>` : ''}
    ${r.advice ? `<p class="explain">🎯 ${esc(r.advice.message)} ${(r.advice.start || []).map((id) => `<a class="btn sm primary" href="#/learn/${id}">${t('diag.start', 'Start here')}</a>`).join(' ')}</p>` : ''}
    ${r.weak_topics?.length ? `<p>${t('tests.weak', 'Revise')}: ${r.weak_topics.map((w) => `<a href="#/learn/${w.subtopic_id}">${esc(w.title)}</a>`).join(', ')}</p>` : ''}<p class="small muted">🤖 ${t('tests.ai', 'Written answers were marked by AI and can be wrong. Ask your teacher if unsure.')}</p></div></div></section>
    <h2 class="section-title">${t('tests.bytopic', 'By topic')}</h2><div class="topic-pills">${r.topics.map((x) => `<a class="topic-pill" href="#/learn/${x.subtopic_id}"><b>${esc(x.title)}</b><span class="muted small">${x.percent}%</span></a>`).join('')}</div>
    <h2 class="section-title">${t('tests.review', 'Review')}</h2>${r.per_question.map((x, i) => `<article class="card pad ${x.awarded >= x.marks ? 'good' : x.awarded > 0 ? 'part' : 'bad'}"><div class="row"><b>${i + 1}.</b><span class="chip">${x.awarded}/${x.marks}</span><span class="spacer"></span></div><div class="prose qtext">${md(x.question)}</div><p><b>${t('mist.yours', 'You answered')}:</b> ${esc(x.your_answer ?? '—')}</p><p>${md(x.feedback || '')}</p>${x.awarded < x.marks ? `<details><summary>${t('mist.show', 'Show answer')}</summary><div class="prose">${md(String(x.model_answer || ''))}</div></details>` : ''}</article>`).join('')}
    <div class="row"><a class="btn primary" href="#/tests/new">${t('tests.another', 'Another test')}</a><a class="btn" href="#/mistakes">${t('nav.mistakes', 'Mistakes notebook')}</a></div>`;
}
