// Shared client state, persisted display/voice preferences, and API-backed helpers.
import { get } from './api.js';
import { $ } from './ui.js';
import { t } from './i18n.js';

const read = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
const write = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage blocked */ } };

export const state = {
  meta: null, user: null, profile: null, unread: 0,
  settings: { rate: 1, autoplay: true, speakReplies: true, captions: true, voiceByLang: {}, ttsEngine: 'auto', sttEngine: 'auto', bargeIn: false, confirmVoice: true, ...read('vidya.settings', {}) },
  prefs: { theme: 'system', fontScale: 100, dyslexia: false, dataSaver: false, spacing: false, ...read('vidya.prefs', {}) },
  progress: {}, due: [], card: null, cards: {}, mistakes: 0, bookmarks: [], streak: 0,
  curriculumCache: {}, last: read('vidya.last', null),
};

export const saveSettings = () => write('vidya.settings', state.settings);
export const savePrefs = () => { write('vidya.prefs', state.prefs); applyPrefs(); };
export function saveLast(topic) { state.last = { id: topic.id, title: topic.title, subject: topic.subject, subject_name: topic.subject_name, grade: topic.grade }; write('vidya.last', state.last); }

export function applyPrefs() {
  const r = document.documentElement, p = state.prefs;
  if (p.theme === 'system') r.removeAttribute('data-theme'); else r.setAttribute('data-theme', p.theme);
  r.style.setProperty('--fs', `${p.fontScale}%`);
  r.classList.toggle('dyslexia', !!p.dyslexia);
  r.classList.toggle('spacing', !!p.spacing);
  r.classList.toggle('data-saver', !!p.dataSaver);
}

const GENERAL = { id: 'general', name: 'My topics', icon: '💡', color: '#6366f1', tagline: '', grades: [7, 8, 9, 10, 11, 12] };
export const subjectInfo = (id) => state.meta.subjects.find((s) => s.id === id) || (id === 'general' ? GENERAL : undefined);
export const langInfo = (id) => state.meta.languages.find((l) => l.id === id) || state.meta.languages[0];
export const speechLang = () => langInfo(state.profile?.language).speech;
export const isStudent = () => state.user?.role === 'student';
export const isStaff = () => ['teacher', 'school_admin', 'admin'].includes(state.user?.role);
export const trackFor = (grade) => (grade >= 11 ? (state.profile?.track || 'CS') : '');

export async function loadCurriculum(subject, grade) {
  const key = `${subject}:${grade}:${state.profile?.board}:${state.profile?.track}`;
  if (!state.curriculumCache[key]) state.curriculumCache[key] = (await get(`/api/curriculum?subject=${subject}&grade=${grade}`)).chapters;
  return state.curriculumCache[key];
}

export async function refreshProgress() {
  if (!isStudent()) return;
  try {
    const p = await get('/api/me/progress');
    Object.assign(state, { progress: p.progress, due: p.due, streak: p.streak, card: p.card, cards: p.cards, mistakes: p.mistakes, bookmarks: p.bookmarks, unread: p.unread });
  } catch { /* offline: keep stale numbers */ }
  const s = $('#streak'); if (s) { s.hidden = false; $('b', s).textContent = state.streak; s.setAttribute('aria-label', `${t('streak.title', 'Your daily streak')}: ${state.streak}`); }
  updateBell();
}

export function updateBell() {
  const b = $('#bell-count'); if (b) { b.hidden = !state.unread; b.textContent = state.unread > 9 ? '9+' : state.unread; }
}

export const masteryClass = (p) => (!p ? '' : p.status === 'completed' ? ((p.retention ?? p.mastery) < 0.5 ? 'weak' : 'completed') : 'started');

// The server writes some short notes in English (plan reasons) and subject names; show them in the chosen language.
export function whyText(why = '') {
  const known = { 'Due for revision so you don\'t forget it': t('plan.why.revise', 'Due for revision so you don\'t forget it'), 'Your recall of this is fading': t('plan.why.fading', 'Your recall of this is fading'),
    'Next topic in your syllabus': t('plan.why.next', 'Next topic in your syllabus'), 'Fix questions you got wrong before': t('plan.why.mistakes', 'Fix questions you got wrong before') };
  const m = /^(\d+) flashcards are due$/.exec(why);
  return m ? t('plan.why.cards', '{n} flashcards are due', { n: m[1] }) : known[why] || why;
}
export function subjectLabel(s) {
  const names = { physics: t('subj.physics', 'Physics'), chemistry: t('subj.chemistry', 'Chemistry'), biology: t('subj.biology', 'Biology'), maths: t('subj.maths', 'Maths'), computers: t('subj.computers', 'Computers'),
    english: t('subj.english', 'English'), social: t('subj.social', 'Social Science'), commerce: t('subj.commerce', 'Commerce') };
  const tags = { physics: t('tag.physics', 'How the universe moves'), chemistry: t('tag.chemistry', 'What everything is made of'), biology: t('tag.biology', 'The science of life'), maths: t('tag.maths', 'The language of patterns'),
    computers: t('tag.computers', 'Think, build, code'), english: t('tag.english', 'Read, write, speak well'), social: t('tag.social', 'History, geography, civics, economics'), commerce: t('tag.commerce', 'Accounts, business, economics') };
  return { name: names[s.id] || s.name, tagline: tags[s.id] || s.tagline };
}
