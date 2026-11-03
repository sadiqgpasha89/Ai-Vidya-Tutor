// Student home, subject pages (topics -> subtopics), and search.
import { get, api } from './api.js';
import { t } from './i18n.js';
import { $, $$, esc, ring, toast } from './ui.js';
import { state, subjectInfo, loadCurriculum, masteryClass, trackFor, whyText, subjectLabel } from './state.js';

const topicLink = (tp) => {
  const s = subjectInfo(tp.subject);
  return `<a class="topic-pill" style="--accent:${s.color}" href="#/learn/${tp.id}"><b>${s.icon} ${esc(tp.title)}</b><span class="muted small">${esc(s.name)} · ${t('common.grade', 'Grade')} ${tp.grade} · ${esc(tp.chapter)}</span></a>`;
};
const TASK = { learn: ['📖', 'plan.learn', 'Learn'], revise: ['🔁', 'plan.revise', 'Revise'], strengthen: ['💪', 'plan.strengthen', 'Strengthen'], cards: ['🃏', 'plan.cards', 'Flashcards'], mistakes: ['🛠️', 'plan.mistakes', 'Fix mistakes'] };
export const taskHref = (k) => (k.topic ? `#/learn/${k.topic.id}` : k.kind === 'cards' ? '#/revise' : '#/mistakes');

export async function renderHome(view) {
  const p = state.profile, hour = new Date().getHours();
  const greet = hour < 12 ? t('home.morning', 'Good morning') : hour < 17 ? t('home.afternoon', 'Good afternoon') : t('home.evening', 'Good evening');
  const [plan, assignments] = await Promise.all([get('/api/me/plan').catch(() => null), get('/api/me/assignments').catch(() => ({ items: [] }))]);
  const card = state.card, goalPct = card ? Math.min(100, Math.round(100 * card.today_xp / card.daily_goal)) : 0;
  const recommended = recommendedSubjects();
  const open = assignments.items.filter((a) => a.status !== 'done').slice(0, 3);
  view.innerHTML = `
    ${state.emailVerified ? '' : `<div class="banner info" id="email-nudge">✉️ ${t('email.nudge', 'Add your email address so you can reset your password if you forget it.')} <button class="btn sm" id="email-add">${t('email.add', 'Add my email address')}</button></div>`}
    <section class="hero">
      <div><h1>${greet}, ${esc(state.user.display_name)} 👋</h1>
        <p class="muted">${t('home.sub', 'Pick a subject, listen to your teacher, and ask any doubt — out loud or by typing.')} ${t('home.studying', 'You are studying')} <b>${t('common.grade', 'Grade')} ${p.grade}</b>${p.goal && p.goal !== 'boards' ? ` · ${esc(state.meta.goals.find((g) => g.id === p.goal)?.label || '')}` : ''}.</p></div>
      ${card ? `<a class="xp-card card" href="#/me" aria-label="${t('home.xp', 'Your progress')}">${ring(goalPct, `${card.today_xp}/${card.daily_goal}`)}<div><b>${t('home.level', 'Level')} ${card.level.level}</b><div class="muted small">${card.xp} XP · ${t('home.dailygoal', 'daily goal')}</div><div class="bar"><i style="width:${Math.round(100 * card.level.into / card.level.needed)}%"></i></div></div></a>` : ''}
    </section>
    <div id="search-results"></div>
    <div id="daily"></div>
    ${plan?.tasks?.length ? `<h2 class="section-title">🗓️ ${t('home.today', "Today's plan")} <a class="small" href="#/plan">${t('common.seeall', 'See all')}</a></h2>
      <div class="topic-pills">${plan.tasks.slice(0, 4).map((k) => `<a class="topic-pill" href="${taskHref(k)}" style="--accent:var(--primary)"><b>${TASK[k.kind][0]} ${esc(k.topic ? k.topic.title : t(TASK[k.kind][1], TASK[k.kind][2]))}</b><span class="muted small">${esc(whyText(k.why))} · ${k.minutes} ${t('common.min', 'min')}</span></a>`).join('')}</div>` : ''}
    ${open.length ? `<h2 class="section-title">📝 ${t('home.assignments', 'From your teacher')} <a class="small" href="#/assignments">${t('common.seeall', 'See all')}</a></h2><div class="topic-pills">${open.map((a) => `<a class="topic-pill ${a.overdue ? 'overdue' : ''}" href="${a.subtopic_id && a.kind !== 'test' ? `#/learn/${a.subtopic_id}` : '#/assignments'}"><b>${esc(a.title)}</b><span class="muted small">${esc(a.class_name)}${a.due_at ? ` · ${t('home.due', 'due')} ${new Date(a.due_at * 1000).toLocaleDateString()}` : ''}</span></a>`).join('')}</div>` : ''}
    <div id="resume"></div>
    <div id="mytopics"></div>
    <h2 class="section-title">${t('home.subjects', 'Your subjects')}</h2>
    <div class="subject-grid" id="subjects"></div>
    <details class="more-subjects"><summary>${t('home.allsubjects', 'All subjects')}</summary><div class="subject-grid" id="subjects-more"></div></details>
    <div class="row" style="margin-top:22px"><a class="btn" href="#/tools">🧰 ${t('nav.tools', 'Tools & simulations')}</a><a class="btn" href="#/tests">📝 ${t('nav.tests', 'Tests')}</a></div>`;
  const chunks = [];
  if (state.due.length) chunks.push(`<h2 class="section-title">🔁 ${t('home.revise', 'Revise today')} <span class="chip">${state.due.length}</span></h2><div class="topic-pills">${state.due.map(topicLink).join('')}</div>`);
  if (state.last) chunks.push(`<h2 class="section-title">▶️ ${t('home.continue', 'Continue where you stopped')}</h2><div class="topic-pills">${topicLink(state.last)}</div>`);
  $('#resume', view).innerHTML = chunks.join('');
  import('./mytopics.js').then((m) => m.homeSection($('#mytopics', view))).catch(() => {});
  import('./daily.js').then((m) => m.homeCard($('#daily', view))).catch(() => {});
  $('#email-add', view)?.addEventListener('click', () => import('./emailcode.js').then((m) => m.openEmailDialog(() => $('#email-nudge', view)?.remove())));

  const cardHtml = (s) => `<a class="subject-card" style="--accent:${s.color}" href="#/subject/${s.id}/${p.grade}"><div class="subject-icon" aria-hidden="true">${s.icon}</div><h3>${esc(subjectLabel(s).name)}</h3>
    <span class="muted small">${esc(subjectLabel(s).tagline)}</span><div class="bar" aria-hidden="true"><i data-bar="${s.id}" style="width:0"></i></div><span class="muted small" data-count="${s.id}">&nbsp;</span></a>`;
  const subs = state.meta.subjects.filter((s) => s.grades.includes(p.grade));
  $('#subjects', view).innerHTML = subs.filter((s) => recommended.includes(s.id)).map(cardHtml).join('');
  $('#subjects-more', view).innerHTML = subs.filter((s) => !recommended.includes(s.id)).map(cardHtml).join('');
  if (!$('#subjects-more', view).children.length) $('.more-subjects', view).remove();
  for (const s of subs) {
    loadCurriculum(s.id, p.grade).then((chapters) => {
      const ids = chapters.flatMap((c) => c.subtopics.map((x) => x.id));
      const done = ids.filter((id) => state.progress[id]?.status === 'completed').length;
      const bar = $(`[data-bar="${s.id}"]`, view), cnt = $(`[data-count="${s.id}"]`, view);
      if (bar) bar.style.width = `${ids.length ? (done / ids.length) * 100 : 0}%`;
      if (cnt) cnt.textContent = t('home.topicsdone', '{done} of {n} topics done', { done, n: ids.length });
    }).catch(() => {});
  }
}

export function recommendedSubjects() {
  const p = state.profile;
  if (p.grade >= 11 && state.meta.stream_subjects[p.stream]) return state.meta.stream_subjects[p.stream];
  return state.meta.subjects.filter((s) => s.grades.includes(p.grade) && s.id !== 'commerce').map((s) => s.id);
}

export async function renderSearch(view, q) {
  view.innerHTML = `<div class="crumbs"><a href="#/">${t('nav.home', 'Home')}</a> › ${t('nav.search', 'Search')}</div><h1>${t('search.results', 'Results for')} “${esc(q)}”</h1><div class="search-results" id="sr" aria-live="polite">${t('common.searching', 'Searching…')}</div>`;
  const { results, mode } = await get(`/api/search?q=${encodeURIComponent(q)}${state.profile?.grade ? `&grade=${state.profile.grade}` : ''}`);
  const all = results.length ? results : (await get(`/api/search?q=${encodeURIComponent(q)}`)).results;
  $('#sr', view).innerHTML = all.length ? `<p class="muted small">${mode === 'semantic' ? t('search.semantic', 'Matched by meaning, so different wording works too.') : t('search.keyword', 'Matched by keywords.')}</p>${all.map(topicLink).join('')}` : `<p class="muted">${t('search.none', 'No matching topic found. Try other words, like “force”, “cell” or “python”.')}</p>`;
}

export async function renderSubject(view, subjectId, grade) {
  const s = subjectInfo(subjectId);
  if (!s || !state.meta.grades.includes(grade) || !s.grades.includes(grade)) { location.hash = '#/'; return; }
  const track = trackFor(grade);
  view.innerHTML = `
    <div class="crumbs"><a href="#/">${t('nav.home', 'Home')}</a> › ${esc(s.name)}</div>
    <div class="subject-head" style="--accent:${s.color}">
      <div class="subject-icon" style="--accent:${s.color}" aria-hidden="true">${s.icon}</div><div><h1>${esc(subjectLabel(s).name)}</h1><span class="muted">${esc(subjectLabel(s).tagline)}</span></div><div class="spacer"></div>
      <div class="grade-tabs" role="tablist" aria-label="${t('common.grade', 'Grade')}">${state.meta.grades.filter((g) => s.grades.includes(g)).map((g) => `<button class="grade-tab" role="tab" aria-selected="${g === grade}" data-g="${g}" style="--accent:${s.color}">${g}</button>`).join('')}</div>
    </div>
    <div class="row"><p class="muted" style="flex:1">${t('subject.help', 'Tap a chapter to see its topics, then tap a topic to start learning.')} <span class="chip tiny" title="${esc(t('subject.levelhint', 'Change your level in Settings to see easier or harder topics.'))}">${esc((state.meta.levels.find((l) => l.id === state.profile.level)?.label || '').split(' - ')[0])}</span>${subjectId === 'computers' && grade >= 11 ? ` <b>${esc(state.meta.tracks.find((x) => x.id === track)?.label || '')}</b> (${t('subject.track', 'change in Settings')})` : ''}</p>
      <button class="btn sm" id="diag">🎯 ${t('subject.diag', 'Placement check')}</button><button class="btn sm" id="mocktest">📝 ${t('subject.test', 'Test me on this subject')}</button></div>
    <div id="chapters" style="--accent:${s.color}">${t('common.loading', 'Loading…')}</div>`;
  $$('.grade-tab', view).forEach((b) => (b.onclick = () => (location.hash = `#/subject/${subjectId}/${b.dataset.g}`)));
  $('#diag', view).onclick = async (e) => {
    e.currentTarget.disabled = true; toast(t('diag.preparing', 'Preparing a short check…'), 6000);
    try { const d = await api('/api/diagnostic', { subject: subjectId, grade }); sessionStorage.setItem(`vidya.test.${d.id}`, JSON.stringify(d)); location.hash = `#/test/${d.id}`; }
    catch (er) { toast(er.message); e.currentTarget.disabled = false; }
  };
  const chapters = await loadCurriculum(subjectId, grade);
  $('#mocktest', view).onclick = () => { location.hash = `#/tests/new/${chapters.filter((c) => !c.group).slice(0, 4).map((c) => c.subtopics[0].id).join(',')}`; };
  const box = $('#chapters', view);
  const HEAD = { bridge: [t('subject.bridge', 'Build your foundation'), t('subject.bridge.sub', 'Earlier lessons this class builds on. Do these first if something feels hard.')],
    extension: [t('subject.extension', 'Challenge extensions'), t('subject.extension.sub', 'Beyond the syllabus: for olympiads, JEE, NEET and the curious. Written by AI, not checked by a teacher yet.')] };
  let lastGroup = null;
  box.innerHTML = chapters.map((c) => {
    const head = c.group !== lastGroup && HEAD[c.group] ? `<div class="group-head"><h2>${esc(HEAD[c.group][0])}</h2><p class="muted small">${esc(HEAD[c.group][1])}</p></div>` : '';
    lastGroup = c.group;
    const done = c.subtopics.filter((x) => state.progress[x.id]?.status === 'completed').length;
    return `${head}<section class="chapter card" data-id="${c.id}">
      <button aria-expanded="false" aria-controls="sub-${c.id}"><span class="num">${c.number}</span><span>${esc(c.title)}${c.group === 'bridge' ? ` <span class="chip tiny">${t('common.grade', 'Grade')} ${c.grade}</span>` : ''}${c.board ? ` <span class="chip tiny">${esc(c.board.toUpperCase())}</span>` : ''}${c.track ? ` <span class="chip tiny">${esc(c.track)}</span>` : ''}</span>
        <span class="muted small">${done}/${c.subtopics.length}</span><span class="caret" aria-hidden="true">▶</span></button>
      <div class="subtopics" id="sub-${c.id}">${c.subtopics.map((x) => `<a class="subtopic" href="#/learn/${x.id}"><span class="dot ${masteryClass(state.progress[x.id])}" aria-hidden="true"></span><span>${esc(x.title)}</span>${state.bookmarks.includes(x.id) ? '<span aria-label="bookmarked">⭐</span>' : ''}${state.progress[x.id]?.status === 'completed' ? `<span class="muted small">${Math.round((state.progress[x.id].retention ?? state.progress[x.id].mastery) * 100)}%</span>` : ''}</a>`).join('')}</div>
    </section>`;
  }).join('');
  $$('.chapter > button', box).forEach((b) => (b.onclick = () => { const open = b.parentElement.classList.toggle('open'); b.setAttribute('aria-expanded', open); }));
  const first = chapters.find((c) => c.subtopics.some((x) => state.progress[x.id])) || chapters.find((c) => !c.group) || chapters[0];
  if (first) $(`.chapter[data-id="${first.id}"] > button`, box)?.click();
}
