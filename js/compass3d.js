/* ============================================================
   Perch — 3D compass (WebGL via Three.js)
   A glossy extruded needle that sweeps like a compass on a tilted
   dial, with gyro/pointer parallax and swappable DESIGNS (skins).
   Degrades to the flat SVG arrow when WebGL/Three is unavailable
   or reduce-motion is set. Global: window.Compass3D
   ============================================================ */
(function () {
  'use strict';

  const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ARRIVAL = 0xe79a45, ARRIVAL_EMIS = 0x6b3c10;

  let renderer, scene, camera, dial, needle, mesh, mat, raf = 0;
  let curAngle = 0, tgtAngle = 0;
  let tiltX = 0, tiltY = 0, tTiltX = 0, tTiltY = 0;
  let arrival = false, arrivalMix = 0, t0 = 0;
  let design = { base: 0x32a98f, emissive: 0x0e3a31, metalness: 0.35, roughness: 0.32, shape: 'kite' };

  // ----- needle shapes (pointing +Y) -----
  function shapePath(name) {
    const s = new THREE.Shape();
    if (name === 'dart') {
      s.moveTo(0, 1.28); s.lineTo(0.40, -0.55); s.lineTo(0, -0.98); s.lineTo(-0.40, -0.55);
    } else if (name === 'diamond') {
      s.moveTo(0, 1.15); s.lineTo(0.52, 0); s.lineTo(0, -1.15); s.lineTo(-0.52, 0);
    } else if (name === 'chevron') {
      s.moveTo(0, 1.12); s.lineTo(0.72, -0.46); s.lineTo(0.70, -0.86); s.lineTo(0, -0.50);
      s.lineTo(-0.70, -0.86); s.lineTo(-0.72, -0.46);
    } else if (name === 'needle') {
      s.moveTo(0, 1.25); s.lineTo(0.16, 0); s.lineTo(0, -1.05); s.lineTo(-0.16, 0);
    } else if (name === 'spear') {
      s.moveTo(0, 1.32); s.lineTo(0.30, 0.50); s.lineTo(0.13, 0.34); s.lineTo(0.13, -1.0);
      s.lineTo(-0.13, -1.0); s.lineTo(-0.13, 0.34); s.lineTo(-0.30, 0.50);
    } else if (name === 'leaf') {
      s.moveTo(0, 1.22); s.quadraticCurveTo(0.55, 0.15, 0, -1.05); s.quadraticCurveTo(-0.55, 0.15, 0, 1.22);
    } else if (name === 'star') {
      s.moveTo(0, 1.12); s.lineTo(0.18, 0.18); s.lineTo(0.62, 0); s.lineTo(0.18, -0.18);
      s.lineTo(0, -1.12); s.lineTo(-0.18, -0.18); s.lineTo(-0.62, 0); s.lineTo(-0.18, 0.18);
    } else { // kite (default navigation arrow)
      s.moveTo(0, 1.12); s.lineTo(0.72, -0.78); s.lineTo(0, -0.30); s.lineTo(-0.72, -0.78);
    }
    s.closePath();
    return s;
  }

  function buildMesh() {
    if (mesh) { needle.remove(mesh); mesh.geometry.dispose(); }
    const geo = new THREE.ExtrudeGeometry(shapePath(design.shape), {
      depth: 0.34, bevelEnabled: true, bevelThickness: 0.08, bevelSize: 0.07, bevelSegments: 3, steps: 1,
    });
    geo.center();
    mat = new THREE.MeshStandardMaterial({
      color: design.base, emissive: design.emissive, metalness: design.metalness, roughness: design.roughness,
      emissiveIntensity: design.emissiveIntensity || 1,
    });
    mesh = new THREE.Mesh(geo, mat);
    needle.add(mesh);
  }

  function init(canvas) {
    if (!window.THREE) return false;
    try { renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true }); }
    catch (e) { return false; }
    if (!renderer || !renderer.getContext()) return false;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(0, 0, 5.4); camera.lookAt(0, 0, 0);

    dial = new THREE.Group(); dial.rotation.x = -0.46; scene.add(dial);
    needle = new THREE.Group(); dial.add(needle);
    buildMesh();

    const disc = new THREE.Mesh(
      new THREE.CircleGeometry(1.45, 48),
      new THREE.MeshStandardMaterial({ color: 0xffffff, transparent: true, opacity: 0.06, roughness: 1 })
    );
    disc.position.z = -0.28; dial.add(disc);

    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 1.15); key.position.set(-3, 5, 5); scene.add(key);
    const rim = new THREE.DirectionalLight(0x9fe9d6, 0.6); rim.position.set(3, -2, 2); scene.add(rim);
    const pt = new THREE.PointLight(0xffffff, 0.5); pt.position.set(0, 1.5, 3); scene.add(pt);

    resize(); Compass3D.available = true; loop();
    return true;
  }

  function resize() {
    if (!renderer) return;
    const c = renderer.domElement;
    const w = c.clientWidth || 240, h = c.clientHeight || 240;
    if (c.width !== w || c.height !== h) {
      renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
    }
  }

  const lerp = (a, b, n) => a + (b - a) * n;

  function loop(ts) {
    raf = requestAnimationFrame(loop);
    if (!t0) t0 = ts || 0;
    const t = ((ts || 0) - t0) / 1000;
    resize();

    let d = ((tgtAngle - curAngle + 540) % 360) - 180;
    curAngle += d * (reduceMotion ? 1 : 0.16);
    needle.rotation.z = -curAngle * Math.PI / 180;

    tiltX = lerp(tiltX, tTiltX, 0.08); tiltY = lerp(tiltY, tTiltY, 0.08);
    dial.rotation.x = -0.46 + tiltY * 0.18 + (reduceMotion ? 0 : Math.sin(t * 1.1) * 0.015);
    dial.rotation.y = tiltX * 0.22;
    needle.position.y = reduceMotion ? 0 : Math.sin(t * 1.6) * 0.05;
    needle.position.z = reduceMotion ? 0 : Math.sin(t * 1.6 + 1) * 0.03;

    arrivalMix = lerp(arrivalMix, arrival ? 1 : 0, 0.12);
    mat.color.lerpColors(new THREE.Color(design.base), new THREE.Color(ARRIVAL), arrivalMix);
    mat.emissive.lerpColors(new THREE.Color(design.emissive), new THREE.Color(ARRIVAL_EMIS), arrivalMix);
    needle.scale.setScalar(1 + (arrival ? Math.sin(t * 4) * 0.04 + 0.06 : 0));

    renderer.render(scene, camera);
  }

  window.Compass3D = {
    available: false,
    init, resize,
    setAngle(deg) { tgtAngle = ((deg % 360) + 360) % 360; },
    setTilt(x, y) { tTiltX = Math.max(-1, Math.min(1, x)); tTiltY = Math.max(-1, Math.min(1, y)); },
    setArrival(v) { arrival = !!v; },
    setDesign(d) {
      const shapeChanged = d.shape && d.shape !== design.shape;
      design = Object.assign({}, design, d);
      if (!mat) return;
      if (shapeChanged) buildMesh();
      else { mat.metalness = design.metalness; mat.roughness = design.roughness; mat.emissiveIntensity = design.emissiveIntensity || 1; }
    },
    stop() { if (raf) cancelAnimationFrame(raf); },
  };
})();
