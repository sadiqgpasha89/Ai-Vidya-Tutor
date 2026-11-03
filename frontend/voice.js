// Speech: text-to-speech (browser voices or private server voices) with sentence queue + word highlighting,
// speech-to-text (browser recognition or private server Whisper), and voice-activity detection for barge-in.
import { blob } from './api.js';
import { state } from './state.js';

const synth = typeof window !== 'undefined' ? window.speechSynthesis : null;
const SR = typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
export const supportsBrowserTTS = !!synth;
export const supportsBrowserSTT = !!SR;
export const supportsRecording = typeof MediaRecorder !== 'undefined' && !!navigator.mediaDevices?.getUserMedia;

// One chunk = one utterance. Used by BOTH the speaker and the transcript so indices line up.
export function splitSentences(text) {
  const raw = String(text || '').replace(/\s+/g, ' ').trim();
  if (!raw) return [];
  const parts = raw.match(/[^.!?।॥?。！？؟۔]+[.!?।॥?。！？؟۔]+["')\]」』）]*\s*|[^.!?।॥?。！？؟۔]+$/g) || [raw];
  const out = [];
  for (const p of parts) {
    let s = p.trim();
    while (s.length > 220) {
      let cut = s.lastIndexOf(',', 200); if (cut < 80) cut = s.lastIndexOf(' ', 200); if (cut < 40) cut = 200;
      out.push(s.slice(0, cut + 1).trim()); s = s.slice(cut + 1).trim();
    }
    if (s) out.push(s);
  }
  return out;
}

let voices = [];
const loadVoices = () => { voices = synth ? synth.getVoices() : []; };
if (synth) { loadVoices(); synth.addEventListener?.('voiceschanged', loadVoices); }
export const listVoices = () => voices;

export function pickVoice(lang, preferredURI) {
  const prefix = lang.slice(0, 2).toLowerCase();
  if (preferredURI) { const v = voices.find((x) => x.voiceURI === preferredURI); if (v && v.lang.toLowerCase().startsWith(prefix)) return v; }
  const matches = voices.filter((v) => v.lang.toLowerCase().replace('_', '-').startsWith(prefix));
  const score = (v) => (v.lang.replace('_', '-').toLowerCase() === lang.toLowerCase() ? 4 : 0) + (/google|natural|neural|online/i.test(v.name) ? 2 : 0) + (v.localService ? 0 : 1);
  return matches.sort((a, b) => score(b) - score(a))[0] || null;
}

// ---- server voice availability (filled in by app.js from /api/meta) --------------------------------
export const serverVoice = { tts: [], stt: false };
export function ttsEngineFor(langCode, speechTag, preferredURI) {
  const pref = state.settings.ttsEngine, serverOk = serverVoice.tts.includes(langCode);
  if (pref === 'server') return serverOk ? 'server' : 'browser';
  if (pref === 'browser') return 'browser';
  // auto: a real device voice for this language wins; otherwise the server voice; otherwise the browser default
  if (supportsBrowserTTS && pickVoice(speechTag, preferredURI)) return 'browser';
  return serverOk ? 'server' : 'browser';
}

class Speaker {
  constructor() { this.token = 0; this.queue = []; this.idx = 0; this.opts = null; this.speaking = false; this.paused = false; this.ended = true; this.pending = ''; this.quick = 0; this.busy = false; this.audio = null; this.prefetch = new Map(); }
  get supported() { return supportsBrowserTTS || serverVoice.tts.length > 0; }
  /** Start a fresh speaking session. opts: {lang, langCode, rate, voiceURI, engine, onSentence, onWord, onIdle, onStop, onFail, onBlocked} */
  begin(opts) {
    this.stop(true);
    this.opts = { lang: 'en-IN', langCode: 'en', rate: 1, voiceURI: '', engine: 'browser', ...opts };
    this.token++; this.queue = []; this.idx = 0; this.ended = false; this.pending = ''; this.speaking = true; this.quick = 0; this.prefetch.clear();
  }
  push(text, streaming = false) {
    if (!this.opts) return;
    this.pending += text;
    const parts = splitSentences(this.pending);
    if (streaming && parts.length && !/[.!?।॥。！？؟۔]["')\]」』）]*$/.test(parts[parts.length - 1])) this.pending = parts.pop(); else this.pending = '';
    for (const p of parts) this.queue.push(p);
    this._pump();
  }
  end() { if (!this.opts) return; if (this.pending) { for (const p of splitSentences(this.pending)) this.queue.push(p); this.pending = ''; } this.ended = true; this._pump(); }
  _idle() { if (this.ended && this.speaking && !this.busy && this.queue.length === 0) { this.speaking = false; this.opts?.onIdle?.(); } }
  _pump() {
    if (this.busy || this.paused) return;
    if (this.queue.length === 0) { this._idle(); return; }
    const text = this.queue.shift(); const i = this.idx++;
    this.busy = true;
    (this.opts.engine === 'server' ? this._speakServer(text, i) : this._speakBrowser(text, i));
  }
  // -- browser engine
  _speakBrowser(text, i) {
    if (!synth) { this.busy = false; return this._fail('unsupported'); }
    const my = this.token; const u = new SpeechSynthesisUtterance(text);
    u.lang = this.opts.lang; u.rate = this.opts.rate;
    const v = pickVoice(this.opts.lang, this.opts.voiceURI); if (v) u.voice = v;
    let t0 = 0;
    u.onstart = () => { t0 = performance.now(); if (my === this.token) this.opts.onSentence?.(text, i); };
    u.onboundary = (e) => { if (my === this.token && e.name === 'word') this.opts.onWord?.(wordIndexAt(text, e.charIndex), i); };
    u.onend = () => {
      if (my !== this.token) return;
      // a voice that "finishes" a long sentence instantly is not really speaking (no engine / voice installed)
      this.quick = (text.length > 25 && (!t0 || performance.now() - t0 < 150)) ? this.quick + 1 : 0;
      if (this.quick >= 2) return this._fail('silent');
      this.busy = false; this._pump();
    };
    u.onerror = (e) => {
      if (my !== this.token || e.error === 'interrupted' || e.error === 'canceled') return;
      if (e.error === 'not-allowed') { this.opts.onBlocked?.(); return this._fail('blocked'); }
      this._fail(e.error || 'error');
    };
    synth.speak(u);
  }
  // -- server engine (Piper): fetch a WAV per sentence, prefetching the next two while one plays
  async _fetchAudio(text) {
    const key = text + '|' + this.opts.langCode;
    if (!this.prefetch.has(key)) {
      this.prefetch.set(key, (async () => {
        const res = await blob('/api/voice/tts', { text, language: this.opts.langCode });
        const timings = JSON.parse(atob(res.headers.get('X-Words') || 'W10=')); // base64 of a JSON array
        return { url: URL.createObjectURL(await res.blob()), timings };
      })());
    }
    return this.prefetch.get(key);
  }
  async _speakServer(text, i) {
    const my = this.token;
    try {
      this.queue.slice(0, 2).forEach((t) => this._fetchAudio(t).catch(() => {}));
      const { url, timings } = await this._fetchAudio(text);
      if (my !== this.token) return;
      const a = this.audio = new Audio(url); a.playbackRate = this.opts.rate;
      this.opts.onSentence?.(text, i);
      let last = -1;
      a.ontimeupdate = () => { if (!timings.length) return; const frac = a.currentTime / (a.duration || 1); let w = 0; while (w + 1 < timings.length && timings[w + 1].t / (timings[timings.length - 1].t + 0.001) * 0.98 <= frac) w++; if (w !== last) { last = w; this.opts.onWord?.(w, i); } };
      a.onended = () => { URL.revokeObjectURL(url); if (my !== this.token) return; this.busy = false; this._pump(); };
      a.onerror = () => { if (my === this.token) this._fail('audio'); };
      await a.play();
    } catch (err) {
      if (my !== this.token) return;
      if (err?.name === 'NotAllowedError') { this.opts.onBlocked?.(); return this._fail('blocked'); }
      this._fail(err?.status === 503 ? 'server-voice-not-ready' : 'server');
    }
  }
  _fail(reason) { const cb = this.opts?.onFail; const fallback = this.opts?.engine === 'server' && supportsBrowserTTS && reason !== 'blocked'; const rest = [...this.queue]; const opts = this.opts; this.stop(true);
    if (fallback && opts) { cb?.(reason, true); this.opts = { ...opts, engine: 'browser' }; this.token++; this.queue = rest; this.ended = true; this.speaking = true; this._pump(); return; }
    cb?.(reason, false); }
  pause() { if (!this.speaking) return; this.paused = true; this.audio?.pause(); synth?.pause(); }
  resume() { if (!this.paused) return; this.paused = false; this.audio?.play(); synth?.resume(); this._pump(); }
  stop(silent = false) {
    this.token++; this.queue = []; this.busy = false; this.paused = false; const was = this.speaking; this.speaking = false; this.ended = true; this.pending = '';
    if (this.audio) { this.audio.pause(); this.audio = null; }
    synth?.cancel(); this.prefetch.clear();
    if (was && !silent) this.opts?.onStop?.();
  }
}
function wordIndexAt(text, charIndex) { return (text.slice(0, charIndex).match(/\S+/g) || []).length; }
export const speaker = new Speaker();

// ---- speech to text -----------------------------------------------------------------------------------
export function sttEngine() {
  const pref = state.settings.sttEngine;
  if (pref === 'server' && serverVoice.stt && supportsRecording) return 'server';
  if (pref === 'browser' && supportsBrowserSTT) return 'browser';
  if (supportsBrowserSTT) return 'browser';
  return serverVoice.stt && supportsRecording ? 'server' : null;
}

class Listener {
  constructor() { this.rec = null; this.active = false; this.stopFn = null; }
  /** callbacks: onInterim(text), onFinal({text, confidence, alternatives}), onEnd(gotSpeech), onError(code), onLevel(0..1) */
  start({ lang, langCode, onInterim, onFinal, onEnd, onError, onLevel }) {
    this.stop();
    return sttEngine() === 'server' ? this._server({ langCode, onFinal, onEnd, onError, onLevel, onInterim }) : this._browser({ lang, onInterim, onFinal, onEnd, onError });
  }
  _browser({ lang, onInterim, onFinal, onEnd, onError }) {
    if (!SR) { onError?.('unsupported'); return false; }
    const rec = new SR(); rec.lang = lang; rec.interimResults = true; rec.continuous = false; rec.maxAlternatives = 3;
    let finalText = '', conf = 0, alts = [];
    rec.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) { finalText += r[0].transcript; conf = r[0].confidence || 0; alts = [...r].slice(1).map((a) => a.transcript); } else interim += r[0].transcript;
      }
      onInterim?.((finalText + interim).trim());
    };
    rec.onerror = (e) => { if (e.error !== 'no-speech' && e.error !== 'aborted') onError?.(e.error); };
    rec.onend = () => { this.active = false; this.rec = null; if (finalText.trim()) onFinal?.({ text: finalText.trim(), confidence: conf, alternatives: alts }); onEnd?.(!!finalText.trim()); };
    try { rec.start(); this.rec = rec; this.active = true; this.stopFn = () => rec.stop(); return true; } catch { onError?.('start-failed'); return false; }
  }
  async _server({ langCode, onFinal, onEnd, onError, onLevel, onInterim }) {
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); } catch (e) { onError?.(e.name === 'NotAllowedError' ? 'not-allowed' : 'no-mic'); return false; }
    this.active = true;
    const rec = new MediaRecorder(stream); const chunks = [];
    const ctx = new AudioContext(); const an = ctx.createAnalyser(); an.fftSize = 512; ctx.createMediaStreamSource(stream).connect(an);
    const buf = new Uint8Array(an.fftSize); let heard = false, silentSince = performance.now(), stopped = false; const t0 = performance.now();
    const stop = () => { if (stopped) return; stopped = true; clearInterval(timer); try { rec.state !== 'inactive' && rec.stop(); } catch { /* already stopped */ } };
    const timer = setInterval(() => {
      an.getByteTimeDomainData(buf); let sum = 0; for (const v of buf) { const x = (v - 128) / 128; sum += x * x; }
      const level = Math.sqrt(sum / buf.length); onLevel?.(Math.min(1, level * 6));
      if (level > 0.02) { heard = true; silentSince = performance.now(); }
      const now = performance.now();
      if ((heard && now - silentSince > 1300) || now - t0 > 30000 || (!heard && now - t0 > 7000)) stop();
    }, 80);
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    rec.onstop = async () => {
      stream.getTracks().forEach((tr) => tr.stop()); ctx.close(); this.active = false;
      if (!heard) { onEnd?.(false); return; }
      onInterim?.('…');
      try {
        const res = await fetch(`/api/voice/stt?language=${langCode || ''}`, { method: 'POST', credentials: 'same-origin', body: new Blob(chunks, { type: rec.mimeType }) });
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Speech recognition failed');
        const out = await res.json();
        if (out.text) onFinal?.({ text: out.text, confidence: out.confidence, alternatives: [] });
        onEnd?.(!!out.text);
      } catch (e) { onError?.(e.message || 'server'); onEnd?.(false); }
    };
    rec.start(); this.rec = rec; this.stopFn = stop; return true;
  }
  stop() { try { this.stopFn?.(); } catch { /* already stopped */ } }
  abort() { try { this.rec?.abort?.(); } catch { /* ignore */ } this.stop(); this.active = false; }
}
export const listener = new Listener();

// ---- voice-activity detection: lets the student interrupt AIVidya by simply speaking (use headphones) ---------
export async function startBargeIn(onSpeech) {
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: false } }); } catch { return null; }
  const ctx = new AudioContext(); const an = ctx.createAnalyser(); an.fftSize = 512; ctx.createMediaStreamSource(stream).connect(an);
  const buf = new Uint8Array(an.fftSize); let since = 0, fired = false;
  const timer = setInterval(() => {
    an.getByteTimeDomainData(buf); let sum = 0; for (const v of buf) { const x = (v - 128) / 128; sum += x * x; }
    if (Math.sqrt(sum / buf.length) > 0.06) { since ||= performance.now(); if (!fired && performance.now() - since > 350) { fired = true; onSpeech(); } } else since = 0;
  }, 60);
  return () => { clearInterval(timer); stream.getTracks().forEach((t) => t.stop()); ctx.close(); };
}
