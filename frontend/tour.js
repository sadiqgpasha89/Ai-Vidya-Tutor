// First-run guided tour: highlights a few controls with short explanations (keyboard accessible, skippable).
import { t } from './i18n.js';
import { $, esc } from './ui.js';

export function stopTour() { document.querySelectorAll('.tour').forEach((e) => e.remove()); document.querySelectorAll('.tour-hl').forEach((e) => e.classList.remove('tour-hl')); }

export function startTour(force = false) {
  if (!force && localStorage.getItem('vidya.tour')) return;
  if (!force && document.querySelector('#modal-root .overlay')) { // a dialog (first-run settings) is open: show the tour once it is closed, and only on the home page
    setTimeout(() => { if (!location.hash || location.hash === '#/') startTour(false); }, 800); return;
  }
  stopTour();
  const steps = [
    ['#view', t('tour.1', 'This is your home. Pick a subject card to see its chapters and topics.')],
    ['#search-input', t('tour.2', 'Search any topic. You can type a question too — it matches by meaning.')],
    ['#menu-btn', t('tour.3', 'The menu: your subjects, tests, plan, notes and tools are all in here.')],
    ['#lang-btn', t('tour.5', 'Choose your language here: the app, the lessons and the voice all switch together.')],
    ['#settings-btn', t('tour.4', 'Settings: language, voice, text size, goals and privacy.')],
  ];
  let i = 0;
  const box = document.createElement('div'); box.className = 'tour'; box.setAttribute('role', 'dialog'); box.setAttribute('aria-label', 'Tour');
  document.body.append(box);
  const end = () => { box.remove(); document.querySelectorAll('.tour-hl').forEach((e) => e.classList.remove('tour-hl')); try { localStorage.setItem('vidya.tour', '1'); } catch { /* storage blocked */ } };
  const show = () => {
    document.querySelectorAll('.tour-hl').forEach((e) => e.classList.remove('tour-hl'));
    const [sel, text] = steps[i]; const target = $(sel);
    if (!target || target.offsetParent === null) { if (++i < steps.length) return show(); return end(); }
    target.classList.add('tour-hl');
    box.innerHTML = `<p>${esc(text)}</p><div class="row"><span class="muted small">${i + 1}/${steps.length}</span><span class="spacer"></span><button class="btn sm" data-skip>${t('tour.skip', 'Skip')}</button><button class="btn sm primary" data-next autofocus>${i + 1 === steps.length ? t('tour.done', 'Done') : t('tour.next', 'Next')}</button></div>`;
    $('[data-skip]', box).onclick = end;
    $('[data-next]', box).onclick = () => (++i < steps.length ? show() : end());
    $('[data-next]', box).focus();
  };
  show();
}
