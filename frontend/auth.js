// Sign in with an emailed code (or a password), sign up in three short steps, parental-consent waiting screen, and parent linking.
import { api, get } from './api.js';
import { t } from './i18n.js';
import { $, $$, esc, toast, download } from './ui.js';
import { state } from './state.js';
import { codeField, deliveryNote, resendTimer } from './emailcode.js';

let onDone = () => {};
export const setAuthDone = (fn) => { onDone = fn; };

function shell(inner) {
  $('#view').innerHTML = `<div class="auth-wrap"><section class="card auth-card">${inner}</section></div>`;
  for (const id of ['menu-btn', 'bell', 'settings-btn', 'health', 'streak']) $('#' + id).hidden = true; $('#search-form').hidden = true;
}

const tabs = (active) => `<div class="tabs auth-tabs" role="tablist">
  <button class="tab" role="tab" aria-selected="${active === 'in'}" data-go="in">${t('auth.signin', 'Sign in')}</button>
  <button class="tab" role="tab" aria-selected="${active === 'up'}" data-go="up">${t('auth.signup', 'Create account')}</button></div>`;

const rememberOn = () => { try { return localStorage.getItem('vidya.remember') === '1'; } catch { return false; } };
const rememberBox = () => `<label class="check"><input type="checkbox" id="remember" ${rememberOn() ? 'checked' : ''}> ${t('auth.remember', 'Keep me signed in on this device for {d} days', { d: state.meta?.remember_days || 30 })}</label>
  <small class="muted">${t('auth.remember.help', 'Only on your own phone or computer. On a shared one, leave it off: you will be signed out after {m} minutes without activity.', { m: state.meta?.idle_minutes || 120 })}</small>`;
const remember = () => { const on = !!$('#remember')?.checked; try { localStorage.setItem('vidya.remember', on ? '1' : '0'); } catch { /* optional */ } return on; };
const fail = (id, er) => { const x = $(id); x.textContent = typeof er === 'string' ? er : er.message; x.hidden = !x.textContent; };

export function showAuth(mode = 'in', notice = '') {
  if (mode === 'up') return signupForm();
  if (mode === 'pw') return passwordForm(notice);
  return codeForm(notice);
}

const welcome = (notice) => `<h1>${t('auth.welcome', 'Welcome to AIVidya 🎓')}</h1><p class="muted">${t('auth.tagline', 'Your personal AI teacher for Physics, Chemistry, Biology, Maths, Computers, English and more.')}</p>${notice ? `<p class="banner info" role="status">${esc(notice)}</p>` : ''}${tabs('in')}`;

/** The usual way in: type your email, then the 6-digit code that arrives. */
function codeForm(notice = '') {
  shell(`${welcome(notice)}
    <form id="f1" novalidate>
      <div class="field"><label for="u">${t('auth.email.or.username', 'Email address (or username)')}</label><input id="u" type="text" autocomplete="username" autocapitalize="none" inputmode="email" required autofocus>
        <small class="muted">${t('auth.code.help', 'We will email you a 6-digit code. No password needed.')}</small></div>
      ${rememberBox()}
      <p class="error" id="err" role="alert" hidden></p>
      <button class="btn primary wide" type="submit">${t('auth.code.send', 'Email me a code')}</button>
      <p class="small"><a href="#" id="pw">${t('auth.usepassword', 'Use a password instead')}</a></p>
    </form>
    <form id="f2" hidden novalidate><p id="sent"></p><div id="note"></div>${codeField('code')}
      <p class="error" id="err2" role="alert" hidden></p>
      <button class="btn primary wide" type="submit">${t('auth.signin', 'Sign in')}</button>
      <div class="row"><button class="btn" type="button" id="again"></button><span class="spacer"></span><button class="btn ghost" type="button" id="wrong">${t('otp.wrong', 'Wrong email? Go back')}</button></div></form>`);
  $$('[data-go]').forEach((b) => (b.onclick = () => showAuth(b.dataset.go)));
  $('#pw').onclick = (e) => { e.preventDefault(); showAuth('pw'); };
  let timer = null;
  const ask = async () => {
    const id = $('#u').value.trim(); if (!id) return;
    fail('#err', ''); fail('#err2', '');
    try {
      const r = await api('/api/auth/code/start', { identifier: id });
      $('#f1').hidden = true; $('#f2').hidden = false;
      $('#sent').textContent = t('auth.code.sent', 'If there is an account for that, we have emailed it a 6-digit code. It works for {m} minutes.', { m: r.minutes || 10 });
      $('#note').innerHTML = deliveryNote(r.delivery);
      timer ? timer.restart(r.resend_seconds ?? 60) : (timer = resendTimer($('#again'), r.resend_seconds ?? 60));
      $('#code').focus();
    } catch (er) { fail('#err', er); }
  };
  $('#f1').onsubmit = (e) => { e.preventDefault(); ask(); };
  $('#again').onclick = ask;
  $('#wrong').onclick = () => { timer?.stop(); $('#f2').hidden = true; $('#f1').hidden = false; $('#u').focus(); };
  $('#f2').onsubmit = async (e) => {
    e.preventDefault();
    try { await api('/api/auth/code/verify', { identifier: $('#u').value.trim(), code: $('#code').value, remember: remember() }); timer?.stop(); await onDone(); }
    catch (er) { fail('#err2', er); }
  };
}

/** For people who set a password (in Settings) or whose account has one from before. */
function passwordForm(notice = '') {
  shell(`${welcome(notice)}
    <form id="f" novalidate>
      <div class="field"><label for="u">${t('auth.username.or.email', 'Username or email')}</label><input id="u" type="text" autocomplete="username" autocapitalize="none" required autofocus></div>
      <div class="field"><label for="p">${t('auth.password', 'Password')}</label><input id="p" type="password" autocomplete="current-password" required></div>
      ${rememberBox()}
      <p class="error" id="err" role="alert" hidden></p>
      <button class="btn primary wide" type="submit">${t('auth.signin', 'Sign in')}</button>
      <p class="small"><a href="#" id="usecode">${t('auth.usecode', 'Forgot it, or no password yet? Email me a code instead')}</a></p>
    </form>`);
  $$('[data-go]').forEach((b) => (b.onclick = () => showAuth(b.dataset.go)));
  $('#usecode').onclick = (e) => { e.preventDefault(); showAuth('in'); };
  $('#f').onsubmit = async (e) => {
    e.preventDefault();
    try { await api('/api/auth/login', { username: $('#u').value, password: $('#p').value, remember: remember() }); await onDone(); } catch (er) { fail('#err', er); }
  };
}

/** Step 2 of signing up: the code that was emailed. `back` returns to the first step with the address typed. */
function otpScreen(info, back) {
  shell(`<h1>${t('otp.title', 'Check your email')}</h1>
    <p id="sent">${t('otp.sentto', 'We sent a 6-digit code to <b>{email}</b>. It works for {m} minutes.', { email: esc(info.email), m: 10 })}</p><div id="note">${deliveryNote(info.delivery)}</div>
    <form id="f" novalidate>${codeField('code')}<p class="error" id="err" role="alert" hidden></p>
      <button class="btn primary wide" type="submit">${t('otp.verify', 'Verify')}</button>
      <div class="row"><button class="btn" type="button" id="again"></button><span class="spacer"></span><button class="btn ghost" type="button" id="wrong">${t('otp.wrong', 'Wrong email? Go back')}</button></div></form>`);
  const timer = resendTimer($('#again'), info.resend_seconds ?? 60);
  $('#code').focus();
  $('#wrong').onclick = () => { timer.stop(); back(); };
  $('#again').onclick = async () => {
    fail('#err', '');
    try { const r = await api('/api/auth/signup/resend', { pending: info.pending }); $('#note').innerHTML = deliveryNote(r.delivery); timer.restart(r.resend_seconds ?? 60); toast(t('otp.resent', 'A new code is on its way')); }
    catch (er) { fail('#err', er); }
  };
  $('#f').onsubmit = async (e) => {
    e.preventDefault(); fail('#err', '');
    try { const r = await api('/api/auth/signup/verify', { pending: info.pending, code: $('#code').value }); timer.stop(); profileStep(r.ticket, r.email); }
    catch (er) { fail('#err', er); }
  };
}

/** Step 1 of signing up: just the email address. */
function signupForm(email = '') {
  shell(`<h1>${t('auth.signup', 'Create account')}</h1>${tabs('up')}
    <form id="f" novalidate>
      <div class="field"><label for="em">${t('auth.email', 'Email address')}</label><input id="em" type="email" autocomplete="email" inputmode="email" autocapitalize="none" required autofocus>
        <small class="muted">${t('auth.signup.help', 'We will email you a 6-digit code to check it is yours. There is no password to remember: next time we send another code.')}</small></div>
      <p class="error" id="err" role="alert" hidden></p>
      <button class="btn primary wide" type="submit">${t('common.continue', 'Continue')}</button>
    </form>`);
  $$('[data-go]').forEach((b) => (b.onclick = () => showAuth(b.dataset.go)));
  $('#em').value = email;
  $('#f').onsubmit = async (e) => {
    e.preventDefault();
    try { const info = await api('/api/auth/signup/start', { email: $('#em').value }); otpScreen(info, () => signupForm($('#em') ? $('#em').value : email)); }
    catch (er) { fail('#err', er); }
  };
}

/** Step 3 of signing up: the few things the teacher needs to know. Board and school code are tucked away (Settings can change them). */
function profileStep(ticket, maskedEmail) {
  const m = state.meta, year = new Date().getFullYear();
  shell(`<h1>${t('auth.almost', 'Almost done 🎉')}</h1><p class="muted">${t('auth.verified', '{email} is confirmed.', { email: esc(maskedEmail) })}</p>
    <form id="f" novalidate>
      <div class="field"><span class="label">${t('auth.iam', 'I am a…')}</span><div class="choice-row" id="role">
        ${[['student', t('role.student', 'Student')], ['parent', t('role.parent', 'Parent')], ['teacher', t('role.teacher', 'Teacher')]].map(([v, l], i) => `<button type="button" class="choice" data-v="${v}" aria-pressed="${i === 0}">${l}</button>`).join('')}</div></div>
      <div class="field"><label for="dn">${t('auth.name', 'Your first name')}</label><input id="dn" type="text" maxlength="40" required autocomplete="given-name" autofocus></div>
      <div class="field"><label for="by">${t('auth.birthyear', 'Year of birth')}</label><input id="by" type="number" min="${year - 70}" max="${year - 5}" inputmode="numeric" required></div>
      <div id="stu"><div class="field"><span class="label">${t('profile.grade', 'Your grade')}</span><div class="choice-row" id="grade">${m.grades.map((g) => `<button type="button" class="choice" data-v="${g}" aria-pressed="${g === 9}">${g}</button>`).join('')}</div></div></div>
      <details class="more"><summary>${t('auth.more', 'More options')}</summary>
        <div id="board-field" class="field"><label for="board">${t('profile.board', 'Board')}</label><select id="board">${m.boards.map((b) => `<option>${b}</option>`).join('')}</select></div>
        <div class="field"><label for="school">${t('auth.school', 'School code (optional)')}</label><input id="school" type="text" autocapitalize="characters" maxlength="10"></div></details>
      <label class="check"><input type="checkbox" id="terms"> ${t('auth.accept', 'I accept the')} <a href="#/legal/terms" target="_blank">${t('legal.terms', 'Terms')}</a> ${t('auth.and', 'and')} <a href="#/legal/privacy" target="_blank">${t('legal.privacy', 'Privacy notice')}</a></label>
      ${rememberBox()}
      <p class="muted small" id="minor-note" hidden>${t('auth.minor', 'Because you are under 18, a parent or guardian must approve your account in the next step.')}</p>
      <p class="error" id="err" role="alert" hidden></p>
      <button class="btn primary wide" type="submit">${t('auth.create', 'Create my account')}</button>
    </form>`);
  const val = (id) => $(`#${id} .choice[aria-pressed="true"]`)?.dataset.v;
  const pick = (id) => $$(`#${id} .choice`).forEach((b) => (b.onclick = () => { $$(`#${id} .choice`).forEach((x) => x.setAttribute('aria-pressed', x === b)); if (id === 'role') { $('#stu').hidden = $('#board-field').hidden = b.dataset.v !== 'student'; note(); } }));
  const note = () => { $('#minor-note').hidden = !(val('role') === 'student' && $('#by').value && year - +$('#by').value < 18); };
  pick('role'); pick('grade'); $('#by').oninput = note;
  $('#f').onsubmit = async (e) => {
    e.preventDefault();
    const role = val('role');
    const body = { ticket, display_name: $('#dn').value, role, birth_year: +$('#by').value || null, school_code: $('#school').value || null, accept_terms: $('#terms').checked, remember: remember(),
      profile: role === 'student' ? { grade: +val('grade'), language: localStorage.getItem('vidya.ui') || 'en', board: $('#board').value, level: 'standard' } : undefined };
    try {
      const r = await api('/api/auth/signup/finish', body);
      if (r.link_code) {
        shell(`<h1>${t('otp.done', 'Your account is ready 🎉')}</h1><div class="explain"><b>${t('auth.parentcode', 'Code for your parent or guardian')}</b><div class="code-box" aria-label="Parent code">${esc(r.link_code)}</div><p class="small">${t('auth.parentcode.help', 'Ask them to create a Parent account and enter this code. It lets them approve your account and see your progress.')}</p></div>
          <button class="btn primary wide" id="go">${t('common.continue', 'Continue')}</button>`);
        $('#go').onclick = () => onDone();
      } else onDone();
    } catch (er) { fail('#err', er); }
  };
}

// ---- a child's account waiting for a parent -----------------------------------------------------------------
export async function showConsentWaiting() {
  let me;
  try { me = await get('/api/auth/me'); } catch { return showAuth('in'); }
  shell(`<h1>${t('consent.title', 'Waiting for a parent or guardian')}</h1>
    <p>${t('consent.help', 'Because you are under 18, a parent or guardian must approve your account before you can start. Ask them to open AIVidya, create a Parent account, and enter this code:')}</p>
    <div class="code-box" aria-label="Parent code">${esc(me.link_code || '—')}</div>
    <div class="row"><button class="btn primary" id="check">${t('consent.check', 'I have been approved — check')}</button><button class="btn" id="out">${t('auth.signout', 'Sign out')}</button></div>`);
  $('#check').onclick = async () => { try { await get('/api/me/progress'); await onDone(); } catch { toast(t('consent.not', 'Not approved yet')); } };
  $('#out').onclick = async () => { await api('/api/auth/logout', {}); showAuth('in'); };
}

export function linkChildDialog(openModal, done) {
  const m = openModal(`<p>${t('parent.link.help', 'Enter the code your child sees on their screen.')}</p><div class="field"><label for="lc">${t('parent.code', 'Child code')}</label><input id="lc" type="text" autocapitalize="characters" maxlength="12" autofocus></div>
    <p class="error" id="le" hidden></p><div class="row end"><button class="btn primary" id="lgo">${t('parent.link', 'Approve and link')}</button></div>`, { title: t('parent.link.title', 'Link your child') });
  $('#lgo', m.el).onclick = async () => {
    try { await api('/api/parent/link', { code: $('#lc', m.el).value }); m.close(); toast(t('parent.linked', 'Linked! Your child can now start learning.')); done?.(); }
    catch (er) { const x = $('#le', m.el); x.textContent = er.message; x.hidden = false; }
  };
}
