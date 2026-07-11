/* ============================================================
   SikaSafe — community API client (optional)
   The app works fully offline. If a community server is configured
   (edit DEFAULT_API below, or set it in the app), scam-number
   lookups and reports also use the shared blocklist. Every call is
   time-limited and fails soft, so the app never blocks on the network.
   ============================================================ */
(function () {
'use strict';

// Set this to your deployed backend to enable community mode for everyone,
// or leave blank and let users connect a server from the Reports screen.
const DEFAULT_API = '';

const LS_API = 'sikasafe.api';
const LS_CID = 'sikasafe.cid';

function base() {
  try { return (localStorage.getItem(LS_API) || DEFAULT_API || '').replace(/\/+$/, ''); }
  catch { return DEFAULT_API; }
}
function available() { return !!base(); }

function clientId() {
  try {
    let c = localStorage.getItem(LS_CID);
    if (!c) {
      c = (self.crypto && crypto.randomUUID) ? crypto.randomUUID()
        : String(Math.random()).slice(2) + Date.now().toString(36);
      localStorage.setItem(LS_CID, c);
    }
    return c;
  } catch { return 'anon'; }
}

async function fetchJSON(path, opts = {}, ms = 6000) {
  if (!base()) throw new Error('no community server configured');
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    const res = await fetch(base() + path, { ...opts, signal: ctrl.signal });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(data.error || ('HTTP ' + res.status)), { status: res.status, data });
    return data;
  } finally { clearTimeout(timer); }
}

const lookup = (number) => fetchJSON('/api/lookup?number=' + encodeURIComponent(number));
const stats = () => fetchJSON('/api/stats');
const recent = () => fetchJSON('/api/recent');
const report = (o) => fetchJSON('/api/report', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ ...o, client_id: clientId() }),
});
function setBase(url) {
  try { url ? localStorage.setItem(LS_API, url.replace(/\/+$/, '')) : localStorage.removeItem(LS_API); } catch {}
}

window.SikaApi = { available, base, setBase, lookup, report, stats, recent, clientId };
})();
