// The 🔥 chip in the top bar: your daily study streak. Tapping it explains the streak and shows the last two weeks.
import { get } from './api.js';
import { t } from './i18n.js';
import { $, openModal } from './ui.js';
import { state } from './state.js';

const dayKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

export async function openStreak() {
  let days = [];
  try { days = (await get('/api/me/activity')).days || []; } catch { /* offline: show the count only */ }
  const done = new Set(days), today = new Date();
  const dots = Array.from({ length: 14 }, (_, i) => { const d = new Date(today); d.setDate(today.getDate() - (13 - i)); return { d, on: done.has(dayKey(d)) }; });
  const n = state.streak || 0;
  const m = openModal(`<div class="streak-card">
      <p class="streak-big" aria-hidden="true">🔥 <b>${n}</b></p>
      <p class="streak-line"><b>${n === 1 ? t('streak.one', '1 day in a row') : n ? t('streak.many', '{n} days in a row', { n }) : t('streak.none', 'No streak yet')}</b></p>
      <p class="muted">${t('streak.what', 'Your streak counts the days in a row that you studied: opened a lesson, asked AIVidya a doubt, took a quiz or revised flashcards. Do a little each day to keep it growing. If you miss a whole day, it starts again from 1.')}</p>
      <p class="muted">${n ? t('streak.keep', 'Study something today to keep it going.') : t('streak.start', 'Open any lesson today to start your streak.')}</p>
      ${days.length || n ? `<div class="streak-days" role="img" aria-label="${t('streak.last14', 'Your last 14 days')}">${dots.map(({ d, on }) => `<span class="sd${on ? ' on' : ''}" title="${d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}"><i>${on ? '🔥' : ''}</i><small>${d.toLocaleDateString(undefined, { weekday: 'narrow' })}</small></span>`).join('')}</div>` : ''}
      <div class="row end"><a class="btn" href="#/me" id="streak-me">${t('streak.progress', 'See my progress')}</a><button class="btn primary" type="button" id="streak-ok">${t('common.ok', 'OK')}</button></div></div>`, { title: t('streak.title', 'Your daily streak') });
  $('#streak-ok', m.el).onclick = m.close; $('#streak-me', m.el).onclick = m.close;
}
