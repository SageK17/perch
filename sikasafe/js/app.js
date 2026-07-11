/* ============================================================
   SikaSafe — app UI
   Vanilla JS, no build step, works offline. Nothing leaves the
   phone: reports and language choice live in localStorage only.
   ============================================================ */
'use strict';

const { UI, RULES, SCAMS, SITUATIONS, CONTACTS, EMERGENCY, LOCALES, t } = window.SikaData;
const { analyzeText, normNumber } = window.SikaDetector;

const REPORTS_KEY = 'sikasafe.reports.v1';
const LOCALE_KEY = 'sikasafe.locale.v1';

window.SikaState = {
  locale: (() => { try { return localStorage.getItem(LOCALE_KEY) || 'en'; } catch { return 'en'; } })(),
  view: 'check',
};

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const ico = (id, cls = 'ic') => `<svg class="${cls}" aria-hidden="true"><use href="#i-${id}"/></svg>`;

/* ---------- storage ---------- */
function getReports() {
  try { return JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]'); } catch { return []; }
}
function saveReports(r) { try { localStorage.setItem(REPORTS_KEY, JSON.stringify(r)); } catch {} }

/* ---------- language ---------- */
function setLocale(code) {
  window.SikaState.locale = code;
  try { localStorage.setItem(LOCALE_KEY, code); } catch {}
  renderAll();
}

function renderLangSwitch() {
  const wrap = $('#lang');
  wrap.innerHTML = LOCALES.map((l) =>
    `<button class="lang-btn ${l.code === window.SikaState.locale ? 'is-active' : ''}" data-loc="${l.code}">${esc(l.label)}${l.draft ? ' •' : ''}</button>`
  ).join('');
  wrap.querySelectorAll('.lang-btn').forEach((b) =>
    b.addEventListener('click', () => setLocale(b.dataset.loc)));
}

/* ---------- navigation ---------- */
function setView(v) {
  window.SikaState.view = v;
  document.querySelectorAll('.view').forEach((el) => { el.hidden = el.dataset.view !== v; });
  document.querySelectorAll('.navbtn').forEach((b) => {
    const on = b.dataset.view === v;
    b.classList.toggle('is-active', on);
    b.setAttribute('aria-current', on ? 'page' : 'false');
  });
  window.scrollTo(0, 0);
}

/* ============================================================
   CHECK
   ============================================================ */
function renderCheck() {
  const gaNote = window.SikaState.locale === 'gaa'
    ? `<p class="ga-note">${ico('info')} ${esc(t(UI.gaDraftNote))}</p>` : '';
  $('#view-check').innerHTML = `
    ${gaNote}
    <h1 class="h-title">${esc(t(UI.checkTitle))}</h1>
    <p class="h-sub">${esc(t(UI.checkSub))}</p>
    <textarea id="msg" class="msg" rows="4" placeholder="${esc(t(UI.pastePlaceholder))}"></textarea>
    <div class="row">
      <button id="btn-analyze" class="btn primary">${ico('shield')} ${esc(t(UI.analyze))}</button>
      <button id="btn-clear" class="btn ghost">${esc(t(UI.clear))}</button>
    </div>
    <div id="result" class="result" hidden></div>
    <p class="or">${esc(t(UI.orPick))}</p>
    <div class="chips">
      ${SITUATIONS.map((s) => `<button class="chip" data-scam="${s.id}">${esc(t(s.label))}</button>`).join('')}
    </div>
    <div class="rules-card">
      <div class="rules-head">
        <h2>${ico('star')} ${esc(t(UI.golden))}</h2>
        <button id="btn-share" class="btn tiny">${ico('share')} ${esc(t(UI.shareRules))}</button>
      </div>
      <ol class="rules">
        ${RULES.map((r) => `<li><span class="ri">${ico(r.icon)}</span><div><b>${esc(t(r.title))}</b><span>${esc(t(r.body))}</span></div></li>`).join('')}
      </ol>
    </div>
    <p class="fineprint">${ico('info')} ${esc(t(UI.disclaimer))}</p>`;

  $('#btn-analyze').addEventListener('click', () => {
    const text = $('#msg').value.trim();
    if (!text) { $('#msg').focus(); return; }
    showResult(analyzeText(text));
  });
  $('#btn-clear').addEventListener('click', () => {
    $('#msg').value = ''; $('#result').hidden = true; $('#msg').focus();
  });
  $('#btn-share').addEventListener('click', shareRules);
  $('#view-check').querySelectorAll('.chip').forEach((c) =>
    c.addEventListener('click', () => showSituation(c.dataset.scam)));
}

function verdictCard(level, title, line, bodyHtml) {
  return `<div class="verdict ${level}">
    <div class="v-head">${ico(level === 'danger' ? 'danger' : level === 'caution' ? 'warn' : 'check')}
      <div><b>${esc(title)}</b><span>${esc(line)}</span></div></div>
    ${bodyHtml || ''}
  </div>`;
}

function showResult(a) {
  const flags = a.hits.length
    ? `<div class="flags"><p class="flags-h">${a.hits.length} warning sign${a.hits.length > 1 ? 's' : ''} found:</p>
        ${a.hits.map((h) => `<div class="flag"><b>${ico('warn', 'ic sm')} ${esc(t(h.flag))}</b><span>${esc(t(h.advice))}</span></div>`).join('')}</div>`
    : `<div class="flags"><p class="flags-h">No known scam phrases were detected in the text.</p></div>`;
  const box = $('#result');
  box.innerHTML = verdictCard(a.verdict.level, t(a.verdict.title), t(a.verdict.line), flags);
  box.hidden = false;
  box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function showSituation(id) {
  const s = SCAMS.find((x) => x.id === id);
  if (!s) return;
  const body = `
    <div class="sit-body">
      <p class="sit-how">${esc(t(s.how))}</p>
      <div class="two">
        <div><p class="lbl">${ico('warn', 'ic sm')} Warning signs</p><ul>${t(s.signs).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>
        <div><p class="lbl">${ico('check', 'ic sm')} What to do</p><ul>${t(s.protect).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>
      </div>
    </div>`;
  const box = $('#result');
  box.innerHTML = verdictCard('caution', t(s.name), 'This is a common scam. Here is how it works and what to do:', body);
  box.hidden = false;
  box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* ============================================================
   LEARN
   ============================================================ */
function renderLearn() {
  $('#view-learn').innerHTML = `
    <h1 class="h-title">${esc(t(UI.nav.learn))}</h1>
    <p class="h-sub">The scams doing the rounds in Ghana — and exactly how to beat each one.</p>
    <div class="scam-list">
      ${SCAMS.map((s, i) => `
        <details class="scam" ${i === 0 ? 'open' : ''}>
          <summary><span class="ri">${ico(s.icon)}</span><b>${esc(t(s.name))}</b>${ico('chevron', 'ic chev')}</summary>
          <div class="scam-inner">
            <p>${esc(t(s.how))}</p>
            <p class="lbl">${ico('warn', 'ic sm')} Warning signs</p>
            <ul>${t(s.signs).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
            <p class="lbl">${ico('check', 'ic sm')} How to protect yourself</p>
            <ul>${t(s.protect).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
          </div>
        </details>`).join('')}
    </div>`;
}

/* ============================================================
   REPORTS (community — local for now)
   ============================================================ */
function renderReport() {
  const reports = getReports();
  $('#view-report').innerHTML = `
    <h1 class="h-title">${esc(t(UI.reportTitle))}</h1>
    <p class="h-sub">${esc(t(UI.reportSub))}</p>
    <div class="lookup">
      <input id="lookup-num" class="inp" inputmode="tel" placeholder="${esc(t(UI.lookupPlaceholder))}">
      <button id="btn-lookup" class="btn primary">${ico('search')} ${esc(t(UI.lookup))}</button>
    </div>
    <div id="lookup-result"></div>
    <details class="report-form">
      <summary>${ico('flag')} ${esc(t(UI.reportNumber))}</summary>
      <div class="rf-inner">
        <input id="rep-num" class="inp" inputmode="tel" placeholder="Scam phone number">
        <select id="rep-type" class="inp">
          ${SCAMS.map((s) => `<option value="${s.id}">${esc(t(s.name))}</option>`).join('')}
        </select>
        <textarea id="rep-note" class="inp" rows="2" placeholder="What happened? (optional)"></textarea>
        <button id="btn-report" class="btn primary">${ico('flag')} Save report</button>
      </div>
    </details>
    <div class="report-list">
      <p class="lbl">${reports.length} report${reports.length === 1 ? '' : 's'} saved on this phone</p>
      ${reports.length ? reports.slice().reverse().map(reportRow).join('')
        : `<p class="muted">No reports yet. When someone scams you, add the number here.</p>`}
    </div>`;

  $('#btn-lookup').addEventListener('click', doLookup);
  $('#lookup-num').addEventListener('keydown', (e) => { if (e.key === 'Enter') doLookup(); });
  $('#btn-report').addEventListener('click', doReport);
  $('#view-report').querySelectorAll('[data-del]').forEach((b) =>
    b.addEventListener('click', () => { const r = getReports(); r.splice(+b.dataset.del, 1); saveReports(r); renderReport(); }));
}

function reportRow(r, idxFromEnd) {
  const scam = SCAMS.find((s) => s.id === r.type);
  const real = getReports();
  const idx = real.indexOf(r);
  return `<div class="rep">
    <div><b>${esc(r.number)}</b><span>${scam ? esc(t(scam.name)) : 'Scam'}${r.note ? ' · ' + esc(r.note) : ''}</span></div>
    <button class="icon-btn" data-del="${idx}" aria-label="Delete">${ico('trash')}</button>
  </div>`;
}

function doLookup() {
  const num = normNumber($('#lookup-num').value);
  const box = $('#lookup-result');
  if (!num) { box.innerHTML = ''; return; }
  const matches = getReports().filter((r) => normNumber(r.number) === num);
  if (matches.length) {
    box.innerHTML = verdictCard('danger', `Reported ${matches.length} time${matches.length > 1 ? 's' : ''} on this phone`,
      'This number has been flagged as a scam here. Do not send money or share codes.', '');
  } else {
    box.innerHTML = verdictCard('clear', 'Not in your reports',
      'That does not mean it is safe — only that no one has flagged it on this phone. Stay careful.', '');
  }
}

function doReport() {
  const number = $('#rep-num').value.trim();
  if (!number) { $('#rep-num').focus(); return; }
  const reports = getReports();
  reports.push({ number, type: $('#rep-type').value, note: $('#rep-note').value.trim(), ts: Date.now() });
  saveReports(reports);
  renderReport();
}

/* ============================================================
   HELP
   ============================================================ */
function renderHelp() {
  $('#view-help').innerHTML = `
    <h1 class="h-title">${esc(t(UI.helpTitle))}</h1>
    <ol class="steps">
      ${EMERGENCY.map((s) => `<li>${esc(t(s))}</li>`).join('')}
    </ol>
    <h2 class="sec">Official contacts</h2>
    <div class="contacts">
      ${CONTACTS.map(contactCard).join('')}
    </div>
    <p class="fineprint">${ico('info')} SikaSafe is an independent public-safety tool, not affiliated with any network, bank, or agency. Always verify contacts on your provider’s official materials.</p>`;
}

function contactCard(c) {
  const lines = c.lines.map((l) => {
    const href = l.tel ? `tel:${l.tel}` : l.wa ? `https://wa.me/${l.wa}` : l.mail ? `mailto:${l.mail}` : null;
    const icon = l.tel ? 'phone' : l.wa ? 'whatsapp' : 'mail';
    const inner = `${ico(icon, 'ic sm')} <span>${esc(l.label)}: <b>${esc(l.value)}</b></span>`;
    return href ? `<a class="cline" href="${href}">${inner}</a>` : `<span class="cline">${inner}</span>`;
  }).join('');
  return `<div class="contact ${c.primary ? 'primary' : ''}">
    <b>${esc(c.name)}</b>${c.note ? `<p class="cnote">${esc(t(c.note))}</p>` : ''}${lines}</div>`;
}

/* ---------- share ---------- */
async function shareRules() {
  const text = 'SikaSafe — 7 rules to guard your MoMo:\n\n' +
    RULES.map((r, i) => `${i + 1}. ${t(r.title)}`).join('\n') +
    '\n\nNever share your PIN or OTP. Report fraud to CSA: call/SMS 292.';
  try {
    if (navigator.share) { await navigator.share({ title: 'SikaSafe', text }); return; }
  } catch {}
  try { await navigator.clipboard.writeText(text); toast('Rules copied — paste into WhatsApp'); }
  catch { toast('Could not share on this device'); }
}

let toastT;
function toast(msg) {
  let el = $('#toast');
  el.textContent = msg; el.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(() => { el.hidden = true; }, 2600);
}

/* ---------- boot ---------- */
function renderAll() {
  renderLangSwitch();
  const tag = $('#tagline');
  if (tag) tag.textContent = t(UI.tagline);
  document.querySelectorAll('.navbtn').forEach((b) => {
    b.querySelector('.navlabel').textContent = t(UI.nav[b.dataset.view]);
  });
  renderCheck(); renderLearn(); renderReport(); renderHelp();
  setView(window.SikaState.view);
}

function init() {
  document.querySelectorAll('.navbtn').forEach((b) =>
    b.addEventListener('click', () => setView(b.dataset.view)));
  renderAll();
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
}

document.addEventListener('DOMContentLoaded', init);
