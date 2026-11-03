// Boot, routing, navigation, status indicators and legal pages.
import { api, get, on, put } from './api.js';
import { t, setUiLang } from './i18n.js';
import { $, $$, esc, toast, openModal } from './ui.js';
import { state, refreshProgress, applyPrefs, isStudent, isStaff, updateBell } from './state.js';
import { speaker, serverVoice } from './voice.js';
import { showAuth, showConsentWaiting, setAuthDone } from './auth.js';
import { renderHome, renderSubject, renderSearch } from './home.js';
import { openSettings, openNotifications, onProfileSaved } from './settings.js';
import { startTour, stopTour } from './tour.js';
import { initMenu, renderMenu } from './menu.js';
import { initLangPicker, renderLangButton } from './langpicker.js';
import { watchIdle, markActive } from './idle.js';
import { openStreak } from './streak.js';

let leave = () => {};
export const setLeave = (fn) => { leave = fn; };

// The menu, by role. Each group expands; links open pages. Subject names come from the server (English); the rest is translated.
const SUBJECT_NAMES = () => ({ physics: t('subj.physics', 'Physics'), chemistry: t('subj.chemistry', 'Chemistry'), biology: t('subj.biology', 'Biology'), maths: t('subj.maths', 'Maths'), computers: t('subj.computers', 'Computers'),
  english: t('subj.english', 'English'), social: t('subj.social', 'Social Science'), commerce: t('subj.commerce', 'Commerce') });
const teaching = () => ({ id: 'teaching', icon: '🍎', label: t('menu.teaching', 'Teaching'), items: [['#/teach', t('nav.classes', 'Classes')], ['#/teach/review', t('nav.review', 'Review lessons')], ['#/teach/reports', t('nav.reports', 'Reports')],
  ['#/teach/doubts', t('doubt.inbox', 'Doubts')], ['#/teach/worksheets', t('ws.heading', 'Worksheets')], ['#/teach/bank', t('nav.bank', 'Question bank')], ['#/teach/library', t('nav.library', 'Library')]] });
const toolsGroup = () => ({ id: 'tools', icon: '🧰', label: t('nav.tools', 'Tools'), items: [['#/tools', t('menu.sims', 'Simulations & tools')], ['#/voicecheck', t('menu.voicecheck', 'Voice check')]] });
const helpGroup = () => ({ id: 'help', icon: '❓', label: t('menu.help', 'Help'), items: [['#/legal/privacy', t('legal.privacy', 'Privacy notice')], ['#/legal/terms', t('legal.terms', 'Terms')]] });

function menuEntries() {
  const role = state.user.role, names = SUBJECT_NAMES();
  const home = { link: ['#/', t('nav.home', 'Home'), '🏠'] };
  const actions = [{ id: 'tour', icon: '🧭', label: t('menu.tour', 'Take the tour'), action: true }, ...(deferredInstall ? [{ id: 'install', icon: '⬇️', label: t('nav.install', 'Install app'), action: true }] : [])];
  if (role === 'student') {
    const grade = state.profile?.grade, subjects = (state.meta.subjects || []).filter((x) => !grade || x.grades.includes(grade));
    return [home, { link: ['#/mytopics', t('mt.heading', 'My topics'), '💡'] },
      { id: 'subjects', icon: '📚', label: t('menu.subjects', 'Subjects'), items: subjects.map((x) => [`#/subject/${x.id}/${grade || x.grades[0]}`, names[x.id] || x.name, x.icon]) },
      { id: 'practice', icon: '📝', label: t('menu.practice', 'Practice'), items: [['#/daily', t('daily.heading', 'Daily 5')], ['#/revise', t('nav.revise', 'Revise')], ['#/coach', t('coach.heading', 'Answer coach')], ['#/tests', t('nav.tests', 'Tests')], ['#/doubts', t('doubt.heading', 'Ask my teacher')], ['#/mistakes', t('nav.mistakes', 'Mistakes')], ['#/assignments', t('nav.assignments', 'Assignments')]] },
      { id: 'progress', icon: '📈', label: t('menu.progress', 'My progress'), items: [['#/plan', t('nav.plan', 'Plan')], ['#/me', t('nav.me', 'Me')], ['#/notes', t('nav.notes', 'Notes')]] },
      toolsGroup(), helpGroup(), ...actions];
  }
  if (role === 'parent') return [{ link: ['#/parent', t('nav.children', 'My children'), '👪'] }, helpGroup(), ...actions];
  const extra = role === 'teacher' ? [] : [{ link: ['#/admin', 'Admin console', '🛠️'] }];
  return [teaching(), ...extra, toolsGroup(), helpGroup(), ...actions];
}

function renderNav() {
  renderMenu(menuEntries(), location.hash || '#/', async (id) => {
    if (id === 'tour') { location.hash = '#/'; setTimeout(() => startTour(true), 300); }
    if (id === 'install') { deferredInstall.prompt(); deferredInstall = null; renderNav(); }
  });
  const mb = $('#menu-btn'); mb.hidden = false; mb.title = t('menu.title', 'Menu'); mb.setAttribute('aria-label', t('menu.title', 'Menu'));
  $('#search-form').hidden = !isStudent();
  for (const id of ['bell', 'settings-btn', 'health']) $('#' + id).hidden = false;
  $('#settings-btn').title = t('set.title', 'Settings');
  renderLangButton();
}

let deferredInstall = null;
window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); deferredInstall = e; if (state.user) renderNav(); });

const ROUTES = [
  [/^\/?$/, async (v) => (isStudent() ? renderHome(v) : (location.hash = state.user.role === 'parent' ? '#/parent' : '#/teach'))],
  [/^\/subject\/([^/]+)\/(\d+)$/, (v, m) => renderSubject(v, m[1], +m[2])],
  [/^\/mytopics$/, async (v) => (await import('./mytopics.js')).renderMyTopics(v)],
  [/^\/search\/(.+)$/, (v, m) => renderSearch(v, decodeURIComponent(m[1]))],
  [/^\/learn\/([^/?]+)/, async (v, m) => (await import('./lesson.js')).renderLesson(v, decodeURIComponent(m[1]))],
  [/^\/(revise|mistakes|notes|plan|me|tests|assignments)(\/.*)?$/, async (v, m) => (await import('./study.js')).route(v, m[1], (m[2] || '').slice(1))],
  [/^\/daily$/, async (v) => (await import('./daily.js')).renderDaily(v)],
  [/^\/coach(\/.*)?$/, async (v, m) => (await import('./coach.js')).route(v, (m[1] || '').slice(1))],
  [/^\/doubts(\/.*)?$/, async (v, m) => (await import('./doubts.js')).route(v, (m[1] || '').slice(1))],
  [/^\/test\/([^/]+)$/, async (v, m) => (await import('./study.js')).renderTest(v, m[1])],
  [/^\/tools(\/.*)?$/, async (v, m) => (await import('./tools.js')).route(v, (m[1] || '').slice(1))],
  [/^\/voicecheck$/, async (v) => (await import('./tools.js')).renderVoiceCheck(v)],
  [/^\/admin(\/.*)?$/, async (v, m) => (await import('./admin.js')).route(v, (m[1] || '').slice(1))],
  [/^\/(teach|parent)(\/.*)?$/, async (v, m) => (await import('./staff.js')).route(v, m[1], (m[2] || '').slice(1))],
  [/^\/legal\/(privacy|terms)$/, async (v, m) => renderLegal(v, m[1])],
];

async function route() {
  if (!state.user) return;
  const view = $('#view');
  stopTour(); leave(); leave = () => {}; speaker.stop(true); $('#caption').hidden = true;
  document.title = 'AIVidya – ' + t('app.tagline', 'Your AI Teacher');
  const path = location.hash.replace(/^#/, '') || '/';
  renderNav();
  try {
    if (isStudent()) await refreshProgress();
    const hit = ROUTES.find(([re]) => re.test(path.split('?')[0]));
    if (!hit) { view.innerHTML = `<div class="banner">${t('err.notfound', 'That page does not exist.')} <a href="#/">${t('nav.home', 'Home')}</a></div>`; return; }
    await hit[1](view, hit[0].exec(path.split('?')[0]));
  } catch (err) {
    if (err.code === 'consent_required' || err.status === 401) return;
    view.innerHTML = `<div class="banner" role="alert"><b>${t('err.title', 'Something went wrong.')}</b> ${esc(err.message)}<div style="margin-top:8px"><a class="btn sm" href="#/">${t('nav.home', 'Home')}</a></div></div>`;
  }
  if (!/^\/learn\//.test(path)) { window.scrollTo(0, 0); view.focus({ preventScroll: true }); }
  if (path === '/' && isStudent()) setTimeout(() => startTour(), 600);
}

async function renderLegal(view, page) {
  const text = await get(`/api/legal/${page}`);
  const html = window.DOMPurify.sanitize(window.marked.parse(text));
  view.innerHTML = `<article class="card legal prose"><p><a href="#/">← ${t('nav.home', 'Home')}</a></p>${html}</article>`;
}

// ---- status: health dot, offline bar -------------------------------------------------------------------------------------
async function pollHealth() {
  const dot = $('#health');
  try {
    const h = await get('/api/health');
    dot.className = `health ${h.ready ? 'ok' : 'bad'}`; const label = h.ready ? t('health.ok', 'Teacher is ready') : t('health.bad', 'Teacher is not ready: {why}', { why: h.problem || '' });
    dot.title = label; dot.setAttribute('aria-label', label);
    if (!h.ready && !pollHealth.warned) { pollHealth.warned = true; toast(label, 9000); }
    if (h.ready) pollHealth.warned = false;
  } catch { dot.className = 'health bad'; dot.title = t('health.down', 'Cannot reach the AIVidya server'); }
}
const syncOnline = () => { $('#offline').hidden = navigator.onLine; };
window.addEventListener('online', syncOnline); window.addEventListener('offline', syncOnline);

// ---- language: one choice for the buttons and menus, the lessons and answers, and the voice -------------------------------------------
const chosenLanguage = () => (isStudent() && state.profile?.language) || localStorage.getItem('vidya.ui') || 'en';
async function changeLanguage(id) {
  try { localStorage.setItem('vidya.ui', id); } catch { /* storage blocked */ }
  if (isStudent() && state.profile && state.profile.language !== id) {
    const p = state.profile;
    try { state.profile = (await put('/api/me/profile', { grade: p.grade, language: id, level: p.level, board: p.board, goal: p.goal || 'boards', stream: p.stream || '', track: p.track || '', exam_date: p.exam_date || '', daily_minutes: p.daily_minutes || 30 })).profile; }
    catch (er) { toast(er.message); }
    state.curriculumCache = {};
  }
  speaker.stop(true); await setUiLang(id); applyUiText(); if (state.user) { renderNav(); await route(); } else { renderLangButton(); location.reload(); }
}
function applyUiText() {
  $('#skip').textContent = t('nav.skip', 'Skip to content');
  $('#footer').firstElementChild.textContent = t('footer.ai', 'AI can make mistakes — check with your teacher or textbook.');
  $('#search-input').placeholder = t('search.placeholder', 'Search any topic or ask a question…');
  $('#offline').textContent = t('offline.msg', 'You are offline. Lessons you opened before still work.');
}

// ---- boot --------------------------------------------------------------------------------------------------------------------------
async function enter() {
  let me;
  try { me = await get('/api/auth/me'); } catch (e) { if (e.status === 401) return; throw e; } // the 401 handler has already shown the sign-in page (and why)
  markActive(); state.user = me.user; state.emailMasked = me.email || null; state.emailVerified = !!me.email_verified; state.hasPassword = !!me.has_password; state.remembered = !!me.remembered; state.profile = me.profile || null; state.unread = me.unread || 0;
  if (state.user.role === 'student' && state.user.consent === 'pending') return showConsentWaiting();
  await setUiLang(chosenLanguage());
  applyUiText();
  renderNav(); updateBell(); pollHealth(); setInterval(pollHealth, 60000); syncOnline();
  if (state.meta.auth === 'off' && isStudent() && !localStorage.getItem('vidya.onboarded')) { localStorage.setItem('vidya.onboarded', '1'); openSettings('profile'); }
  if (!location.hash) location.hash = '#/';
  await route();
}

async function boot() {
  applyPrefs();
  try { state.meta = await get('/api/meta'); } catch { $('#view').innerHTML = `<div class="banner">${t('err.server', 'Cannot reach the AIVidya server. Start it with ./run.sh and reload.')}</div>`; return; }
  Object.assign(serverVoice, { tts: state.meta.voice.tts_languages, stt: state.meta.voice.stt });
  setAuthDone(enter);
  const idleNotice = (m) => t('auth.idle', 'You were signed out after {m} minutes of inactivity. Please sign in again.').replace('{m}', m);
  on('auth:required', (code) => { state.user = null; showAuth('in', code === 'idle' ? idleNotice(state.meta.idle_minutes) : ''); });
  watchIdle((m) => { state.user = null; showAuth('in', idleNotice(m)); });
  on('consent:required', () => showConsentWaiting());
  onProfileSaved(async () => { await setUiLang(chosenLanguage()); renderNav(); await route(); });
  initMenu(); initLangPicker(changeLanguage); await setUiLang(chosenLanguage()); applyUiText(); renderLangButton();
  $('#settings-btn').onclick = () => state.user && openSettings();
  $('#streak').onclick = () => state.user && openStreak();
  $('#bell').onclick = () => state.user && openNotifications();
  $('#caption-stop').onclick = () => speaker.stop();
  $('#search-form').onsubmit = (e) => { e.preventDefault(); const q = $('#search-input').value.trim(); if (q) location.hash = `#/search/${encodeURIComponent(q)}`; };
  window.addEventListener('hashchange', route);
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
  await enter();
}
boot();
