/* SikaSafe service worker — offline-first app shell.
   The whole point is that it works with no data and no signal, so we
   pre-cache everything and serve from cache first. */
const CACHE = 'sikasafe-v2';
const ASSETS = [
  './',
  'index.html',
  'css/styles.css',
  'js/data.js',
  'js/detector.js',
  'js/api.js',
  'js/app.js',
  'manifest.webmanifest',
  'icons/favicon.svg',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  // Never intercept the community API (cross-origin, or same-origin /api/) —
  // those must always hit the live network, never a stale cache.
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
      }
      return res;
    }).catch(() => caches.match('index.html')))
  );
});
