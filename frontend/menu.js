// The menu: a drawer that slides in from the left behind the ☰ button. Groups expand and collapse; the group you are in opens by itself.
import { t } from './i18n.js';
import { $, $$, esc } from './ui.js';

const KEY = 'vidya.menu';
const read = () => { try { return new Set(JSON.parse(localStorage.getItem(KEY) || '[]')); } catch { return new Set(); } };
const write = (s) => { try { localStorage.setItem(KEY, JSON.stringify([...s])); } catch { /* storage blocked: groups just start closed */ } };
const here = (href, cur) => cur === href || (href.length > 3 && cur.startsWith(href + '/'));

let opener = null;
export const isOpen = () => !$('#drawer').hidden;

export function openMenu() {
  const d = $('#drawer'); if (!d.hidden) return;
  opener = document.activeElement; d.hidden = false; $('#drawer-overlay').hidden = false; $('#menu-btn').setAttribute('aria-expanded', 'true');
  requestAnimationFrame(() => d.classList.add('open'));
  ($('.dgroup[aria-expanded="true"], .dlink[aria-current="page"], .dgroup, .dlink', d) || d).focus();
}
export function closeMenu(restore = true) {
  const d = $('#drawer'); if (d.hidden) return;
  d.classList.remove('open'); $('#menu-btn').setAttribute('aria-expanded', 'false'); $('#drawer-overlay').hidden = true;
  setTimeout(() => { if (!d.classList.contains('open')) d.hidden = true; }, 180);
  if (restore) (opener && document.contains(opener) ? opener : $('#menu-btn')).focus();
}

export function initMenu() {
  $('#menu-btn').onclick = () => (isOpen() ? closeMenu() : openMenu());
  $('#drawer-overlay').onclick = () => closeMenu();
  document.addEventListener('keydown', (e) => {
    if (!isOpen()) return;
    if (e.key === 'Escape') { e.preventDefault(); closeMenu(); }
    if (e.key === 'Tab') { // keep keyboard focus inside the open menu
      const f = $$('#drawer button, #drawer a').filter((x) => x.offsetParent !== null); if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  window.addEventListener('hashchange', () => closeMenu(false));
}

/** items: [{link: [href, label, icon]} | {id, icon, label, items: [[href, label, icon?]]} | {id, icon, label, action: fn}] */
export function renderMenu(entries, cur, onAction) {
  const open = read();
  const link = ([href, label, icon], cls = 'dlink') => `<a class="${cls}" href="${esc(href)}" ${here(href, cur) ? 'aria-current="page"' : ''}>${icon ? `<span class="di" aria-hidden="true">${icon}</span>` : ''}<span>${esc(label)}</span></a>`;
  $('#drawer').innerHTML = `<div class="drawer-head"><b>${esc(t('menu.title', 'Menu'))}</b><button class="icon-btn small" id="drawer-close" aria-label="${esc(t('common.close', 'Close'))}">✕</button></div>
    <ul class="dlist">${entries.map((e) => {
    if (e.link) return `<li>${link(e.link)}</li>`;
    if (e.action) return `<li><button class="dlink" data-action="${esc(e.id)}"><span class="di" aria-hidden="true">${e.icon}</span><span>${esc(e.label)}</span></button></li>`;
    const active = e.items.some(([href]) => here(href, cur)), expanded = open.has(e.id) || active;
    return `<li class="dgroup-wrap"><button class="dgroup" id="dh-${e.id}" aria-expanded="${expanded}" aria-controls="dg-${e.id}" data-group="${e.id}"><span class="di" aria-hidden="true">${e.icon}</span><span>${esc(e.label)}</span><span class="caret" aria-hidden="true">▸</span></button>
      <ul class="dsub" id="dg-${e.id}" ${expanded ? '' : 'hidden'}>${e.items.map((i) => `<li>${link(i, 'dlink sub')}</li>`).join('')}</ul></li>`;
  }).join('')}</ul>`;
  $('#drawer-close').onclick = () => closeMenu();
  $$('.dgroup', $('#drawer')).forEach((b) => (b.onclick = () => {
    const ex = b.getAttribute('aria-expanded') === 'true'; b.setAttribute('aria-expanded', !ex); $('#' + b.getAttribute('aria-controls')).hidden = ex;
    const s = read(); ex ? s.delete(b.dataset.group) : s.add(b.dataset.group); write(s);
  }));
  $$('[data-action]', $('#drawer')).forEach((b) => (b.onclick = () => { closeMenu(false); onAction?.(b.dataset.action); }));
  $$('a.dlink', $('#drawer')).forEach((a) => a.addEventListener('click', () => closeMenu(false)));
}
