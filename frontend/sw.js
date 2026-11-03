// Service worker: caches the app shell and lessons you have opened, so they work offline; shows push notifications.
const SHELL = 'vidya-shell-v12';
const DATA = 'vidya-data-v1';
const CORE = ['/', '/styles.css', '/app.js', '/api.js', '/ui.js', '/i18n.js', '/state.js', '/render.js', '/voice.js', '/auth.js', '/home.js', '/settings.js', '/tour.js', '/lesson.js', '/chat.js', '/assess.js', '/menu.js', '/langpicker.js', '/idle.js', '/studynotes.js', '/streak.js', '/emailcode.js', '/admin.js',
  '/vendor/marked.min.js', '/vendor/purify.min.js', '/vendor/katex/katex.min.js', '/vendor/katex/katex.min.css', '/icons/icon.svg', '/manifest.webmanifest'];

self.addEventListener('install', (e) => { e.waitUntil(caches.open(SHELL).then((c) => Promise.allSettled(CORE.map((u) => c.add(u)))).then(() => self.skipWaiting())); });
self.addEventListener('activate', (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => ![SHELL, DATA].includes(k)).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });

self.addEventListener('fetch', (e) => {
  const req = e.request, url = new URL(req.url);
  if (url.origin !== location.origin) return;
  // Lesson streams are POSTs and personal: never cached. A few GET resources are kept for offline reading.
  if (req.method !== 'GET') return;
  if (url.pathname.startsWith('/api/')) {
    const keep = /^\/api\/(topic\/|curriculum|meta|chat\/history|notes|me\/plan|revision)/.test(url.pathname);
    if (!keep) return;
    e.respondWith(fetch(req).then((res) => { if (res.ok) { const copy = res.clone(); caches.open(DATA).then((c) => c.put(req, copy)); } return res; }).catch(() => caches.match(req).then((hit) => hit || new Response(JSON.stringify({ detail: 'You are offline' }), { status: 503, headers: { 'Content-Type': 'application/json' } }))));
    return;
  }
  // static files: network first (so updates arrive), fall back to cache
  e.respondWith(fetch(req).then((res) => { if (res.ok && !url.pathname.startsWith('/vendor/pyodide')) { const copy = res.clone(); caches.open(SHELL).then((c) => c.put(req, copy)); } return res; }).catch(() => caches.match(req).then((hit) => hit || caches.match('/'))));
});

self.addEventListener('push', (e) => {
  let d = { title: 'AIVidya', body: '', link: '/' }; try { d = { ...d, ...e.data.json() }; } catch { /* plain text push */ }
  e.waitUntil(self.registration.showNotification(d.title, { body: d.body, icon: '/icons/icon-192.png', badge: '/icons/icon-192.png', data: { link: d.link || '/' } }));
});
self.addEventListener('notificationclick', (e) => { e.notification.close(); e.waitUntil(clients.openWindow(e.notification.data?.link || '/')); });
