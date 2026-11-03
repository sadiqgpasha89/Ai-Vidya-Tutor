// Tutor chat: persisted history, streaming answers read aloud, board, photos, voice input (browser or private), barge-in, hands-free.
import { api, get, sse } from './api.js';
import { t } from './i18n.js';
import { md, esc } from './render.js';
import { speaker, listener, supportsBrowserTTS, sttEngine, startBargeIn } from './voice.js';
import { $, $$, toast, openModal } from './ui.js';
import { state, speechLang, langInfo, saveSettings } from './state.js';
import { L, speakOpts, speakText, warnIfNoVoice, caption, rewardToast } from './lesson.js';
import { reportDialog, openCheckWork } from './assess.js';

const QUICK = [['🧒', 'quick.simpler', 'Explain simpler', 'I did not understand. Please explain this again in simpler words with a different everyday example.'], ['➕', 'quick.example', 'Another example', 'Please give me one more worked example of this, step by step.'],
  ['❓', 'quick.why', 'Why is it true?', 'Why is this true? Help me understand the reason, not just the rule.'], ['🌍', 'quick.where', 'Where is it used?', 'Where is this used in real life, especially in India?'],
  ['⚠️', 'quick.mistakes', 'Common mistakes', 'What are the most common mistakes students make in this topic?'], ['🎤', 'quick.test', 'Test me', 'Ask me one short question to check whether I really understood, then wait for my answer.']];
const TOOL_LABEL = { show_on_board: ['✍️', 'tool.board', 'Writing on the board…'], calculator: ['🧮', 'tool.calc', 'Calculating…'], algebra: ['🧮', 'tool.algebra', 'Working out the algebra…'], plot_graph: ['📈', 'tool.plot', 'Drawing a graph…'],
  run_python: ['💻', 'tool.python', 'Running the code…'], unit_convert: ['📏', 'tool.units', 'Converting units…'], search_textbook: ['📚', 'tool.textbook', 'Looking in your textbook…'], web_search: ['🌐', 'tool.web', 'Searching the web…'],
  find_topics: ['🔎', 'tool.find', 'Looking through the syllabus…'], record_learning_signal: ['📌', 'tool.note', 'Making a note…'], get_student_profile: ['📒', 'tool.profile', 'Checking your progress…'],
  check_student_work: ['✅', 'tool.check', 'Checking your steps…'], reading_photo: ['📷', 'tool.photo', 'Reading your photo…'], get_prerequisites: ['🧱', 'tool.prereq', 'Checking what you need first…'] };

let c; // chat state for the current lesson
export function leaveChat() { c?.abort?.abort(); c?.stopBarge?.(); c?.cleanup?.(); c?.unfit?.(); c = null; }

export function mountChat(side, ctx) {
  c = { ctx, asking: false, handsfree: false, empty: 0, images: [], boards: [], lastUser: '', muted: false, abort: null, stopBarge: null };
  side.innerHTML = `
    <div class="tabs" role="tablist"><button class="tab" role="tab" aria-selected="true" data-p="chat">💬 ${t('chat.tab', 'Ask AIVidya')}</button><button class="tab" role="tab" aria-selected="false" data-p="board">📋 ${t('board.tab', 'Board')}<span class="badge" hidden></span></button></div>
    <div class="pane active" id="pane-chat">
      <div class="chat-log" id="chat-log" aria-live="polite" aria-relevant="additions"></div>
      <div class="quick" id="quick">${QUICK.map(([e, k, d]) => `<button class="chip">${e} ${t(k, d)}</button>`).join('')}</div>
      <div class="toggle-row">${speaker.supported ? `<label><input type="checkbox" id="speak-replies"> 🔊 ${t('chat.speak', 'Speak answers')}</label>` : ''}${sttEngine() ? `<label><input type="checkbox" id="handsfree"> 🎙️ ${t('chat.handsfree', 'Hands-free')}</label>` : `<span>🎙️ ${t('chat.novoice', 'Voice input needs Chrome/Edge or the server voice.')}</span>`}
        <button class="link" id="clear-chat">${t('chat.clear', 'Clear chat')}</button></div>
      <div class="attach" id="attach" hidden></div>
      <div class="confirm-voice" id="confirm" hidden></div>
      <form class="composer" id="composer"><textarea id="q" rows="2" placeholder="${t('chat.placeholder', 'Ask a doubt about {t}…', { t: ctx.topic.title })}" aria-label="${t('chat.yourq', 'Your question')}"></textarea>
        <input type="file" id="photo" accept="image/*" capture="environment" hidden><button type="button" class="icon-btn" id="photo-btn" aria-label="${t('chat.photo', 'Attach a photo of your work')}" title="${t('chat.photo', 'Attach a photo of your work')}">📷</button>
        ${sttEngine() ? `<button type="button" class="mic" id="mic" aria-label="${t('chat.speakq', 'Speak your question')}" title="${t('chat.speakq', 'Speak your question')}">🎤</button>` : ''}
        <span class="spacer"></span><button class="btn primary" id="send" type="submit">${t('chat.send', 'Send')}</button></form>
    </div>
    <div class="pane board-pane" id="pane-board"><div class="empty" id="board-empty">${t('board.empty', 'The board is empty.')}<br>${t('board.empty2', 'AIVidya writes formulas, steps and diagrams here when you ask.')}</div></div>`;
  // keep the whole chat, including the text box, inside the window whatever its height or the scroll position
  const fit = () => {
    if (!side.isConnected) return;
    if (getComputedStyle(side).position === 'static') { // phone: the chat fills the screen under the Lesson / Ask AIVidya switch
      const bar = document.querySelector('.mobile-tabs');
      side.style.height = Math.max(380, innerHeight - (bar ? bar.getBoundingClientRect().height : 0) - 24) + 'px'; return;
    }
    side.style.height = Math.max(380, innerHeight - Math.max(side.getBoundingClientRect().top, 64) - 14) + 'px';
  };
  addEventListener('resize', fit); addEventListener('scroll', fit, { passive: true }); fit();
  c.unfit = () => { removeEventListener('resize', fit); removeEventListener('scroll', fit); };
  $$('.tab', side).forEach((b) => (b.onclick = () => showPane(b.dataset.p)));
  $('#quick', side).onclick = (e) => { const i = $$('.chip', e.currentTarget).indexOf(e.target.closest('.chip')); if (i >= 0) ask(QUICK[i][3]); };
  const q = $('#q', side);
  q.addEventListener('input', () => { q.style.height = 'auto'; q.style.height = Math.min(q.scrollHeight, 180) + 'px'; });
  q.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#composer').requestSubmit(); } });
  $('#composer', side).onsubmit = (e) => { e.preventDefault(); if (c.asking) return stopAsking(); const tx = q.value.trim(); if (tx || c.images.length) { q.value = ''; q.style.height = 'auto'; ask(tx); } };
  const sr = $('#speak-replies', side); if (sr) { sr.checked = state.settings.speakReplies; sr.onchange = () => { state.settings.speakReplies = sr.checked; saveSettings(); if (!sr.checked) speaker.stop(); }; }
  $('#handsfree', side)?.addEventListener('change', (e) => setHandsfree(e.target.checked));
  $('#mic', side)?.addEventListener('click', () => (listener.active ? listener.stop() : startListening()));
  $('#photo-btn', side).onclick = () => $('#photo', side).click();
  $('#photo', side).onchange = onPhoto;
  $('#clear-chat', side).onclick = async () => { await api(`/api/chat/history?subtopic_id=${ctx.topic.id}`, undefined, 'DELETE'); $('#chat-log').innerHTML = ''; $$('.board-card', $('#pane-board')).forEach((e) => e.remove()); $('#board-empty').hidden = false; greet(); };
  loadHistory();
}

const showPane = (name) => { $$('.tab').forEach((x) => x.setAttribute('aria-selected', x.dataset.p === name)); $('#pane-chat').classList.toggle('active', name === 'chat'); $('#pane-board').classList.toggle('active', name === 'board'); if (name === 'board') $('.tab .badge').hidden = true; };

function greet() {
  addBot(t('chat.hello', "Hi {name}! I'm AIVidya. Ask me anything about <b>{topic}</b> — tap 🎤 and speak, type, or send a photo of your work. I'll keep it simple and stay on this topic.", { name: esc(state.user.display_name), topic: esc(c.ctx.topic.title) }), true);
}
async function loadHistory() {
  const mine = c;
  try {
    const h = await get(`/api/chat/history?subtopic_id=${c.ctx.topic.id}`); if (c !== mine) return;
    if (!h.messages.length) greet();
    h.messages.forEach((m) => (m.role === 'user' ? addUser(m.content, true) : addBot(`<div class="prose">${md(m.content)}</div>`, true, m.content)));
    h.boards.slice().reverse().forEach((b) => addToBoard(b, true));
    scroll();
  } catch { greet(); }
}

const scroll = () => { const l = $('#chat-log'); if (l) l.scrollTop = l.scrollHeight; };
function addBot(html, raw = true, text = '') {
  const el = document.createElement('div'); el.className = 'msg bot'; el.innerHTML = html;
  if (text) decorate(el, text);
  $('#chat-log').append(el); scroll(); return el;
}
function decorate(el, text) { // per-answer actions: report a mistake, regenerate (last only)
  const tools = document.createElement('div'); tools.className = 'msg-tools';
  tools.innerHTML = `<button class="chip tiny" data-r="report" aria-label="${t('chat.report', 'Report a mistake')}">⚑ ${t('chat.report', 'Report a mistake')}</button>`;
  tools.querySelector('[data-r="report"]').onclick = () => reportDialog('chat', c.ctx.topic.id, text.slice(0, 300));
  const askBtn = document.createElement('button'); askBtn.className = 'chip tiny'; askBtn.textContent = `🙋 ${t('doubt.ask', 'Ask my teacher')}`;
  askBtn.onclick = () => import('./doubts.js').then((m) => m.askTeacher({ topic: c.ctx.topic, question: c.lastUser, aiAnswer: text }));
  tools.append(askBtn);
  el.append(tools);
}
function addUser(text, saved = false) {
  const el = document.createElement('div'); el.className = 'msg user'; el.innerHTML = md(text).replace(/<p>|<\/p>/g, ''); $('#chat-log').append(el); if (!saved) scroll(); return el;
}
function addToBoard(b, quiet = false) {
  $('#board-empty').hidden = true;
  const el = document.createElement('div'); el.innerHTML = boardHtml(b);
  const card = el.firstElementChild;
  card.querySelector('[data-save]').onclick = async () => { await api('/api/notes', { subtopic_id: c.ctx.topic.id, title: b.title, body: b.markdown || '' }); toast(t('note.saved', 'Saved to your notes')); };
  $('#pane-board').prepend(card);
  if (!quiet && !$('#pane-board').classList.contains('active')) $('.tab .badge').hidden = false;
}
export function boardHtml(b) {
  const img = b.svg ? `<img alt="${t('board.diagram', 'Diagram')}: ${esc(b.title)}" src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(b.svg)}">` : '';
  return `<div class="board-card"><div class="row"><h4>📋 ${esc(b.title)}</h4><span class="spacer"></span><button class="chip tiny" data-save>📓 ${t('hl.note', 'Save to notes')}</button></div><div class="prose">${md(b.markdown || '')}</div>${img}</div>`;
}

function takeSpeakable(acc, from, final) {
  const rest = acc.slice(from); if (final) return { text: rest, next: acc.length };
  let cut = -1; const re = /[.!?।॥。！？؟۔](?=\s|$)/g; let m;
  while ((m = re.exec(rest))) { const seg = rest.slice(0, m.index + 1); if ((seg.match(/\$/g) || []).length % 2 === 0 && (seg.match(/```/g) || []).length % 2 === 0) cut = m.index + 1; }
  return cut < 0 ? { text: '', next: from } : { text: rest.slice(0, cut), next: from + cut };
}
function setAsking(on) { c.asking = on; const s = $('#send'); s.textContent = on ? `⏹ ${t('common.stop', 'Stop')}` : t('chat.send', 'Send'); s.classList.toggle('danger', on); $('#quick').style.opacity = on ? 0.6 : 1; }
function stopAsking() { c.abort?.abort(); speaker.stop(); }

export async function ask(text, { regenerate = false } = {}) {
  const my = c; if (!my || my.asking) return;
  const images = my.images.slice(); my.images = []; renderAttach();
  if (!regenerate) addUser(text || t('chat.photoonly', '📷 (photo)'));
  my.lastUser = text; setAsking(true);
  const bubble = addBot('<span class="typing" aria-label="typing"><i></i><i></i><i></i></span>', true);
  let acc = '', spoken = 0, errored = false; const extras = [];
  my.abort = new AbortController(); my.muted = false; my.stopBarge?.(); my.stopBarge = null;
  const talk = speaker.supported && state.settings.speakReplies && !state.prefs.dataSaver;
  if (talk) {
    listener.abort(); warnIfNoVoice();
    speaker.begin(speakOpts({ onSentence: (tx) => caption(tx), onStop: () => { $('#caption').hidden = true; my.stopBarge?.(); },
      onIdle: () => { $('#caption').hidden = true; my.stopBarge?.(); my.stopBarge = null; if (c === my && my.handsfree && !my.muted) setTimeout(() => c === my && my.handsfree && startListening(), 300); } }));
    if (state.settings.bargeIn) startBargeIn(() => { speaker.stop(); my.muted = true; startListening(); }).then((stop) => { if (c === my && speaker.speaking) my.stopBarge = stop; else stop?.(); });
  }
  const paint = () => { bubble.querySelector('.prose, .typing')?.remove(); bubble.querySelectorAll('.status-line').forEach((x) => x.remove()); const p = document.createElement('div'); p.className = 'prose'; p.innerHTML = md(acc); bubble.prepend(p); extras.forEach((h) => { if (!h.node.isConnected) bubble.append(h.node); }); scroll(); };
  let raf = 0; const schedule = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; paint(); }); };
  let status = null;
  const note = (txt) => { status ||= Object.assign(document.createElement('div'), { className: 'status-line' }); status.textContent = txt; if (!status.isConnected) bubble.append(status); };
  try {
    for await (const ev of sse('/api/chat/stream', { subtopic_id: my.ctx.topic.id, message: text, images, regenerate }, my.abort.signal)) {
      if (c !== my) return;
      if (ev.type === 'text') { acc += ev.delta; schedule(); if (talk && !my.muted) { const s = takeSpeakable(acc, spoken, false); if (s.text) { spoken = s.next; speaker.push(speakText(s.text)); } } }
      else if (ev.type === 'replace') { acc = ev.text; spoken = acc.length; speaker.stop(true); schedule(); }
      else if (ev.type === 'queue') note(ev.ahead > 0 ? t('queue.wait', 'Waiting in line — {n} ahead of you…', { n: ev.ahead }) : '…');
      else if (ev.type === 'model') note(`🧠 ${t('chat.harder', 'Thinking harder about this one…')}`);
      else if (ev.type === 'tool') { const [e, k, d] = TOOL_LABEL[ev.name] || ['…', 'tool.other', 'Working…']; note(`${e} ${t(k, d)}`); }
      else if (ev.type === 'board') { const n = document.createElement('div'); n.innerHTML = boardHtml(ev); const node = n.firstElementChild; node.querySelector('[data-save]').onclick = async () => { await api('/api/notes', { subtopic_id: my.ctx.topic.id, title: ev.title, body: ev.markdown || '' }); toast(t('note.saved', 'Saved to your notes')); }; extras.push({ node }); addToBoard(ev); schedule(); }
      else if (ev.type === 'suggest') { const n = document.createElement('div'); n.className = 'suggest'; n.innerHTML = ev.topics.map((tp) => `<a class="chip" href="#/learn/${tp.id}?q=${encodeURIComponent(text)}">📚 ${esc(tp.title)} · ${esc(tp.subject_name)} ${t('common.grade', 'G')}${tp.grade}</a>`).join(''); extras.push({ node: n }); schedule(); }
      else if (ev.type === 'sources') { const n = document.createElement('div'); n.className = 'suggest'; n.innerHTML = ev.passages.map((p) => `<span class="chip">📚 ${esc(p.title)} p.${p.page}${p.scope === 'student' ? ` (${t('lib.mine', 'my upload')})` : ''}</span>`).join(''); extras.push({ node: n }); schedule(); }
      else if (ev.type === 'signal') { const n = document.createElement('div'); n.className = 'signal'; n.textContent = ev.kind === 'mastered' ? `⭐ ${t('sig.mastered', 'AIVidya noted that you understood this well')}` : `📌 ${t('sig.note', 'AIVidya made a note to help you better')}`; $('#chat-log').append(n); }
      else if (ev.type === 'error') { errored = true; acc += (acc ? '\n\n' : '') + `⚠️ ${ev.message}`; schedule(); }
    }
  } catch (err) {
    if (err.name !== 'AbortError') { errored = true; acc += (acc ? '\n\n' : '') + `⚠️ ${err.message || t('chat.conn', 'Connection problem.')}`; }
    else acc += acc ? `\n\n_(${t('chat.stopped', 'stopped')})_` : '';
  } finally {
    cancelAnimationFrame(raf);
    if (c === my) {
      if (!acc && !extras.length) acc = t('chat.empty', 'Hmm, I could not form an answer. Please try asking again.'); paint();
      if (talk && !my.muted) { const s = takeSpeakable(acc, spoken, true); if (s.text && !errored) speaker.push(speakText(s.text)); speaker.end(); }
      if (acc && !errored) decorate(bubble, acc);
      const regen = document.createElement('button'); regen.className = 'chip tiny'; regen.textContent = `↻ ${t('chat.regen', 'Regenerate')}`; regen.onclick = () => { $$('.msg.bot').pop()?.remove(); $$('.msg.user').pop()?.remove(); ask(my.lastUser, { regenerate: true }); }; bubble.querySelector('.msg-tools')?.append(regen);
      setAsking(false); refreshAfter();
      if (errored && my.handsfree) setHandsfree(false);
    }
  }
}
const refreshAfter = () => import('./state.js').then((m) => m.refreshProgress());

/* ---- photos ---- */
async function onPhoto(e) {
  const files = [...e.target.files].slice(0, 3 - c.images.length); e.target.value = '';
  for (const f of files) { try { c.images.push(await shrink(f)); } catch { toast(t('chat.badphoto', 'That photo could not be read.')); } }
  renderAttach();
}
function shrink(file) { // downscale to <=1280px JPEG so uploads stay small
  return new Promise((resolve, reject) => {
    const img = new Image(); const url = URL.createObjectURL(file);
    img.onload = () => { const s = Math.min(1, 1280 / Math.max(img.width, img.height)); const cv = document.createElement('canvas'); cv.width = Math.round(img.width * s); cv.height = Math.round(img.height * s); cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height); URL.revokeObjectURL(url); resolve(cv.toDataURL('image/jpeg', 0.82).split(',')[1]); };
    img.onerror = reject; img.src = url;
  });
}
function renderAttach() {
  const a = $('#attach'); if (!a) return; a.hidden = !c.images.length;
  a.innerHTML = c.images.map((b, i) => `<span class="thumb"><img alt="${t('chat.attached', 'Attached photo')} ${i + 1}" src="data:image/jpeg;base64,${b}"><button class="x" data-i="${i}" aria-label="${t('common.remove', 'Remove')}">✕</button></span>`).join('');
  $$('.x', a).forEach((x) => (x.onclick = () => { c.images.splice(+x.dataset.i, 1); renderAttach(); }));
}

/* ---- voice input ---- */
function startListening() {
  if (!c) return; const mic = $('#mic'), q = $('#q'); const my = c;
  speaker.stop(true); my.muted = true; $('#caption').hidden = true; my.stopBarge?.();
  const lang = langInfo(state.profile.language);
  const ok = listener.start({
    lang: lang.speech, langCode: lang.id,
    onInterim: (tx) => { q.value = tx; },
    onLevel: (lv) => { mic.style.setProperty('--lv', lv); },
    onFinal: ({ text, confidence, alternatives }) => {
      q.value = ''; my.empty = 0;
      const unsure = state.settings.confirmVoice && ((confidence && confidence < 0.75) || sttEngine() === 'server' && confidence < 0.6);
      if (!unsure || my.handsfree && confidence >= 0.5) return ask(text);
      confirmVoice(text, alternatives);
    },
    onEnd: (got) => {
      mic.classList.remove('listening'); mic.textContent = '🎤';
      if (!got && my.handsfree) { if (++my.empty >= 2) { setHandsfree(false); toast(t('chat.nothing', 'I did not hear anything, so I stopped listening. Tap 🎤 to talk again.')); } else setTimeout(() => c === my && my.handsfree && startListening(), 300); }
    },
    onError: (e) => { mic.classList.remove('listening'); mic.textContent = '🎤'; toast(e === 'not-allowed' || e === 'service-not-allowed' ? t('chat.micblocked', 'Microphone permission is blocked. Allow it in the browser address bar and try again.') : e === 'unsupported' ? t('chat.needchrome', 'Voice input needs Chrome or Edge.') : `${t('chat.voiceprob', 'Voice input problem')}: ${e}`, 5000); if (my.handsfree) setHandsfree(false); },
  });
  if (ok) { mic.classList.add('listening'); mic.textContent = '⏹'; q.placeholder = t('chat.listening', 'Listening… speak now'); }
}
function confirmVoice(text, alts) { // recognition was unsure: let the student fix it before sending
  const box = $('#confirm'); box.hidden = false;
  box.innerHTML = `<p class="small">${t('chat.didyousay', 'Did you say…?')}</p><textarea id="cv" rows="2" aria-label="${t('chat.didyousay', 'Did you say…?')}">${esc(text)}</textarea>${alts?.length ? `<div class="suggest">${alts.slice(0, 2).map((a) => `<button class="chip" data-alt>${esc(a)}</button>`).join('')}</div>` : ''}<div class="row"><button class="btn sm primary" id="cv-ok">${t('chat.send', 'Send')}</button><button class="btn sm" id="cv-no">${t('common.cancel', 'Cancel')}</button></div>`;
  $$('[data-alt]', box).forEach((b) => (b.onclick = () => { $('#cv', box).value = b.textContent; }));
  $('#cv-ok', box).onclick = () => { const v = $('#cv', box).value.trim(); box.hidden = true; if (v) ask(v); };
  $('#cv-no', box).onclick = () => { box.hidden = true; };
  $('#cv', box).focus();
}
function setHandsfree(on) {
  if (!c) return; c.handsfree = on; c.empty = 0; const cb = $('#handsfree'); if (cb) cb.checked = on;
  if (on) { if (!state.settings.speakReplies) { state.settings.speakReplies = true; saveSettings(); const sr = $('#speak-replies'); if (sr) sr.checked = true; } toast(t('chat.hf.on', 'Hands-free on: speak your question, AIVidya will answer out loud.')); if (!c.asking) startListening(); }
  else { listener.abort(); const mic = $('#mic'); if (mic) { mic.classList.remove('listening'); mic.textContent = '🎤'; } $('#q').placeholder = t('chat.placeholder', 'Ask a doubt about {t}…', { t: c.ctx.topic.title }); }
}
