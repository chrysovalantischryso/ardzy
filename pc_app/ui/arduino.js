/* Ardzy - Arduino features: Examples, Library Manager, Monitor input, Serial Plotter.
   Uses helpers from app.js: $, esc, api, out, S, showTab, refreshProjects, selectProject. */

/* ================================================================ Examples */
const EX = { list: [], pick: null };

async function openExamples() {
  const r = await api('/api/examples');
  EX.list = r.examples || [];
  EX.pick = null;
  $('exFind').value = '';
  $('exName').value = '';
  renderExamples();
  $('dlgExamples').showModal();
  $('exFind').focus();
}

function renderExamples() {
  const q = $('exFind').value.trim().toLowerCase();
  const groups = {};
  EX.list.filter(e => !q || (e.group + ' ' + e.name).toLowerCase().includes(q))
    .forEach(e => (groups[e.group] = groups[e.group] || []).push(e));
  $('exList').innerHTML = Object.entries(groups).map(([g, items]) => `<h4>${esc(g)}</h4>` + items.map(e =>
    `<div class="item ${EX.pick === e.path ? 'active' : ''}" data-path="${esc(e.path)}">${esc(e.name.replace(/^\d+\./, '').replace(/\//g, ' / '))}</div>`).join('')).join('')
    || '<div class="empty">No examples found.</div>';
  $('exList').querySelectorAll('.item').forEach(el => el.onclick = () => {
    EX.pick = el.dataset.path;
    const base = EX.pick.split(/[\\/]/).pop();
    if (!$('exName').value || $('exName').dataset.auto === '1') { $('exName').value = 'my_' + base; $('exName').dataset.auto = '1'; }
    renderExamples();
  });
}

async function createFromExample(e) {
  e.preventDefault();
  if (!EX.pick) return alert('Choose an example first.');
  const name = $('exName').value.trim();
  if (!/^[A-Za-z0-9_.-]+$/.test(name)) return $('exName').reportValidity();
  const r = await api('/api/examples/new', { path: EX.pick, name });
  if (!r.ok) return alert(r.out);
  $('dlgExamples').close();
  await refreshProjects();
  selectProject(name);
}

/* ================================================================ Library Manager */
const LIB = { mode: 'find', timer: null };

function openLibs() {
  $('dlgLibs').showModal();
  setLibMode(LIB.mode);
  $('libFind').focus();
}

function setLibMode(m) {
  LIB.mode = m;
  $('libSeg').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.v === m));
  libsRefresh();
}

async function libsRefresh() {
  if (!$('dlgLibs').open) return;
  if (LIB.mode === 'installed') {
    const r = await api('/api/libs/installed');
    const libs = r.libraries || [];
    $('libInfo').innerHTML = `${libs.length} installed in <code>${esc(r.folder || '')}</code>. Built into Ardzy (made for this board): ${(r.builtin || []).join(', ')}.`;
    $('libList').innerHTML = libs.map(l => `<div class="lib">
        <div><b>${esc(l.name)}</b> <span class="hint">${esc(l.version)} &middot; ${esc(l.author)}</span>
          <div class="hint">${esc(l.sentence)}</div>
          <div class="hint">headers: ${esc(l.headers.join(', ') || '-')}${l.examples ? ' &middot; ' + l.examples + ' example(s) in Examples' : ''}</div></div>
        <button class="ghost small" data-rm="${esc(l.name)}">Remove</button></div>`).join('') || '<div class="empty">No libraries installed yet: use Find.</div>';
    $('libList').querySelectorAll('[data-rm]').forEach(b => b.onclick = async () => {
      if (!confirm('Remove the library ' + b.dataset.rm + '?')) return;
      const x = await api('/api/libs/remove', { name: b.dataset.rm });
      if (!x.ok) out(x.out, 'err');
      libsRefresh();
    });
    return;
  }
  $('libInfo').textContent = 'Searching ...';
  const r = await api('/api/libs/search', { q: $('libFind').value.trim(), limit: 60 });
  if (!r.ok) { $('libInfo').textContent = r.out || 'The library list could not be loaded (internet needed the first time).'; return; }
  $('libInfo').textContent = `${r.count} libraries found` + (r.count > r.results.length ? ` (showing ${r.results.length})` : '') +
    '. Most libraries that use Wire, SPI, Serial and the pins work; ones made only for one chip (AVR registers, ESP32 radio) do not.';
  $('libList').innerHTML = r.results.map(l => `<div class="lib">
      <div><b>${esc(l.name)}</b> <span class="hint">${esc(l.version)} &middot; ${esc(l.author)}${l.category ? ' &middot; ' + esc(l.category) : ''}</span>
        <div>${esc(l.sentence)}</div>
        <div class="hint">${l.architectures && l.architectures.length && !l.architectures.includes('*') ? 'made for: ' + esc(l.architectures.join(', ')) + ' &middot; ' : ''}${l.dependencies.length ? 'needs: ' + esc(l.dependencies.join(', ')) : ''}</div></div>
      ${l.builtin ? '<span class="badge">built in</span>' : l.installed ? `<span class="badge">installed ${esc(l.installed)}</span>` :
        `<button class="small" data-in="${esc(l.name)}">Install</button>`}</div>`).join('');
  $('libList').querySelectorAll('[data-in]').forEach(b => b.onclick = async () => {
    b.disabled = true; b.textContent = 'Installing ...';
    showTab('output');
    const x = await api('/api/libs/install', { name: b.dataset.in });
    if (!x.ok) { out(x.out, 'err'); b.disabled = false; b.textContent = 'Install'; }
  });
}

/* ================================================================ Monitor input */
async function sendMonitor() {
  const text = $('monIn').value;
  if (!S.connected) return out('No board connected.', 'warn');
  const r = await api('/api/board/serial_in', { text, nl: $('monNl').checked });
  appendLine($('mon'), '> ' + text, r.ok ? 'head' : 'err');
  if (!r.ok) appendLine($('mon'), r.out, 'err');
  $('monIn').value = '';
}

/* ================================================================ Serial Plotter */
const PLOT = { series: {}, order: [], max: 400, paused: false, colors: ['#2f9e58', '#4f8fe0', '#e0884f', '#b65fd6', '#d6b23a', '#3ab8b8', '#e05f8a', '#7d8a2e'] };

function plotLine(line) {
  if (PLOT.paused || /^(===|Started|Stopped|ardzy-app)/.test(line)) return;
  const vals = {};
  const pairs = [...line.matchAll(/([A-Za-z_][\w .-]*?)\s*[:=]\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)/g)];
  if (pairs.length) pairs.forEach(m => vals[m[1].trim()] = parseFloat(m[2]));
  else {
    const nums = line.trim().split(/[\s,;\t]+/).filter(Boolean);
    if (!nums.length || !nums.every(n => /^-?\d+(\.\d+)?([eE][-+]?\d+)?$/.test(n))) return;
    nums.forEach((n, i) => vals['value ' + (i + 1)] = parseFloat(n));
  }
  for (const [k, v] of Object.entries(vals)) {
    if (!PLOT.series[k]) { PLOT.series[k] = []; PLOT.order.push(k); }
  }
  for (const k of PLOT.order) {
    const a = PLOT.series[k];
    a.push(k in vals ? vals[k] : (a.length ? a[a.length - 1] : 0));
    if (a.length > PLOT.max) a.shift();
  }
  drawPlot();
}

function drawPlot() {
  const cv = $('plot'); if (!cv || cv.offsetParent === null) return;
  const W = cv.width = cv.clientWidth * devicePixelRatio, H = cv.height = cv.clientHeight * devicePixelRatio;
  const g = cv.getContext('2d'), css = getComputedStyle(document.body);
  g.clearRect(0, 0, W, H);
  const all = PLOT.order.flatMap(k => PLOT.series[k]);
  if (!all.length) return;
  let lo = Math.min(...all), hi = Math.max(...all);
  if (hi === lo) { hi += 1; lo -= 1; }
  const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
  const L = 56 * devicePixelRatio, B = 8 * devicePixelRatio;
  g.font = `${11 * devicePixelRatio}px Segoe UI, sans-serif`;
  g.fillStyle = css.getPropertyValue('--muted'); g.strokeStyle = css.getPropertyValue('--line'); g.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = B + (H - 2 * B) * i / 4, v = hi - (hi - lo) * i / 4;
    g.beginPath(); g.moveTo(L, y); g.lineTo(W, y); g.stroke();
    g.fillText(Math.abs(v) >= 1000 ? v.toFixed(0) : v.toFixed(2), 4, y + 4);
  }
  PLOT.order.forEach((k, si) => {
    const a = PLOT.series[k];
    g.strokeStyle = PLOT.colors[si % PLOT.colors.length]; g.lineWidth = 2 * devicePixelRatio; g.beginPath();
    a.forEach((v, i) => {
      const x = L + (W - L) * (i + PLOT.max - a.length) / (PLOT.max - 1), y = B + (H - 2 * B) * (hi - v) / (hi - lo);
      i ? g.lineTo(x, y) : g.moveTo(x, y);
    });
    g.stroke();
  });
  $('plotLegend').innerHTML = PLOT.order.map((k, si) => {
    const a = PLOT.series[k];
    return `<span><i style="background:${PLOT.colors[si % PLOT.colors.length]}"></i>${esc(k)} <b>${a.length ? +a[a.length - 1].toFixed(3) : ''}</b></span>`;
  }).join('');
}

/* ================================================================ wiring */
$('btnExamples').onclick = openExamples;
$('exFind').oninput = renderExamples;
$('exName').oninput = () => $('exName').dataset.auto = '0';
$('btnExOk').onclick = createFromExample;
$('btnLibs').onclick = openLibs;
$('libSeg').querySelectorAll('button').forEach(b => b.onclick = e => { e.preventDefault(); setLibMode(b.dataset.v); });
$('libFind').oninput = () => { clearTimeout(LIB.timer); LIB.timer = setTimeout(() => { if (LIB.mode !== 'find') setLibMode('find'); else libsRefresh(); }, 350); };
$('libFind').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); libsRefresh(); } };
$('btnLibZip').onclick = async e => { e.preventDefault(); showTab('output'); const r = await api('/api/libs/zip', {}); if (!r.ok) out(r.out, 'warn'); };
$('monIn').onkeydown = e => { if (e.key === 'Enter') sendMonitor(); };
$('plotPause').onclick = () => { PLOT.paused = !PLOT.paused; $('plotPause').textContent = PLOT.paused ? 'Go on' : 'Pause'; };
$('plotClear').onclick = () => { PLOT.series = {}; PLOT.order = []; drawPlot(); $('plotLegend').innerHTML = ''; };
window.addEventListener('resize', drawPlot);
document.querySelector('.bottom-tabs button[data-tab="plotter"]').addEventListener('click', () => setTimeout(drawPlot, 0));
window.plotLine = plotLine;
window.libsRefresh = libsRefresh;
