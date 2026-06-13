/* ============================================================
   Perch — find the nearest place to sit
   100% client-side. No backend, no login, no tracking.
   Data: OpenStreetMap via the Overpass API (free, keyless).
   ============================================================ */
'use strict';

/* ---------- Config ---------- */
const OVERPASS_ENDPOINTS = [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
];
const NOMINATIM = 'https://nominatim.openstreetmap.org/search';
const OVERPASS_TIMEOUT = 22000;   // ms
const REFETCH_MOVE_M = 150;       // refetch when user moves this far from last fetch centre
const ARRIVAL_M = 15;             // "you're here" radius
const CACHE_KEY = 'perch.lastResults.v1';
const PREFS_KEY = 'perch.prefs.v1';
const FAVS_KEY  = 'perch.favs.v1';
const UNLOCK_KEY = 'perch.unlocked.v1';

// --- Commercial config: Sage connects a real checkout here. See DEPLOY.md. ---
// Replace SHOP_URL with your Gumroad / Payhip / Ko-fi product link, and set your
// own UNLOCK_CODE (handed to buyers after purchase). Cosmetic only — never gates
// the core "find a seat" feature.
const SHOP_URL = 'https://ko-fi.com/';
const UNLOCK_CODE = 'PERCHPRO';

// --- Place types: what to find nearby ---
const PLACE_TYPES = {
  sit: { label: 'Seats', noun: 'seat', icon: 'i-seat',
    q: (r, lat, lon) => `node["amenity"="bench"](around:${r},${lat},${lon});way["amenity"="bench"](around:${r},${lat},${lon});node["leisure"="picnic_table"](around:${r},${lat},${lon});node["amenity"="shelter"](around:${r},${lat},${lon});node["highway"="rest_area"](around:${r},${lat},${lon});` },
  food: { label: 'Food', noun: 'place to eat', icon: 'i-food',
    q: (r, lat, lon) => ['fast_food', 'restaurant', 'cafe', 'ice_cream', 'food_court'].map((a) => `node["amenity"="${a}"](around:${r},${lat},${lon});way["amenity"="${a}"](around:${r},${lat},${lon});`).join('') },
  parks: { label: 'Parks', noun: 'park', icon: 'i-tree',
    q: (r, lat, lon) => `way["leisure"="park"](around:${r},${lat},${lon});relation["leisure"="park"](around:${r},${lat},${lon});way["leisure"="garden"](around:${r},${lat},${lon});way["leisure"="dog_park"](around:${r},${lat},${lon});way["leisure"="nature_reserve"](around:${r},${lat},${lon});node["leisure"="park"](around:${r},${lat},${lon});` },
  zoos: { label: 'Zoos', noun: 'zoo', icon: 'i-zoo',
    q: (r, lat, lon) => `node["tourism"="zoo"](around:${r},${lat},${lon});way["tourism"="zoo"](around:${r},${lat},${lon});relation["tourism"="zoo"](around:${r},${lat},${lon});node["tourism"="aquarium"](around:${r},${lat},${lon});way["tourism"="aquarium"](around:${r},${lat},${lon});` },
  views: { label: 'Views', noun: 'viewpoint', icon: 'i-mountain',
    q: (r, lat, lon) => `node["tourism"="viewpoint"](around:${r},${lat},${lon});way["tourism"="viewpoint"](around:${r},${lat},${lon});` },
  play: { label: 'Play', noun: 'playground', icon: 'i-play',
    q: (r, lat, lon) => `node["leisure"="playground"](around:${r},${lat},${lon});way["leisure"="playground"](around:${r},${lat},${lon});` },
  culture: { label: 'Culture', noun: 'place', icon: 'i-museum',
    q: (r, lat, lon) => `node["tourism"="museum"](around:${r},${lat},${lon});way["tourism"="museum"](around:${r},${lat},${lon});node["tourism"="gallery"](around:${r},${lat},${lon});node["amenity"="library"](around:${r},${lat},${lon});way["amenity"="library"](around:${r},${lat},${lon});node["tourism"="artwork"](around:${r},${lat},${lon});` },
};

// --- Compass designs (cosmetic skins for the 3D compass) ---
const DESIGNS = [
  { id: 'classic',  name: 'Classic',    premium: false, base: 0x32a98f, emissive: 0x0e3a31, metalness: 0.35, roughness: 0.32, ei: 1.0, shape: 'kite',    css: '#2f7d6b', sw: ['#5fe0c8', '#2f7d6b'], tag: 'The original Perch green.' },
  { id: 'midnight', name: 'Midnight',   premium: false, base: 0x4da8ff, emissive: 0x0a2540, metalness: 0.50, roughness: 0.25, ei: 1.0, shape: 'diamond', css: '#2a6df0', sw: ['#7cc1ff', '#13315c'], tag: 'Cool, calm, after-dark blue.' },
  { id: 'sunset',   name: 'Sunset',     premium: false, base: 0xff8a4c, emissive: 0x5a1e0a, metalness: 0.40, roughness: 0.30, ei: 1.0, shape: 'kite',    css: '#e8702f', sw: ['#ffb37a', '#e0531f'], tag: 'Golden hour, all day.' },
  { id: 'mariner',  name: 'Mariner',    premium: false, base: 0xe23b3b, emissive: 0x3a0a0a, metalness: 0.45, roughness: 0.30, ei: 1.0, shape: 'needle',  css: '#d12f2f', sw: ['#ff6b6b', '#9c1f1f'], tag: 'Old-school sea-compass needle.' },
  { id: 'gold',     name: 'Gold Lux',   premium: true,  base: 0xe7c14d, emissive: 0x4a3308, metalness: 0.92, roughness: 0.18, ei: 1.0, shape: 'dart',    css: '#c89b2c', sw: ['#ffe08a', '#b8901f'], tag: 'Solid-gold flex.' },
  { id: 'rose',     name: 'Rose Gold',  premium: true,  base: 0xe8a0a8, emissive: 0x4a2025, metalness: 0.88, roughness: 0.20, ei: 1.0, shape: 'diamond', css: '#cf7d86', sw: ['#ffc2c9', '#b96872'], tag: 'Soft, shiny, sophisticated.' },
  { id: 'emerald',  name: 'Emerald',    premium: true,  base: 0x21d39a, emissive: 0x0a8f63, metalness: 0.55, roughness: 0.12, ei: 1.2, shape: 'leaf',    css: '#13a87a', sw: ['#5df0c0', '#0c7a59'], tag: 'A glowing gemstone leaf.' },
  { id: 'neon',     name: 'Neon',       premium: true,  base: 0xc14dff, emissive: 0xa030ff, metalness: 0.50, roughness: 0.22, ei: 1.6, shape: 'chevron', css: '#a02fe0', sw: ['#d98aff', '#6a1f9c'], tag: 'Vaporwave nights, full glow.' },
  { id: 'obsidian', name: 'Obsidian',   premium: true,  base: 0x4a5160, emissive: 0x0a0c10, metalness: 0.96, roughness: 0.16, ei: 1.0, shape: 'spear',   css: '#3a3f4a', sw: ['#6b7280', '#1a1d22'], tag: 'Stealthy black blade.' },
  { id: 'aurora',   name: 'Aurora',     premium: true,  base: 0x49e0c0, emissive: 0x2f6fe0, metalness: 0.45, roughness: 0.14, ei: 1.5, shape: 'star',    css: '#2fb0c0', sw: ['#8ef0d0', '#5a7cf0'], tag: 'Northern-lights shimmer.' },
  { id: 'inferno',  name: 'Inferno',    premium: true,  base: 0xff5a2a, emissive: 0xff3300, metalness: 0.50, roughness: 0.24, ei: 1.7, shape: 'spear',   css: '#e23d10', sw: ['#ffb14a', '#d12a00'], tag: 'Molten, glowing heat.' },
  { id: 'frost',    name: 'Frost',      premium: true,  base: 0xbfe9ff, emissive: 0x2a6f9c, metalness: 0.60, roughness: 0.10, ei: 1.1, shape: 'needle',  css: '#7cc6e8', sw: ['#e6f7ff', '#5aa0d8'], tag: 'Ice-cut and crystal clear.' },
];
const designById = (id) => DESIGNS.find((d) => d.id === id) || DESIGNS[0];
const FREE_SURPRISES = 10;

/* ---------- State ---------- */
const state = {
  user: null,            // {lat, lon, accuracy, manual:boolean}
  heading: null,         // degrees clockwise from true north, or null
  seats: [],             // normalised seats with dist+bearing (all, unfiltered)
  filter: 'any',         // 'any' | 'backrest' | 'shade'
  targetId: null,        // pinned seat id, or null = use nearest in filter
  view: 'compass',
  lastFetchCentre: null, // {lat, lon} of the centre of the last Overpass call
  fetching: false,
  watchId: null,
  arrived: false,
  prefs: { radius: 500, bigtext: false, imperial: false, design: 'classic', placeType: 'sit', surpriseCount: 0 },
  favs: {},              // id -> seat
  unlocked: false,       // premium compass designs unlocked
  arOpen: false,         // AR camera HUD open
  arStream: null,
};

/* ---------- DOM ---------- */
const $ = (sel) => document.querySelector(sel);
const el = {
  body: document.body,
  splash: $('#splash'),
  app: $('#main'),
  start: $('#btn-start'),
  manualFromSplash: $('#btn-manual-from-splash'),
  home: $('#btn-home'),
  locLabel: $('#loc-label'),
  locText: $('#loc-text'),
  locDot: $('.loc-dot'),
  settingsBtn: $('#btn-settings'),
  banner: $('#banner'),
  // compass
  compassLive: $('#compass-live'),
  compassEmpty: $('#compass-empty'),
  arrow: $('#arrow'),
  rose: $('.compass-rose'),
  canvas3d: $('#compass-3d'),
  distance: $('#compass-distance'),
  desc: $('#compass-desc'),
  hint: $('#compass-hint'),
  // list / map
  seatList: $('#seat-list'),
  map: $('#map'),
  // nav + chips
  navbtns: document.querySelectorAll('.navbtn'),
  chips: document.querySelectorAll('.chip'),
  // dialogs
  dlgLoc: $('#dlg-location'),
  locInput: $('#loc-input'),
  locSearch: $('#loc-search'),
  locStatus: $('#loc-status'),
  locResults: $('#loc-results'),
  useGps: $('#btn-use-gps'),
  dlgSettings: $('#dlg-settings'),
  setRadius: $('#set-radius'),
  setRadiusOut: $('#set-radius-out'),
  setBigtext: $('#set-bigtext'),
  setImperial: $('#set-imperial'),
  dlgSeat: $('#dlg-seat'),
  seatTitle: $('#seat-title'),
  seatBadges: $('#seat-badges'),
  seatMeta: $('#seat-meta'),
  seatPoint: $('#seat-point'),
  seatDirections: $('#seat-directions'),
  seatShare: $('#seat-share'),
  seatFav: $('#seat-fav'),
  seatReport: $('#seat-report'),
  seatClose: $('#seat-close'),
  toast: $('#toast'),
  // place types
  placebtns: document.querySelectorAll('.placebtn'),
  // actions
  btnRandom: $('#btn-random'),
  btnAR: $('#btn-ar'),
  btnShop: $('#btn-shop'),
  btnRefresh: $('#btn-refresh'),
  filters: $('.view-compass .filters'),
  // shop
  dlgShop: $('#dlg-shop'), shopGrid: $('#shop-grid'), shopClose: $('#shop-close'),
  // unlock
  dlgUnlock: $('#dlg-unlock'), unlockBuy: $('#unlock-buy'), unlockInput: $('#unlock-input'),
  unlockApply: $('#unlock-apply'), unlockStatus: $('#unlock-status'), unlockClose: $('#unlock-close'),
  // qr / meet
  seatMeet: $('#seat-meet'), dlgQr: $('#dlg-qr'), qrBox: $('#qr-box'), qrWhere: $('#qr-where'),
  qrShare: $('#qr-share'), qrClose: $('#qr-close'),
  // AR
  arScreen: $('#ar-screen'), arVideo: $('#ar-video'), arMarker: $('#ar-marker'),
  arCue: $('#ar-cue'), arMsg: $('#ar-msg'), arClose: $('#ar-close'),
  // dinner tools
  btnDinner: $('#btn-dinner'), dlgDinner: $('#dlg-dinner'), dinnerClose: $('#dinner-close'),
  segBtns: document.querySelectorAll('#dlg-dinner .seg-btn'),
  dTotal: $('#d-total'), dPeople: $('#d-people'), dTip: $('#d-tip'), dSplitOut: $('#d-split-out'),
  dNames: $('#d-names'), dSpin: $('#d-spin'), dWhoOut: $('#d-who-out'),
  // reveal + misc
  reveal: $('#reveal'), revealName: $('#reveal .reveal-name'), revealSub: $('#reveal .reveal-sub'),
  randomLabel: $('#random-label'),
};
const prefersReducedMotion = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

let map = null, youMarker = null, seatLayer = null, lineLayer = null;
let openSeat = null;       // seat shown in the detail dialog

/* ============================================================
   Geo maths
   ============================================================ */
const toRad = (d) => (d * Math.PI) / 180;
const toDeg = (r) => (r * 180) / Math.PI;

function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dφ = toRad(lat2 - lat1), dλ = toRad(lon2 - lon1);
  const a = Math.sin(dφ / 2) ** 2 +
            Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dλ / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function bearing(lat1, lon1, lat2, lon2) {
  const φ1 = toRad(lat1), φ2 = toRad(lat2), Δλ = toRad(lon2 - lon1);
  const y = Math.sin(Δλ) * Math.cos(φ2);
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
  return (toDeg(Math.atan2(y, x)) + 360) % 360;
}

const COMPASS_PTS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
const compassPoint = (deg) => COMPASS_PTS[Math.round(deg / 45) % 8];

function fmtDistance(m) {
  if (state.prefs.imperial) {
    const ft = m * 3.28084;
    if (ft < 1000) return { num: Math.round(ft / 5) * 5, unit: 'ft' };
    return { num: (ft / 5280).toFixed(ft < 5280 ? 2 : 1), unit: 'mi' };
  }
  if (m < 1000) return { num: Math.round(m / 5) * 5, unit: 'm' };
  return { num: (m / 1000).toFixed(m < 10000 ? 1 : 0), unit: 'km' };
}

/* ============================================================
   Seat normalisation
   ============================================================ */
function describeSit(tags, category) {
  const bits = [];
  if (tags.backrest === 'yes') bits.push('has a backrest');
  else if (tags.backrest === 'no') bits.push('no backrest');
  if (tags.covered === 'yes' || tags.shelter === 'yes' || tags.amenity === 'shelter') bits.push('shaded');
  if (tags.material) bits.push(tags.material);
  return bits.length ? `${category} · ${bits.join(', ')}` : category;
}

const CATEGORY = {
  bench: 'Bench', picnic_table: 'Picnic table', shelter: 'Shelter', rest_area: 'Rest area',
  park: 'Park', garden: 'Garden', dog_park: 'Dog park', nature_reserve: 'Nature reserve',
  zoo: 'Zoo', aquarium: 'Aquarium', viewpoint: 'Viewpoint', playground: 'Playground',
  museum: 'Museum', gallery: 'Gallery', library: 'Library', artwork: 'Artwork',
  fast_food: 'Fast food', restaurant: 'Restaurant', cafe: 'Café', ice_cream: 'Ice cream', food_court: 'Food court',
};
function categoryOf(t) {
  return CATEGORY[t.amenity] || CATEGORY[t.leisure] || CATEGORY[t.tourism] || CATEGORY[t.highway] || 'Place';
}

const cuisineLabel = (c) => (c || '').split(';')[0].replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase());

function normalise(elements) {
  const pt = state.prefs.placeType;
  const isSit = pt === 'sit', isFood = pt === 'food';
  const out = [];
  for (const e of elements) {
    const lat = e.lat ?? e.center?.lat;
    const lon = e.lon ?? e.center?.lon;
    if (lat == null || lon == null) continue;        // skip un-locatable ways
    const t = e.tags || {};
    const category = categoryOf(t);
    const cuisine = isFood ? cuisineLabel(t.cuisine) : '';
    const independent = isFood && !t.brand && !t['brand:wikidata'] && !t['operator:wikidata'];
    let desc;
    if (isSit) desc = describeSit(t, category);
    else if (isFood) desc = `${t.name || category}${cuisine ? ' · ' + cuisine : ' · ' + category}`;
    else desc = t.name ? `${t.name} · ${category}` : category;
    out.push({
      id: `${e.type}/${e.id}`,
      lat, lon, tags: t, category,
      name: t.name || category,
      comfort: {
        backrest: t.backrest === 'yes',
        shade: t.covered === 'yes' || t.shelter === 'yes' || t.amenity === 'shelter',
        shelter: t.amenity === 'shelter' || t.shelter === 'yes',
      },
      food: isFood ? { cuisine, independent } : null,
      desc,
    });
  }
  return out;
}

function recomputeGeometry() {
  if (!state.user) return;
  const { lat, lon } = state.user;
  for (const s of state.seats) {
    s.dist = haversine(lat, lon, s.lat, s.lon);
    s.bearing = bearing(lat, lon, s.lat, s.lon);
  }
  state.seats.sort((a, b) => a.dist - b.dist);
}

function filteredSeats() {
  if (state.filter === 'backrest') return state.seats.filter((s) => s.comfort.backrest);
  if (state.filter === 'shade') return state.seats.filter((s) => s.comfort.shade);
  return state.seats;
}

function currentTarget() {
  const list = filteredSeats();
  if (!list.length) return null;
  if (state.targetId) {
    const pinned = list.find((s) => s.id === state.targetId);
    if (pinned) return pinned;
  }
  return list[0];
}

/* ============================================================
   Overpass fetch (with mirror fallback)
   ============================================================ */
function buildQuery(lat, lon, radius) {
  const pt = PLACE_TYPES[state.prefs.placeType] || PLACE_TYPES.sit;
  return `[out:json][timeout:25];\n(\n${pt.q(radius, lat, lon)}\n);\nout center tags;`;
}

async function overpassFetch(lat, lon, radius) {
  const body = 'data=' + encodeURIComponent(buildQuery(lat, lon, radius));
  let lastErr;
  for (const url of OVERPASS_ENDPOINTS) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), OVERPASS_TIMEOUT);
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body, signal: ctrl.signal,
      });
      clearTimeout(timer);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      return json.elements || [];
    } catch (err) {
      clearTimeout(timer);
      lastErr = err;
      // try next mirror
    }
  }
  throw lastErr || new Error('All Overpass endpoints failed');
}

async function loadSeats(lat, lon, { force = false } = {}) {
  if (state.fetching) { state._pending = { lat, lon }; return; }   // queue; runs after current fetch
  // Skip refetch if we haven't moved far and not forced
  if (!force && state.lastFetchCentre) {
    const moved = haversine(lat, lon, state.lastFetchCentre.lat, state.lastFetchCentre.lon);
    if (moved < REFETCH_MOVE_M) return;
  }
  state.fetching = true;
  el.body.classList.add('searching');
  const reqType = state.prefs.placeType;
  showBanner(`Looking for ${placeNoun()}s nearby…`, 'info');
  try {
    const elements = await overpassFetch(lat, lon, state.prefs.radius);
    if (state.prefs.placeType !== reqType) return;   // place type changed mid-flight — discard; queued refetch handles it
    state.seats = normalise(elements);
    state.lastFetchCentre = { lat, lon };
    recomputeGeometry();
    cacheResults();
    hideBanner();
    render();
    if (!state.seats.length) {
      showBanner(`No ${placeNoun()}s mapped within ${fmtRadius()}. Try a larger radius in settings.`, 'info');
    }
  } catch (err) {
    console.warn('Overpass failed:', err);
    if (state.seats.length) {
      showBanner("Couldn't refresh — showing the last results.", 'error');
    } else if (!restoreCache(lat, lon)) {
      showBanner("Couldn't reach the map service. Check your connection and try again.", 'error');
      render();
    }
  } finally {
    state.fetching = false;
    el.body.classList.remove('searching');
    if (state._pending) { const p = state._pending; state._pending = null; loadSeats(p.lat, p.lon, { force: true }); }
  }
}

// Re-run the search for the current area (the refresh button).
function refreshSearch() {
  if (!state.user) { openLocationDialog('Pick a location to search around.'); return; }
  if (state.fetching) return;
  state.lastFetchCentre = null;
  toast(`Searching this area…`);
  loadSeats(state.user.lat, state.user.lon, { force: true });
}

/* ============================================================
   Geolocation
   ============================================================ */
function startWatching() {
  if (!('geolocation' in navigator)) { onGeoError({ code: 2 }); return; }
  if (state.watchId != null) navigator.geolocation.clearWatch(state.watchId);
  state.watchId = navigator.geolocation.watchPosition(onGeoPosition, onGeoError, {
    enableHighAccuracy: true, maximumAge: 10000, timeout: 20000,
  });
}

function onGeoPosition(pos) {
  const { latitude: lat, longitude: lon, accuracy } = pos.coords;
  const first = !state.user || state.user.manual;
  state.user = { lat, lon, accuracy, manual: false };
  setLocLabel('My location', false);
  recomputeGeometry();
  loadSeats(lat, lon, { force: first });
  render();
}

function onGeoError(err) {
  // 1 = denied, 2 = unavailable, 3 = timeout
  if (err.code === 1) {
    openLocationDialog("Location is off. Turn it on, or enter a place below.");
  } else {
    openLocationDialog("Couldn't get your GPS. Enter a place to search around instead.");
  }
}

/* ============================================================
   Device orientation → compass heading
   ============================================================ */
function startCompass() {
  const handler = (event) => {
    let h = null;
    if (typeof event.webkitCompassHeading === 'number') {
      h = event.webkitCompassHeading;                 // iOS: already true-north, clockwise
    } else if (event.absolute && typeof event.alpha === 'number') {
      h = (360 - event.alpha);                         // others: alpha is counter-clockwise
      const sa = (screen.orientation && screen.orientation.angle) || 0;
      h = (h + sa) % 360;
    }
    if (h != null && !Number.isNaN(h)) {
      state.heading = (h + 360) % 360;
      if (state.view === 'compass') updateCompass();
      if (state.arOpen) updateAR();
    }
    // Feed device tilt to the 3D compass for parallax depth.
    if (window.Compass3D && (event.gamma != null || event.beta != null)) {
      const gx = Math.max(-30, Math.min(30, event.gamma || 0)) / 30;
      const gy = Math.max(-30, Math.min(30, (event.beta || 0) - 90)) / 30;
      window.Compass3D.setTilt(gx, gy);
    }
  };
  if (window.DeviceOrientationEvent) {
    window.addEventListener('deviceorientationabsolute', handler, true);
    window.addEventListener('deviceorientation', handler, true);
  }
}

// iOS requires a permission request from inside a user gesture.
async function requestCompassPermission() {
  try {
    const D = window.DeviceOrientationEvent;
    if (D && typeof D.requestPermission === 'function') {
      const r = await D.requestPermission();
      if (r !== 'granted') return;
    }
    startCompass();
  } catch { /* compass simply stays unavailable; static bearing is the fallback */ }
}

/* ============================================================
   Rendering
   ============================================================ */
function render() {
  updateCompass();
  if (state.view === 'list') renderList();
  if (state.view === 'map') renderMap();
  if (state.arOpen) updateAR();
}

let countTargetId = null, countRaf = 0;
function setDistanceDisplay(d, animate) {
  const render = (numStr) => { el.distance.innerHTML = `<span class="num">${numStr}</span><span class="unit">${d.unit}</span>`; };
  if (!animate || prefersReducedMotion) { render(d.num); return; }
  cancelAnimationFrame(countRaf);
  const end = parseFloat(d.num) || 0;
  const isInt = String(d.num).indexOf('.') < 0;
  const t0 = performance.now(), dur = 650;
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur);
    const v = end * (1 - Math.pow(1 - k, 3));   // easeOutCubic
    render(isInt ? String(Math.round(v)) : v.toFixed(1));
    if (k < 1) countRaf = requestAnimationFrame(step); else render(d.num);
  };
  countRaf = requestAnimationFrame(step);
}

function updateCompass() {
  const target = currentTarget();
  if (!target) {
    el.compassLive.hidden = true;
    el.compassEmpty.hidden = false;
    el.compassEmpty.innerHTML = state.seats.length
      ? `<h2>No matching seats</h2><p>No seats with that filter nearby. Try “Any seat”.</p>`
      : `<h2>No ${placeNoun()}s found yet</h2><p>Nothing mapped within ${fmtRadius()}. Widen the radius in settings, or move the location.</p>`;
    el.body.classList.remove('arrived');
    if (window.Compass3D) window.Compass3D.setArrival(false);
    return;
  }
  el.compassEmpty.hidden = true;
  el.compassLive.hidden = false;

  const d = fmtDistance(target.dist);
  const animate = target.id !== countTargetId;   // count-up only when the target changes
  countTargetId = target.id;
  setDistanceDisplay(d, animate);
  el.desc.textContent = target.desc;

  // Arrival?
  const arrived = target.dist <= ARRIVAL_M;
  if (arrived !== state.arrived) {
    state.arrived = arrived;
    el.body.classList.toggle('arrived', arrived);
    if (window.Compass3D) window.Compass3D.setArrival(arrived);
    if (arrived) { vibrate([60, 40, 60]); el.desc.textContent = "You're here — " + target.desc; if (window.FX) window.FX.confettiBurst(); }
  }
  if (arrived) return;

  // Heading-up when we have a live device heading; north-up otherwise.
  const hasHeading = state.heading != null && !state.user?.manual;
  const angle = hasHeading ? (target.bearing - state.heading + 360) % 360 : target.bearing;

  // Spin the compass rose so N/E/S/W point to real north under the fixed needle.
  if (el.rose) el.rose.style.transform = hasHeading ? `rotate(${-state.heading}deg)` : 'none';

  if (window.Compass3D && window.Compass3D.available) {
    window.Compass3D.setAngle(angle);
  } else {
    el.arrow.style.transform = `rotate(${angle}deg)`;
    el.arrow.classList.toggle('is-stale', !hasHeading);
  }

  el.hint.hidden = hasHeading;
  if (!hasHeading) el.hint.textContent = `${compassPoint(target.bearing)} of you · the “N” marks north`;
}

const ico = (id) => `<svg class="ic"><use href="#${id}"/></svg>`;

const favLabel = (on) => `<svg class="ic" width="18" height="18"><use href="#i-star"/></svg>${on ? 'Saved' : 'Save'}`;

const YOU_PIN_SVG =
  '<svg class="you-pin" width="22" height="22" viewBox="0 0 24 24">' +
  '<circle cx="12" cy="12" r="8" fill="#fff"/><circle class="core" cx="12" cy="12" r="5.5"/></svg>';

function seatMarkerSvg(isTarget) {
  const fill = isTarget ? '#e8924a' : '#2f7d6b';
  const icon = (PLACE_TYPES[state.prefs.placeType] || PLACE_TYPES.sit).icon;
  return `<svg class="seat-marker" width="${isTarget ? 34 : 28}" height="${isTarget ? 42 : 35}" viewBox="0 0 30 38">` +
    `<path d="M15 1C7.8 1 2 6.6 2 13.5 2 22 15 37 15 37s13-15 13-23.5C28 6.6 22.2 1 15 1z" fill="${fill}" stroke="#fff" stroke-width="1.6"/>` +
    `<svg x="6.5" y="4.5" width="17" height="17" viewBox="0 0 24 24"><use href="#${icon}" color="#fff"/></svg>` +
    `</svg>`;
}

const placeIcon = () => (PLACE_TYPES[state.prefs.placeType] || PLACE_TYPES.sit).icon;

function badgesHtml(s) {
  const out = [];
  if (s.food) {
    out.push(`<span class="badge muted">${ico('i-food')}${s.category}</span>`);
    if (s.food.cuisine) out.push(`<span class="badge cuisine">${escapeHtml(s.food.cuisine)}</span>`);
    if (s.food.independent) out.push(`<span class="badge local">${ico('i-heart')}Local</span>`);
  } else {
    if (s.comfort.backrest) out.push(`<span class="badge">${ico('i-backrest')}Backrest</span>`);
    if (s.comfort.shade) out.push(`<span class="badge shade">${ico(s.comfort.shelter ? 'i-shelter' : 'i-sun')}${s.comfort.shelter ? 'Shelter' : 'Shaded'}</span>`);
    if (s.category !== 'Bench') out.push(`<span class="badge muted">${ico(placeIcon())}${s.category}</span>`);
  }
  if (state.favs[s.id]) out.push(`<span class="badge save">${ico('i-star')}Saved</span>`);
  return out.join('');
}

function renderList() {
  const list = filteredSeats();
  el.seatList.innerHTML = '';
  if (!list.length) {
    el.seatList.innerHTML = `<li class="muted" style="padding:24px;text-align:center">No seats to show. Try “Any seat” or a larger radius.</li>`;
    return;
  }
  for (const s of list.slice(0, 60)) {
    const d = fmtDistance(s.dist);
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.className = 'seat-card';
    btn.type = 'button';
    btn.innerHTML =
      `<span class="dist">${d.num}<span class="unit">${d.unit}</span></span>` +
      `<span class="body"><span class="name">${escapeHtml(s.name)}</span>` +
      `<span class="badges">${badgesHtml(s) || `<span class="badge muted">${ico('i-seat')}Seat</span>`}</span></span>` +
      `<span class="chevron"><svg width="22" height="22"><use href="#i-chevron"/></svg></span>`;
    btn.addEventListener('click', () => openSeatDialog(s));
    li.appendChild(btn);
    el.seatList.appendChild(li);
  }
}

function renderMap() {
  if (!state.user) return;
  if (!map) {
    map = L.map('map', { zoomControl: true, attributionControl: true });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);
    seatLayer = L.layerGroup().addTo(map);
    lineLayer = L.layerGroup().addTo(map);
  }
  const { lat, lon } = state.user;
  map.setView([lat, lon], 17);

  if (!youMarker) {
    youMarker = L.marker([lat, lon], {
      icon: L.divIcon({ className: '', html: YOU_PIN_SVG, iconSize: [22, 22], iconAnchor: [11, 11] }),
      keyboard: false, interactive: false,
    }).addTo(map);
  } else {
    youMarker.setLatLng([lat, lon]);
  }

  seatLayer.clearLayers();
  lineLayer.clearLayers();
  const list = filteredSeats();
  const target = currentTarget();
  for (const s of list.slice(0, 80)) {
    const isTarget = target && s.id === target.id;
    const w = isTarget ? 34 : 28, h = isTarget ? 42 : 35;
    const m = L.marker([s.lat, s.lon], {
      icon: L.divIcon({ className: '', html: seatMarkerSvg(isTarget), iconSize: [w, h], iconAnchor: [w / 2, h] }),
      title: s.name,
      zIndexOffset: isTarget ? 1000 : 0,
    });
    m.on('click', () => openSeatDialog(s));
    seatLayer.addLayer(m);
  }
  if (target) {
    lineLayer.addLayer(L.polyline([[lat, lon], [target.lat, target.lon]],
      { color: '#2f7d6b', weight: 4, opacity: .7, dashArray: '2 8' }));
  }
  setTimeout(() => map.invalidateSize(), 0);
}

/* ============================================================
   Seat detail dialog
   ============================================================ */
function openSeatDialog(s) {
  openSeat = s;
  el.seatTitle.textContent = s.name;
  el.seatBadges.innerHTML = badgesHtml(s) || `<span class="badge muted">${ico('i-seat')}Seat</span>`;
  const d = fmtDistance(s.dist);
  el.seatMeta.textContent = `${d.num} ${d.unit} away · ${compassPoint(s.bearing)}` +
    (s.tags.material ? ` · ${s.tags.material}` : '');
  el.seatFav.innerHTML = favLabel(!!state.favs[s.id]);
  el.dlgSeat.showModal();
}

/* ============================================================
   UI wiring
   ============================================================ */
function setView(view) {
  state.view = view;
  el.body.dataset.appView = view;
  el.navbtns.forEach((b) => {
    const active = b.dataset.view === view;
    b.classList.toggle('is-active', active);
    if (active) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  });
  if (view === 'list') renderList();
  if (view === 'map') renderMap();
  if (view === 'compass') {
    updateCompass();
    if (window.Compass3D && window.Compass3D.available) requestAnimationFrame(() => window.Compass3D.resize());
  }
}

function setFilter(f) {
  state.filter = f;
  el.chips.forEach((c) => {
    const active = c.dataset.filter === f;
    c.classList.toggle('is-active', active);
    c.setAttribute('aria-pressed', String(active));
  });
  // If the pinned target no longer matches, fall back to nearest.
  if (state.targetId && !filteredSeats().some((s) => s.id === state.targetId)) state.targetId = null;
  render();
}

let compass3dReady = false;
function enterApp() {
  el.body.dataset.view = 'app';
  el.app.hidden = false;
  if (!compass3dReady && window.Compass3D && el.canvas3d) {
    compass3dReady = true;
    if (window.Compass3D.init(el.canvas3d)) {
      el.body.classList.add('has-3d');
      startTiltParallax();
    }
  }
  applyDesign(state.prefs.design);
  setView('compass');
}

// Desktop parallax: tilt the 3D compass toward the pointer.
function startTiltParallax() {
  const ring = document.querySelector('.compass-ring');
  if (!ring) return;
  ring.addEventListener('pointermove', (e) => {
    const r = ring.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width - 0.5) * 2;
    const y = ((e.clientY - r.top) / r.height - 0.5) * 2;
    window.Compass3D.setTilt(x * 0.8, -y * 0.8);
  });
  ring.addEventListener('pointerleave', () => window.Compass3D.setTilt(0, 0));
}

function setLocLabel(text, manual) {
  el.locText.textContent = text;
  el.locDot.classList.toggle('is-manual', !!manual);
}

function fmtRadius() {
  const r = state.prefs.radius;
  return state.prefs.imperial ? `${Math.round(r * 3.28084 / 10) * 10} ft` : `${r} m`;
}

/* ---------- Banner / toast ---------- */
let bannerTimer;
function showBanner(msg, kind) {
  el.banner.textContent = msg;
  el.banner.className = 'banner' + (kind === 'error' ? ' error' : '');
  el.banner.hidden = false;
  clearTimeout(bannerTimer);
  if (kind !== 'error') bannerTimer = setTimeout(hideBanner, 4000);
}
function hideBanner() { el.banner.hidden = true; }

let toastTimer;
function toast(msg) {
  el.toast.textContent = msg;
  el.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.toast.hidden = true; }, 2600);
}

function vibrate(pattern) { try { navigator.vibrate?.(pattern); } catch {} }

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

/* ============================================================
   Manual location (Nominatim)
   ============================================================ */
function openLocationDialog(message) {
  el.locStatus.textContent = message || '';
  el.locResults.innerHTML = '';
  if (!el.dlgLoc.open) el.dlgLoc.showModal();
  setTimeout(() => el.locInput.focus(), 50);
}

async function geocode() {
  const q = el.locInput.value.trim();
  if (!q) return;
  el.locStatus.textContent = 'Searching…';
  el.locResults.innerHTML = '';
  try {
    const url = `${NOMINATIM}?q=${encodeURIComponent(q)}&format=json&limit=6&addressdetails=0`;
    const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
    const data = await res.json();
    if (!data.length) { el.locStatus.textContent = 'No matches. Try a different spelling.'; return; }
    el.locStatus.textContent = '';
    for (const r of data) {
      const li = document.createElement('li');
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = r.display_name;
      b.addEventListener('click', () => pickManualLocation(parseFloat(r.lat), parseFloat(r.lon), r.display_name));
      li.appendChild(b);
      el.locResults.appendChild(li);
    }
  } catch {
    el.locStatus.textContent = "Couldn't search right now. Check your connection.";
  }
}

function pickManualLocation(lat, lon, label) {
  if (state.watchId != null) { navigator.geolocation.clearWatch(state.watchId); state.watchId = null; }
  state.user = { lat, lon, accuracy: null, manual: true };
  state.lastFetchCentre = null;
  state.targetId = null;
  setLocLabel(label.split(',')[0], true);
  el.dlgLoc.close();
  recomputeGeometry();
  render();
  loadSeats(lat, lon, { force: true });
}

/* ============================================================
   Prefs / cache / favourites (localStorage)
   ============================================================ */
function loadPrefs() {
  try { Object.assign(state.prefs, JSON.parse(localStorage.getItem(PREFS_KEY) || '{}')); } catch {}
  try { state.favs = JSON.parse(localStorage.getItem(FAVS_KEY) || '{}'); } catch {}
  try { state.unlocked = localStorage.getItem(UNLOCK_KEY) === '1'; } catch {}
  if (designById(state.prefs.design).premium && !state.unlocked) state.prefs.design = 'classic';
  if (!PLACE_TYPES[state.prefs.placeType]) state.prefs.placeType = 'sit';
  applyPrefs();
}
function savePrefs() { try { localStorage.setItem(PREFS_KEY, JSON.stringify(state.prefs)); } catch {} }
function saveFavs()  { try { localStorage.setItem(FAVS_KEY, JSON.stringify(state.favs)); } catch {} }

function applyPrefs() {
  el.body.classList.toggle('bigtext', state.prefs.bigtext);
  el.setRadius.value = state.prefs.radius;
  el.setRadiusOut.textContent = fmtRadius();
  el.setBigtext.checked = state.prefs.bigtext;
  el.setImperial.checked = state.prefs.imperial;
  el.body.dataset.place = state.prefs.placeType;
  el.placebtns.forEach((b) => { const on = b.dataset.place === state.prefs.placeType; b.classList.toggle('is-active', on); b.setAttribute('aria-selected', String(on)); });
  document.documentElement.style.setProperty('--arrow-color', designById(state.prefs.design).css);
  if (el.randomLabel) el.randomLabel.textContent = state.prefs.placeType === 'food' ? "I'm hungry" : 'Surprise me';
}

function cacheResults() {
  if (!state.user) return;
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({
      centre: state.lastFetchCentre, label: el.locText.textContent,
      seats: state.seats.map((s) => ({ id: s.id, lat: s.lat, lon: s.lon, tags: s.tags })),
      ts: Date.now(),
    }));
  } catch {}
}

function restoreCache(lat, lon) {
  try {
    const c = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null');
    if (!c || !c.seats?.length) return false;
    state.seats = normalise(c.seats.map((s) => ({ type: 'node', id: s.id.split('/')[1], lat: s.lat, lon: s.lon, tags: s.tags })));
    recomputeGeometry();
    render();
    showBanner('Offline — showing your last results.', 'info');
    return true;
  } catch { return false; }
}

/* ============================================================
   Place types (Seats / Parks / Zoos)
   ============================================================ */
function placeNoun() { return (PLACE_TYPES[state.prefs.placeType] || PLACE_TYPES.sit).noun; }

function setPlaceType(pt) {
  if (!PLACE_TYPES[pt]) return;
  state.prefs.placeType = pt;
  savePrefs();
  el.body.dataset.place = pt;
  el.placebtns.forEach((b) => {
    const on = b.dataset.place === pt;
    b.classList.toggle('is-active', on);
    b.setAttribute('aria-selected', String(on));
  });
  // comfort filters only apply to seats — reset to "any"
  state.filter = 'any';
  el.chips.forEach((c) => { const on = c.dataset.filter === 'any'; c.classList.toggle('is-active', on); c.setAttribute('aria-pressed', String(on)); });
  state.targetId = null;
  state.seats = [];
  state.lastFetchCentre = null;
  if (el.randomLabel) el.randomLabel.textContent = pt === 'food' ? "I'm hungry" : 'Surprise me';
  render();
  if (state.user) loadSeats(state.user.lat, state.user.lon, { force: true });
}

/* ============================================================
   "Surprise me" — random place within radius (10 free, then Perch Plus)
   ============================================================ */
function surprisesLeft() { return Math.max(0, FREE_SURPRISES - (state.prefs.surpriseCount || 0)); }

function surpriseMe() {
  const list = filteredSeats();
  if (!list.length) { toast(`No ${placeNoun()}s nearby to pick from`); return; }
  if (!state.unlocked && surprisesLeft() <= 0) { openUnlock('surprise'); return; }
  if (!state.unlocked) { state.prefs.surpriseCount = (state.prefs.surpriseCount || 0) + 1; savePrefs(); }
  const pick = list[Math.floor(Math.random() * list.length)];
  surpriseReveal(list, pick);
}

function landSurprise(pick) {
  state.targetId = pick.id;
  setView('compass');
  render();
  const d = fmtDistance(pick.dist);
  const left = state.unlocked ? '' : ` · ${surprisesLeft()} free left`;
  toast(`${pick.name} — ${d.num} ${d.unit} away${left}`);
}

function surpriseReveal(list, pick) {
  if (prefersReducedMotion) { landSurprise(pick); return; }
  const overlay = el.reveal;
  overlay.hidden = false;
  overlay.classList.remove('landed');
  el.revealSub.textContent = state.prefs.placeType === 'food' ? "Tonight you're eating at…" : 'Your spot is…';
  const names = list.map((s) => s.name);
  let ticks = 0; const total = 16;
  let done = false;
  const finish = () => {
    if (done) return; done = true;
    clearInterval(iv);
    el.revealName.textContent = pick.name;
    overlay.classList.add('landed');
    const d = fmtDistance(pick.dist);
    el.revealSub.textContent = `${d.num} ${d.unit} away`;
    vibrate([40, 30, 90]);
    if (window.FX) window.FX.confettiBurst();
    setTimeout(() => { overlay.hidden = true; landSurprise(pick); }, 1500);
  };
  const iv = setInterval(() => {
    el.revealName.textContent = names[Math.floor(Math.random() * names.length)] || pick.name;
    if (++ticks >= total) finish();
  }, 85);
  overlay.onclick = finish;   // tap to skip
}

/* ============================================================
   Dinner tools — split the bill / who pays (the thrill)
   ============================================================ */
function dinnerSplit() {
  const total = parseFloat(el.dTotal.value) || 0;
  const people = Math.max(1, parseInt(el.dPeople.value) || 1);
  const tip = Math.max(0, parseFloat(el.dTip.value) || 0);
  const each = (total * (1 + tip / 100)) / people;
  el.dSplitOut.textContent = total > 0 ? `Each pays ${each.toFixed(2)}` : 'Each pays —';
}

function dinnerSpin() {
  const names = el.dNames.value.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
  if (names.length < 2) { el.dWhoOut.textContent = 'Add at least two names.'; return; }
  const winner = names[Math.floor(Math.random() * names.length)];
  el.dSpin.disabled = true;
  el.dWhoOut.classList.remove('landed');
  if (prefersReducedMotion) { el.dWhoOut.textContent = `${winner} pays!`; el.dWhoOut.classList.add('landed'); el.dSpin.disabled = false; vibrate([40,30,90]); return; }
  let ticks = 0; const total = 18;
  const iv = setInterval(() => {
    el.dWhoOut.textContent = names[Math.floor(Math.random() * names.length)];
    if (++ticks >= total) {
      clearInterval(iv);
      el.dWhoOut.textContent = `${winner} pays!`;
      el.dWhoOut.classList.add('landed');
      el.dSpin.disabled = false;
      vibrate([40, 30, 120]);
    }
  }, 80);
}

function openDinner() {
  selectDtab('split');
  dinnerSplit();
  el.dWhoOut.textContent = '';
  el.dlgDinner.showModal();
}

function selectDtab(tab) {
  el.segBtns.forEach((b) => { const on = b.dataset.dtab === tab; b.classList.toggle('is-active', on); b.setAttribute('aria-selected', String(on)); });
  document.getElementById('dtab-split').hidden = tab !== 'split';
  document.getElementById('dtab-who').hidden = tab !== 'who';
}

/* ============================================================
   Compass designs + shop
   ============================================================ */
function applyDesign(id) {
  const d = designById(id);
  if (d.premium && !state.unlocked) return;
  state.prefs.design = d.id;
  savePrefs();
  document.documentElement.style.setProperty('--arrow-color', d.css);
  if (window.Compass3D && window.Compass3D.available) {
    window.Compass3D.setDesign({ base: d.base, emissive: d.emissive, metalness: d.metalness, roughness: d.roughness, shape: d.shape, emissiveIntensity: d.ei });
  }
}

const SHAPE_2D = {
  kite:    'M50 8 L75 86 L50 66 L25 86 Z',
  dart:    'M50 5 L65 76 L50 92 L35 76 Z',
  diamond: 'M50 6 L76 50 L50 94 L24 50 Z',
  chevron: 'M50 8 L80 64 L78 86 L50 60 L22 86 L20 64 Z',
  needle:  'M50 6 L58 50 L50 94 L42 50 Z',
  spear:   'M50 4 L62 34 L55 46 L55 92 L45 92 L45 46 L38 34 Z',
  leaf:    'M50 6 C72 34 72 64 50 94 C28 64 28 34 50 6 Z',
  star:    'M50 6 L59 41 L94 50 L59 59 L50 94 L41 59 L6 50 L41 41 Z',
};

function needleThumb(d, overlayHtml) {
  const gid = 'g_' + d.id;
  const path = SHAPE_2D[d.shape] || SHAPE_2D.kite;
  const glow = d.ei >= 1.4 ? `filter:drop-shadow(0 0 6px ${d.sw[0]})` : '';
  return `<span class="swatch">` +
    `<svg viewBox="0 0 100 100" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" aria-hidden="true">` +
    `<defs><linearGradient id="${gid}" x1="0" y1="0" x2="0.8" y2="1"><stop offset="0" stop-color="${d.sw[0]}"/><stop offset="1" stop-color="${d.sw[1]}"/></linearGradient></defs>` +
    `<circle cx="50" cy="50" r="46" fill="none" stroke="rgba(25,75,64,.12)" stroke-width="2"/>` +
    `<path d="${path}" fill="url(#${gid})" stroke="rgba(0,0,0,.16)" stroke-width="1.5" stroke-linejoin="round" style="${glow}"/>` +
    `</svg>${overlayHtml}</span>`;
}

function renderShop() {
  el.shopGrid.innerHTML = '';
  for (const d of DESIGNS) {
    const owned = !d.premium || state.unlocked;
    const active = state.prefs.design === d.id;
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'design-card' + (active ? ' is-active' : '') + (owned ? '' : ' is-locked');
    const overlay = active ? `<span class="ov chk"><svg class="ic" width="22" height="22"><use href="#i-check"/></svg></span>`
      : (!owned ? `<span class="ov lk"><svg class="ic" width="20" height="20"><use href="#i-lock"/></svg></span>` : '');
    const badge = d.premium
      ? `<span class="tag premium">${ico('i-sparkle')}Premium</span>`
      : `<span class="tag free">Free</span>`;
    card.innerHTML =
      needleThumb(d, overlay) +
      `<span class="design-name">${d.name}</span>` +
      `<span class="design-desc">${d.tag}</span>` +
      badge;
    card.addEventListener('click', () => {
      if (!owned) { openUnlock(); return; }
      applyDesign(d.id); renderShop(); toast(`${d.name} compass applied`);
    });
    el.shopGrid.appendChild(card);
  }
}

function openShop() { renderShop(); el.dlgShop.showModal(); }

function openUnlock(mode) {
  el.unlockStatus.textContent = '';
  el.unlockInput.value = '';
  const title = document.getElementById('unlock-title');
  const sub = document.getElementById('unlock-sub');
  if (mode === 'surprise') {
    title.textContent = "You've used your 10 free surprises";
    sub.textContent = 'Perch Plus gives you unlimited “Surprise me” plus every premium compass design — one tap, one-time, and it keeps Perch free and ad-free for everyone. (Finding a seat is always free.)';
  } else {
    title.textContent = 'Perch Plus';
    sub.textContent = 'Unlock every premium compass design and unlimited “Surprise me” — one-time, and it helps keep Perch free and ad-free for everyone.';
  }
  el.dlgUnlock.showModal();
}

function tryUnlock(code) {
  if ((code || '').trim().toUpperCase() === UNLOCK_CODE.toUpperCase()) {
    state.unlocked = true;
    try { localStorage.setItem(UNLOCK_KEY, '1'); } catch {}
    el.unlockStatus.textContent = 'Unlocked! Every design is yours. Thank you for supporting Perch.';
    renderShop();
    setTimeout(() => el.dlgUnlock.close(), 1100);
    return true;
  }
  el.unlockStatus.textContent = "That code didn't work — check it and try again.";
  return false;
}

/* ============================================================
   Meet here (QR) — privacy-safe "connect with people"
   ============================================================ */
function osmGeoUrl(s) { return `https://www.openstreetmap.org/?mlat=${s.lat}&mlon=${s.lon}#map=19/${s.lat}/${s.lon}`; }

function openMeet(s) {
  const url = osmGeoUrl(s);
  el.qrBox.innerHTML = '';
  try {
    const qr = qrcode(0, 'M');
    qr.addData(url);
    qr.make();
    const img = new Image();
    img.src = qr.createDataURL(6, 12);
    img.alt = 'QR code to this spot';
    el.qrBox.appendChild(img);
  } catch (e) {
    el.qrBox.textContent = 'Could not generate a code on this device.';
  }
  const d = fmtDistance(s.dist);
  el.qrWhere.textContent = `${s.name} · ${d.num} ${d.unit} from you`;
  el.dlgQr.dataset.url = url;
  el.dlgQr.showModal();
}

/* ============================================================
   AR camera HUD (sensor-based: camera + compass, no cloud AI)
   ============================================================ */
async function openAR() {
  if (!state.user) { toast('Find your location first'); return; }
  state.arOpen = true;
  el.arScreen.hidden = false;
  el.body.classList.add('ar-open');
  el.arMsg.hidden = true; el.arMarker.hidden = true; el.arCue.hidden = true;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    arFallback('This device has no camera access. Use the Direction or Map view instead.');
    return;
  }
  try {
    state.arStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
    el.arVideo.srcObject = state.arStream;
    el.arVideo.play().catch(() => {});
    requestCompassPermission();        // iOS: ask for motion/orientation if not yet granted
    updateAR();
  } catch (e) {
    arFallback('Camera access was blocked. Allow the camera to use AR — or use the Direction and Map views.');
  }
}

function arFallback(msg) { el.arMsg.hidden = false; el.arMsg.textContent = msg; el.arMarker.hidden = true; el.arCue.hidden = true; }

function closeAR() {
  state.arOpen = false;
  el.body.classList.remove('ar-open');
  el.arScreen.hidden = true;
  if (state.arStream) { state.arStream.getTracks().forEach((t) => t.stop()); state.arStream = null; }
  el.arVideo.srcObject = null;
}

function updateAR() {
  if (!state.arOpen) return;
  const target = currentTarget();
  if (!target) { arFallback(`No ${placeNoun()} found nearby. Widen the radius or move the map.`); return; }
  const hasHeading = state.heading != null && !state.user?.manual;
  if (!hasHeading) {
    arFallback("Live AR uses your phone's compass. On this device, try the Direction or Map view.");
    return;
  }
  el.arMsg.hidden = true;
  const delta = ((target.bearing - state.heading + 540) % 360) - 180;   // -180..180
  const d = fmtDistance(target.dist);
  const HALF_FOV = 33;
  if (Math.abs(delta) <= HALF_FOV) {
    el.arCue.hidden = true;
    el.arMarker.hidden = false;
    const left = 50 + (delta / HALF_FOV) * 46;
    el.arMarker.style.left = Math.max(6, Math.min(94, left)) + '%';
    el.arMarker.querySelector('.ar-dist').textContent = `${d.num} ${d.unit}`;
    el.arMarker.querySelector('.ar-name').textContent = target.name;
  } else {
    el.arMarker.hidden = true;
    el.arCue.hidden = false;
    el.arCue.textContent = Math.abs(delta) > 135 ? 'Turn around' : (delta > 0 ? 'Turn right' : 'Turn left');
  }
}

/* ============================================================
   Event listeners
   ============================================================ */
function wire() {
  // Start (the all-important first gesture: GPS + iOS compass permission)
  el.start.addEventListener('click', () => {
    enterApp();
    requestCompassPermission();
    startWatching();
  });
  el.manualFromSplash.addEventListener('click', () => { enterApp(); openLocationDialog('Enter a place to find seats nearby.'); });

  el.home.addEventListener('click', () => { el.body.dataset.view = 'splash'; el.app.hidden = true; });
  el.locLabel.addEventListener('click', () => openLocationDialog(''));
  el.btnRefresh.addEventListener('click', refreshSearch);

  // Bottom nav + filter chips
  el.navbtns.forEach((b) => b.addEventListener('click', () => setView(b.dataset.view)));
  el.chips.forEach((c) => c.addEventListener('click', () => setFilter(c.dataset.filter)));

  // Place types (Seats / Parks / Zoos)
  el.placebtns.forEach((b) => b.addEventListener('click', () => setPlaceType(b.dataset.place)));

  // Compass actions
  el.btnRandom.addEventListener('click', surpriseMe);
  el.btnAR.addEventListener('click', openAR);
  el.arClose.addEventListener('click', closeAR);

  // Dinner tools
  el.btnDinner.addEventListener('click', openDinner);
  el.dinnerClose.addEventListener('click', () => el.dlgDinner.close());
  el.segBtns.forEach((b) => b.addEventListener('click', () => selectDtab(b.dataset.dtab)));
  [el.dTotal, el.dPeople, el.dTip].forEach((i) => i.addEventListener('input', dinnerSplit));
  el.dSpin.addEventListener('click', dinnerSpin);

  // Compass shop + unlock
  el.btnShop.addEventListener('click', openShop);
  el.shopClose.addEventListener('click', () => el.dlgShop.close());
  el.unlockClose.addEventListener('click', () => el.dlgUnlock.close());
  el.unlockBuy.addEventListener('click', () => window.open(SHOP_URL, '_blank', 'noopener'));
  el.unlockApply.addEventListener('click', () => tryUnlock(el.unlockInput.value));
  el.unlockInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); tryUnlock(el.unlockInput.value); } });

  // Meet here (QR)
  el.seatMeet.addEventListener('click', () => { if (openSeat) { const s = openSeat; el.dlgSeat.close(); openMeet(s); } });
  el.qrClose.addEventListener('click', () => el.dlgQr.close());
  el.qrShare.addEventListener('click', async () => {
    const url = el.dlgQr.dataset.url;
    try { if (navigator.share) await navigator.share({ title: 'Meet here', text: 'Meet me at this spot', url }); else { await navigator.clipboard.writeText(url); toast('Link copied'); } } catch {}
  });

  // Settings
  el.settingsBtn.addEventListener('click', () => el.dlgSettings.showModal());
  el.setRadius.addEventListener('input', () => { state.prefs.radius = +el.setRadius.value; el.setRadiusOut.textContent = fmtRadius(); });
  el.setRadius.addEventListener('change', () => { savePrefs(); if (state.user) loadSeats(state.user.lat, state.user.lon, { force: true }); });
  el.setBigtext.addEventListener('change', () => { state.prefs.bigtext = el.setBigtext.checked; el.body.classList.toggle('bigtext', state.prefs.bigtext); savePrefs(); });
  el.setImperial.addEventListener('change', () => { state.prefs.imperial = el.setImperial.checked; applyPrefs(); savePrefs(); render(); });

  // Manual-location dialog
  el.locSearch.addEventListener('click', geocode);
  el.locInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); geocode(); } });
  el.useGps.addEventListener('click', () => { el.dlgLoc.close(); requestCompassPermission(); startWatching(); });

  // Seat detail
  el.seatClose.addEventListener('click', () => el.dlgSeat.close());
  el.seatPoint.addEventListener('click', () => {
    if (!openSeat) return;
    state.targetId = openSeat.id;
    el.dlgSeat.close();
    setView('compass');
    render();
    toast('Pointing you to this seat');
  });
  el.seatDirections.addEventListener('click', () => {
    if (!openSeat || !state.user) return;
    const u = state.user, s = openSeat;
    window.open(`https://www.openstreetmap.org/directions?engine=fossgis_osrm_foot&route=${u.lat}%2C${u.lon}%3B${s.lat}%2C${s.lon}`, '_blank', 'noopener');
  });
  el.seatShare.addEventListener('click', async () => {
    if (!openSeat) return;
    const s = openSeat;
    const url = `https://www.openstreetmap.org/?mlat=${s.lat}&mlon=${s.lon}#map=19/${s.lat}/${s.lon}`;
    const shareData = { title: 'A place to sit', text: `${s.name} — a place to sit`, url };
    try {
      if (navigator.share) await navigator.share(shareData);
      else { await navigator.clipboard.writeText(url); toast('Link copied'); }
    } catch {}
  });
  el.seatFav.addEventListener('click', () => {
    if (!openSeat) return;
    const id = openSeat.id;
    if (state.favs[id]) { delete state.favs[id]; toast('Removed from saved'); }
    else { state.favs[id] = { id, lat: openSeat.lat, lon: openSeat.lon, name: openSeat.name, tags: openSeat.tags }; toast('Saved'); }
    saveFavs();
    el.seatFav.innerHTML = favLabel(!!state.favs[id]);
    el.seatBadges.innerHTML = badgesHtml(openSeat) || `<span class="badge muted">${ico('i-seat')}Seat</span>`;
    render();
  });
  el.seatReport.addEventListener('click', () => {
    if (!openSeat) return;
    const s = openSeat;
    window.open(`https://www.openstreetmap.org/note/new#map=19/${s.lat}/${s.lon}`, '_blank', 'noopener');
  });

  // Re-render the compass when the device is rotated (portrait/landscape)
  window.addEventListener('orientationchange', () => { if (state.view === 'map' && map) setTimeout(() => map.invalidateSize(), 200); });

  // Offline/online banners
  window.addEventListener('offline', () => showBanner('Offline — showing your last results.', 'info'));
  window.addEventListener('online', () => { hideBanner(); if (state.user && !state.user.manual) loadSeats(state.user.lat, state.user.lon, { force: true }); });
}

/* ============================================================
   Service worker (offline app shell)
   ============================================================ */
function registerSW() {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
  }
}

/* ---------- Boot ---------- */
loadPrefs();
wire();
registerSW();
if (window.FX) { try { window.FX.initBackground(document.getElementById('fx-bg')); window.FX.initBurst(document.getElementById('fx-burst')); } catch (e) {} }
// Expose a tiny hook for manual testing without GPS (used by the dev harness only).
window.__perchSetLocation = (lat, lon, label) => { enterApp(); pickManualLocation(lat, lon, label || 'Test location'); };
