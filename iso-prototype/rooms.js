// Reference code from the room lab (a browser demo). It is a prototype, not the final module.
// Part 1: shape functions and the room generator (port to Python in stage/arena.py).
// Part 2: the isometric room renderer, with the wall cut rule (port to TypeScript in stage/web/src).
// See isometric-view.md, sections "Room shapes" and "Geometry".
// Needed from the demo page: `floors`, `walls` (tile images), `col` (a prop picture), `act` (actor pictures), `ogre`, HW = 32, HH = 16.

  const makeRng = seed => { let h = 2166136261; for (const ch of String(seed)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619); let a = h >>> 0; return () => { a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; };
  const ri = (r, a, b) => a + Math.floor(r() * (b - a + 1));
  const mk = (w, h, f) => Array.from({ length: h }, (_, y) => Array.from({ length: w }, (_, x) => !!f(x, y)));
  const SHAPES = {
    rect: (w, h) => mk(w, h, () => 1),
    L: (w, h, r) => { const cw = ri(r, w * .4, w * .55), ch = ri(r, h * .4, h * .6), sx = r() < .5 ? 0 : w - cw, sy = r() < .5 ? 0 : h - ch; return mk(w, h, (x, y) => !(x >= sx && x < sx + cw && y >= sy && y < sy + ch)); },
    T: (w, h) => { const cw = Math.round(w * .3), ch = Math.round(h * .55); return mk(w, h, (x, y) => !(y < ch && (x < cw || x >= w - cw))); },
    cross: (w, h) => { const cw = Math.round(w * .3), ch = Math.round(h * .3); return mk(w, h, (x, y) => !((x < cw || x >= w - cw) && (y < ch || y >= h - ch))); },
    nave: (w, h, r) => { const t = Math.round(w * .5), tw = Math.max(3, Math.round(w * .2)), nh = Math.max(3, Math.round(h * .38)), ty = Math.round((h - nh) / 2); return mk(w, h, (x, y) => (y >= ty && y < ty + nh) || (x >= t && x < t + tw)); },
    U: (w, h) => { const nw = Math.round(w * .34), nd = Math.round(h * .58), sx = Math.round((w - nw) / 2); return mk(w, h, (x, y) => !(x >= sx && x < sx + nw && y < nd)); },
    H: (w, h) => { const nw = Math.round(w * .34), nd = Math.round(h * .38), sx = Math.round((w - nw) / 2); return mk(w, h, (x, y) => !(x >= sx && x < sx + nw && (y < nd || y >= h - nd))); },
    octagon: (w, h) => { const c = Math.floor(Math.min(w, h) / 3); return mk(w, h, (x, y) => Math.min(x + y, w - 1 - x + y, x + h - 1 - y, w - 1 - x + h - 1 - y) >= c); },
    diamond: (w, h) => mk(w, h, (x, y) => Math.abs(x + .5 - w / 2) / (w / 2) + Math.abs(y + .5 - h / 2) / (h / 2) <= 1),
    ellipse: (w, h) => mk(w, h, (x, y) => ((x + .5 - w / 2) / (w / 2)) ** 2 + ((y + .5 - h / 2) / (h / 2)) ** 2 <= 1),
    ring: (w, h) => { const rad = Math.min(w, h) * .22; return mk(w, h, (x, y) => ((x + .5 - w / 2) / (w / 2)) ** 2 + ((y + .5 - h / 2) / (h / 2)) ** 2 <= 1 && Math.hypot(x + .5 - w / 2, (y + .5 - h / 2) * w / h) > rad); },
    twin: (w, h, r) => { const a = Math.round(w * .38), h1 = ri(r, h * .6, h), h2 = ri(r, h * .6, h), cy = Math.round(h / 2) + ri(r, -1, 1); return mk(w, h, (x, y) => (x < a && y >= (h - h1) / 2 && y < (h + h1) / 2) || (x >= w - a && y >= (h - h2) / 2 && y < (h + h2) / 2) || (x >= a && x < w - a && (y === cy || y === cy + 1))); },
    zigzag: (w, h) => { const t = Math.max(3, Math.round(h / 3)), v = Math.round(w * .66); return mk(w, h, (x, y) => (x < v && y < t) || (x >= v - t && x < v) || (x >= v - t && y >= h - t)); },
    dogleg: (w, h, r) => { const a = Math.round(w * .62), b = Math.round(h * .62); return mk(w, h, (x, y) => (x < a && y < b) || (x >= w - a && y >= h - b)); },
    blob: (w, h, r) => { const cs = Array.from({ length: ri(r, 4, 6) }, () => [r() * w, r() * h, Math.min(w, h) * (.25 + r() * .22)]); return mk(w, h, (x, y) => cs.some(([cx, cy, rad]) => Math.hypot(x + .5 - cx, y + .5 - cy) <= rad)); },
    cave: (w, h, r) => { let g = mk(w, h, (x, y) => x > 0 && y > 0 && x < w - 1 && y < h - 1 && r() < .57); for (let i = 0; i < 4; i++) g = mk(w, h, (x, y) => { let n = 0; for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) n += g[y + b]?.[x + a] ? 1 : 0; return n >= 5; }); return g; },
  };
  const SIZES = { S: [[9, 12], [7, 9]], M: [[14, 18], [9, 12]], L: [[20, 26], [13, 17]] };
  const NAMES = { twin: 'twin rooms', nave: 'nave and transept', hall: 'long hall' };
  const ORDER = ['rect', 'hall', 'L', 'T', 'cross', 'nave', 'U', 'H', 'octagon', 'diamond', 'ellipse', 'ring', 'twin', 'zigzag', 'dogleg', 'blob', 'cave'];
  function biggest(g) {
    const h = g.length, w = g[0].length, seen = mk(w, h, () => 0); let best = [];
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (g[y][x] && !seen[y][x]) {
      const comp = [[x, y]], q = [[x, y]]; seen[y][x] = true;
      while (q.length) { const [cx, cy] = q.pop(); for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) { const nx = cx + dx, ny = cy + dy; if (g[ny]?.[nx] && !seen[ny][nx]) { seen[ny][nx] = true; comp.push([nx, ny]); q.push([nx, ny]); } } }
      if (comp.length > best.length) best = comp;
    }
    return best;
  }
  function genRoom(name, seed, sizeKey, turn) {
    for (let t = 0; t < 60; t++) {
      const r = makeRng(`${name}:${seed}:${t}`), cls = SIZES[sizeKey === 'any' ? 'SML'[ri(r, 0, 2)] : sizeKey];
      let w = ri(r, ...cls[0]), h = ri(r, ...cls[1]);
      if (name === 'hall') { w = ri(r, 20, 27); h = ri(r, 6, 8); }
      if (name === 'cave') { w = Math.max(w, 13); h = Math.max(h, 10); }
      let cells = biggest(SHAPES[name === 'hall' ? 'rect' : name](w, h, r));
      if (cells.length < Math.max(40, .3 * w * h)) continue;
      // random orientation: transpose and/or mirror
      const tr = turn === 'rand' ? ri(r, 0, 7) : 0;
      cells = cells.map(([x, y]) => { if (tr & 1) [x, y] = [y, x]; if (tr & 2) x = -x; if (tr & 4) y = -y; return [x, y]; });
      const x0 = Math.min(...cells.map(c => c[0])), y0 = Math.min(...cells.map(c => c[1]));
      cells = cells.map(([x, y]) => [x - x0 + 1, y - y0 + 1]);
      const W = Math.max(...cells.map(c => c[0])) + 2, H = Math.max(...cells.map(c => c[1])) + 2;
      const grid = Array.from({ length: H }, () => Array(W).fill(' ')); cells.forEach(([x, y]) => grid[y][x] = '.');
      for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (grid[y][x] === ' ') { let n = false; for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) if (grid[y + b]?.[x + a] === '.') n = true; if (n) grid[y][x] = '#'; }
      const fl = (x, y) => grid[y]?.[x] === '.', inner = c => { let n = 0; for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) n += fl(c[0] + a, c[1] + b); return n; };
      const cx = cells.reduce((s, c) => s + c[0], 0) / cells.length, cy = cells.reduce((s, c) => s + c[1], 0) / cells.length, d = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
      const far = (o, list) => list.reduce((b, c) => d(c, o) > d(b, o) ? c : b);
      const A = far([cx, cy], cells), B = far(A, cells); if (d(A, B) < 7) continue;
      const near = (o, n, skip) => cells.filter(c => !skip.some(s => s[0] === c[0] && s[1] === c[1])).sort((a, b) => (d(a, o) - (inner(a) >= 8 ? .6 : 0)) - (d(b, o) - (inner(b) >= 8 ? .6 : 0))).slice(0, n);
      const party = near(A, 2, []), foes = near(B, 3, party), used = [...party, ...foes];
      const props = []; const cand = cells.filter(c => inner(c) === 9 && d(c, A) > 3 && d(c, B) > 3).sort(() => r() - .5);
      for (const c of cand) { if (props.length >= ri(r, 2, 4)) break; if (props.every(p => Math.max(Math.abs(p[0] - c[0]), Math.abs(p[1] - c[1])) > 2)) props.push(c); }
      const open = cells.filter(c => !props.some(p => p[0] === c[0] && p[1] === c[1])), set = new Set(open.map(c => c.join())), seen = new Set([open[0].join()]), q = [open[0]];
      while (q.length) { const [x, y] = q.pop(); for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) { const k = (x + dx) + ',' + (y + dy); if (set.has(k) && !seen.has(k)) { seen.add(k); q.push([x + dx, y + dy]); } } }
      if (seen.size !== open.length) continue;
      return { name: NAMES[name] || name, w: W, h: H, grid: grid.map(r => r.join('')), props, party, foes, floor: cells.length };
    }
  }
  const variant = (x, y, n) => { const h = (Math.imul(x, 374761393) ^ Math.imul(y, 668265263)) >>> 0; const k = ((h ^ (h >>> 13)) >>> 0) % (n * 2); return k < n ? k : 0; };
  function room(r) {
    const WH = 48, top = WH + 64, ox = r.h * HW + 8, W = (r.w + r.h) * HW + 16, H = top + (r.w + r.h) * HH + 36, S = 2;
    const cv = document.createElement('canvas'); cv.width = W * S; cv.height = H * S; cv.style.aspectRatio = `${W} / ${H}`;
    const c = cv.getContext('2d'); c.imageSmoothingEnabled = false; c.setTransform(S, 0, 0, S, 0, 0); c.fillStyle = '#0b0910'; c.fillRect(0, 0, W, H);
    const at = (x, y) => (r.grid[y] || '')[x] || ' ', pr = (x, y) => [ox + (x - y) * HW, top + (x + y) * HH];
    const things = [];
    for (let y = 0; y < r.h; y++) for (let x = 0; x < r.w; x++) if (at(x, y) === '.') { const [px, py] = pr(x, y); c.save(); c.setTransform(S, S * .5, -S, S * .5, S * px, S * py); c.drawImage(floors[variant(x, y, floors.length)], 0, 0, 32.7, 32.7); c.restore(); }
    for (let y = 0; y < r.h; y++) for (let x = 0; x < r.w; x++) if (at(x, y) === '#') {
      const cutIt = at(x - 1, y) === '.' || at(x, y - 1) === '.' || at(x - 1, y - 1) === '.', h = cutIt ? 12 : WH, [px, py] = pr(x, y), tex = walls[variant(x, y, walls.length)];
      things.push({ d: cutIt ? x + y - .4 : -1 + (x + y) * .001, f: () => {
        const face = (m, fx, fy, shade) => { c.save(); c.setTransform(S, S * m, 0, S, S * fx, S * (fy - h)); if (h <= 32) c.drawImage(tex, 0, 0, 32, h, 0, 0, 32, h); else { c.drawImage(tex, 0, 0, 32, 32, 0, h - 32, 32, 32); c.drawImage(tex, 0, 64 - h, 32, h - 32, 0, 0, 32, h - 32); } c.fillStyle = `rgba(8,4,16,${shade})`; c.fillRect(0, 0, 32, h); c.restore(); };
        if (at(x, y + 1) !== '#') face(.5, px - HW, py + HH, .22);
        if (at(x + 1, y) !== '#') face(-.5, px, py + 2 * HH, .42);
        c.save(); c.setTransform(S, S * .5, -S, S * .5, S * px, S * (py - h)); c.drawImage(tex, 0, 0, 32, 32, 0, 0, 32.7, 32.7); c.fillStyle = 'rgba(255,240,220,.16)'; c.fillRect(0, 0, 32.7, 32.7); c.restore();
      } });
    }
    const sprite = (img, x, y, ring, scale = 1, face) => things.push({ d: x + y + .01, f: () => {
      c.setTransform(S, 0, 0, S, 0, 0); const [px, py] = pr(x, y), fx = px, fy = py + HH;
      if (ring) { c.fillStyle = ring; c.beginPath(); c.ellipse(fx, fy, 15, 6, 0, 0, 7); c.fill(); }
      if (scale > 1) c.drawImage(img, Math.round(fx - img.width * scale / 2), Math.round(fy - img.height * scale + 2), img.width * scale, img.height * scale);
      else c.drawImage(img, Math.round(fx - img.width / 2), Math.round(fy - (ring ? 60 : img.height - 4)));
    } });
    r.props.forEach(([x, y]) => sprite(col, x, y, null));
    r.party.forEach(([x, y], i) => sprite(i ? act.ally : act.hero, x, y, 'rgba(95,208,138,.8)'));
    r.foes.forEach(([x, y], i) => i === 2 ? sprite(ogre, x, y, 'rgba(239,106,90,.8)', 2) : sprite(i ? act.skeletonL : act.goblinL, x, y, 'rgba(239,106,90,.8)'));
    things.sort((a, b) => a.d - b.d).forEach(t => t.f());
    return cv;
  }
