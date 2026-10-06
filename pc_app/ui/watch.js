/* Ardzy - Watch and Data logger.
   Watch (bottom tab): every value the program prints as  name:number  or  name="text"  (Ardzy.watch / ardzy.watch
   print these; so do Plotter lines) shows live in a table with min / max / average / rate and a small graph,
   and can be recorded to a CSV file on the PC.
   Data logger (a card in the Board view): the board records its sensors, pins and the program's values to the SD
   card by itself, for hours, also with the PC off; the app lists the logs, draws them and saves them as CSV.
   Uses app.js (S, $, esc, api, out, markNew, showTab) and board.js (bget, bpost, BV, kv, CARDS). */

const W = { vars: {}, order: [], hidden: new Set(), rec: null, renderT: null, filter: '', sort: 'first' };
// name:value with nothing in between (what watch() prints), so ordinary sentences ("RESULT: 11 of 13") stay out
const W_NUM = /(?:^|[\s,;])([A-Za-z_][\w.\[\]-]*)[:=](-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(?![\w.])/g;
const W_TXT = /([A-Za-z_][\w.-]*)="([^"]*)"/g;
const W_SYSTEM = /^(===|Started |Stopped |Stopping |ardzy-app|Traceback|\s+File ")/;

function watchLine(line) {
  if (W_SYSTEM.test(line)) return;
  const now = Date.now(), found = {};
  for (const m of line.matchAll(W_TXT)) found[m[1]] = m[2];
  for (const m of line.matchAll(W_NUM)) if (!(m[1] in found)) found[m[1]] = parseFloat(m[2]);
  const keys = Object.keys(found);
  if (!keys.length) return;
  for (const k of keys) {
    const v = found[k];
    let w = W.vars[k];
    if (!w) { w = W.vars[k] = { n: 0, hist: [], first: now, text: typeof v === 'string', changes: 0 }; W.order.push(k); }
    if (w.v !== v) w.changes++;
    w.v = v; w.t = now; w.n++;
    w.times = (w.times || []).filter(t => now - t < 5000); w.times.push(now);
    if (typeof v === 'number') {
      w.text = false;
      w.min = w.min === undefined ? v : Math.min(w.min, v);
      w.max = w.max === undefined ? v : Math.max(w.max, v);
      w.sum = (w.sum || 0) + v; w.cnt = (w.cnt || 0) + 1;
      w.hist.push(v); if (w.hist.length > 120) w.hist.shift();
    }
  }
  if (W.rec && W.rec.on) {
    W.rec.rows.push(Object.assign({ t: now }, found));
    keys.forEach(k => { if (!W.rec.cols.includes(k)) W.rec.cols.push(k); });
    if (W.rec.rows.length > 500000) { W.rec.on = false; out('Watch recording stopped at 500 000 rows: save it, then start again.', 'warn'); }
  }
  clearTimeout(W.renderT);
  W.renderT = setTimeout(watchRender, 200);
}

const wFmt = v => typeof v !== 'number' ? String(v) : Math.abs(v) >= 1e6 || (Math.abs(v) < 1e-3 && v) ? v.toExponential(3)
  : Number.isInteger(v) ? String(v) : v.toFixed(Math.abs(v) < 10 ? 3 : Math.abs(v) < 1000 ? 2 : 1);
function wSpark(h) {
  if (h.length < 2) return '';
  const lo = Math.min(...h), hi = Math.max(...h), r = hi - lo || 1;
  const pts = h.map((v, i) => `${(i * 120 / (h.length - 1)).toFixed(1)},${(22 - 20 * (v - lo) / r).toFixed(1)}`).join(' ');
  return `<svg viewBox="0 0 120 24" class="wspark" preserveAspectRatio="none"><polyline points="${pts}"/></svg>`;
}
function watchRender() {
  const box = $('watchBody');
  if (!box || box.offsetParent === null) { watchInfo(); return; }
  const now = Date.now(), f = W.filter.toLowerCase();
  let keys = W.order.filter(k => !W.hidden.has(k) && (!f || k.toLowerCase().includes(f)));
  if (W.sort === 'name') keys = keys.slice().sort();
  if (W.sort === 'recent') keys = keys.slice().sort((a, b) => W.vars[b].t - W.vars[a].t);
  box.innerHTML = keys.length ? `<table class="wtable"><tr><th>Name</th><th>Value</th><th>Min</th><th>Max</th><th>Average</th><th>Updates</th><th>Last</th><th>Last 120</th><th></th></tr>` +
    keys.map(k => {
      const w = W.vars[k], age = (now - w.t) / 1000, rate = w.times.length > 1 ? (w.times.length - 1) / ((w.times[w.times.length - 1] - w.times[0]) / 1000 || 1) : 0;
      return `<tr class="${age < 1.2 ? 'fresh' : age > 10 ? 'stale' : ''}"><td class="wn">${esc(k)}</td><td class="wv">${esc(wFmt(w.v))}</td>
        <td class="num">${w.text ? '' : wFmt(w.min)}</td><td class="num">${w.text ? '' : wFmt(w.max)}</td><td class="num">${w.text ? '' : wFmt(w.sum / w.cnt)}</td>
        <td class="num">${rate ? rate.toFixed(1) + '/s' : w.n}</td><td class="num">${age < 1 ? 'now' : age < 60 ? age.toFixed(0) + ' s ago' : Math.floor(age / 60) + ' min ago'}</td>
        <td>${w.text ? '' : wSpark(w.hist)}</td><td><button class="ghost tiny" data-hide="${esc(k)}" title="Hide this value">&times;</button></td></tr>`;
    }).join('') + '</table>'
    : `<div class="wempty"><b>No values yet.</b> Print them from your program and they appear here, live:<br>
      <code>Ardzy.watch("speed", speed);</code> (sketch) &nbsp; <code>watch(speed=speed)</code> (Python: <code>from ardzy import watch</code>)<br>
      or any line like <code>temp:42.5 fan:1200</code> or <code>state="running"</code>.</div>`;
  box.querySelectorAll('[data-hide]').forEach(b => b.onclick = () => { W.hidden.add(b.dataset.hide); watchRender(); });
  watchInfo();
}
function watchInfo() {
  if (!$('watchInfo')) return;
  const n = W.order.length, hid = W.hidden.size;
  $('watchInfo').textContent = `${n} value${n === 1 ? '' : 's'}${hid ? `, ${hid} hidden` : ''}` +
    (W.rec ? ` · recording ${W.rec.on ? 'on' : 'paused'}: ${W.rec.rows.length} rows, ${W.rec.cols.length} columns` : '');
  $('watchRec').textContent = W.rec && W.rec.on ? 'Pause recording' : W.rec ? 'Go on recording' : 'Record';
  $('watchRec').classList.toggle('recording', !!(W.rec && W.rec.on));
  $('watchSave').disabled = !(W.rec && W.rec.rows.length);
}
function watchWire() {
  $('watchFind').oninput = () => { W.filter = $('watchFind').value; watchRender(); };
  $('watchSort').onchange = () => { W.sort = $('watchSort').value; watchRender(); };
  $('watchClear').onclick = () => { W.vars = {}; W.order = []; W.hidden.clear(); watchRender(); };
  $('watchShow').onclick = () => { W.hidden.clear(); watchRender(); };
  $('watchRec').onclick = () => {
    if (!W.rec) W.rec = { on: true, rows: [], cols: [], t0: Date.now() };
    else W.rec.on = !W.rec.on;
    watchInfo();
  };
  $('watchSave').onclick = async () => {
    const r = W.rec;
    if (!r || !r.rows.length) return;
    const q = v => v === undefined ? '' : typeof v === 'string' ? '"' + v.replace(/"/g, '""') + '"' : v;
    const csv = ['time,seconds,' + r.cols.join(',')].concat(r.rows.map(x => new Date(x.t).toTimeString().slice(0, 8) + ',' +
      ((x.t - r.t0) / 1000).toFixed(3) + ',' + r.cols.map(c => q(x[c])).join(','))).join('\n');
    const res = await api('/api/savelog', { name: 'watch_' + (S.status && S.status.current || 'program'), ext: 'csv', text: csv + '\n' });
    out(res.ok ? `Watch recording saved (${r.rows.length} rows): ${res.path}` : 'Not saved: ' + res.out, res.ok ? 'ok' : 'err');
    if (res.ok && confirm('Saved. Start a new recording (the saved rows are cleared)?')) { W.rec = null; watchInfo(); }
  };
  // every Monitor line also goes to Watch
  const mon0 = window.monAdd;
  window.monAdd = function (text, cls) {
    mon0(text, cls);
    if (S.monCursor === null) return;                                  // (the old output shown when the app starts)
    if (/^=== .*: starting program ===/.test(text)) { W.vars = {}; W.order = []; watchRender(); return; }   // a new run, a new table
    watchLine(String(text));
  };
  setInterval(() => { if ($('watchBody') && $('watchBody').offsetParent) watchRender(); }, 1000);   // (the "last" column ages)
  watchRender();
}

/* ---------------------------------------------------------------- the board's data logger (Board view card) */
const LG = { status: null, logs: [], view: null };
function loggerCardHtml() {
  return `<div class="dcard" data-card="logger"><h3>Data logger</h3><div id="lgBody" class="hint">reading ...</div></div>`;
}
async function loggerRefresh() {
  if (!$('lgBody')) return;
  const r = await bget('/api/logger');
  if (!r.ok) { $('lgBody').innerHTML = `<div class="hint">${/not found/.test(r.out || '') ? 'This board image has no data logger yet: update the board (System, Settings and update).' : esc(r.out || 'no answer')}</div>`; return; }
  LG.status = r.status; LG.logs = r.logs;
  const st = r.status, run = st.running;
  const dur = s => s < 90 ? Math.round(s) + ' s' : s < 5400 ? Math.round(s / 60) + ' min' : (s / 3600).toFixed(1) + ' h';
  const when = t => t ? new Date(t * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-';
  $('lgBody').innerHTML = (run ? `<div class="lg-run"><span class="lg-dot"></span><b>Recording "${esc(st.name)}"</b> every ${st.interval} s
      (${esc((st.channels || []).join(', '))}) &middot; ${st.samples || 0} samples, ${st.size_kb || 0} KB, for ${dur(Date.now() / 1000 - st.started)}
      ${st.hours ? ' &middot; stops after ' + st.hours + ' h' : ''}<span class="grow"></span><button class="ghost small" id="lgStop">Stop</button></div>`
    : `<div class="lg-form">
      <label>Name <input id="lgName" placeholder="(date and time)" spellcheck="false"></label>
      <label>Every <select id="lgInt">${[[0.2, '0.2 s'], [0.5, '0.5 s'], [1, '1 s'], [2, '2 s'], [5, '5 s'], [10, '10 s'], [30, '30 s'], [60, '1 min'], [300, '5 min']].map(([v, t]) => `<option value="${v}" ${v === 1 ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
      <label>For <select id="lgHours"><option value="0">until I stop it</option><option value="0.25">15 min</option><option value="1">1 hour</option><option value="8">8 hours</option><option value="24">1 day</option><option value="168">1 week</option></select></label>
      <div class="lg-ch"><label class="check"><input type="checkbox" id="lgS" checked> sensors (temperature, supplies, CPU, memory)</label>
        <label class="check"><input type="checkbox" id="lgP"> pins, LEDs and fan speeds (needs the pin-control design, which sketches use)</label>
        <label class="check"><input type="checkbox" id="lgG" checked> my program's values (name:value lines, Ardzy.watch)</label></div>
      <button class="primary small" id="lgStart">Start recording</button></div>`) +
    (st.why && !run ? `<div class="hint">The last recording ended: ${esc(st.why)}.</div>` : '') +
    `<table class="lg-list"><tr><th>Log</th><th>Started</th><th>Length</th><th>Rows</th><th>Size</th><th></th></tr>` +
    (r.logs.length ? r.logs.slice().reverse().map(l => `<tr><td><b>${esc(l.name)}</b></td><td>${when(l.start)}</td><td>${l.start ? dur(l.end - l.start) : '-'}</td>
      <td class="num">${l.rows}</td><td class="num">${l.size_kb < 1024 ? l.size_kb + ' KB' : (l.size_kb / 1024).toFixed(1) + ' MB'}</td>
      <td class="lg-act"><button class="ghost tiny" data-lv="${esc(l.name)}" title="Draw it">Chart</button><button class="ghost tiny" data-ls="${esc(l.name)}" title="Save on this PC as CSV (Excel, LibreOffice)">CSV</button><button class="ghost tiny" data-ld="${esc(l.name)}" title="Delete it from the board" ${run && st.name === l.name ? 'disabled' : ''}>&times;</button></td></tr>`).join('')
      : '<tr><td colspan="6" class="hint">No logs yet.</td></tr>') + '</table>' +
    `<div class="hint">Logs are kept on the SD card (${st.free_mb ? (st.free_mb / 1024).toFixed(1) + ' GB free' : ''}); recording goes on when the app is closed, and stops by itself before the card is full.</div>`;
  if (run) $('lgStop').onclick = async () => { await bpost('/api/logger/stop'); loggerRefresh(); };
  else $('lgStart').onclick = async () => {
    const ch = [['lgS', 'sensors'], ['lgP', 'pins'], ['lgG', 'program']].filter(([id]) => $(id).checked).map(x => x[1]);
    if (!ch.length) { out('Choose at least one thing to record.', 'warn'); return; }
    const q = qs({ name: $('lgName').value.trim(), interval: $('lgInt').value, ch: ch.join(','), hours: $('lgHours').value });
    const res = await bpost('/api/logger/start?' + q);
    if (!res.ok) out('Logger: ' + res.out, 'err'); else out(`Data logger recording "${res.name}" every ${res.interval} s.`, 'ok');
    loggerRefresh();
  };
  $('lgBody').querySelectorAll('[data-lv]').forEach(b => b.onclick = () => logChart(b.dataset.lv));
  $('lgBody').querySelectorAll('[data-ls]').forEach(b => b.onclick = async () => {
    const c = await bget('/api/logger/csv?name=' + encodeURIComponent(b.dataset.ls));
    if (!c.ok) return out(c.out, 'err');
    const res = await api('/api/savelog', { name: 'log_' + b.dataset.ls, ext: 'csv', text: c.csv });
    out(res.ok ? 'Log saved: ' + res.path : 'Not saved: ' + res.out, res.ok ? 'ok' : 'err');
  });
  $('lgBody').querySelectorAll('[data-ld]').forEach(b => b.onclick = async () => {
    if (!confirm(`Delete the log "${b.dataset.ld}" from the board?`)) return;
    const res = await bpost('/api/logger/delete?name=' + encodeURIComponent(b.dataset.ld));
    if (!res.ok) out(res.out, 'err');
    loggerRefresh();
  });
}

// a log drawn: pick the columns, zoom with the wheel, point for values
async function logChart(name) {
  const c = await bget('/api/logger/csv?name=' + encodeURIComponent(name));
  if (!c.ok) return out(c.out, 'err');
  const lines = c.csv.trim().split('\n'), head = lines[0].split(',');
  const rows = lines.slice(1).map(l => l.split(','));
  const cols = head.slice(2).map((h, i) => ({ name: h, i: i + 2, vals: rows.map(r => parseFloat(r[i + 2])) }))
    .filter(col => col.vals.some(v => !isNaN(v)));
  const secs = rows.map(r => parseFloat(r[1]));
  const pal = ['#e8743b', '#4f8fe0', '#2fbf6c', '#a35ad8', '#d0a020', '#20a3a3', '#e04f8f', '#7a8b2f'];
  const pick = new Set(cols.filter(col => /temp|prog\./.test(col.name)).slice(0, 3).map(col => col.name));
  if (!pick.size && cols.length) pick.add(cols[0].name);
  LG.view = { name, cols, secs, rows, pick, x0: 0, x1: 1, pal };
  $('lgDlgTitle').textContent = `Log "${name}": ${rows.length} rows, ${secs.length ? Math.round(secs[secs.length - 1]) : 0} s`;
  $('lgCols').innerHTML = cols.map((col, i) => `<label class="chip ${pick.has(col.name) ? 'on' : ''}" style="--c:${pal[i % pal.length]}"><input type="checkbox" data-col="${esc(col.name)}" ${pick.has(col.name) ? 'checked' : ''}>${esc(col.name)}</label>`).join('');
  $('lgCols').querySelectorAll('[data-col]').forEach(cb => cb.onchange = () => {
    if (cb.checked) pick.add(cb.dataset.col); else pick.delete(cb.dataset.col);
    cb.parentElement.classList.toggle('on', cb.checked); logDraw();
  });
  const cv = $('lgCanvas');
  cv.onwheel = e => {
    e.preventDefault();
    const v = LG.view, r = cv.getBoundingClientRect(), fx = v.x0 + (e.clientX - r.left) / r.width * (v.x1 - v.x0);
    const k = e.deltaY < 0 ? 0.75 : 1 / 0.75, w = Math.min(1, (v.x1 - v.x0) * k);
    v.x0 = Math.max(0, Math.min(1 - w, fx - (fx - v.x0) * w / (v.x1 - v.x0))); v.x1 = v.x0 + w; logDraw();
  };
  cv.onmousemove = e => { LG.view.hover = (e.clientX - cv.getBoundingClientRect().left) / cv.clientWidth; logDraw(); };
  cv.onmouseleave = () => { LG.view.hover = null; logDraw(); };
  $('lgReset').onclick = e => { e.preventDefault(); LG.view.x0 = 0; LG.view.x1 = 1; logDraw(); };
  $('dlgLog').showModal();
  setTimeout(logDraw, 30);
}
function logDraw() {
  const v = LG.view, cv = $('lgCanvas');
  if (!v || !cv.clientWidth) return;
  const dpr = window.devicePixelRatio || 1;
  cv.width = Math.round(cv.clientWidth * dpr); cv.height = Math.round(cv.clientHeight * dpr);
  const g = cv.getContext('2d'), W = cv.width, H = cv.height, css = getComputedStyle(document.body), pad = 8 * dpr;
  const tEnd = v.secs[v.secs.length - 1] || 1, ta = v.x0 * tEnd, tb = v.x1 * tEnd;
  g.clearRect(0, 0, W, H);
  g.strokeStyle = css.getPropertyValue('--line'); g.lineWidth = 1;
  for (let i = 0; i <= 4; i++) { const y = Math.round(pad + (H - 2 * pad) * i / 4) + .5; g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
  g.fillStyle = css.getPropertyValue('--muted'); g.font = `${11 * dpr}px Segoe UI`;
  g.fillText(`${ta.toFixed(0)} s`, 4 * dpr, H - 3 * dpr);
  const lab = `${tb.toFixed(0)} s`; g.fillText(lab, W - g.measureText(lab).width - 4 * dpr, H - 3 * dpr);
  const tip = [];
  let hi = -1;
  if (v.hover !== null && v.hover !== undefined) {
    const th = ta + v.hover * (tb - ta);
    hi = 0; v.secs.forEach((s, i) => { if (Math.abs(s - th) < Math.abs(v.secs[hi] - th)) hi = i; });
  }
  v.cols.forEach((col, ci) => {
    if (!v.pick.has(col.name)) return;
    const idx = v.secs.map((s, i) => i).filter(i => v.secs[i] >= ta && v.secs[i] <= tb && !isNaN(col.vals[i]));
    if (!idx.length) return;
    const vals = idx.map(i => col.vals[i]);
    let lo = Math.min(...vals), hi2 = Math.max(...vals);
    const m = Math.max((hi2 - lo) * .1, Math.abs(hi2) * .002 + 1e-9); lo -= m; hi2 += m;
    const step = Math.max(1, Math.floor(idx.length / (W / 1.5)));        // (thin out very long logs)
    g.strokeStyle = v.pal[ci % v.pal.length]; g.lineWidth = 1.6 * dpr; g.beginPath();
    idx.forEach((i, n) => { if (n % step && n !== idx.length - 1) return;
      const x = W * (v.secs[i] - ta) / (tb - ta), y = H - pad - (H - 2 * pad) * (col.vals[i] - lo) / (hi2 - lo); n ? g.lineTo(x, y) : g.moveTo(x, y); });
    g.stroke();
    if (hi >= 0 && !isNaN(col.vals[hi])) tip.push(`<div><i style="background:${v.pal[ci % v.pal.length]}"></i>${esc(col.name)} ${wFmt(col.vals[hi])}</div>`);
  });
  if (hi >= 0) {
    const x = W * (v.secs[hi] - ta) / (tb - ta);
    g.strokeStyle = css.getPropertyValue('--muted'); g.lineWidth = dpr; g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke();
    $('lgTip').hidden = false;
    $('lgTip').innerHTML = `<b>${esc(v.rows[hi][0])}</b> (${v.secs[hi].toFixed(1)} s)` + tip.join('');
    $('lgTip').style.left = Math.min(cv.clientWidth - 200, x / dpr + 12) + 'px';
  } else $('lgTip').hidden = true;
}

watchWire();
