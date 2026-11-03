// Proving an email address with a six-digit code: used when signing up, and from Settings for accounts that have no verified email yet.
import { api } from './api.js';
import { t } from './i18n.js';
import { $, esc, toast, openModal } from './ui.js';
import { state } from './state.js';

/** A code box that counts down before "Send again" works. Returns { stop() }. */
export function resendTimer(button, seconds, label = t('otp.resend', 'Send a new code')) {
  let left = Math.max(0, Math.ceil(seconds)), h = null;
  const paint = () => { button.disabled = left > 0; button.textContent = left > 0 ? t('otp.resend.wait', '{label} in {s}s', { label, s: left }) : label; };
  const tick = () => { left -= 1; paint(); if (left <= 0) { clearInterval(h); h = null; } };
  paint(); if (left > 0) h = setInterval(tick, 1000);
  return { restart(s) { left = Math.ceil(s); clearInterval(h); paint(); if (left > 0) h = setInterval(tick, 1000); }, stop() { clearInterval(h); } };
}

export const codeField = (id = 'code') => `<div class="field"><label for="${id}">${t('otp.code', '6-digit code')}</label>
  <input id="${id}" class="otp-input" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="7" pattern="[0-9 ]*" placeholder="······" required></div>`;

export const deliveryNote = (delivery) => delivery === 'log'
  ? `<p class="banner warn" role="status">${t('otp.nomail', 'This server has no email set up yet, so no email was sent. Ask the person who runs AIVidya for your code (it is in the server log), or ask them to set up email.')}</p>` : '';

/** Add or change the email address of the account you are signed in to. */
export function openEmailDialog(done) {
  const has = !!state.emailMasked;
  const m = openModal(`<div id="e1"><p class="muted">${has ? t('email.change.help', 'We will send a 6-digit code to the new address to check it is yours.') : t('email.add.help', 'Add your email address. If you ever forget your password, we will send a code there so you can set a new one.')}</p>
      <div class="field"><label for="em">${t('auth.email', 'Email address')}</label><input id="em" type="email" autocomplete="email" autofocus></div>
      ${has && state.hasPassword ? `<div class="field"><label for="pw">${t('priv.old', 'Current password')}</label><input id="pw" type="password" autocomplete="current-password"></div>` : ''}
      <p class="error" id="ee" role="alert" hidden></p><div class="row end"><button class="btn primary" id="esend">${t('otp.send', 'Send code')}</button></div></div>
    <div id="e2" hidden><p id="e2h"></p><div id="e2n"></div>${codeField('ecode')}<p class="error" id="ee2" role="alert" hidden></p>
      <div class="row"><button class="btn" id="eresend" type="button"></button><span class="spacer"></span><button class="btn primary" id="everify">${t('otp.verify', 'Verify')}</button></div></div>`, { title: t('email.title', 'Your email address') });
  const show = (id, msg) => { const x = $(id, m.el); x.textContent = msg; x.hidden = !msg; };
  let timer = null, email = '';
  const send = async (first) => {
    show('#ee', ''); show('#ee2', '');
    try {
      const r = await api('/api/auth/email/start', { email: first ? $('#em', m.el).value : email, password: $('#pw', m.el)?.value || '' });
      email = first ? $('#em', m.el).value : email;
      $('#e1', m.el).hidden = true; $('#e2', m.el).hidden = false;
      $('#e2h', m.el).innerHTML = t('otp.sentto', 'We sent a 6-digit code to <b>{email}</b>. It works for {m} minutes.', { email: esc(r.email), m: 10 });
      $('#e2n', m.el).innerHTML = deliveryNote(r.delivery);
      timer ? timer.restart(r.resend_seconds) : (timer = resendTimer($('#eresend', m.el), r.resend_seconds));
      $('#ecode', m.el).focus();
    } catch (er) { show(first ? '#ee' : '#ee2', er.message); }
  };
  $('#esend', m.el).onclick = () => send(true);
  $('#eresend', m.el).onclick = () => send(false);
  $('#everify', m.el).onclick = async () => {
    try { const r = await api('/api/auth/email/verify', { code: $('#ecode', m.el).value }); timer?.stop(); state.emailMasked = r.email; state.emailVerified = true; m.close(); toast(t('email.done', 'Email address confirmed ✓')); done?.(); }
    catch (er) { show('#ee2', er.message); }
  };
}
