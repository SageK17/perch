/* SikaSafe service worker — offline-first app shell.
   The whole point is that it works with no data and no signal, so we
   pre-cache everything and serve from cache first. */
const CACHE = 'sikasafe-v1';
const ASSETS = [
  './',
  'index.html',
  'css/styles.css',
  'js/data.js',
  'js/detector.js',
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
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => {
      // cache same-origin GETs as we go
      if (res.ok && new URL(e.request.url).origin === self.location.origin) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
      }
      return res;
    }).catch(() => caches.match('index.html')))
  );
});
