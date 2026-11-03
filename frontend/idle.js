// Signs the student out after a stretch with no keyboard, mouse, touch or scroll activity (the server enforces the same limit), unless they asked to be remembered on this device.
import { api } from './api.js';
import { state } from './state.js';

const KEY = 'vidya.active'; // shared between tabs: activity in any tab keeps all of them signed in
let last = Date.now(), pinged = Date.now(), onIdle = () => {};

const read = () => { try { return Math.max(last, +localStorage.getItem(KEY) || 0); } catch { return last; } };
const touch = () => {
  const now = Date.now(); if (now - last < 5000) return; last = now; // a few writes a minute is plenty
  try { localStorage.setItem(KEY, String(now)); } catch { /* private mode: this tab still tracks its own activity */ }
};

export function watchIdle(fn) {
  onIdle = fn;
  for (const ev of ['pointerdown', 'pointermove', 'keydown', 'wheel', 'scroll', 'touchstart']) addEventListener(ev, touch, { passive: true, capture: true });
  const check = async () => {
    const limit = (state.meta?.idle_minutes || 0) * 60000;
    if (!state.user || state.remembered || state.meta?.auth === 'off' || !limit) return; // a remembered device is never signed out for inactivity
    if (Date.now() - read() < limit) { // still active: reading and scrolling make no requests, so tell the server now and then or it would count the student as away
      if (last > pinged && Date.now() - pinged > Math.min(300000, limit / 4)) { pinged = Date.now(); api('/api/auth/ping', {}).catch(() => {}); }
      return;
    }
    last = Date.now(); // restart the clock so a failed sign-out call is not repeated every check
    try { await api('/api/auth/logout', {}); } catch { /* already signed out, or the server is unreachable: either way show the sign-in page */ }
    onIdle(limit / 60000);
  };
  setInterval(check, 30000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) check(); }); // a laptop that slept past the limit signs out on wake-up
}

export const markActive = () => { last = Date.now(); try { localStorage.setItem(KEY, String(last)); } catch { /* optional */ } };
