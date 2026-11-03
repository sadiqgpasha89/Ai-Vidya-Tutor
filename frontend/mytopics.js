// Topics a student adds themselves. The local model writes a lesson on each one, just like a syllabus topic; only this student can see them.
import { api, get } from './api.js';
import { t } from './i18n.js';
import { $, $$, esc, openModal, toast } from './ui.js';
import { state, subjectLabel } from './state.js';

const EXAMPLES = () => [t('mt.ex1', 'How do black holes form?'), t('mt.ex2', 'How does GPS know where I am?'), t('mt.ex3', 'Why do we dream?'), t('mt.ex4', 'How does a vaccine work?')];

const subjectName = (id) => (id === 'general' ? t('mt.general', 'Anything') : subjectLabel(state.meta.subjects.find((s) => s.id === id) || { id, name: id, tagline: '' }).name);

export function openAddTopic() {
  const subs = state.meta.subjects.filter((s) => s.grades.includes(state.profile.grade));
  const m = openModal(`<form id="mt-form" novalidate>
      <p class="muted">${t('mt.intro', 'Type anything you would like to learn. AIVidya writes a lesson on it, in your language, at your level. Only you can see it.')}</p>
      <div class="field"><label for="mt-title">${t('mt.title', 'What do you want to learn?')}</label><input id="mt-title" type="text" maxlength="120" required autocomplete="off" placeholder="${esc(EXAMPLES()[Math.floor(Math.random() * 4)])}"></div>
      <div class="field"><label for="mt-details">${t('mt.details', 'Anything specific? (optional)')}</label><textarea id="mt-details" maxlength="500" rows="3" placeholder="${esc(t('mt.details.ph', 'For example: I know the basics, explain the maths part slowly.'))}"></textarea></div>
      <div class="field"><label for="mt-subject">${t('mt.subject', 'Which subject is it closest to?')}</label><select id="mt-subject"><option value="general">${esc(t('mt.general', 'Anything'))}</option>${subs.map((s) => `<option value="${s.id}">${esc(subjectLabel(s).name)}</option>`).join('')}</select></div>
      <p class="error" id="mt-err" role="alert" hidden></p>
      <div class="row end"><button class="btn primary" id="mt-go" type="submit">✨ ${t('mt.go', 'Write my lesson')}</button></div>
    </form>`, { title: `💡 ${t('mt.add', 'Add a topic')}` });
  const err = (msg) => { const e = $('#mt-err', m.el); e.textContent = msg; e.hidden = !msg; };
  $('#mt-title', m.el).focus();
  $('#mt-form', m.el).onsubmit = async (ev) => {
    ev.preventDefault(); err('');
    const title = $('#mt-title', m.el).value.trim();
    if (title.length < 3) return err(t('mt.short', 'Give your topic a name of at least 3 letters.'));
    const btn = $('#mt-go', m.el); btn.disabled = true;
    try {
      const { item } = await api('/api/my-topics', { title, details: $('#mt-details', m.el).value.trim(), subject: $('#mt-subject', m.el).value });
      m.close(); location.hash = `#/learn/${item.id}`;
    } catch (e) { err(e.message); btn.disabled = false; }
  };
}

async function remove(id, title, after) {
  if (!window.confirm(t('mt.confirmdelete', 'Remove “{title}” and its lesson, notes and chat?', { title }))) return;
  try { await api(`/api/my-topics/${id}`, undefined, 'DELETE'); toast(t('mt.removed', 'Removed')); after(); } catch (e) { toast(e.message); }
}

const card = (it) => `<div class="topic-pill mytopic" data-id="${it.id}"><a href="#/learn/${it.id}"><b>💡 ${esc(it.title)}</b><span class="muted small">${esc(subjectName(it.subject))}</span></a>
  <button class="icon-btn small" data-del="${it.id}" data-title="${esc(it.title)}" aria-label="${esc(t('mt.remove', 'Remove'))} ${esc(it.title)}" title="${esc(t('mt.remove', 'Remove'))}">✕</button></div>`;

function wireDelete(root, reload) { $$('[data-del]', root).forEach((b) => (b.onclick = () => remove(b.dataset.del, b.dataset.title, reload))); }

/** The short section on the home page. */
export async function homeSection(host) {
  const draw = async () => {
    let items = []; try { items = (await get('/api/my-topics')).items; } catch { /* the rest of the page still works */ }
    host.innerHTML = `<h2 class="section-title">💡 ${t('mt.heading', 'My topics')} ${items.length > 6 ? `<a class="small" href="#/mytopics">${t('common.seeall', 'See all')}</a>` : ''}</h2>
      <div class="topic-pills">${items.slice(0, 6).map(card).join('')}<button class="topic-pill addtopic" id="mt-add"><b>＋ ${t('mt.add', 'Add a topic')}</b><span class="muted small">${t('mt.addhint', 'Anything you are curious about')}</span></button></div>`;
    $('#mt-add', host).onclick = openAddTopic; wireDelete(host, draw);
  };
  await draw();
}

export async function renderMyTopics(view) {
  const draw = async () => {
    const { items } = await get('/api/my-topics');
    view.innerHTML = `<div class="crumbs"><a href="#/">${t('nav.home', 'Home')}</a> › ${t('mt.heading', 'My topics')}</div>
      <div class="row"><h1 style="flex:1">💡 ${t('mt.heading', 'My topics')}</h1><button class="btn primary" id="mt-add">＋ ${t('mt.add', 'Add a topic')}</button></div>
      <p class="muted">${t('mt.intro', 'Type anything you would like to learn. AIVidya writes a lesson on it, in your language, at your level. Only you can see it.')}</p>
      ${items.length ? `<div class="topic-pills">${items.map(card).join('')}</div>` : `<p class="empty">${t('mt.none', 'You have not added a topic yet. Try one: {ex}', { ex: esc(EXAMPLES()[0]) })}</p>`}`;
    $('#mt-add', view).onclick = openAddTopic; wireDelete(view, draw);
  };
  await draw();
}
