// Prepared study notes: short bullet points with a diagram for each part, kept on the server, downloadable and printable.
import { api, get, del } from './api.js';
import { t } from './i18n.js';
import { md, esc } from './render.js';
import { $, toast, openModal, confirmDialog, fmtDate } from './ui.js';

const img = (svg, alt) => `<img alt="${esc(alt)}" src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}">`;

export const savedNotes = async (id) => (await get(`/api/lesson-notes?subtopic_id=${encodeURIComponent(id)}`)).notes;

function doc(n) {
  return `<article class="notes-doc"><p class="muted small">${esc(n.subject_name || '')} · ${t('common.grade', 'Grade')} ${n.grade ?? ''} · ${fmtDate(n.updated_at)}</p><h2 class="notes-title">${esc(n.title)}</h2>
    ${n.summary ? `<div class="notes-summary prose">${md(n.summary)}</div>` : ''}
    ${n.sections.map((s) => `<section class="notes-part"><h3>${esc(s.heading)}</h3><div class="prose"><ul>${s.bullets.map((b) => `<li>${md(b).replace(/^<p>|<\/p>\s*$/g, '')}</li>`).join('')}</ul></div>${s.svg ? `<figure class="lesson-figure">${img(s.svg, `${t('lesson.diagram.alt', 'Diagram of')} ${s.heading}`)}</figure>` : ''}</section>`).join('')}
    ${n.remember?.length ? `<section class="notes-remember"><h3>⭐ ${t('notes.remember', 'Remember')}</h3><div class="prose"><ul>${n.remember.map((b) => `<li>${md(b).replace(/^<p>|<\/p>\s*$/g, '')}</li>`).join('')}</ul></div></section>` : ''}
    <p class="muted small">🤖 ${t('notes.ai', 'Made by AI from your lesson — check it against your textbook.')}</p></article>`;
}

export function showNotes(topic, n, after = () => {}) {
  const q = `subtopic_id=${encodeURIComponent(topic.id)}`;
  const m = openModal(`${doc(n)}<div class="row notes-actions">
      <a class="btn primary" href="/api/lesson-notes/download?${q}&format=html" download>⬇️ ${t('notes.dlhtml', 'Download (web page)')}</a>
      <a class="btn" href="/api/lesson-notes/download?${q}&format=md" download>⬇️ ${t('notes.dlmd', 'Download (Markdown)')}</a>
      <button class="btn" id="n-print">🖨️ ${t('notes.print', 'Print / save as PDF')}</button><span class="spacer"></span>
      <button class="btn" id="n-redo">🔄 ${t('notes.redo', 'Prepare again')}</button><button class="btn danger" id="n-del">🗑️ ${t('common.delete', 'Delete')}</button></div>`, { title: t('notes.heading', 'Study notes'), wide: true });
  $('#n-print', m.el).onclick = () => {
    document.body.classList.add('print-notes');
    addEventListener('afterprint', () => document.body.classList.remove('print-notes'), { once: true });
    window.print();
  };
  $('#n-redo', m.el).onclick = async () => { m.close(); await prepare(topic, true, after); };
  $('#n-del', m.el).onclick = async () => { if (await confirmDialog(t('notes.delconfirm', 'Delete these notes? You can prepare them again any time.'), { danger: true })) { await del(`/api/lesson-notes?${q}`); m.close(); toast(t('notes.deleted', 'Notes deleted')); after(null); } };
}

/** Open the saved notes for a topic, or write them first. force = write them again. */
export async function prepare(topic, force = false, after = () => {}) {
  if (!force) { try { const have = await savedNotes(topic.id); if (have) { showNotes(topic, have, after); return have; } } catch { /* fall through to writing */ } }
  const m = openModal(`<div class="notes-wait" role="status"><p>📝 ${t('notes.writing', 'Preparing your notes… this takes about a minute.')}</p><div class="skeleton" style="width:90%"></div><div class="skeleton" style="width:70%"></div><div class="skeleton" style="width:80%"></div></div>`, { title: t('notes.heading', 'Study notes'), dismissable: true });
  try {
    const r = await api('/api/lesson-notes/prepare', { subtopic_id: topic.id });
    m.close(); showNotes(topic, r.notes, after); after(r.notes); return r.notes;
  } catch (er) {
    $('.notes-wait', m.el).innerHTML = `<div class="banner" role="alert"><b>${t('notes.failed', "Couldn't prepare the notes.")}</b> ${esc(er.message)}</div><div class="row"><button class="btn" id="n-retry">↻ ${t('common.retry', 'Try again')}</button></div>`;
    $('#n-retry', m.el).onclick = () => { m.close(); prepare(topic, force, after); };
  }
  return null;
}
