// The language button in the top-right corner: one choice sets the language of the buttons and menus, of the lessons and answers, and of the voice.
import { t } from './i18n.js';
import { $, $$, esc } from './ui.js';
import { state } from './state.js';

const label = (l) => l.native;
let applyChoice = async () => {};

export const currentLang = () => state.meta.languages.find((l) => l.id === (document.documentElement.lang || 'en')) || state.meta.languages[0];

export function renderLangButton() {
  const l = currentLang(); $('#lang-label').textContent = l.native; $('#lang-btn').setAttribute('aria-label', `${t('lang.title', 'Language')}: ${l.name}`);
  $('#lang-btn').title = t('lang.tip', 'Language of the app, the lessons and the voice');
}

function panelHtml() {
  const cur = currentLang().id, group = (id, heading) => `<div class="lang-group" role="group" aria-label="${esc(heading)}"><div class="lang-heading">${esc(heading)}</div>${state.meta.languages.filter((l) => l.group === id).map((l) =>
    `<button class="lang-opt" role="option" data-lang="${l.id}" aria-selected="${l.id === cur}" lang="${l.id}"><span class="ln">${esc(label(l))}</span><span class="le">${esc(l.name)}${l.experimental ? ` · ${esc(t('lang.beta', 'beta'))}` : ''}</span><span class="tick" aria-hidden="true">${l.id === cur ? '✓' : ''}</span></button>`).join('')}</div>`;
  return `${group('india', t('lang.india', 'Indian languages'))}${group('world', t('lang.world', 'International languages'))}<p class="lang-note">${esc(t('lang.note', 'Changes the buttons, the lessons and answers, and the voice.'))}</p>`;
}

function close(restore = true) { const p = $('#lang-panel'); if (p.hidden) return; p.hidden = true; $('#lang-btn').setAttribute('aria-expanded', 'false'); if (restore) $('#lang-btn').focus(); }
function open() {
  const p = $('#lang-panel'); p.innerHTML = panelHtml(); p.hidden = false; $('#lang-btn').setAttribute('aria-expanded', 'true');
  $$('.lang-opt', p).forEach((b) => (b.onclick = async () => { close(false); await applyChoice(b.dataset.lang); $('#lang-btn').focus(); }));
  ($('.lang-opt[aria-selected="true"]', p) || $('.lang-opt', p)).focus();
}

export function initLangPicker(apply) {
  applyChoice = apply;
  $('#lang-btn').onclick = () => ($('#lang-panel').hidden ? open() : close());
  document.addEventListener('click', (e) => { if (!$('#lang-panel').hidden && !e.target.closest('.lang-wrap')) close(false); });
  document.addEventListener('keydown', (e) => {
    if ($('#lang-panel').hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); const o = $$('.lang-opt', $('#lang-panel')), i = o.indexOf(document.activeElement); o[(i + (e.key === 'ArrowDown' ? 1 : -1) + o.length) % o.length].focus(); }
  });
}
