// Settings: profile & goals, display (accessibility), voice, notifications, privacy (export/delete), account.
import { api, get, put, blob } from './api.js';
import { t } from './i18n.js';
import { $, $$, esc, openModal, toast, confirmDialog, download } from './ui.js';
import { state, savePrefs, saveSettings, isStudent } from './state.js';
import { listVoices, speaker, supportsBrowserTTS, supportsBrowserSTT, serverVoice } from './voice.js';

let afterSave = () => {};
export const onProfileSaved = (fn) => { afterSave = fn; };

const choice = (id, items, cur, attr = 'aria-pressed') => `<div class="choice-row" id="${id}" role="group">${items.map((i) => `<button type="button" class="choice" data-v="${esc(i.id)}" ${attr}="${String(i.id) === String(cur)}">${esc(i.label)}</button>`).join('')}</div>`;
const pickable = (root, id) => $$(`#${id} .choice`, root).forEach((b) => (b.onclick = () => $$(`#${id} .choice`, root).forEach((x) => x.setAttribute('aria-pressed', x === b))));
const chosen = (root, id) => $(`#${id} .choice[aria-pressed="true"]`, root)?.dataset.v;

export async function openSettings(tab = 'profile') {
  const student = isStudent();
  const tabsList = [...(student ? [['profile', t('set.profile', 'Profile & goals')]] : []), ['display', t('set.display', 'Display')], ...(student ? [['voice', t('set.voice', 'Voice')]] : []), ['notify', t('set.notify', 'Notifications')], ['privacy', t('set.privacy', 'Privacy & account')]];
  const m = openModal('', { title: t('set.title', 'Settings'), wide: true });
  m.el.innerHTML = `<div class="tabs" role="tablist">${tabsList.map(([id, l]) => `<button class="tab" role="tab" data-t="${id}" aria-selected="${id === (tabsList.find(([i]) => i === tab) ? tab : tabsList[0][0])}">${l}</button>`).join('')}</div><div id="pane" class="settings-pane"></div>`;
  const show = (id) => { $$('.tab', m.el).forEach((b) => b.setAttribute('aria-selected', b.dataset.t === id)); ({ profile, display, voice, notify, privacy })[id](m); };
  $$('.tab', m.el).forEach((b) => (b.onclick = () => show(b.dataset.t)));
  show(tabsList.find(([i]) => i === tab) ? tab : tabsList[0][0]);
}

// ---- profile -----------------------------------------------------------------------------------------------------------
function profile(m) {
  const p = state.profile, meta = state.meta, pane = $('#pane', m.el);
  pane.innerHTML = `<form id="pf">
    <div class="field"><label for="pf-name">${t('profile.name', 'Your first name')}</label><input id="pf-name" type="text" maxlength="40" value="${esc(state.user.display_name)}"></div>
    <div class="field"><span class="label">${t('profile.grade', 'Your grade')}</span>${choice('pf-grade', meta.grades.map((g) => ({ id: g, label: g })), p.grade)}</div>
    <div class="field"><span class="label">${t('profile.level', 'How should I teach?')}</span>${choice('pf-level', meta.levels.map((l) => ({ id: l.id, label: l.label.split(' - ')[0] })), p.level)}<small class="muted" id="lvl-help">${esc(meta.levels.find((l) => l.id === p.level)?.label.split(' - ')[1] || '')}</small></div>
    <div class="field"><label for="pf-board">${t('profile.board', 'Board')}</label><select id="pf-board">${meta.boards.map((b) => `<option ${b === p.board ? 'selected' : ''}>${b}</option>`).join('')}</select></div>
    <div class="field"><label for="pf-goal">${t('profile.goal', 'What are you preparing for?')}</label><select id="pf-goal">${meta.goals.map((g) => `<option value="${g.id}" ${g.id === p.goal ? 'selected' : ''}>${esc(g.label)}</option>`).join('')}</select></div>
    <div id="senior" ${p.grade >= 11 ? '' : 'hidden'}>
      <div class="field"><label for="pf-stream">${t('profile.stream', 'Stream (Grades 11–12)')}</label><select id="pf-stream"><option value="">—</option>${meta.streams.map((s) => `<option value="${s.id}" ${s.id === p.stream ? 'selected' : ''}>${esc(s.label)}</option>`).join('')}</select></div>
      <div class="field"><label for="pf-track">${t('profile.track', 'Computers track')}</label><select id="pf-track">${meta.tracks.map((x) => `<option value="${x.id.toUpperCase()}" ${x.id.toUpperCase() === (p.track || 'CS') ? 'selected' : ''}>${esc(x.label)}</option>`).join('')}</select></div></div>
    <div class="field"><label for="pf-exam">${t('profile.exam', 'Exam date (optional) — AIVidya will pace your plan')}</label><input id="pf-exam" type="date" value="${esc(p.exam_date || '')}"></div>
    <div class="field"><label for="pf-min">${t('profile.minutes', 'Minutes you can study per day')}: <b id="pf-min-v">${p.daily_minutes}</b></label><input id="pf-min" type="range" min="10" max="180" step="5" value="${p.daily_minutes}"></div>
    <div class="row"><button class="btn primary" type="submit">${t('common.save', 'Save')}</button></div></form>`;
  pickable(pane, 'pf-grade'); pickable(pane, 'pf-level');
  $$('#pf-grade .choice', pane).forEach((b) => b.addEventListener('click', () => { $('#senior', pane).hidden = +b.dataset.v < 11; }));
  $$('#pf-level .choice', pane).forEach((b) => b.addEventListener('click', () => { $('#lvl-help', pane).textContent = meta.levels.find((l) => l.id === b.dataset.v).label.split(' - ')[1]; }));
  $('#pf-min', pane).oninput = (e) => { $('#pf-min-v', pane).textContent = e.target.value; };
  $('#pf', pane).onsubmit = async (e) => {
    e.preventDefault();
    try {
      const name = $('#pf-name', pane).value.trim();
      if (name && name !== state.user.display_name) { await put('/api/me/name', { display_name: name }); state.user.display_name = name; }
      const body = { grade: +chosen(pane, 'pf-grade'), language: state.profile.language, level: chosen(pane, 'pf-level'), board: $('#pf-board', pane).value, goal: $('#pf-goal', pane).value,
        stream: $('#pf-stream', pane).value, track: $('#pf-track', pane).value, exam_date: $('#pf-exam', pane).value, daily_minutes: +$('#pf-min', pane).value };
      state.profile = (await put('/api/me/profile', body)).profile; state.curriculumCache = {};
      speaker.stop(true); toast(t('common.saved', 'Saved ✓')); m.close(); await afterSave();
    } catch (er) { toast(er.message); }
  };
}

// ---- display / accessibility -------------------------------------------------------------------------------------------
function display(m) {
  const pr = state.prefs, pane = $('#pane', m.el);
  pane.innerHTML = `<div class="field"><span class="label">${t('disp.theme', 'Colour theme')}</span>${choice('d-theme', [['system', t('disp.system', 'Match my device')], ['light', t('disp.light', 'Light')], ['dark', t('disp.dark', 'Dark')], ['contrast', t('disp.contrast', 'High contrast')]].map(([id, label]) => ({ id, label })), pr.theme)}</div>
    <div class="field"><label for="d-fs">${t('disp.fontsize', 'Text size')}: <b id="d-fs-v">${pr.fontScale}%</b></label><input id="d-fs" type="range" min="90" max="170" step="10" value="${pr.fontScale}"></div>
    <label class="check"><input type="checkbox" id="d-dys" ${pr.dyslexia ? 'checked' : ''}> ${t('disp.dyslexia', 'Dyslexia-friendly font')}</label>
    <label class="check"><input type="checkbox" id="d-sp" ${pr.spacing ? 'checked' : ''}> ${t('disp.spacing', 'More space between lines')}</label>
    <label class="check"><input type="checkbox" id="d-ds" ${pr.dataSaver ? 'checked' : ''}> ${t('disp.datasaver', 'Data saver (no auto-play audio or animations)')}</label>`;
  pickable(pane, 'd-theme');
  const apply = () => { pr.theme = chosen(pane, 'd-theme'); pr.fontScale = +$('#d-fs', pane).value; pr.dyslexia = $('#d-dys', pane).checked; pr.spacing = $('#d-sp', pane).checked; pr.dataSaver = $('#d-ds', pane).checked; $('#d-fs-v', pane).textContent = `${pr.fontScale}%`; savePrefs(); };
  $$('input, .choice', pane).forEach((el) => el.addEventListener('input', apply)); $$('#d-theme .choice', pane).forEach((el) => el.addEventListener('click', apply));
}

// ---- voice -------------------------------------------------------------------------------------------------------------------
function voice(m) {
  const s = state.settings, pane = $('#pane', m.el), lang = state.meta.languages.find((l) => l.id === state.profile.language);
  const voices = listVoices().filter((v) => v.lang.toLowerCase().startsWith(lang.speech.slice(0, 2)));
  const serverHas = serverVoice.tts.includes(lang.id);
  pane.innerHTML = `<div class="field"><label for="v-tts">${t('voice.tts', 'Teacher voice (speaker)')}</label><select id="v-tts">
      <option value="auto">${t('voice.auto', 'Automatic (best available)')}</option><option value="browser">${t('voice.browser', 'This device’s voices')}</option>
      <option value="server" ${serverHas ? '' : 'disabled'}>${t('voice.server', 'AIVidya server voice (consistent quality)')}${serverHas ? '' : ' — ' + t('voice.nonehere', 'not available for this language')}</option></select></div>
    ${supportsBrowserTTS ? `<div class="field"><label for="v-voice">${t('voice.pick', 'Device voice for')} ${esc(lang.name)}</label><select id="v-voice"><option value="">${t('voice.auto', 'Automatic (best available)')}</option>${voices.map((v) => `<option value="${esc(v.voiceURI)}" ${v.voiceURI === s.voiceByLang[lang.id] ? 'selected' : ''}>${esc(v.name)} (${esc(v.lang)})</option>`).join('')}</select>${voices.length ? '' : `<small class="muted">${t('voice.novoices', 'No device voice found for this language — try the server voice, or install one in your system settings.')}</small>`}</div>` : ''}
    <div class="field"><label for="v-stt">${t('voice.stt', 'Voice input (microphone)')}</label><select id="v-stt"><option value="auto">${t('voice.auto', 'Automatic (best available)')}</option>
      <option value="browser" ${supportsBrowserSTT ? '' : 'disabled'}>${t('voice.sttbrowser', 'Browser recognition (Chrome/Edge — audio goes to the browser maker)')}</option>
      <option value="server" ${serverVoice.stt ? '' : 'disabled'}>${t('voice.sttserver', 'Private: recognised on the AIVidya server')}</option></select></div>
    <label class="check"><input type="checkbox" id="v-confirm" ${s.confirmVoice ? 'checked' : ''}> ${t('voice.confirm', 'Show what I said before sending (when recognition is unsure)')}</label>
    <label class="check"><input type="checkbox" id="v-barge" ${s.bargeIn ? 'checked' : ''}> ${t('voice.barge', 'Let me interrupt AIVidya by speaking (use headphones)')}</label>
    <label class="check"><input type="checkbox" id="v-auto" ${s.autoplay ? 'checked' : ''}> ${t('voice.autoplay', 'Auto-play lessons')}</label>
    <label class="check"><input type="checkbox" id="v-cap" ${s.captions ? 'checked' : ''}> ${t('voice.captions', 'Live captions')}</label>
    <div class="row"><button class="btn" id="v-test">🔊 ${t('voice.test', 'Test voice')}</button><a class="btn" href="#/voicecheck" id="v-check">🩺 ${t('voice.check', 'Voice check')}</a></div>`;
  $('#v-tts', pane).value = s.ttsEngine; $('#v-stt', pane).value = s.sttEngine;
  const save = () => {
    s.ttsEngine = $('#v-tts', pane).value; s.sttEngine = $('#v-stt', pane).value; s.confirmVoice = $('#v-confirm', pane).checked; s.bargeIn = $('#v-barge', pane).checked;
    s.autoplay = $('#v-auto', pane).checked; s.captions = $('#v-cap', pane).checked; const v = $('#v-voice', pane); if (v) s.voiceByLang[lang.id] = v.value; saveSettings();
  };
  $$('select, input', pane).forEach((el) => el.addEventListener('change', save));
  $('#v-check', pane).onclick = () => m.close();
  $('#v-test', pane).onclick = () => {
    save(); const engine = s.ttsEngine === 'server' || (s.ttsEngine === 'auto' && serverHas && !voices.length) ? 'server' : 'browser';
    speaker.begin({ lang: lang.speech, langCode: lang.id, rate: s.rate, voiceURI: s.voiceByLang[lang.id] || '', engine, onFail: (why) => toast(t('voice.testfail', 'Could not play audio ({why}).', { why })) });
    speaker.push(t('voice.sample', 'Hello! I am AIVidya, your teacher. Let us learn something wonderful today.')); speaker.end();
  };
}

// ---- notifications -----------------------------------------------------------------------------------------------------------
async function notify(m) {
  const pane = $('#pane', m.el); pane.textContent = t('common.loading', 'Loading…');
  const c = await get('/api/me/contact');
  pane.innerHTML = `<p class="muted small">${t('notify.help', 'Reminders appear inside AIVidya. You can also get them by e-mail, phone push or WhatsApp if this server has those switched on.')}</p>
    <div class="field"><label for="n-mail">${t('notify.email', 'E-mail')}</label><input id="n-mail" type="email" value="${esc(c.email || '')}" ${c.channels.email ? '' : 'disabled'}><label class="check"><input type="checkbox" id="n-me" ${c.notify_email ? 'checked' : ''} ${c.channels.email ? '' : 'disabled'}> ${t('notify.email.on', 'Send reminders by e-mail')}</label>${c.channels.email ? '' : `<small class="muted">${t('notify.off', 'Not enabled on this server.')}</small>`}</div>
    <div class="field"><label for="n-phone">${t('notify.phone', 'WhatsApp number (with country code)')}</label><input id="n-phone" type="tel" placeholder="+91…" value="${esc(c.phone || '')}" ${c.channels.whatsapp ? '' : 'disabled'}><label class="check"><input type="checkbox" id="n-mw" ${c.notify_whatsapp ? 'checked' : ''} ${c.channels.whatsapp ? '' : 'disabled'}> ${t('notify.wa.on', 'Send reminders on WhatsApp')}</label>${c.channels.whatsapp ? '' : `<small class="muted">${t('notify.off', 'Not enabled on this server.')}</small>`}</div>
    <div class="field"><span class="label">${t('notify.push', 'Phone / browser push')}</span><button class="btn" id="n-push" ${c.channels.push && 'serviceWorker' in navigator && 'PushManager' in window ? '' : 'disabled'}>🔔 ${t('notify.push.on', 'Turn on push notifications')}</button>${c.channels.push ? '' : `<small class="muted">${t('notify.off', 'Not enabled on this server.')}</small>`}</div>
    <div class="row"><button class="btn primary" id="n-save">${t('common.save', 'Save')}</button></div>`;
  $('#n-save', pane).onclick = async () => { await put('/api/me/contact', { email: $('#n-mail', pane).value || null, phone: $('#n-phone', pane).value || null, notify_email: $('#n-me', pane).checked, notify_whatsapp: $('#n-mw', pane).checked }); toast(t('common.saved', 'Saved ✓')); };
  $('#n-push', pane).onclick = async () => {
    try {
      const perm = await Notification.requestPermission(); if (perm !== 'granted') return toast(t('notify.denied', 'Permission was not given.'));
      const reg = await navigator.serviceWorker.ready;
      const key = Uint8Array.from(atob(c.vapid_public.replace(/-/g, '+').replace(/_/g, '/')), (ch) => ch.charCodeAt(0));
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
      await api('/api/me/push', sub.toJSON()); toast(t('notify.push.done', 'Push notifications are on.'));
    } catch (er) { toast(er.message); }
  };
}

// ---- privacy & account --------------------------------------------------------------------------------------------------------
function privacy(m) {
  const pane = $('#pane', m.el);
  pane.innerHTML = `<p><a href="#/legal/privacy">${t('legal.privacy', 'Privacy notice')}</a> · <a href="#/legal/terms">${t('legal.terms', 'Terms')}</a></p>
    <h3>${t('priv.data', 'Your data')}</h3><div class="row"><button class="btn" id="p-export">⬇️ ${t('priv.export', 'Download all my data')}</button>${isStudent() ? `<a class="btn" href="/api/notes/export.md" download>📓 ${t('priv.notes', 'Download my notes')}</a>` : ''}</div>
    ${isStudent() ? `<h3>${t('priv.parent', 'Parent or guardian')}</h3><p class="small muted">${t('priv.parent.help', 'Your parent can link to your account with a code to see your progress.')}</p><button class="btn" id="p-code">${t('priv.code', 'Show my parent code')}</button> <span id="p-code-v" class="code-inline"></span>` : ''}
    <h3>${t('priv.account', 'Account')}</h3><p class="small" id="p-email-line">✉️ ${state.emailVerified ? `${t('email.yours', 'Your email address')}: <b>${esc(state.emailMasked || '')}</b> ✓` : t('email.none', 'No email address yet. Add one so you can reset your password if you forget it.')}</p><div class="row"><button class="btn" id="p-email">${state.emailVerified ? t('email.change', 'Change email address') : t('email.add', 'Add my email address')}</button><button class="btn" id="p-pw">🔑 ${state.hasPassword ? t('priv.password', 'Change password') : t('priv.password.set', 'Set a password (optional)')}</button><button class="btn" id="p-out">${t('auth.signout', 'Sign out')}</button><button class="btn" id="p-outall">${t('priv.outall', 'Sign out everywhere')}</button></div>
    <h3 class="danger-title">${t('priv.delete', 'Delete my account')}</h3><p class="small muted">${t('priv.delete.help', 'This permanently erases your profile, progress, chats, notes and uploads. It cannot be undone.')}</p><button class="btn danger" id="p-del">🗑️ ${t('priv.delete', 'Delete my account')}</button>`;
  $('#p-export', pane).onclick = async () => { download('aividya-my-data.zip', await (await blob('/api/me/export')).blob()); };
  $('#p-code', pane)?.addEventListener('click', async () => { const me = await get('/api/auth/me'); $('#p-code-v', pane).textContent = me.link_code || t('priv.code.none', 'Already linked or not needed'); });
  $('#p-out', pane).onclick = async () => { await api('/api/auth/logout', {}); location.hash = '#/'; location.reload(); };
  $('#p-outall', pane).onclick = async () => { await api('/api/auth/logout?all_devices=true', {}); location.hash = '#/'; location.reload(); };
  $('#p-email', pane).onclick = () => import('./emailcode.js').then((m) => m.openEmailDialog(() => { $('#p-email-line', pane).innerHTML = `✉️ ${t('email.yours', 'Your email address')}: <b>${esc(state.emailMasked || '')}</b> ✓`; $('#p-email', pane).textContent = t('email.change', 'Change email address'); }));
  $('#p-pw', pane).onclick = () => {
    const d = openModal(`${state.hasPassword ? `<div class="field"><label for="o">${t('priv.old', 'Current password')}</label><input id="o" type="password" autocomplete="current-password"></div>` : `<p class="muted">${t('priv.password.set.help', 'You sign in with an emailed code. A password is optional: with one you can sign in without waiting for an email.')}</p>`}<div class="field"><label for="n">${t('auth.newpass', 'New password (8+ characters)')}</label><input id="n" type="password" autocomplete="new-password"></div><p class="error" id="e" hidden></p><div class="row end"><button class="btn primary" id="go">${t('common.save', 'Save')}</button></div>`, { title: state.hasPassword ? t('priv.password', 'Change password') : t('priv.password.set', 'Set a password (optional)') });
    $('#go', d.el).onclick = async () => { try { await api('/api/auth/password', { old_password: $('#o', d.el)?.value || '', new_password: $('#n', d.el).value }); d.close(); state.hasPassword = true; toast(t('priv.pw.done', 'Password changed. Please sign in again.')); setTimeout(() => location.reload(), 900); } catch (er) { const x = $('#e', d.el); x.textContent = er.message; x.hidden = false; } };
  };
  $('#p-del', pane).onclick = async () => {
    if (!(await confirmDialog(t('priv.delete.confirm', 'Really delete everything? This cannot be undone.'), { danger: true, yes: t('priv.delete.yes', 'Delete forever') }))) return;
    const d = openModal(`${state.hasPassword ? `<div class="field"><label for="pw">${t('auth.password', 'Password')}</label><input id="pw" type="password" autocomplete="current-password"></div>` : ''}<div class="field"><label for="cf">${t('priv.type', 'Type DELETE to confirm')}</label><input id="cf" type="text"></div><p class="error" id="e" hidden></p><div class="row end"><button class="btn danger" id="go">${t('priv.delete.yes', 'Delete forever')}</button></div>`, { title: t('priv.delete', 'Delete my account') });
    $('#go', d.el).onclick = async () => { try { await api('/api/me/delete', { confirm: $('#cf', d.el).value, password: $('#pw', d.el)?.value || '' }); location.hash = '#/'; location.reload(); } catch (er) { const x = $('#e', d.el); x.textContent = er.message; x.hidden = false; } };
  };
}

// ---- notification centre -----------------------------------------------------------------------------------------------------
export async function openNotifications() {
  const m = openModal(t('common.loading', 'Loading…'), { title: t('notif.title', 'Notifications') });
  const { items } = await get('/api/notifications');
  m.el.innerHTML = items.length ? `<ul class="notif-list">${items.map((n) => `<li class="${n.read_at ? '' : 'unread'}"><a href="${esc((n.link || '').replace('/#', '#'))}" data-id="${n.id}"><b>${esc(n.title)}</b><span class="muted small">${esc(n.body || '')}</span></a></li>`).join('')}</ul><div class="row end"><button class="btn sm" id="readall">${t('notif.markall', 'Mark all read')}</button></div>` : `<p class="empty">${t('notif.none', 'Nothing new.')}</p>`;
  $$('a[data-id]', m.el).forEach((a) => (a.onclick = () => { api('/api/notifications/read', { id: +a.dataset.id }); m.close(); }));
  $('#readall', m.el)?.addEventListener('click', async () => { await api('/api/notifications/read', {}); state.unread = 0; $('#bell-count').hidden = true; m.close(); });
}
