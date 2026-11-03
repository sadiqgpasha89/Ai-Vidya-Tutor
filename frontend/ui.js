// Small UI toolkit: escaping, modals with focus trapping, toasts, confirm dialogs, charts, file helpers.
import { t } from './i18n.js';

export const $ = (sel, el = document) => el.querySelector(sel);
export const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const debounce = (fn, ms = 250) => { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); }; };

export function toast(message, ms = 3200) {
  const root = $('#toast-root');
  if ([...root.children].some((el) => el.textContent === message)) return; // no stacked duplicates
  const el = document.createElement('div'); el.className = 'toast'; el.textContent = message; el.setAttribute('role', 'status');
  root.append(el); setTimeout(() => el.remove(), ms);
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
let modalSeq = 0;

export function openModal(html, { title = '', onClose, dismissable = true, wide = false } = {}) {
  const root = $('#modal-root');
  const previous = document.activeElement;
  const id = `modal-${++modalSeq}`;
  const overlay = document.createElement('div'); overlay.className = 'overlay';
  overlay.innerHTML = `<div class="modal card${wide ? ' wide' : ''}" role="dialog" aria-modal="true" ${title ? `aria-labelledby="${id}-t"` : 'aria-label="Dialog"'}>
    ${dismissable ? `<button class="icon-btn small close" aria-label="${t('common.close', 'Close')}">✕</button>` : ''}${title ? `<h2 id="${id}-t">${esc(title)}</h2>` : ''}<div class="modal-body">${html}</div></div>`;
  const modal = $('.modal', overlay);
  const close = () => { overlay.remove(); previous?.focus?.(); onClose?.(); };
  if (dismissable) {
    $('.close', overlay).onclick = close;
    overlay.addEventListener('mousedown', (e) => { if (e.target === overlay) close(); });
  }
  overlay.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && dismissable) { e.stopPropagation(); close(); }
    if (e.key === 'Tab') { // keep keyboard focus inside the dialog
      const items = $$(FOCUSABLE, modal).filter((x) => x.offsetParent !== null);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  root.append(overlay);
  ($('[autofocus]', overlay) || $('input, textarea, select, button.primary', overlay) || $('.close', overlay) || modal).focus?.();
  return { el: $('.modal-body', overlay), modal, close, overlay };
}

export function confirmDialog(message, { yes = t('common.yes', 'Yes'), no = t('common.cancel', 'Cancel'), danger = false } = {}) {
  return new Promise((resolve) => {
    let answered = false;
    const m = openModal(`<p>${esc(message)}</p><div class="row end"><button class="btn" data-no>${esc(no)}</button><button class="btn ${danger ? 'danger' : 'primary'}" data-yes>${esc(yes)}</button></div>`,
      { onClose: () => { if (!answered) resolve(false); } });
    $('[data-yes]', m.el).onclick = () => { answered = true; m.close(); resolve(true); };
    $('[data-no]', m.el).onclick = () => { answered = true; m.close(); resolve(false); };
  });
}

export function promptDialog(label, { value = '', multiline = false, ok = t('common.save', 'Save') } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const m = openModal(`<div class="field"><label for="pd">${esc(label)}</label>${multiline ? `<textarea id="pd">${esc(value)}</textarea>` : `<input id="pd" type="text" value="${esc(value)}">`}</div>
      <div class="row end"><button class="btn" data-no>${t('common.cancel', 'Cancel')}</button><button class="btn primary" data-yes>${esc(ok)}</button></div>`, { onClose: () => { if (!done) resolve(null); } });
    $('[data-yes]', m.el).onclick = () => { done = true; const v = $('#pd', m.el).value; m.close(); resolve(v); };
    $('[data-no]', m.el).onclick = () => { done = true; m.close(); resolve(null); };
  });
}

export const fmtDate = (ts) => (ts ? new Date(ts * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—');
export const fmtDateTime = (ts) => (ts ? new Date(ts * 1000).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—');
export function timeAgo(ts) {
  if (!ts) return '—';
  const s = Math.max(1, Math.floor(Date.now() / 1000 - ts));
  return s < 90 ? t('time.now', 'just now') : s < 5400 ? t('time.min', '{n} min ago', { n: Math.round(s / 60) }) : s < 129600 ? t('time.hr', '{n} h ago', { n: Math.round(s / 3600) }) : t('time.day', '{n} days ago', { n: Math.round(s / 86400) });
}

export function download(filename, data, type = 'application/octet-stream') {
  const url = URL.createObjectURL(data instanceof Blob ? data : new Blob([data], { type }));
  const a = Object.assign(document.createElement('a'), { href: url, download: filename });
  document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export const readB64 = (file) => new Promise((resolve, reject) => {
  const r = new FileReader(); r.onload = () => resolve(String(r.result).split(',')[1]); r.onerror = reject; r.readAsDataURL(file);
});

// ---- tiny SVG charts (no library) -----------------------------------------------------------------
export function barChart(rows, { height = 160, color = 'var(--primary)', label = (r) => r.label, value = (r) => r.value } = {}) {
  const max = Math.max(1, ...rows.map(value)); const w = 100 / Math.max(rows.length, 1);
  return `<svg viewBox="0 0 100 ${height / 4}" class="chart" role="img" aria-label="bar chart" preserveAspectRatio="none">${rows.map((r, i) => {
    const h = (value(r) / max) * (height / 4 - 8);
    return `<rect x="${i * w + w * 0.15}" y="${height / 4 - 6 - h}" width="${w * 0.7}" height="${h}" rx="0.8" fill="${color}"><title>${esc(label(r))}: ${value(r)}</title></rect>`;
  }).join('')}</svg><div class="chart-axis">${rows.map((r) => `<span>${esc(String(label(r)).slice(-5))}</span>`).join('')}</div>`;
}
export function heat(v) { // 0..1 mastery -> colour; null = not started
  if (v == null) return 'var(--surface-2)';
  return `hsl(${Math.round(v * 120)}, 60%, ${42 + (1 - v) * 8}%)`;
}
export const ring = (pct, label) => `<div class="score-ring" style="--p:${Math.max(0, Math.min(100, pct))}" data-label="${esc(label ?? pct + '%')}" role="img" aria-label="${esc(label ?? pct + '%')}"></div>`;
