// Fetch helpers: JSON calls and Server-Sent-Event streams. Session is an HttpOnly cookie, so nothing secret lives in JS.
const listeners = {};
export const on = (name, fn) => { (listeners[name] ||= []).push(fn); };
const emit = (name, detail) => (listeners[name] || []).forEach((fn) => fn(detail));

async function fail(res) {
  let detail = res.statusText;
  try { detail = (await res.json()).detail ?? detail; } catch { /* body was not JSON */ }
  const err = new Error(typeof detail === 'string' ? detail : detail?.message || 'Something went wrong');
  err.status = res.status; err.code = typeof detail === 'object' ? detail?.code : '';
  if (res.status === 401) emit('auth:required', err.code);
  if (err.code === 'consent_required') emit('consent:required');
  throw err;
}

export async function api(path, body, method) {
  const opts = { credentials: 'same-origin' };
  if (body !== undefined) Object.assign(opts, { method: method || 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  else if (method) opts.method = method;
  const res = await fetch(path, opts);
  if (!res.ok) await fail(res);
  const type = res.headers.get('content-type') || '';
  return type.includes('json') ? res.json() : res.text();
}
export const get = (path) => api(path);
export const put = (path, body) => api(path, body, 'PUT');
export const del = (path) => api(path, undefined, 'DELETE');

export async function blob(path, body) {
  const res = await fetch(path, { credentials: 'same-origin', ...(body !== undefined ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) });
  if (!res.ok) await fail(res);
  return res;
}

export async function* sse(path, body, signal) {
  const res = await fetch(path, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal });
  if (!res.ok) await fail(res);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const frame = buf.slice(0, i); buf = buf.slice(i + 2);
      const line = frame.split('\n').find((l) => l.startsWith('data: '));
      if (line) { try { yield JSON.parse(line.slice(6)); } catch { /* ignore a bad frame */ } }
    }
  }
}
