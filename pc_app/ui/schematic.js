/* Ardzy - Schematic: the design drawn as blocks and wires (like Vivado's RTL schematic).
   Yosys reads the Verilog (engine /api/fpga/schematic, fpga/schematic.py); here each module is laid out left to right
   from its inputs to its outputs. Click a module's box to go inside it, click another box to see where it is made
   in the Verilog, the mouse wheel zooms, dragging moves. Uses app.js (S, $, esc, api, out, openFile) and
   projtools.js (ptDialog). */

const SC = { data: null, path: [], zoom: 1, x: 0, y: 0, sel: null, find: '' };

const SC_OPS = {
  $add: '+', $sub: '-', $mul: '*', $div: '/', $mod: '%', $pow: '**', $neg: '-', $pos: '+',
  $and: '&', $or: '|', $xor: '^', $xnor: '~^', $not: '~', $logic_not: '!', $logic_and: '&&', $logic_or: '||',
  $reduce_and: '&(all)', $reduce_or: '|(any)', $reduce_xor: '^(parity)', $reduce_bool: '|(any)',
  $eq: '==', $ne: '!=', $eqx: '===', $nex: '!==', $lt: '<', $le: '<=', $gt: '>', $ge: '>=',
  $shl: '<<', $shr: '>>', $sshl: '<<<', $sshr: '>>>', $shift: 'shift', $shiftx: 'select', $mux: 'MUX', $pmux: 'MUX (case)',
  $bmux: 'MUX', $demux: 'DEMUX', $concat: '{ , }', $slice: '[ : ]', $lut: 'LUT',
  $dff: 'FF', $dffe: 'FF (enable)', $adff: 'FF (reset)', $adffe: 'FF (reset, enable)', $sdff: 'FF (sync reset)',
  $sdffe: 'FF (sync reset, enable)', $sdffce: 'FF (sync reset, enable)', $dffsr: 'FF (set, reset)', $dlatch: 'LATCH',
  $aldff: 'FF (load)', $mem: 'RAM', $mem_v2: 'RAM', $memrd: 'RAM read', $memrd_v2: 'RAM read', $memwr: 'RAM write',
  $memwr_v2: 'RAM write', $meminit: 'RAM init', $meminit_v2: 'RAM init', $tribuf: 'tri-state', $assert: 'assert',
};
const SC_REG = /^\$(a|s|al)?dff|^\$dlatch|^\$mem/;

function scOpName(t) { return SC_OPS[t] || t.replace(/^\$paramod\$[0-9a-f]+\\/, '').replace(/^\$paramod\\([^\\]+)\\.*/, '$1').replace(/^\$/, ''); }
function scModName(t) { const m = SC.data.modules[t]; return m ? m.name : scOpName(t); }

async function scOpen(project) {
  project = project || S.project;
  if (!project) return out(T('Choose a project first.'), 'warn');
  const d = ptDialog('dlgSchem', TF('Schematic: {0}', project));
  d.classList.add('schem-dlg');
  const body = d.querySelector('.ptbody');
  body.innerHTML = `<p class="hint">${T('Reading the design ...')}</p>`;
  d.querySelector('.ptfoot').innerHTML = `<button value="close" class="primary">${T('Close')}</button>`;
  if (!d.open) d.showModal();
  const r = await api('/api/fpga/schematic?project=' + encodeURIComponent(project));
  if (!r.ok) { body.innerHTML = `<p class="hint l-err">${esc(r.out)}</p>`; return; }
  SC.data = r; SC.project = project; SC.path = [{ type: r.top, inst: r.top }];
  body.innerHTML = `<div class="schem-bar"><span id="scCrumbs" class="schem-crumbs"></span><span class="grow"></span>
      <input type="search" id="scFind" placeholder="${esc(T('find a block or a wire'))}" spellcheck="false">
      <span class="seg"><button type="button" id="scZin">+</button><button type="button" id="scZout">-</button><button type="button" id="scFit">${T('fit')}</button></span></div>
    <div class="schem-view" id="scView"><svg id="scSvg"><g id="scG"></g></svg></div>
    <div class="schem-info hint" id="scInfo"></div>`;
  $('scZin').onclick = () => scZoomBy(1.25); $('scZout').onclick = () => scZoomBy(0.8); $('scFit').onclick = scFit;
  $('scFind').oninput = () => { SC.find = $('scFind').value.trim().toLowerCase(); scMark(); };
  scWire();
  scShow();
}

/* ---------------- one module: nodes, wires, layout ---------------- */
function scGraph(mod) {
  const nodes = [], drv = new Map();
  const add = n => { n.i = nodes.length; nodes.push(n); return n; };
  mod.ports.forEach(p => {
    if (p.dir !== 'input') add({ kind: 'out', label: p.name, ins: [{ name: '', bits: p.bits }], outs: [], width: p.bits.length });
    else { const n = add({ kind: 'in', label: p.name, ins: [], outs: [{ name: '', bits: p.bits }], width: p.bits.length }); n.outs[0].node = n; }
  });
  mod.cells.forEach(c => {
    const ins = [], outs = [];
    Object.entries(c.conns).forEach(([pn, v]) => (v.dir === 'input' ? ins : outs).push({ name: pn, bits: v.bits }));
    const sub = SC.data.modules[c.type];
    const kind = sub ? 'mod' : SC_REG.test(c.type) ? 'reg' : 'op';
    // a register without a name of its own: the name of the signal it holds
    const label = c.name || (kind === 'reg' && outs.length ? scNetName(mod, outs[0].bits.filter(b => typeof b === 'number')).replace(/ \[\d+\]$/, '') : '');
    add({ kind, cell: c, label, type: c.type, ins, outs, width: c.width });
  });
  nodes.forEach(n => n.outs.forEach((p, k) => p.bits.forEach(b => { if (typeof b === 'number') drv.set(b, { n, k }); })));
  // wires: for every input pin, the output pins that drive its bits
  const edges = [];
  nodes.forEach(n => n.ins.forEach((p, k) => {
    const seen = new Map(), consts = [];
    p.bits.forEach(b => {
      if (typeof b !== 'number') { consts.push(b); return; }
      const d = drv.get(b);
      if (!d) return;
      const key = d.n.i + ':' + d.k;
      if (!seen.has(key)) seen.set(key, { from: d.n, fk: d.k, to: n, tk: k, bits: [] });
      seen.get(key).bits.push(b);
    });
    seen.forEach(e => { e.label = scNetName(mod, e.bits); edges.push(e); });
    if (consts.length === p.bits.length && p.bits.length) p.konst = scConst(p.bits);
  }));
  return { nodes, edges };
}
function scNetName(mod, bits) {
  const names = bits.map(b => mod.nets[b]).filter(Boolean);
  if (!names.length) return '';
  const base = names[0].replace(/\[\d+\]$/, '');
  return names.every(n => n.replace(/\[\d+\]$/, '') === base) ? (bits.length > 1 ? `${base} [${bits.length}]` : names[0]) : names[0] + ' ...';
}
function scConst(bits) {
  if (bits.some(b => b === 'x' || b === 'z')) return bits.length + "'b" + bits.slice().reverse().join('');
  let v = 0n; bits.slice().reverse().forEach(b => { v = v * 2n + (b === '1' ? 1n : 0n); });
  return bits.length === 1 ? String(v) : bits.length + "'h" + v.toString(16);
}

function scLayout(g) {
  const { nodes, edges } = g, succ = nodes.map(() => []), pred = nodes.map(() => []);
  // cut the loops (a register's output that comes back to its input) by a depth-first walk from the inputs
  const state = new Array(nodes.length).fill(0), back = new Set();
  edges.forEach((e, i) => succ[e.from.i].push(i));
  const order = nodes.filter(n => n.kind === 'in').concat(nodes.filter(n => n.kind === 'reg'), nodes);
  for (const s of order) {
    if (state[s.i]) continue;
    const stack = [[s.i, 0]]; state[s.i] = 1;
    while (stack.length) {
      const top = stack[stack.length - 1], [v, k] = top;
      if (k < succ[v].length) {
        top[1]++;
        const ei = succ[v][k], w = edges[ei].to.i;
        if (state[w] === 1) back.add(ei);
        else if (!state[w]) { state[w] = 1; stack.push([w, 0]); }
      } else { state[v] = 2; stack.pop(); }
    }
  }
  edges.forEach((e, i) => { e.back = back.has(i); if (!e.back) pred[e.to.i].push(e.from.i); });
  // columns: the longest way from an input (inputs left, outputs right)
  const lvl = new Array(nodes.length).fill(0), done = new Array(nodes.length).fill(false);
  const indeg = pred.map(p => p.length), q = nodes.filter(n => !indeg[n.i]).map(n => n.i);
  const fwd = nodes.map(() => []);
  edges.forEach(e => { if (!e.back) fwd[e.from.i].push(e.to.i); });
  while (q.length) {
    const v = q.shift(); done[v] = true;
    fwd[v].forEach(w => { lvl[w] = Math.max(lvl[w], lvl[v] + 1); if (--indeg[w] === 0) q.push(w); });
  }
  nodes.forEach(n => { if (n.kind === 'in') lvl[n.i] = 0; });
  let maxL = 0;
  nodes.forEach(n => { if (n.kind !== 'out') maxL = Math.max(maxL, lvl[n.i]); });
  nodes.forEach(n => { if (n.kind === 'out') lvl[n.i] = maxL + 1; else if (n.kind !== 'in') lvl[n.i] = Math.max(1, lvl[n.i]); });
  // sizes
  nodes.forEach(n => {
    const pinw = Math.max(0, ...n.ins.map(p => p.name.length)) + Math.max(0, ...n.outs.map(p => p.name.length));
    const title = n.kind === 'mod' ? Math.max(scModName(n.type).length, n.label.length) : n.kind === 'in' || n.kind === 'out' ? n.label.length + 4 : Math.max(scOpName(n.type).length, (n.label || '').length);
    n.w = n.kind === 'in' || n.kind === 'out' ? Math.max(60, title * 7.2 + 26) : Math.max(70, title * 7.2 + 24, pinw * 6.4 + 34);
    const pins = Math.max(n.ins.length, n.outs.length, 1);
    n.h = n.kind === 'in' || n.kind === 'out' ? 24 : 34 + pins * 15;
  });
  // rows: order each column by where its inputs come from (two sweeps)
  const cols = [];
  nodes.forEach(n => (cols[lvl[n.i]] = cols[lvl[n.i]] || []).push(n));
  for (let c = 0; c < cols.length; c++) if (!cols[c]) cols[c] = [];
  const pos = new Array(nodes.length).fill(0);
  cols.forEach(col => col.forEach((n, i) => pos[n.i] = i));
  const bary = (n, list) => list.length ? list.reduce((a, j) => a + pos[j], 0) / list.length : pos[n.i];
  for (let sweep = 0; sweep < 3; sweep++) {
    for (let c = 1; c < cols.length; c++) { cols[c].sort((a, b) => bary(a, pred[a.i]) - bary(b, pred[b.i])); cols[c].forEach((n, i) => pos[n.i] = i); }
    for (let c = cols.length - 2; c >= 0; c--) { cols[c].sort((a, b) => bary(a, fwd[a.i]) - bary(b, fwd[b.i])); cols[c].forEach((n, i) => pos[n.i] = i); }
  }
  // coordinates
  let x = 20, H = 0;
  cols.forEach(col => {
    const cw = Math.max(60, ...col.map(n => n.w));
    let y = 20;
    col.forEach(n => { n.x = x + (n.kind === 'out' ? 0 : n.kind === 'in' ? cw - n.w : (cw - n.w) / 2); n.y = y; y += n.h + 22; });
    H = Math.max(H, y);
    x += cw + 110;
  });
  // center the shorter columns
  cols.forEach(col => { if (!col.length) return; const h = col[col.length - 1].y + col[col.length - 1].h - col[0].y, off = (H - 20 - h) / 2 - col[0].y + 10; col.forEach(n => n.y += Math.max(0, off)); });
  g.W = x; g.H = H + 30;
  return g;
}
const scPinY = (n, k, side) => n.kind === 'in' || n.kind === 'out' ? n.y + n.h / 2 : n.y + 30 + k * 15;

/* ---------------- drawing ---------------- */
function scShow() {
  const cur = SC.path[SC.path.length - 1], mod = SC.data.modules[cur.type];
  $('scCrumbs').innerHTML = SC.path.map((p, i) => `<button type="button" class="ghost tiny" data-i="${i}">${esc(i ? p.inst + ' : ' + scModName(p.type) : scModName(p.type))}</button>`).join('<span class="hint"> &gt; </span>');
  $('scCrumbs').querySelectorAll('[data-i]').forEach(b => b.onclick = () => { SC.path = SC.path.slice(0, +b.dataset.i + 1); scShow(); });
  if (!mod) { $('scG').innerHTML = ''; return; }
  if (!mod.own) {
    $('scG').innerHTML = '';
    $('scInfo').innerHTML = esc(TF('{0} is part of the Ardzy library: its ports are shown on the box one level up.', mod.name));
    return;
  }
  const g = scLayout(scGraph(mod));
  SC.g = g;
  const parts = [];
  g.edges.forEach((e, i) => {
    const x1 = e.from.x + e.from.w, y1 = scPinY(e.from, e.fk), x2 = e.to.x, y2 = scPinY(e.to, e.tk);
    let d;
    if (!e.back && x2 > x1) { const dx = Math.max(30, (x2 - x1) / 2); d = `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`; }
    else { const yb = Math.max(e.from.y + e.from.h, e.to.y + e.to.h) + 14 + (i % 5) * 4; d = `M${x1},${y1} C${x1 + 60},${y1} ${x1 + 60},${yb} ${x1},${yb} L${x2},${yb} C${x2 - 60},${yb} ${x2 - 60},${y2} ${x2},${y2}`; }
    parts.push(`<path class="sc-w${e.bits.length > 1 ? ' bus' : ''}${e.back ? ' back' : ''}" d="${d}" data-e="${i}"><title>${esc(e.label || '')}${e.bits.length > 1 ? ' (' + e.bits.length + ' bits)' : ''}</title></path>`);
  });
  g.nodes.forEach(n => {
    const id = `data-n="${n.i}"`;
    if (n.kind === 'in' || n.kind === 'out') {
      const w = n.w, h = n.h, x = n.x, y = n.y, tip = 10;
      const shape = n.kind === 'in' ? `M${x},${y} L${x + w - tip},${y} L${x + w},${y + h / 2} L${x + w - tip},${y + h} L${x},${y + h} Z`
        : `M${x + tip},${y} L${x + w},${y} L${x + w},${y + h} L${x + tip},${y + h} L${x},${y + h / 2} Z`;
      parts.push(`<g class="sc-n sc-port" ${id}><path d="${shape}"/><text x="${x + w / 2}" y="${y + h / 2 + 4}" text-anchor="middle">${esc(n.label)}${n.width > 1 ? ` [${n.width}]` : ''}</text></g>`);
      return;
    }
    const cls = n.kind === 'mod' ? 'sc-mod' : n.kind === 'reg' ? 'sc-reg' : 'sc-op';
    const title = n.kind === 'mod' ? scModName(n.type) : scOpName(n.type);
    let s = `<g class="sc-n ${cls}" ${id}><rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="5"/>
      <text class="t" x="${n.x + n.w / 2}" y="${n.y + 14}" text-anchor="middle">${esc(title)}${n.kind !== 'mod' && n.width > 1 ? ` [${n.width}]` : ''}</text>`;
    if (n.label) s += `<text class="nm" x="${n.x + n.w / 2}" y="${n.y + n.h + 12}" text-anchor="middle">${esc(n.label)}</text>`;
    n.ins.forEach((p, k) => {
      const y = scPinY(n, k);
      s += `<text class="pin" x="${n.x + 5}" y="${y + 3.5}">${esc(p.name)}</text>`;
      if (p.konst !== undefined) s += `<text class="konst" x="${n.x - 4}" y="${y + 3.5}" text-anchor="end">${esc(p.konst)}</text>`;
    });
    n.outs.forEach((p, k) => { s += `<text class="pin" x="${n.x + n.w - 5}" y="${scPinY(n, k) + 3.5}" text-anchor="end">${esc(p.name)}</text>`; });
    parts.push(s + '</g>');
  });
  $('scG').innerHTML = parts.join('');
  const svg = $('scSvg');
  svg.setAttribute('width', g.W); svg.setAttribute('height', g.H);
  $('scInfo').innerHTML = esc(TF('{0}: {1} blocks, {2} wires.', mod.name, g.nodes.filter(n => n.kind !== 'in' && n.kind !== 'out').length, g.edges.length)) + ' ' +
    esc(T('Click a module to go inside; click a block to find it in the Verilog; dashed wires go back (through a register).')) +
    (mod.cut ? ' <span class="l-warn">' + esc(T('This module is big: only the modules inside it are drawn.')) + '</span>' : '');
  scFit();
  scMark();
}

function scMark() {
  const f = SC.find, g = SC.g;
  if (!g) return;
  document.querySelectorAll('#scG .sc-n').forEach(el => {
    const n = g.nodes[+el.dataset.n];
    const hit = f && ((n.label || '').toLowerCase().includes(f) || (n.type || '').toLowerCase().includes(f) || (n.kind === 'mod' && scModName(n.type).toLowerCase().includes(f)));
    el.classList.toggle('hit', !!hit);
  });
  document.querySelectorAll('#scG .sc-w').forEach(el => el.classList.toggle('hit', !!f && (g.edges[+el.dataset.e].label || '').toLowerCase().includes(f)));
}

/* ---------------- moving around ---------------- */
function scApply() { $('scG').setAttribute('transform', `translate(${SC.x},${SC.y}) scale(${SC.zoom})`); }
function scFit() {
  const v = $('scView'), g = SC.g;
  if (!v || !g) return;
  const W = v.clientWidth || 900, H = v.clientHeight || 500;
  const svg = $('scSvg'); svg.setAttribute('width', W); svg.setAttribute('height', H);
  SC.zoom = Math.min(1.4, Math.max(0.15, Math.min(W / g.W, H / g.H)));
  SC.x = (W - g.W * SC.zoom) / 2; SC.y = Math.max(0, (H - g.H * SC.zoom) / 2);
  scApply();
}
function scZoomBy(k, cx, cy) {
  const v = $('scView');
  if (cx === undefined) { cx = v.clientWidth / 2; cy = v.clientHeight / 2; }
  const z = Math.min(4, Math.max(0.08, SC.zoom * k));
  SC.x = cx - (cx - SC.x) * z / SC.zoom; SC.y = cy - (cy - SC.y) * z / SC.zoom; SC.zoom = z;
  scApply();
}
function scWire() {
  const v = $('scView');
  let drag = null;
  v.onwheel = e => { e.preventDefault(); const r = v.getBoundingClientRect(); scZoomBy(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top); };
  v.onmousedown = e => { drag = { x: e.clientX, y: e.clientY, sx: SC.x, sy: SC.y, moved: false }; };
  v.onmousemove = e => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    if (drag.moved) { SC.x = drag.sx + dx; SC.y = drag.sy + dy; scApply(); }
  };
  v.onmouseup = e => {
    const moved = drag && drag.moved; drag = null;
    if (moved) return;
    const el = e.target.closest('.sc-n');
    if (!el) return;
    const n = SC.g.nodes[+el.dataset.n];
    if (n.kind === 'mod' && SC.data.modules[n.type] && SC.data.modules[n.type].own) { SC.path.push({ type: n.type, inst: n.label || scModName(n.type) }); scShow(); return; }
    document.querySelectorAll('#scG .sc-n.sel').forEach(x => x.classList.remove('sel'));
    el.classList.add('sel');
    const src = n.cell ? n.cell.src : '';
    const what = n.kind === 'in' ? T('input') : n.kind === 'out' ? T('output') : n.kind === 'mod' ? TF('module {0} (Ardzy library)', scModName(n.type)) : scOpName(n.type);
    $('scInfo').innerHTML = `<b>${esc(n.label || '')}</b> ${esc(what)}${n.width > 1 ? ' · ' + n.width + ' bits' : ''}` +
      (src ? ` · <a href="#" id="scSrc">${esc(src)}</a>` : '');
    if (src) $('scSrc').onclick = ev => {
      ev.preventDefault();
      const [file, line] = src.split(':');
      const proj = S.projects.find(p => p.name === SC.project);
      if (!proj || !proj.files.includes(file)) return;
      $('dlgSchem').close();
      if (SC.project !== S.project) selectProject(SC.project);
      openFile(SC.project, file).then(() => setTimeout(() => cpJump(+line - 1), 30));
    };
  };
  v.onmouseleave = () => { drag = null; };
}
