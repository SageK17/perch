/* Perch service worker — offline app shell.
   Bumps: change CACHE on every release so clients pick up new files. */
const CACHE = 'perch-v4';

const SHELL = [
  './',
  './index.html',
  './css/styles.css',
  './js/app.js',
  './js/compass3d.js',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/favicon.png',
  './icons/apple-touch-icon.png',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
  'https://unpkg.com/three@0.149.0/build/three.min.js',
  'https://unpkg.com/qrcode-generator@1.4.4/qrcode.js',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {})).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // Never cache live data calls — always go to network (they fail gracefully in the app).
  const isData =
    url.hostname.includes('overpass') ||
    url.hostname.includes('nominatim') ||
    url.hostname.includes('mail.ru') ||
    url.hostname.includes('tile.openstreetmap.org') ||
    url.hostname.includes('api.open-meteo.com');
  if (isData) return; // default browser handling

  // App shell + Leaflet: cache-first, fall back to network, then cache the result.
  e.respondWith(
    caches.match(req).then((hit) =>
      hit || fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        return res;
      }).catch(() => caches.match('./index.html'))
    )
  );
});
