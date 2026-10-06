/* Ardzy - Simulation: run the project's Verilog testbench on the PC (Icarus Verilog) and look at the waves.
   Bottom tab "Simulation": testbench, run time, Simulate (F6), New testbench; the signals by module on the left,
   the waves on the right: mouse wheel = zoom, drag = move, click = cursor A, Shift+click = cursor B,
   click a bus name = draw it as a curve (analog). Uses app.js (S, $, esc, api, out, showTab, openFile, refreshProjects). */

const SV = { data: null, sel: [], analog: new Set(), radix: 'hex', t0: 0, t1: 1, curA: null, curB: null, filter: '', showMinor: false,
  drag: null, ROW: 26, NAMEW: 210, project: null };

function simFmtTime(units) {                                    // units of the VCD -> "12.5 ns" / "3.2 us" ...
  const ns = units * (SV.data ? SV.data.timescale_ns : 1);
  const a = Math.abs(ns);
  return a >= 1e6 ? +(ns / 1e6).toFixed(3) + ' ms' : a >= 1e3 ? +(ns / 1e3).toFixed(3) + ' us' : +ns.toFixed(3) + ' ns';
}
function simValAt(id, t) {                                      // the value of a signal at time t (binary search)
  const w = SV.data.waves[id];
  if (!w || !w.length) return 'x';
  let lo = 0, hi = w.length / 2 - 1;
  if (t < w[0]) return 'x';
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (w[2 * m] <= t) lo = m; else hi = m - 1; }
  return w[2 * lo + 1];
}
function simBits(v, width) {                                    // VCD extends a shorter value on the left
  if (v.length >= width) return v.slice(-width);
  const pad = v[0] === 'x' || v[0] === 'z' ? v[0] : '0';
  return pad.repeat(width - v.length) + v;
}
function simFmt(v, width, radix) {
  if (width === 1 || /^[0-9.eE+-]+$/.test(v) && v.includes('.')) return v;
  const b = simBits(v, width);
  if (/[xz]/.test(b)) {
    if (radix !== 'hex') return /^x+$/.test(b) ? 'x' : /^z+$/.test(b) ? 'z' : b;
    let h = '';
    for (let i = b.length; i > 0; i -= 4) { const n = b.slice(Math.max(0, i - 4), i); h = (/[xz]/.test(n) ? (n.includes('z') ? 'z' : 'x') : parseInt(n, 2).toString(16)) + h; }
    return h;
  }
  if (radix === 'bin') return b;
  if (radix === 'dec') return BigInt('0b' + b).toString();
  if (radix === 'signed') { let n = BigInt('0b' + b); if (b[0] === '1') n -= 1n << BigInt(width); return n.toString(); }
  return BigInt('0b' + b).toString(16).padStart(Math.ceil(width / 4), '0');
}
function simNum(v, width, signed) {
  const b = simBits(v, width);
  if (/[xz]/.test(b)) return null;
  let n = Number(BigInt('0b' + b));
  if (signed && b[0] === '1') n -= Math.pow(2, width);
  return n;
}

async function simInfo() {
  if (!S.project) { $('simTb').innerHTML = '<option value="">(choose a project)</option>'; return; }
  const r = await api('/api/sim/info?project=' + encodeURIComponent(S.project));
  if (!r.ok) return;
  const cur = $('simTb').value;
  $('simTb').innerHTML = r.testbenches.length ? r.testbenches.map(t => `<option ${t === cur ? 'selected' : ''}>${esc(t)}</option>`).join('')
    : '<option value="">(no testbench yet)</option>';
  $('simState').textContent = r.testbenches.length ? '' : (r.design.length ? `Design top: ${r.top}. Press "New testbench" to make one.` : 'This project has no Verilog files.');
  if (SV.project !== S.project) { SV.project = S.project; SV.data = null; simLoad(true); }
}
async function simRun() {
  if (!S.project) return out('Choose a project first.', 'warn');
  await saveProject(S.project);
  showTab('output');
  const r = await api('/api/sim/run', { project: S.project, tb: $('simTb').value, ns: +$('simTime').value });
  if (!r.ok) out(r.out, 'err');
}
async function simNewTb() {
  if (!S.project) return out('Choose a project first.', 'warn');
  const r = await api('/api/sim/newtb', { project: S.project });
  if (!r.ok) return out(r.out, 'err');
  await refreshProjects();
  await openFile(S.project, r.name);
  simInfo();
}
async function simLoad(quiet) {
  if (!S.project) return;
  const r = await api('/api/sim/waves?project=' + encodeURIComponent(S.project));
  if (!r.ok) { SV.data = null; if (!quiet) out(r.out, 'warn'); simLayout(); return; }
  const keep = SV.data && SV.data.tb === r.tb ? SV.sel.filter(id => r.signals.some(s => s.name === id)) : null;
  SV.data = r;
  SV.byName = Object.fromEntries(r.signals.map(s => [s.name, s]));
  if (keep && keep.length) SV.sel = keep;
  else {                                                        // first look: from the top down, each name once (a port seen above is the same wire)
    const seen = new Set(), depth = s => s.scope.split('.').length;
    SV.sel = r.signals.filter(s => !s.minor).sort((a, b) => depth(a) - depth(b))
      .filter(s => { const k = s.short.replace(/\[.*$/, ''); if (seen.has(k)) return false; seen.add(k); return true; })
      .slice(0, 24).map(s => s.name);
  }
  SV.t0 = 0; SV.t1 = Math.max(1, r.end); SV.curA = SV.curB = null;
  if (!quiet) showTab('simulation');
  simLayout();
}

function simLayout() {
  const d = SV.data;
  $('simInfo').textContent = d ? `${d.tb} · ${d.signals.length} signals · ${simFmtTime(d.end)}${d.cut ? ' (cut: too many changes)' : ''} · run at ${d.when}` : '';
  if (!d) {
    $('simList').innerHTML = '';
    $('simWaves').hidden = true;
    $('simEmpty').hidden = false;
    return;
  }
  $('simWaves').hidden = false; $('simEmpty').hidden = true;
  simList();
  simDraw();
}
function simList() {
  const d = SV.data, f = SV.filter.toLowerCase();
  const groups = {};
  d.signals.filter(s => (SV.showMinor || !s.minor) && (!f || s.name.toLowerCase().includes(f))).forEach(s => (groups[s.scope] = groups[s.scope] || []).push(s));
  $('simList').innerHTML = Object.entries(groups).map(([sc, list]) => `<div class="sl-scope" title="${esc(sc)}">${esc(sc.split('.').slice(-1)[0])}<span class="hint"> ${esc(sc)}</span></div>` +
    list.map(s => `<label class="sl-sig"><input type="checkbox" data-n="${esc(s.name)}" ${SV.sel.includes(s.name) ? 'checked' : ''}>
      <span>${esc(s.short)}</span>${s.width > 1 ? `<span class="hint">${s.width}</span>` : ''}</label>`).join('')).join('') || '<p class="hint">Nothing matches.</p>';
  $('simList').querySelectorAll('[data-n]').forEach(c => c.onchange = () => {
    const n = c.dataset.n;
    SV.sel = c.checked ? SV.sel.concat(n) : SV.sel.filter(x => x !== n);
    simDraw();
  });
}

function simDraw() {
  const cv = $('simCanvas'), d = SV.data;
  if (!cv || !d || !cv.clientWidth) return;
  const dpr = window.devicePixelRatio || 1, ROW = SV.ROW, AX = 26, NW = SV.NAMEW;
  const rows = SV.sel.map(n => SV.byName[n]).filter(Boolean);
  const hCss = AX + rows.reduce((h, s) => h + (SV.analog.has(s.name) ? ROW * 3 : ROW), 0) + 8;
  cv.style.height = Math.max(hCss, 120) + 'px';
  cv.width = Math.round(cv.clientWidth * dpr); cv.height = Math.round(Math.max(hCss, 120) * dpr);
  const g = cv.getContext('2d'), css = getComputedStyle(document.body);
  const col = { text: css.getPropertyValue('--text'), muted: css.getPropertyValue('--muted'), line: css.getPropertyValue('--line'),
    wave: css.getPropertyValue('--accent').trim() || '#2fbf6c', bus: '#4f8fe0', x: '#e05050', z: '#d0a020', bg: css.getPropertyValue('--code-bg') };
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  const W = cv.clientWidth, X = t => NW + (t - SV.t0) / (SV.t1 - SV.t0) * (W - NW - 8);
  g.fillStyle = col.bg; g.fillRect(0, 0, W, cv.clientHeight);
  // the time axis
  g.font = '11px Segoe UI'; g.fillStyle = col.muted; g.strokeStyle = col.line; g.lineWidth = 1;
  const span = SV.t1 - SV.t0, raw = span / 8, p10 = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 5, 10].map(k => k * p10).find(s => s >= raw) || p10 * 10;
  for (let t = Math.ceil(SV.t0 / step) * step; t <= SV.t1; t += step) {
    const x = Math.round(X(t)) + .5;
    g.beginPath(); g.moveTo(x, AX - 6); g.lineTo(x, cv.clientHeight); g.globalAlpha = .35; g.stroke(); g.globalAlpha = 1;
    g.fillText(simFmtTime(t), x + 3, 14);
  }
  // the rows
  let y = AX;
  const tA = SV.curA !== null ? SV.curA : null;
  for (const s of rows) {
    const an = SV.analog.has(s.name), h = an ? ROW * 3 : ROW, w = d.waves[s.id] || [];
    g.fillStyle = col.text; g.font = '600 12.5px Cascadia Mono, Consolas, monospace';
    const label = s.short.length > 22 ? s.short.slice(0, 21) + '…' : s.short;
    g.fillText(label, 8, y + 15);
    if (tA !== null) {                                       // the value at cursor A next to the name
      g.font = '12px Cascadia Mono, Consolas, monospace'; g.fillStyle = col.wave;
      const v = simFmt(simValAt(s.id, tA), s.width, SV.radix);
      g.textAlign = 'right'; g.fillText(v.length > 12 ? v.slice(0, 11) + '…' : v, NW - 8, y + 15); g.textAlign = 'left';
    }
    g.strokeStyle = col.line; g.globalAlpha = .5; g.beginPath(); g.moveTo(0, y + h - .5); g.lineTo(W, y + h - .5); g.stroke(); g.globalAlpha = 1;
    // the changes inside the window (plus the one before it)
    let i0 = 0;
    while (i0 + 2 < w.length && w[i0 + 2] <= SV.t0) i0 += 2;
    const top = y + 5, bot = y + h - 6;
    if (s.width === 1) {
      for (let i = i0; i < w.length; i += 2) {
        const ta = Math.max(w[i], SV.t0), tb = i + 2 < w.length ? Math.min(w[i + 2], SV.t1) : SV.t1;
        if (ta > SV.t1) break;
        const xa = X(ta), xb = X(tb), v = w[i + 1];
        if (v === 'x' || v === 'z') { g.fillStyle = v === 'x' ? col.x : col.z; g.globalAlpha = .35; g.fillRect(xa, top, Math.max(1, xb - xa), bot - top); g.globalAlpha = 1; continue; }
        const yy = v === '1' ? top : bot;
        g.strokeStyle = col.wave; g.lineWidth = 1.6; g.beginPath();
        if (i > i0 || w[i] >= SV.t0) { const prev = i >= 2 ? w[i - 1] : v; if (prev !== v) { g.moveTo(xa, prev === '1' ? top : bot); g.lineTo(xa, yy); } }
        g.moveTo(xa, yy); g.lineTo(xb, yy); g.stroke();
      }
    } else if (an) {
      const signed = SV.radix === 'signed', pts = [];
      let lo = Infinity, hi = -Infinity;
      for (let i = i0; i < w.length; i += 2) { if (w[i] > SV.t1) break; const n = simNum(w[i + 1], s.width, signed); if (n !== null) { lo = Math.min(lo, n); hi = Math.max(hi, n); pts.push([w[i], n]); } }
      if (pts.length) {
        if (hi === lo) { hi += 1; lo -= 1; }
        g.strokeStyle = col.bus; g.lineWidth = 1.6; g.beginPath();
        pts.forEach(([t, n], k) => { const xx = X(Math.max(t, SV.t0)), yy = bot - (n - lo) / (hi - lo) * (bot - top);
          if (k) { g.lineTo(xx, g.__y); } else g.moveTo(xx, yy); g.lineTo(xx, yy); g.__y = yy; });
        g.lineTo(X(SV.t1), g.__y); g.stroke();
        g.fillStyle = col.muted; g.font = '10.5px Segoe UI'; g.fillText(String(hi), NW + 4, top + 9); g.fillText(String(lo), NW + 4, bot - 1);
      }
    } else {
      for (let i = i0; i < w.length; i += 2) {
        const ta = Math.max(w[i], SV.t0), tb = i + 2 < w.length ? Math.min(w[i + 2], SV.t1) : SV.t1;
        if (ta > SV.t1) break;
        const xa = X(ta), xb = X(tb), v = w[i + 1], bad = /[xz]/.test(v), mid = (top + bot) / 2, e = Math.min(3, (xb - xa) / 2);
        g.strokeStyle = bad ? (v.includes('z') && !v.includes('x') ? col.z : col.x) : col.bus; g.lineWidth = 1.4;
        g.beginPath(); g.moveTo(xa, mid); g.lineTo(xa + e, top); g.lineTo(xb - e, top); g.lineTo(xb, mid); g.lineTo(xb - e, bot); g.lineTo(xa + e, bot); g.closePath(); g.stroke();
        if (bad) { g.globalAlpha = .15; g.fillStyle = g.strokeStyle; g.fill(); g.globalAlpha = 1; }
        const txt = simFmt(v, s.width, SV.radix);
        g.font = '11.5px Cascadia Mono, Consolas, monospace';
        const tw = g.measureText(txt).width;
        if (tw < xb - xa - 8) { g.fillStyle = col.text; g.fillText(txt, xa + (xb - xa - tw) / 2, mid + 4); }
        else if (xb - xa > 18) { g.fillStyle = col.text; const k = Math.floor((xb - xa - 10) / 7); if (k > 1) g.fillText(txt.slice(0, k - 1) + '…', xa + 5, mid + 4); }
      }
    }
    y += h;
  }
  // the cursors
  const cur = (t, c, name) => { if (t === null || t < SV.t0 || t > SV.t1) return; const x = Math.round(X(t)) + .5;
    g.strokeStyle = c; g.lineWidth = 1.2; g.setLineDash([4, 3]); g.beginPath(); g.moveTo(x, AX - 4); g.lineTo(x, cv.clientHeight); g.stroke(); g.setLineDash([]);
    g.fillStyle = c; g.font = '600 11px Segoe UI'; g.fillText(name, x + 3, AX - 2); };
  cur(SV.curA, '#ffb020', 'A'); cur(SV.curB, '#e04fd0', 'B');
  g.fillStyle = col.bg; g.globalAlpha = .0;
  $('simCur').textContent = (SV.curA !== null ? 'A ' + simFmtTime(SV.curA) : 'click the waves to set cursor A') +
    (SV.curB !== null ? ` · B ${simFmtTime(SV.curB)} · B - A = ${simFmtTime(SV.curB - SV.curA)}` +
      (SV.curB !== SV.curA ? ` (${(1e9 / Math.abs((SV.curB - SV.curA) * d.timescale_ns) / 1e6).toPrecision(4)} MHz)` : '') : (SV.curA !== null ? ' · Shift+click for B' : ''));
  g.globalAlpha = 1;
}

function simZoom(k, around) {
  const d = SV.data; if (!d) return;
  const span = SV.t1 - SV.t0, c = around !== undefined ? around : (SV.t0 + SV.t1) / 2;
  const ns = Math.min(d.end || 1, Math.max(2, span * k));
  SV.t0 = Math.max(0, c - (c - SV.t0) * ns / span); SV.t1 = SV.t0 + ns;
  if (SV.t1 > d.end) { SV.t1 = d.end; SV.t0 = Math.max(0, d.end - ns); }
  simDraw();
}
function simWire() {
  $('simRun').onclick = simRun;
  $('btnSim').onclick = () => { simRun(); };
  $('simNew').onclick = simNewTb;
  $('simTbOpen').onclick = () => { const t = $('simTb').value; if (t) openFile(S.project, t); };
  $('simFind').oninput = () => { SV.filter = $('simFind').value; simList(); };
  $('simMinor').onchange = () => { SV.showMinor = $('simMinor').checked; simList(); };
  $('simRadix').onchange = () => { SV.radix = $('simRadix').value; simDraw(); };
  $('simZin').onclick = () => simZoom(0.5);
  $('simZout').onclick = () => simZoom(2);
  $('simFit').onclick = () => { if (SV.data) { SV.t0 = 0; SV.t1 = Math.max(1, SV.data.end); simDraw(); } };
  $('simAll').onclick = () => { if (!SV.data) return; SV.sel = SV.data.signals.filter(s => SV.showMinor || !s.minor).map(s => s.name).slice(0, 200); simList(); simDraw(); };
  $('simNone').onclick = () => { SV.sel = []; simList(); simDraw(); };
  const cv = $('simCanvas');
  const tAt = e => { const r = cv.getBoundingClientRect(); return SV.t0 + (e.clientX - r.left - SV.NAMEW) / (r.width - SV.NAMEW - 8) * (SV.t1 - SV.t0); };
  cv.onwheel = e => { if (!SV.data) return; e.preventDefault(); const r = cv.getBoundingClientRect(); if (e.clientX - r.left < SV.NAMEW) return; simZoom(e.deltaY < 0 ? 0.7 : 1 / 0.7, tAt(e)); };
  cv.onmousedown = e => { if (!SV.data) return; SV.drag = { x: e.clientX, t0: SV.t0, t1: SV.t1, moved: false }; };
  window.addEventListener('mousemove', e => {
    const dr = SV.drag; if (!dr) return;
    const dx = e.clientX - dr.x; if (Math.abs(dx) > 3) dr.moved = true; if (!dr.moved) return;
    const r = cv.getBoundingClientRect(), dt = -dx / (r.width - SV.NAMEW - 8) * (dr.t1 - dr.t0), span = dr.t1 - dr.t0;
    SV.t0 = Math.max(0, Math.min(SV.data.end - span, dr.t0 + dt)); SV.t1 = SV.t0 + span; simDraw();
  });
  window.addEventListener('mouseup', e => {
    const dr = SV.drag; SV.drag = null;
    if (!dr || dr.moved || !SV.data) return;
    const r = cv.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    if (x < SV.NAMEW) {                                          // a click on a name: a bus becomes a curve (and back)
      let yy = 26;
      for (const n of SV.sel) { const s = SV.byName[n]; if (!s) continue; const h = SV.analog.has(n) ? SV.ROW * 3 : SV.ROW;
        if (y >= yy && y < yy + h) { if (s.width > 1) { if (SV.analog.has(n)) SV.analog.delete(n); else SV.analog.add(n); simDraw(); } break; } yy += h; }
      return;
    }
    const t = Math.max(0, Math.min(SV.data.end, tAt(e)));
    if (e.shiftKey) SV.curB = t; else { SV.curA = t; if (SV.curB !== null && e.ctrlKey) SV.curB = null; }
    simDraw();
  });
  window.addEventListener('resize', () => { if ($('simCanvas').offsetParent) simDraw(); });
  document.addEventListener('keydown', e => { if (e.key === 'F6') { e.preventDefault(); simRun(); } });
  // show the tab: read the project's testbenches; a finished simulation loads its waves
  const show0 = window.showTab;
  window.showTab = tab => { show0(tab); if (tab === 'simulation') { simInfo(); setTimeout(simDraw, 0); } };
  simLayout();
}
simWire();
