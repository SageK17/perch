/* ============================================================
   Perch — cinematic FX: drifting glow-particle background +
   confetti bursts. Lightweight canvas, respects reduce-motion.
   Global: window.FX
   ============================================================ */
(function () {
  'use strict';
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const COLORS = ['#5fe0c8', '#2f7d6b', '#e8a04c', '#9fe9d6', '#ffffff'];
  let dpr = Math.min(window.devicePixelRatio || 1, 2);

  /* ---------- Background particle field ---------- */
  let bg, bgx, parts = [], braf = 0, bw = 0, bh = 0;
  function sizeBg() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    bw = bg.clientWidth; bh = bg.clientHeight;
    bg.width = bw * dpr; bg.height = bh * dpr;
    bgx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function makeParts() {
    const n = reduce ? 0 : Math.round(Math.min(56, (bw * bh) / 21000));
    parts = Array.from({ length: n }, () => ({
      x: Math.random() * bw, y: Math.random() * bh,
      r: 1.4 + Math.random() * 3.6,
      vy: -(0.10 + Math.random() * 0.42), vx: (Math.random() - 0.5) * 0.18,
      a: 0.10 + Math.random() * 0.26, tw: Math.random() * Math.PI * 2, ts: 0.5 + Math.random() * 1.2,
      c: COLORS[(Math.random() * COLORS.length) | 0],
    }));
  }
  function drawBg(t) {
    braf = requestAnimationFrame(drawBg);
    bgx.clearRect(0, 0, bw, bh);
    for (const p of parts) {
      p.x += p.vx; p.y += p.vy;
      if (p.y < -12) { p.y = bh + 12; p.x = Math.random() * bw; }
      if (p.x < -12) p.x = bw + 12; else if (p.x > bw + 12) p.x = -12;
      const a = p.a * (0.55 + 0.45 * Math.sin(t * 0.001 * p.ts + p.tw));
      bgx.beginPath();
      bgx.fillStyle = p.c; bgx.globalAlpha = a;
      bgx.shadowColor = p.c; bgx.shadowBlur = p.r * 3.2;
      bgx.arc(p.x, p.y, p.r, 0, 7); bgx.fill();
    }
    bgx.globalAlpha = 1; bgx.shadowBlur = 0;
  }
  function initBackground(canvas) {
    bg = canvas; bgx = canvas.getContext('2d');
    sizeBg(); makeParts();
    window.addEventListener('resize', () => { sizeBg(); makeParts(); });
    if (reduce) {
      for (let i = 0; i < 16; i++) {
        bgx.fillStyle = '#2f7d6b'; bgx.globalAlpha = 0.10;
        bgx.beginPath(); bgx.arc(Math.random() * bw, Math.random() * bh, 1.5 + Math.random() * 3, 0, 7); bgx.fill();
      }
      bgx.globalAlpha = 1;
      return;
    }
    drawBg(0);
  }

  /* ---------- Confetti burst ---------- */
  let bu, bux, conf = [], craf = 0, cw = 0, ch = 0;
  function sizeBurst() { cw = bu.clientWidth; ch = bu.clientHeight; bu.width = cw * dpr; bu.height = ch * dpr; bux.setTransform(dpr, 0, 0, dpr, 0, 0); }
  function confettiBurst(x, y) {
    if (reduce || !bu) return;
    if (typeof x !== 'number') x = cw / 2;
    if (typeof y !== 'number') y = ch * 0.4;
    for (let i = 0; i < 96; i++) {
      const ang = Math.random() * Math.PI * 2, sp = 3 + Math.random() * 7.5;
      conf.push({ x, y, vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp - 3.5, r: 3 + Math.random() * 5,
        c: COLORS[(Math.random() * COLORS.length) | 0], rot: Math.random() * 6, vr: (Math.random() - 0.5) * 0.4, life: 1 });
    }
    if (!craf) craf = requestAnimationFrame(drawBurst);
  }
  function drawBurst() {
    bux.clearRect(0, 0, cw, ch);
    let alive = 0;
    for (const p of conf) {
      if (p.life <= 0) continue; alive++;
      p.vy += 0.17; p.vx *= 0.99; p.x += p.vx; p.y += p.vy; p.rot += p.vr; p.life -= 0.011;
      bux.save(); bux.translate(p.x, p.y); bux.rotate(p.rot); bux.globalAlpha = Math.max(0, p.life);
      bux.fillStyle = p.c; bux.fillRect(-p.r / 2, -p.r / 2, p.r, p.r * 0.62); bux.restore();
    }
    if (alive > 0) craf = requestAnimationFrame(drawBurst);
    else { conf = []; craf = 0; bux.clearRect(0, 0, cw, ch); }
  }
  function initBurst(canvas) { bu = canvas; bux = canvas.getContext('2d'); sizeBurst(); window.addEventListener('resize', sizeBurst); }

  window.FX = { initBackground, initBurst, confettiBurst, reduce };
})();
