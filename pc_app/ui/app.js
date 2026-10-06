/* Ardzy PC app - interface logic. Talks only to the local engine (ardzy_app.py). */
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const TEMPLATES = {
  blocks_sketch: ['Blocks (like Scratch)', 'Snap blocks together in the Blocks view; they become an Arduino sketch. No typing needed.'],
  blocks_fpga: ['FPGA blocks (like Scratch)', 'Hardware from blocks: timers, registers, LEDs, pins, PWM, the ARM. The blocks become Verilog; simulate it, build it.'],
  arduino_sketch: ['Arduino sketch (C++)', 'setup() and loop() in C++, like an Arduino. Arduino libraries, pins J1..J9, LEDs.'],
  board_extras: ['Board LED, buzzer, buttons', 'Status LED, beep and the 2 buttons. No FPGA needed.'],
  python_only: ['Python program', 'Runs on the ARM, no FPGA change. Good first step.'],
  c_program: ['C program', 'Compiled on the board with gcc, then run.'],
  fpga_blink: ['FPGA: blink LEDs', 'Verilog counter on the 4 LEDs. Shows the FPGA flow.'],
  fpga_python_leds: ['FPGA + Python', 'AXI GPIO in the FPGA, LEDs driven from Python.'],
};
const EDITABLE = /\.(py|c|h|v|sv|vhd|xdc|tcl|sh|txt|json|md|dtsi|dts|csv|ino|cpp|hpp)$|^Makefile$/;

const S = {
  projects: [], project: localStorage.getItem('ardzy.project') || '', files: [],
  tabs: [], active: null, cm: null,
  evSince: 0, connected: false, board: null, status: null, monCursor: null, busy: null,
  serialOpen: null, newTpl: 'arduino_sketch',
};

async function api(path, body, method) {
  const opt = { method: method || (body ? 'POST' : 'GET'), headers: { 'X-Ardzy-Token': window.ARDZY_TOKEN } };
  if (body) { opt.body = JSON.stringify(body); opt.headers['Content-Type'] = 'application/json'; }
  const r = await fetch(path, opt);
  return r.json();
}

/* ---------- output panels ---------- */
function appendLine(pre, text, cls, time) {
  const atEnd = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 30;
  const span = document.createElement('span');
  if (cls) span.className = 'l-' + cls;
  span.textContent = text + '\n';
  if (time) { const t = document.createElement('span'); t.className = 'l-t'; t.textContent = time + '  '; pre.appendChild(t); }
  pre.appendChild(span);
  while (pre.childNodes.length > 4000) pre.removeChild(pre.firstChild);
  if (atEnd) pre.scrollTop = pre.scrollHeight;
}
function out(text, cls, t) { appendLine($('out'), text, cls, t || new Date().toTimeString().slice(0, 8)); }
function markNew(tab) {
  const b = document.querySelector(`.bottom-tabs button[data-tab="${tab}"]`);
  if (b && !b.classList.contains('active')) b.classList.add('new');
}
function showTab(tab) {
  document.querySelectorAll('.bottom-tabs button[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.dataset.panel === tab));
  const b = document.querySelector(`.bottom-tabs button[data-tab="${tab}"]`); if (b) b.classList.remove('new');
  if (tab === 'serial') refreshPorts();
  if (tab === 'pins') loadPins();
  if (tab === 'board') refreshStatus();
}

/* ---------- events from the engine (jobs, console, serial) ---------- */
async function pollEvents() {
  try {
    const r = await api('/api/events?since=' + S.evSince);
    for (const e of r.events) {
      S.evSince = e.id;
      if (e.kind === 'job') {
        if (e.state === 'start') out('> ' + e.text, 'head', e.t);
        if (e.state === 'ok' && e.text === 'Upload') { showTab('monitor'); refreshProjects(); }
        if (e.state === 'ok' && e.text === 'Build FPGA') refreshProjects();
        if (e.state !== 'start' && window.onJobEnd && !S.evReplay) onJobEnd(e.text, e.state);
        if (e.text === 'Build FPGA' && e.state !== 'start' && window.BK_after) BK_after(e.state === 'ok');
        if (e.text === 'Simulate' && e.state === 'ok' && window.simLoad) simLoad();
        if (e.text === 'Simulate' && e.state === 'fail' && typeof CP !== 'undefined' && CP.problems.length) showTab('problems');
        if (e.text === 'Install library' && e.state !== 'start' && window.libsRefresh) libsRefresh();
        continue;
      }
      if (e.kind === 'serial') {
        if (e.state === 'open') S.serialOpen = true;
        if (e.state === 'closed') S.serialOpen = false;
        appendLine($('ser'), e.text, e.state ? 'head' : '');
        if (e.state !== undefined) $('btnSerOpen').textContent = S.serialOpen ? 'Close' : 'Open';
        markNew('serial');
        continue;
      }
      appendLine($('out'), e.text, e.kind === 'out' ? '' : e.kind, e.t);
      markNew('output');
    }
    setBusy(r.busy);
  } catch (e) { /* engine restarting */ }
  setTimeout(pollEvents, 400);
}
function setBusy(b) {
  S.busy = b;
  $('stJob').textContent = b ? b + ' ...' : '';
  $('stJob').classList.toggle('busy', !!b);
  ['btnCheck', 'btnUpload', 'btnBuild'].forEach(id => $(id).disabled = !!b);
}

/* ---------- board ---------- */
function setBoard(info, host) {
  S.connected = !!info; S.board = info ? { ...info, host } : null;
  $('boardDot').className = 'dot' + (info ? ' on' : '');
  $('boardName').textContent = info ? `${info.hostname}  (${host})` : 'No board';
  $('stConn').textContent = info ? TF('connected: {0}', info.hostname + ' ' + host) : T('offline');
  S.monCursor = null;
  refreshStatus();
}
async function refreshApp() {
  const r = await api('/api/app');
  $('stVer').textContent = 'Ardzy ' + r.version + (r.stage ? ' ' + r.stage : '');
  const host = r.board.host || null, cur = S.board ? S.board.host : null;
  if (host !== cur || !S.board && host) { if (host) setBoard(r.board.info, host); else setBoard(null); }
  S.settings = r.settings;
}
async function scan(showDialog) {
  out('Scanning the network for Ardzy boards ...', 'head');
  const r = await api('/api/scan', {});
  renderBoardList(r.boards || []);
  if (showDialog || (r.boards || []).length !== 1) { if (!$('dlgBoards').open) $('dlgBoards').showModal(); }
  else if (!S.connected) connect(r.boards[0].host, r.boards[0].port);
}
function renderBoardList(boards) {
  $('boardList').innerHTML = boards.length ? boards.map(b => `
    <div class="item" data-host="${esc(b.host)}" data-port="${b.port || 80}">
      <span class="dot on"></span>
      <div><b>${esc(b.hostname)}</b> <span class="meta">${esc(b.host)} &middot; ${esc(b.os || '')} &middot; FPGA ${esc(b.fpga || '?')}${b.current ? ' &middot; running ' + esc(b.current) : ''}</span></div>
    </div>`).join('') : '<div class="empty">No board answered. Check power and the network cable, then Scan again, or type the address below.</div>';
  $('boardList').querySelectorAll('.item').forEach(el => el.onclick = () => { connect(el.dataset.host, +el.dataset.port); $('dlgBoards').close(); });
}
async function connect(host, port) {
  const r = await api('/api/connect', { host, port: port || 80 });
  if (r.ok) setBoard(r.info, r.host || host); else { out('Cannot connect to ' + host + ': ' + r.out, 'err'); setBoard(null); }
}
async function refreshStatus() {
  if (!S.connected) { $('boardInfo').innerHTML = '<div class="empty">No board connected. Click Scan.</div>'; return; }
  const r = await api('/api/board/status');
  if (!r.ok) { $('boardDot').className = 'dot err'; $('stConn').textContent = 'board not answering'; return; }
  $('boardDot').className = 'dot on';
  const s = r.status, b = S.board || {};
  S.status = s;
  if (S.project) $('chkBoot').checked = s.default === S.project;
  const cards = [
    ['Board', b.hostname], ['Address', (b.ips || [b.host]).join(', ')],
    ['Ardzy image', b.image && b.image.ARDZY_VERSION ? `${b.image.ARDZY_VERSION} (${b.image.BUILD_DATE})` : '-'],
    ['System', b.os], ['Kernel', b.kernel],
    ['FPGA', s.fpga], ['Loaded project', s.current || '-'], ['Program', s.running ? 'running' : 'stopped'],
    ['At boot', s.default || '-'], ['Memory used', s.mem], ['CPU load', s.load], ['Uptime', s.uptime],
  ];
  if (s.temp) cards.push(['Chip temperature', s.temp]);
  if (s.safemode) cards.push(['SAFE MODE', 'default project skipped']);
  $('boardInfo').innerHTML = cards.map(([k, v]) => `<div class="card"><small>${k}</small><b title="${esc(v)}">${esc(v)}</b></div>`).join('');
}
async function pollMonitor() {
  if (S.connected) {
    try {
      const first = S.monCursor === null;
      const r = await api('/api/board/log', { cursor: S.monCursor || '' });
      if (r.ok) {
        if (first) $('mon').textContent = '';
        for (const l of r.lines || []) {
          monAdd(l, /error|traceback|failed/i.test(l) ? 'err' : (l.startsWith('===') ? 'head' : ''));
          if (window.plotLine && !first) plotLine(l);
        }
        if ((r.lines || []).length && !first) markNew('monitor');
        S.monCursor = r.cursor || null;     // null = journal still empty: next poll starts fresh
      }
    } catch (e) { }
  }
  setTimeout(pollMonitor, 1000);
}

/* the monitor keeps every line (up to 20000): the filter, the times and Pause work on that list */
S.mon = []; S.monPaused = false; S.monWaiting = 0;
function monShow(e) {
  const f = $('monFind').value.trim().toLowerCase();
  return !f || e.text.toLowerCase().includes(f);
}
function monAdd(text, cls) {
  const e = { t: new Date().toTimeString().slice(0, 8), text, cls };
  S.mon.push(e);
  if (S.mon.length > 20000) S.mon.splice(0, 2000);
  if (S.monPaused) { S.monWaiting++; monInfo(); return; }
  if (monShow(e)) appendLine($('mon'), text, cls, e.t);
}
function monRender() {
  const pre = $('mon');
  pre.textContent = '';
  S.mon.filter(monShow).slice(-4000).forEach(e => appendLine(pre, e.text, e.cls, e.t));
  pre.scrollTop = pre.scrollHeight;
  monInfo();
}
function monInfo() {
  const f = $('monFind').value.trim();
  $('monInfo').textContent = (S.monPaused ? `paused, ${S.monWaiting} new line${S.monWaiting === 1 ? '' : 's'} waiting` : '')
    + (f ? (S.monPaused ? ' · ' : '') + `${S.mon.filter(monShow).length} of ${S.mon.length} lines` : '');
}
function monWire() {
  $('monFind').oninput = monRender;
  $('monTime').checked = !!pref('montime', '');
  $('mon').classList.toggle('hide-t', !$('monTime').checked);
  $('monTime').onchange = () => { setPref('montime', $('monTime').checked ? '1' : ''); $('mon').classList.toggle('hide-t', !$('monTime').checked); };
  $('monPause').onclick = () => {
    S.monPaused = !S.monPaused;
    $('monPause').textContent = S.monPaused ? 'Resume' : 'Pause';
    if (!S.monPaused) { S.monWaiting = 0; monRender(); } else monInfo();
  };
  const shown = () => S.mon.filter(monShow).map(e => ($('monTime').checked ? e.t + '  ' : '') + e.text).join('\n');
  $('monCopy').onclick = async () => {
    try { await navigator.clipboard.writeText(shown()); out('Monitor copied (' + S.mon.filter(monShow).length + ' lines).', 'ok'); }
    catch (e) { out('Could not copy: ' + e, 'err'); }
  };
  $('monSave').onclick = async () => {
    const r = await api('/api/savelog', { name: 'monitor', text: S.mon.map(e => e.t + '  ' + e.text).join('\n') + '\n' });
    out(r.ok ? 'Monitor saved: ' + r.path : 'Not saved: ' + r.out, r.ok ? 'ok' : 'err');
  };
}

/* the bottom panel: drag its top edge, double-click it or press Ctrl+J to hide / show; both are remembered */
function panelWire() {
  const b = $('bottom'), h = +pref('panelh', 0);
  if (h) b.style.height = h + 'px';
  const setHidden = on => {
    b.classList.toggle('collapsed', on);
    $('btnPanel').textContent = on ? 'Show' : 'Hide';
    setPref('panelhide', on ? '1' : '');
    if (S.cm) S.cm.refresh();
    setTimeout(() => window.dispatchEvent(new Event('resize')), 0);   // (the views fit themselves again)
  };
  setHidden(!!pref('panelhide', ''));
  S.panelToggle = () => setHidden(!b.classList.contains('collapsed'));
  $('btnPanel').onclick = S.panelToggle;
  const grip = $('bottomResize');
  grip.ondblclick = S.panelToggle;
  grip.onmousedown = e => {
    e.preventDefault();
    if (b.classList.contains('collapsed')) setHidden(false);
    const y0 = e.clientY, h0 = b.getBoundingClientRect().height, max = window.innerHeight - 160;
    grip.classList.add('drag');
    const move = ev => { b.style.height = Math.max(120, Math.min(max, h0 + (y0 - ev.clientY))) + 'px'; };
    const up = () => {
      grip.classList.remove('drag');
      document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up);
      setPref('panelh', Math.round(b.getBoundingClientRect().height));
      if (S.cm) S.cm.refresh();
      window.dispatchEvent(new Event('resize'));
    };
    document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
  };
  // a tab clicked while the panel is hidden shows it again
  document.querySelectorAll('.bottom-tabs button[data-tab]').forEach(t => t.addEventListener('click', () => { if (b.classList.contains('collapsed')) setHidden(false); }));
}

/* ---------- projects + files ---------- */
async function refreshProjects() {
  const r = await api('/api/projects');
  S.projects = r.projects || [];
  $('projectList').innerHTML = S.projects.map(p => `
    <div class="item ${p.name === S.project ? 'active' : ''}" data-p="${esc(p.name)}">
      <span>${esc(p.name)}</span>${p.kind === 'arduino' ? '<span class="badge cpp" title="Arduino sketch (C++)">C++</span>' : ''}${p.bit ? '<span class="badge" title="has an FPGA design: ' + esc(p.bit) + '">FPGA</span>' : ''}
      ${S.status && S.status.current === p.name ? '<small>on board</small>' : ''}
    </div>`).join('') || '<div class="empty">No projects yet: click + New.</div>';
  $('projectList').querySelectorAll('.item').forEach(el => el.onclick = () => selectProject(el.dataset.p));
  if (S.project && !S.projects.find(p => p.name === S.project)) S.project = '';
  if (!S.project && S.projects.length) S.project = S.projects[0].name;
  renderFiles();
}
function renderFiles() {
  const p = S.projects.find(p => p.name === S.project);
  $('stProject').textContent = p ? TF('project: {0}', p.name) : '';
  $('tbProject').textContent = p ? p.name : '';
  if (!p) { $('projectFiles').innerHTML = ''; return; }
  $('projectFiles').innerHTML = `<h3><span>${esc(p.name)}</span><button class="ghost small" id="btnNewFile" title="New file">+ file</button></h3>` +
    p.files.map(f => `<div class="file ${EDITABLE.test(f) ? '' : 'bin'}" data-f="${esc(f)}" title="${esc(f)}">${esc(f)}</div>`).join('') +
    (p.bit && !p.files.includes(p.bit) ? `<div class="file bin" title="newest bitstream in the Vivado project">${esc(p.bit)}</div>` : '') +
    `<div class="row"><button class="ghost small" id="btnFolder">Open folder</button>${p.files.some(f => f.endsWith('.xpr')) || p.buildable ? '<button class="ghost small" id="btnVivado">Vivado</button>' : ''}</div>`;
  $('projectFiles').querySelectorAll('.file:not(.bin)').forEach(el => el.onclick = () => openFile(p.name, el.dataset.f));
  $('btnFolder').onclick = () => api('/api/open', { what: 'folder', project: p.name });
  if ($('btnVivado')) $('btnVivado').onclick = () => api('/api/open', { what: 'vivado', project: p.name });
  $('btnNewFile').onclick = async () => {
    const n = prompt('New file name (for example helper.py, top.v, devices.dtsi):');
    if (!n) return;
    const r = await api('/api/file/new', { project: p.name, name: n });
    if (!r.ok) return out(r.out, 'err');
    await refreshProjects(); openFile(p.name, n);
  };
  if (S.status) $('chkBoot').checked = S.status.default === p.name;
}
function selectProject(name) {
  S.project = name; localStorage.setItem('ardzy.project', name);
  refreshProjects();
  const p = S.projects.find(p => p.name === name);
  const first = p && (p.files.find(f => f === name + '.ino') || p.files.find(f => /\.ino$/.test(f)) ||
    p.files.find(f => f === 'main.py') || p.files.find(f => /\.(py|c|v)$/.test(f)));
  if (first) openFile(name, first);
}

/* ---------- editor ---------- */
function modeFor(name) {
  if (/\.py$/.test(name)) return 'python';
  if (/\.(v|sv)$/.test(name)) return 'verilog';
  if (/\.(ino|cpp|hpp|h)$/.test(name)) return 'text/x-c++src';
  if (/\.c$/.test(name)) return 'text/x-csrc';
  if (/\.(tcl|xdc)$/.test(name)) return 'tcl';
  if (/\.sh$/.test(name)) return 'shell';
  if (/\.(dts|dtsi)$/.test(name)) return 'text/x-csrc';
  return null;
}
const pref = (k, d) => { try { const v = localStorage.getItem('ardzy.' + k); return v === null ? d : v; } catch (e) { return d; } };
const setPref = (k, v) => { try { localStorage.setItem('ardzy.' + k, v); } catch (e) { } };
function editorFont(px) {
  px = Math.max(10, Math.min(28, +px || 14));
  setPref('font', px);
  document.querySelector('.CodeMirror').style.fontSize = px + 'px';
  S.cm.refresh();
}
function editorWrap(on) { setPref('wrap', on ? '1' : ''); S.cm.setOption('lineWrapping', !!on); }
function initEditor() {
  S.cm = CodeMirror($('editor'), {
    lineNumbers: true, indentUnit: 4, tabSize: 4, indentWithTabs: false, matchBrackets: true, autoCloseBrackets: true,
    styleActiveLine: true, lineWrapping: !!pref('wrap', ''),
    highlightSelectionMatches: { minChars: 2, showToken: /\w/, annotateScrollbar: false },
    extraKeys: {
      Tab: cm => cm.somethingSelected() ? cm.indentSelection('add') : cm.replaceSelection('    '),
      'Shift-Tab': cm => cm.indentSelection('subtract'),
      'Ctrl-S': () => saveActive(), 'Ctrl-F': 'findPersistent', 'Ctrl-H': 'replace', 'Ctrl-G': 'jumpToLine',
      F3: 'findPersistentNext', 'Shift-F3': 'findPersistentPrev', 'Ctrl-/': 'toggleComment',
      'Ctrl-=': () => editorFont(+pref('font', 14) + 1), 'Ctrl--': () => editorFont(+pref('font', 14) - 1), 'Ctrl-0': () => editorFont(14),
      'Alt-Z': cm => editorWrap(!cm.getOption('lineWrapping')),
    },
  });
  S.cm.on('change', () => {
    const t = S.tabs.find(t => t.key === S.active);
    if (t && !t.loading) { t.dirty = S.cm.getValue() !== t.saved; renderTabs(); }
  });
  S.cm.on('cursorActivity', cm => {
    const c = cm.getCursor(), sel = cm.getSelection();
    $('stCursor').textContent = S.active ? `Ln ${c.line + 1}, Col ${c.ch + 1}` + (sel ? ` (${sel.length} selected)` : '') : '';
  });
  editorFont(pref('font', 14));
}
async function openFile(project, name) {
  const key = project + '/' + name;
  let t = S.tabs.find(t => t.key === key);
  if (!t) {
    const r = await api('/api/file?project=' + encodeURIComponent(project) + '&name=' + encodeURIComponent(name));
    if (!r.ok) return out(r.out, 'err');
    t = { key, project, name, saved: r.text, doc: CodeMirror.Doc(r.text, modeFor(name)), dirty: false };
    S.tabs.push(t);
  }
  activate(key);
}
function activate(key) {
  const t = S.tabs.find(t => t.key === key);
  if (!t) return;
  S.active = key;
  t.loading = true; S.cm.swapDoc(t.doc); t.loading = false;
  $('welcome').style.display = 'none';
  renderTabs(); S.cm.refresh(); S.cm.focus();
}
function renderTabs() {
  $('editorTabs').innerHTML = S.tabs.map(t => `<div class="tab ${t.key === S.active ? 'active' : ''} ${t.dirty ? 'dirty' : ''}" data-k="${esc(t.key)}" title="${esc(t.key)}">
    <span class="name">${esc(t.name)}</span><span class="x" data-x="${esc(t.key)}">&times;</span></div>`).join('');
  $('editorTabs').querySelectorAll('.tab').forEach(el => el.onclick = e => {
    if (e.target.dataset.x) return closeTab(e.target.dataset.x);
    activate(el.dataset.k);
  });
}
function closeTab(key) {
  const t = S.tabs.find(t => t.key === key);
  if (t && t.dirty && !confirm(t.name + ' has unsaved changes. Close anyway?')) return;
  S.tabs = S.tabs.filter(t => t.key !== key);
  if (S.active === key) {
    S.active = null;
    if (S.tabs.length) activate(S.tabs[S.tabs.length - 1].key);
    else { S.cm.swapDoc(CodeMirror.Doc('')); $('welcome').style.display = ''; }
  }
  renderTabs();
}
async function saveTab(t) {
  const text = t.doc.getValue();
  const r = await api('/api/file', { project: t.project, name: t.name, text });
  if (r.ok) { t.saved = text; t.dirty = false; renderTabs(); } else out('Save failed: ' + r.out, 'err');
  return r.ok;
}
async function saveActive() { const t = S.tabs.find(t => t.key === S.active); if (t) await saveTab(t); }
async function saveProject(p) { for (const t of S.tabs.filter(t => t.project === p && t.dirty)) await saveTab(t); }

/* ---------- actions ---------- */
function needProject() { if (!S.project) { out('Choose a project first (left side).', 'warn'); return false; } return true; }
async function doCheck() { if (!needProject()) return; await saveProject(S.project); showTab('output'); await api('/api/verify', { project: S.project }); }
async function doUpload() {
  if (!needProject()) return;
  await saveProject(S.project); showTab('output');
  if (!S.connected) { out('No board connected: scanning ...', 'warn'); await scan(false); if (!S.connected) return; }
  S.monCursor = null;
  const r = await api('/api/upload', { project: S.project, run: true, default: $('chkBoot').checked });
  if (!r.ok) out(r.out, 'err');
}
async function doBuild() { if (!needProject()) return; await saveProject(S.project); showTab('output'); const r = await api('/api/build', { project: S.project }); if (!r.ok) out(r.out, 'err'); }
async function boardAction(action, project) {
  if (!S.connected) return out('No board connected.', 'warn');
  await api('/api/board/action', { action, project: project || '' });
  refreshStatus(); refreshProjects();
}

/* ---------- serial ---------- */
async function refreshPorts() {
  const r = await api('/api/serial/ports');
  const cur = $('serPort').value;
  $('serPort').innerHTML = (r.ports || []).map(p => `<option value="${esc(p.port)}">${esc(p.port)}  ${esc(p.desc)}</option>`).join('') || '<option value="">no COM ports found</option>';
  if (cur) $('serPort').value = cur;
  S.serialOpen = !!r.open; $('btnSerOpen').textContent = S.serialOpen ? 'Close' : 'Open';
}

/* ---------- pins reference (data: pins.json, made by scripts/make_pins.py) ---------- */
async function loadPins() {
  if ($('pinTables').dataset.done) return;
  const d = await (await fetch('pins.json')).json();
  const xdc = (pin, port) => `set_property -dict {PACKAGE_PIN ${pin} IOSTANDARD LVCMOS33} [get_ports {${port}}]`;
  const tbl = (title, head, rows) => `<h4>${title}</h4><table><tr>${head.map(h => `<th>${h}</th>`).join('')}</tr>${rows.join('')}</table>`;
  const conn = d.connectors.map(r => `<tr class="copy" data-x="${esc(xdc(r.pin, r.port))}">
      <td>${r.conn}</td><td>${r.cpin}</td><td class="pin">${r.pin}</td><td class="mono">${r.port}</td><td>${r.bitmain}</td><td class="mono">${r.old}</td></tr>`);
  const other = d.pl_other.map(r => `<tr class="copy" data-x="${esc(xdc(r.pin, r.port))}">
      <td>${esc(r.what)}</td><td class="pin">${r.pin}</td><td class="mono">${esc(r.port)}</td><td>${esc(r.notes)}</td></tr>`);
  const layout = d.layout.map(r => `<tr><td>${r.pin}</td><td>${esc(r.func)}</td></tr>`);
  const ps = d.ps.map(r => `<tr><td>${esc(r.name)}</td><td class="pin">MIO${r.mio}</td><td>${esc(r.volt)}</td><td class="mono">${esc(r.use)}</td></tr>`);
  const banks = d.banks.map(r => `<tr><td>${esc(r.bank)}</td><td>${r.volt}</td><td>${r.side}</td><td>${esc(r.used_for)}</td></tr>`);
  $('pinTables').innerHTML =
    tbl('Connectors J1..J9: FPGA pins (port jN[0..3])', ['Conn', 'Pin', 'FPGA pin', 'Port', 'Bitmain name', 'old name'], conn) +
    tbl('Other FPGA pins', ['What', 'FPGA pin', 'Port', 'Notes'], other) +
    tbl('Every connector J1..J9: the 18 pins', ['Pin', 'Function'], layout) +
    tbl('ARM side (Linux / Python)', ['What', 'Pin', 'Voltage', 'Use'], ps) +
    tbl('I/O banks', ['Bank', 'Voltage', 'Side', 'Used for'], banks);
  $('pinTables').dataset.done = '1';
  $('pinTables').querySelectorAll('tr.copy').forEach(tr => tr.onclick = async () => {
    try { await navigator.clipboard.writeText(tr.dataset.x); out('Copied: ' + tr.dataset.x, 'ok'); }
    catch (e) { out(tr.dataset.x); }
  });
}
function filterPins() {
  const q = $('pinFind').value.trim().toLowerCase();
  $('pinTables').querySelectorAll('tr').forEach(tr => {
    if (tr.querySelector('th')) return;
    tr.classList.toggle('hidden', !!q && !tr.textContent.toLowerCase().includes(q));
  });
}

/* ---------- dialogs ---------- */
function openNew() {
  $('newName').value = '';
  $('newTemplates').innerHTML = Object.entries(TEMPLATES).map(([k, [t, d]]) =>
    `<div class="tpl ${k === S.newTpl ? 'active' : ''}" data-t="${k}"><b>${t}</b><small>${d}</small></div>`).join('');
  $('newTemplates').querySelectorAll('.tpl').forEach(el => el.onclick = () => {
    S.newTpl = el.dataset.t; $('newTemplates').querySelectorAll('.tpl').forEach(x => x.classList.toggle('active', x === el));
  });
  $('dlgNew').showModal(); $('newName').focus();
}

/* ---------- wiring ---------- */
function wire() {
  $('btnCheck').onclick = doCheck;
  $('btnUpload').onclick = doUpload;
  $('btnBuild').onclick = doBuild;
  $('btnStop').onclick = () => boardAction('stop');
  $('btnRestart').onclick = () => boardAction('restart');
  $('chkBoot').onchange = () => S.connected && S.project && boardAction('default', $('chkBoot').checked ? S.project : '');
  $('btnScan').onclick = () => scan(true);
  $('boardPill').onclick = () => { $('dlgBoards').showModal(); scan(true); };
  $('btnNewProject').onclick = openNew;
  $('btnWeb').onclick = () => api('/api/open', { what: 'web' });
  $('btnUnload').onclick = () => boardAction('unload');
  $('btnDisconnect').onclick = async () => { await api('/api/disconnect', {}); setBoard(null); };
  $('btnClear').onclick = () => {
    const tab = document.querySelector('.bottom-tabs button.active').dataset.tab;
    const pre = { output: 'out', monitor: 'mon', serial: 'ser', regs: 'regOut' }[tab];
    if (pre) $(pre).textContent = '';
  };
  document.querySelectorAll('.bottom-tabs button[data-tab]').forEach(b => b.onclick = () => showTab(b.dataset.tab));
  $('btnPeek').onclick = async () => { const r = await api('/api/board/peek', { addr: $('regAddr').value.trim(), n: 4 }); $('regOut').textContent = r.out || ''; };
  $('btnPoke').onclick = async () => {
    const r = await api('/api/board/poke', { addr: $('regAddr').value.trim(), value: $('regVal').value.trim() });
    $('regOut').textContent = r.ok ? 'written' : (r.out || 'failed'); if (r.ok) $('btnPeek').click();
  };
  $('btnSerRefresh').onclick = refreshPorts;
  $('pinFind').oninput = filterPins;
  $('btnSerOpen').onclick = async () => {
    const r = S.serialOpen ? await api('/api/serial/close', {}) : await api('/api/serial/open', { port: $('serPort').value, baud: +$('serBaud').value });
    if (!r.ok) appendLine($('ser'), r.out, 'err');
  };
  $('serIn').onkeydown = async e => {
    if (e.key !== 'Enter') return;
    const r = await api('/api/serial/send', { text: $('serIn').value });
    if (!r.ok) appendLine($('ser'), r.out, 'err');
    $('serIn').value = '';
  };
  $('btnNewOk').onclick = async e => {
    e.preventDefault();
    const name = $('newName').value.trim();
    if (!/^[A-Za-z0-9_.-]+$/.test(name)) return $('newName').reportValidity();
    const r = await api('/api/project/new', { name, template: S.newTpl });
    if (!r.ok) return alert(r.out);
    $('dlgNew').close(); await refreshProjects(); selectProject(name);
  };
  $('btnRescan').onclick = e => { e.preventDefault(); scan(true); };
  $('btnManual').onclick = async e => {
    e.preventDefault();
    const v = $('manualHost').value.trim(); if (!v) return;
    // "name", "1.2.3.4", "1.2.3.4:8080", "fe80::1%13" or "[fe80::1%13]:8080"
    let h = v, p = 80;
    const m = v.match(/^\[(.+)\]:(\d+)$/) || (v.split(':').length === 2 ? v.match(/^(.+):(\d+)$/) : null);
    if (m) { h = m[1]; p = +m[2]; }
    await connect(h, p);
    if (S.connected) $('dlgBoards').close();
  };
  $('btnSettings').onclick = async () => {
    const r = await api('/api/app');
    $('setWs').value = r.settings.workspace; $('setViv').value = r.settings.vivado; $('setHosts').value = (r.settings.manual_hosts || []).join(', ');
    $('setTool').value = r.settings.fpga_tool || 'builtin';
    const tc = await api('/api/fpga/toolchain');
    $('setToolInfo').textContent = tc.builtin ? 'Built-in toolchain: ' + tc.dir : 'Built-in toolchain not found (tools/fpga).';
    $('setTheme').value = pref('theme', ''); $('setFont').value = String(pref('font', 14)); $('setWrap').checked = !!pref('wrap', '');
    $('dlgSettings').showModal();
  };
  $('btnSetOk').onclick = async e => {
    e.preventDefault();
    await api('/api/settings', { workspace: $('setWs').value.trim(), vivado: $('setViv').value.trim(), manual_hosts: $('setHosts').value.split(','),
      fpga_tool: $('setTool').value });
    setTheme($('setTheme').value); editorFont($('setFont').value); editorWrap($('setWrap').checked);
    $('dlgSettings').close(); refreshProjects();
  };
  $('setTheme').onchange = () => setTheme($('setTheme').value);          // (a preview right away)
  $('setKeys').onclick = e => { e.preventDefault(); $('dlgKeys').showModal(); };
  monWire(); panelWire();
  document.addEventListener('keydown', e => {
    if (e.key === 'F1') { e.preventDefault(); if (!$('dlgKeys').open) $('dlgKeys').showModal(); return; }
    if (!e.ctrlKey) return;
    const k = e.key.toLowerCase();
    if (k === 'j') { e.preventDefault(); S.panelToggle(); }
    const views = ['code', 'board', 'io', 'tools', 'gallery', 'learn', 'map', 'system', 'blocks'];
    if (!e.shiftKey && !e.altKey && /^[1-9]$/.test(k)) { e.preventDefault(); showView(views[+k - 1]); }
    if (k === 'u') { e.preventDefault(); doUpload(); }
    if (k === 'r') { e.preventDefault(); doCheck(); }
    if (k === 's') { e.preventDefault(); saveActive(); }
  });
  window.addEventListener('beforeunload', e => { if (S.tabs.some(t => t.dirty)) { e.preventDefault(); e.returnValue = ''; } });
}

function setTheme(t) {
  setPref('theme', t || '');
  if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
}

(async function start() {
  initEditor(); wire();
  // the other scripts (views, Blockly ...) first: what follows uses them (and they listen to the replayed output)
  if (document.readyState !== 'complete') await new Promise(r => window.addEventListener('load', r, { once: true }));
  await refreshApp();
  await refreshProjects();
  const hp = (location.hash.match(/project=([\w.-]+)/) || [])[1];   // a link to a project: #project=blink
  if (hp && S.projects.some(p => p.name === hp)) S.project = hp;
  if (S.project) selectProject(S.project);
  pollEvents(); pollMonitor();
  const hv = (location.hash.match(/view=(\w+)/) || [])[1] || (window.appStartView && appStartView());   // #view=map, or App settings
  if (hv && hv !== 'code' && window.showView) showView(hv);
  const ht = (location.hash.match(/tab=(\w+)/) || [])[1];      // and to a bottom tab: #tab=watch
  if (ht) showTab(ht);
  setInterval(refreshApp, 5000);
  setInterval(() => S.connected && document.querySelector('.panel.active')?.dataset.panel === 'board' && refreshStatus(), 3000);
  setInterval(() => S.connected && api('/api/board/status').then(r => { if (r.ok) { S.status = r.status; $('boardDot').className = 'dot on'; } else { $('boardDot').className = 'dot err'; } }), 4000);
})();
