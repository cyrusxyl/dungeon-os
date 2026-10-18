// Reference code from the isometric prop tuner (a browser demo). It is a prototype, not the final module.
// It draws one prop as a chain of vertical (V) and horizontal (H) bands, or upright, on a 2x canvas.
// Port it to stage/web/src/lib (TypeScript). See isometric-view.md, section "Prop poses".
// Needed from the demo page: `atlas` (an image with every prop), `p.r` = [x, y, w, h] of a prop in it,
// `floors` (floor tile images), constants SIDE = .62, TOPL = 1.22, SLAB = .6, and the helper `clamp`.
// `u` = { face: 'sw' | 'se', start: 'V' | 'H' | 'U', n: band count, split: [rows], band: [[size, thickness], ...], ws: width }.
const HW = 32, HH = 16, SIDE = .62, TOPL = 1.22, SLAB = .6
const clamp = (v, a, b) => Math.max(a, Math.min(b, v))

  const info = p => {
    if (p._i) return p._i;
    const [rx, ry, w, h] = p.r, cv = document.createElement('canvas'); cv.width = w; cv.height = h;
    const c = cv.getContext('2d'); c.drawImage(atlas, rx, ry, w, h, 0, 0, w, h);
    const id = c.getImageData(0, 0, w, h), cnt = new Map();
    for (let i = 0; i < w * h; i++) { const [r, g, b, a] = id.data.slice(i * 4, i * 4 + 4); if (a < 200 || .3 * r + .59 * g + .11 * b < 45) continue; const k = ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3); cnt.set(k, (cnt.get(k) || 0) + 1); }
    let best = null, n = 0; for (const [k, v] of cnt) if (v > n) { n = v; best = k; }
    const color = best == null ? [120, 90, 70] : [((best >> 10) & 31) << 3 | 4, ((best >> 5) & 31) << 3 | 4, (best & 31) << 3 | 4];
    return p._i = { cv, id, w, h, color };
  };
  const shade = (c, f) => c.map(v => clamp(Math.round(v * f), 0, 255));
  // the picture's outline (rows r0..r1) in one colour; mode 'top' keeps only the first two rows of each column
  function tint(i, rgb, mode, r0 = 0, r1 = i.h) {
    const cv = document.createElement('canvas'); cv.width = i.w; cv.height = i.h; const c = cv.getContext('2d'), out = c.createImageData(i.w, i.h);
    for (let x = 0; x < i.w; x++) { let ty = -1; for (let y = r0; y < r1; y++) { if (i.id.data[(y * i.w + x) * 4 + 3] > 128) { if (ty < 0) ty = y; if (mode === 'sil' || y <= ty + 1) { const o = (y * i.w + x) * 4; out.data[o] = rgb[0]; out.data[o + 1] = rgb[1]; out.data[o + 2] = rgb[2]; out.data[o + 3] = 255; } } } }
    c.putImageData(out, 0, 0); return cv;
  }
  const base = (cv, cw, ch, cx, cy) => {
    const c = cv.getContext('2d'); c.imageSmoothingEnabled = false; c.setTransform(2, 0, 0, 2, 0, 0); c.fillStyle = '#0b0910'; c.fillRect(0, 0, cw, ch);
    for (let i = -2; i <= 2; i++) for (let j = -2; j <= 2; j++) { c.save(); c.setTransform(2, 1, -2, 1, 2 * (cx + (i - j) * HW), 2 * (cy - HH + (i + j) * HH)); c.drawImage(floors[(i + 3 + (j + 3) * 5) % floors.length], 0, 0, 32.6, 32.6); c.restore(); }
    return c;
  };
  const T = (o, a, b, c, d, e, f) => o.setTransform(2 * a, 2 * b, 2 * c, 2 * d, 2 * e, 2 * f);   // logical matrix onto the 2x canvas
  const stage = (cv, cw, ch, cx, cy, face, draw) => {
    const c = base(cv, cw, ch, cx, cy), off = document.createElement('canvas'); off.width = cw * 2; off.height = ch * 2;
    const o = off.getContext('2d'); o.imageSmoothingEnabled = false; const k = draw(o);
    c.setTransform(face === 'se' ? -1 : 1, 0, 0, 1, face === 'se' ? 4 * cx : 0, 0); c.drawImage(off, 0, 0);
    if (k < 1) { c.setTransform(2, 0, 0, 2, 0, 0); c.font = '9px monospace'; c.fillStyle = '#a79cc0'; c.fillText('×' + k.toFixed(2), cw - 36, ch - 5); }
  };

  // ---- the band chain. V = vertical band hangs down from the current edge. H = horizontal band lies forward from it.
  const modeOf = u => u.start === 'U' ? 'U' : Array.from({ length: u.n }, (_, j) => (j % 2 === 0) === (u.start === 'V') ? 'V' : 'H').join('');
  function bands(cv, p, u, cw = CW, ch = CH, cx = CX, cy = CY) {
    if (u.start === 'U') { const i = info(p), k = Math.min(1, (cw - 16) / i.w, (ch - 24) / i.h); return stage(cv, cw, ch, cx, cy, u.face, o => { o.setTransform(2 * k, 0, 0, 2 * k, 2 * (cx - i.w * k / 2), 2 * (cy + 4 - i.h * k)); o.drawImage(i.cv, 0, 0); return k; }); }
    const i = info(p), { w, h } = i, ws = u.ws, mode = modeOf(u), nb = mode.length;
    const cutAt = []; { let prev = 0; u.split.slice(0, nb - 1).forEach((v, j) => { prev = clamp(v, prev + 2, h - 2 * (nb - 1 - j)); cutAt.push(prev); }); }
    const segs = [0, ...cutAt].map((a0, j) => ({ rs: a0, re: [...cutAt, h][j], t: mode[j], bs: u.band[j][0], bt: u.band[j][1] }));
    const Vpx = segs.filter(g => g.t === 'V').reduce((t, g) => t + (g.re - g.rs) * g.bs, 0), Hpx = segs.filter(g => g.t === 'H').reduce((t, g) => t + (g.re - g.rs) * g.bs, 0);
    const vt = Math.max(0, ...segs.filter(g => g.t === 'V').map(g => g.bt)), ht = Math.max(0, ...segs.filter(g => g.t === 'H').map(g => g.bt));
    stage(cv, cw, ch, cx, cy, u.face, o => {
      const W = w * ws, span = W + Hpx + vt, k = Math.min(1, (cw - 20) / span, (ch - 30) / (Vpx + .5 * span + ht));
      const Ox = cx - k * W / 2 + k * Hpx / 2 - k * vt / 2, Oy = cy - .25 * k * W - .25 * k * Hpx + .25 * k * vt + 4;
      let z = Vpx, vp = 0, first = true;
      const colA = shade(i.color, SIDE), colT = shade(i.color, TOPL), colS = shade(i.color, SLAB), colB = shade(i.color, Math.min(1.4, SLAB * 1.3));
      const made = [], art = [];
      for (const g of segs) {
        const n = g.re - g.rs, src = img => o.drawImage(img, 0, g.rs, w, n, 0, g.rs, w, n), uo = 0;
        if (g.t === 'V') {
          const e = Ox - k * vp, f = Oy + .5 * k * vp - k * z - k * g.bs * g.rs, isFirst = first;
          const sil = tint(i, colA, 'sil', g.rs, g.re), top = isFirst ? tint(i, colT, 'top', g.rs, g.re) : null;
          made.push(() => { for (const img of top ? [sil, top] : [sil]) for (let t = g.bt; t >= 1; t--) { T(o, k * ws, .5 * k * ws, 0, k * g.bs, e + t * k, f - t * k / 2); src(img); } });
          art.push(() => { T(o, k * ws, .5 * k * ws, 0, k * g.bs, e, f); src(i.cv); });
          z -= n * g.bs;
        } else {
          const D = g.bs, e = Ox - k * vp + k * D * g.rs, f = Oy + .5 * k * vp - .5 * k * D * g.rs - k * z, cxS = Ox + k * W / 2 - k * (vp + n * D / 2);
          const A = tint(i, colS, 'sil', g.rs, g.re), B = tint(i, colB, 'sil', g.rs, g.re);
          const slab = (img, dy = 0) => { T(o, k * ws, .5 * k * ws, -k * D, .5 * k * D, e, f + dy); src(img); };
          made.push(() => { for (let t = g.bt * k; t > 0; t -= .5) slab(A, t); o.save(); o.setTransform(1, 0, 0, 1, 0, 0); o.beginPath(); o.rect(0, 0, 2 * cxS, 2 * ch); o.clip(); for (let t = g.bt * k; t > 0; t -= .5) slab(B, t); o.restore(); });
          art.push(() => slab(i.cv));
          vp += n * D;
        }
        first = false;
      }
      made.forEach(f => f()); art.forEach(f => f());
      return k;
    });
  }
