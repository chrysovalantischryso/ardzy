/* Ardzy - tools like the Arduino IDE's and Vivado's:
     Auto Format (Ctrl+T), files and projects: rename, delete (to the workspace's _trash), duplicate, archive (zip);
     FPGA projects: the build report (utilisation and timing) and I/O planning (each port on a board pin).
   Uses app.js (S, $, esc, api, out, T, TF, refreshProjects, openFile, selectProject, showTab). */

const PT = { menu: null };

/* ---------------- Auto Format ---------------- */
// re-indent with the language's own rules; only for languages where the indent does not change the meaning
const FORMAT_MODES = /^(text\/x-c|text\/x-c\+\+src|text\/x-csrc|javascript|go|rust|verilog|lua|text\/x-java)/;
function autoFormat() {
  const cm = S.cm, t = S.tabs.find(x => x.key === S.active);
  if (!cm || !t) return;
  const mode = cm.getOption('mode'), name = typeof mode === 'string' ? mode : (mode && mode.name) || '';
  if (!FORMAT_MODES.test(name)) {
    return out(TF('Auto Format is for C, C++, Arduino, JavaScript, Go, Rust, Verilog and Lua; {0} is left as it is (its indentation is part of the program).', t.name), 'warn');
  }
  const cur = cm.getCursor(), top = cm.getScrollInfo().top;
  cm.operation(() => {
    for (let i = 0; i < cm.lineCount(); i++) {
      const line = cm.getLine(i);
      if (/\s+$/.test(line)) cm.replaceRange('', { line: i, ch: line.replace(/\s+$/, '').length }, { line: i, ch: line.length });
      cm.indentLine(i, 'smart');
    }
    const last = cm.lineCount() - 1;
    if (cm.getLine(last) !== '') cm.replaceRange('\n', { line: last, ch: cm.getLine(last).length });
  });
  cm.setCursor(cur); cm.scrollTo(null, top);
  out(TF('{0}: formatted (indentation and spaces at line ends). Ctrl+Z takes it back.', t.name), 'ok');
}

/* ---------------- a small menu ---------------- */
function ptMenu(x, y, items) {
  ptMenuClose();
  const m = document.createElement('div');
  m.className = 'ptmenu';
  m.innerHTML = items.map((it, i) => it === '-' ? '<hr>' : `<button data-i="${i}" ${it.disabled ? 'disabled' : ''}>${esc(it.label)}</button>`).join('');
  document.body.appendChild(m);
  const r = m.getBoundingClientRect();
  m.style.left = Math.min(x, innerWidth - r.width - 8) + 'px';
  m.style.top = Math.min(y, innerHeight - r.height - 8) + 'px';
  m.querySelectorAll('button').forEach(b => b.onclick = () => { ptMenuClose(); items[+b.dataset.i].run(); });
  PT.menu = m;
  setTimeout(() => document.addEventListener('mousedown', ptMenuAway), 0);
}
function ptMenuAway(e) { if (PT.menu && !PT.menu.contains(e.target)) ptMenuClose(); }
function ptMenuClose() { if (PT.menu) { PT.menu.remove(); PT.menu = null; } document.removeEventListener('mousedown', ptMenuAway); }
document.addEventListener('keydown', e => { if (e.key === 'Escape') ptMenuClose(); });

async function ptCall(path, body, okMsg) {
  const r = await api(path, body);
  if (!r.ok) { alert(r.out); return null; }
  if (okMsg) out(okMsg, 'ok');
  return r;
}

function fileMenu(project, name, x, y) {
  ptMenu(x, y, [
    { label: T('Open'), run: () => openFile(project, name) },
    { label: T('Rename ...'), run: async () => {
      const to = prompt(T('New name of the file:'), name);
      if (!to || to === name) return;
      if (await ptCall('/api/file/rename', { project, name, to })) {
        const t = S.tabs.find(x => x.key === project + '/' + name);
        if (t && typeof closeTab === 'function') closeTab(t.key);
        await refreshProjects(); openFile(project, to);
      }
    } },
    { label: T('Delete (to the trash folder)'), run: async () => {
      if (!confirm(TF('Delete {0}? It goes to the _trash folder of your projects folder, so it can be taken back.', name))) return;
      if (await ptCall('/api/file/delete', { project, name })) {
        const t = S.tabs.find(x => x.key === project + '/' + name);
        if (t && typeof closeTab === 'function') closeTab(t.key);
        refreshProjects();
      }
    } },
  ]);
}

function projectMenu(name, x, y) {
  const p = S.projects.find(q => q.name === name) || {};
  const fpga = (p.files || []).some(f => /\.s?v$/.test(f));
  ptMenu(x, y, [
    { label: T('Rename ...'), run: async () => {
      const to = prompt(T('New name of the project:'), name);
      if (!to || to === name) return;
      if (await ptCall('/api/project/rename', { name, to })) {
        S.tabs.filter(t => t.project === name).forEach(t => typeof closeTab === 'function' && closeTab(t.key));
        await refreshProjects(); selectProject(to);
      }
    } },
    { label: T('Duplicate ...'), run: async () => {
      const to = prompt(T('Name of the copy:'), name + '_copy');
      if (to && await ptCall('/api/project/duplicate', { name, to })) { await refreshProjects(); selectProject(to); }
    } },
    { label: T('Archive (zip)'), run: () => ptCall('/api/project/archive', { name, open: 1 }) },
    { label: T('Open folder'), run: () => api('/api/open', { what: 'folder', project: name }) },
    '-',
    { label: T('I/O planning (pins) ...'), disabled: !fpga, run: () => ioPlan(name) },
    { label: T('Build report ...'), disabled: !fpga, run: () => buildReport(name) },
    '-',
    { label: T('Delete (to the trash folder)'), run: async () => {
      if (!confirm(TF('Delete the project {0}? It goes to the _trash folder of your projects folder, so it can be taken back.', name))) return;
      if (await ptCall('/api/project/delete', { name })) {
        S.tabs.filter(t => t.project === name).forEach(t => typeof closeTab === 'function' && closeTab(t.key));
        if (S.project === name) S.project = '';
        refreshProjects();
      }
    } },
  ]);
}

/* ---------------- a dialog made on demand ---------------- */
function ptDialog(id, title) {
  let d = $(id);
  if (!d) {
    d = document.createElement('dialog');
    d.id = id;
    d.className = 'wide';
    d.innerHTML = `<form method="dialog"><h2></h2><div class="ptbody"></div><div class="row end ptfoot"></div></form>`;
    document.body.appendChild(d);
  }
  d.querySelector('h2').textContent = title;
  return d;
}

/* ---------------- the build report (like Vivado's utilisation and timing summary) ---------------- */
async function buildReport(name) {
  const r = await api('/api/fpga/report', { project: name });
  const d = ptDialog('dlgReport', TF('Build report: {0}', name));
  const body = d.querySelector('.ptbody');
  if (!r.ok) {
    body.innerHTML = `<p class="hint">${esc(T(r.out))}</p>`;
  } else {
    const p = r.report, names = { LUT: T('LUTs (logic)'), FF: T('flip-flops'), BRAM: T('block RAM (36 Kb)'), DSP: T('DSP slices'), PINS: T('pins') };
    const used = Object.assign({}, p.used, { PINS: p.pins });
    const bar = pct => `<span class="rbar"><i style="width:${Math.min(100, pct).toFixed(1)}%" class="${pct > 85 ? 'hi' : ''}"></i></span>`;
    const rows = Object.keys(names).map(k => {
      const v = used[k] || 0, max = p.max[k], pct = 100 * v / max;
      return `<tr><td>${esc(names[k])}</td><td class="num">${v}</td><td class="num">${max}</td><td>${bar(pct)} ${pct.toFixed(pct < 10 ? 1 : 0)} %</td></tr>`;
    }).join('');
    const extra = [['LUT_RAM', T('LUT memory')], ['SRL', T('shift registers')], ['CARRY', T('carry chains')], ['BUFG', T('clock buffers')], ['MMCM_PLL', T('clock makers (MMCM / PLL)')]]
      .filter(([k]) => p.used[k]).map(([k, t]) => `${esc(t)} ${p.used[k]}`).join(' &middot; ');
    const clocks = Object.entries(p.clocks || {}).map(([c, v]) => `<tr><td class="mono">${esc(c)}</td><td class="num">${v.fmax.toFixed(1)} MHz</td>
        <td class="num">${v.need} MHz</td><td class="${v.pass ? 'l-ok' : 'l-err'}">${v.pass ? TF('meets it ({0} % to spare)', (v.fmax / v.need * 100 - 100).toFixed(0)) : TF('too slow ({0} % short)', (100 - v.fmax / v.need * 100).toFixed(0))}</td></tr>`).join('');
    body.innerHTML = `<p class="hint">${esc(TF('{0}, top {1}, built {2} in {3} s for the {4} ({5}).', p.bit, p.top, p.date, p.seconds, p.board_name, p.part))}</p>
      <h4>${T('Utilisation')}</h4><table class="rtable"><tr><th></th><th>${T('used')}</th><th>${T('on the chip')}</th><th></th></tr>${rows}</table>
      ${extra ? `<p class="hint">${extra}</p>` : ''}
      <h4>${T('Timing')}</h4>${clocks ? `<table class="rtable"><tr><th>${T('clock')}</th><th>${T('reaches')}</th><th>${T('needed')}</th><th></th></tr>${clocks}</table>`
        : `<p class="hint">${T('No clock in the design: only logic between pins, nothing to time.')}</p>`}
      <p class="${p.hold_problems ? 'l-err' : 'hint'}">${p.hold_problems ? TF('{0} hold-time problems: the design may not work reliably.', p.hold_problems) : T('No hold-time problems.')}
        ${p.timing_ok ? '' : ' ' + T('Make the slow paths shorter (a register stage) or use a slower clock.')}</p>
      ${p.ethernet_added ? `<p class="hint">${esc(TF('The Ethernet of the {0} was added to this design by the build (it counts in the numbers above).', p.board_name))}</p>` : ''}`;
  }
  d.querySelector('.ptfoot').innerHTML = `<button value="close" class="primary">${T('Close')}</button>`;
  d.showModal();
}

/* ---------------- I/O planning (like Vivado's I/O Planning) ---------------- */
async function ioPlan(name) {
  const r = await api('/api/fpga/ioplan?project=' + encodeURIComponent(name));
  const d = ptDialog('dlgIoPlan', TF('I/O planning: {0}', name));
  const body = d.querySelector('.ptbody');
  if (!r.ok) { body.innerHTML = `<p class="hint">${esc(r.out)}</p>`; d.querySelector('.ptfoot').innerHTML = `<button value="close">${T('Close')}</button>`; return d.showModal(); }
  const groups = {};
  r.pins.forEach(p => (groups[p.group] = groups[p.group] || []).push(p));
  const options = sel => `<option value="">${T('(no pin)')}</option>` + Object.entries(groups).map(([g, ps]) => `<optgroup label="${esc(g)}">` +
    ps.map(p => `<option value="${esc(p.pin)}" ${p.pin === sel ? 'selected' : ''} ${p.reserved ? 'disabled' : ''}>${esc(p.pin)}  ${esc(p.name)}  (${esc(p.note)})${p.reserved ? ' - Ethernet' : ''}</option>`).join('') + '</optgroup>').join('') +
    (sel && !r.pins.some(p => p.pin === sel) ? `<option value="${esc(sel)}" selected>${esc(sel)} (${T('not in the board list')})</option>` : '');
  body.innerHTML = `<p class="hint">${esc(TF('The ports of {0} on the {1}. Choose a pin for each; Save writes them into io_plan.xdc (older lines for the same ports become comments).', r.top, r.board_name))}</p>
    <div class="iotable"><table class="rtable"><tr><th>${T('port')}</th><th></th><th>${T('board pin')}</th><th>${T('standard')}</th></tr>` +
    r.ports.map(p => `<tr data-port="${esc(p.port)}"><td class="mono">${esc(p.port)}</td><td class="hint">${esc(p.dir)}</td>
      <td><select class="iopin">${options(p.pin)}</select></td>
      <td><select class="iostd">${r.standards.map(s => `<option ${s === p.iostd ? 'selected' : ''}>${s}</option>`).join('')}</select></td></tr>`).join('') +
    `</table></div><p class="hint" id="ioWarn"></p>`;
  const check = () => {
    const seen = {}, dup = [];
    body.querySelectorAll('select.iopin').forEach(s => { s.classList.remove('dup'); if (s.value) (seen[s.value] = seen[s.value] || []).push(s); });
    Object.entries(seen).forEach(([pin, ss]) => { if (ss.length > 1) { dup.push(pin); ss.forEach(s => s.classList.add('dup')); } });
    const free = [...body.querySelectorAll('select.iopin')].filter(s => !s.value).length;
    $('ioWarn').innerHTML = (dup.length ? `<span class="l-err">${esc(TF('Chosen twice: {0}', dup.join(', ')))}</span> ` : '') +
      (free ? esc(TF('{0} ports without a pin (the build places them anywhere: give each one a pin).', free)) : esc(T('Every port has a pin.')));
    $('ioSave').disabled = dup.length > 0;
  };
  d.querySelector('.ptfoot').innerHTML = `<button value="close" class="ghost">${T('Close')}</button><button class="primary" id="ioSave">${T('Save')}</button>`;
  body.querySelectorAll('select.iopin').forEach(s => s.onchange = check);
  $('ioSave').onclick = async e => {
    e.preventDefault();
    const assign = {};
    body.querySelectorAll('tr[data-port]').forEach(tr => assign[tr.dataset.port] = { pin: tr.querySelector('.iopin').value, iostd: tr.querySelector('.iostd').value });
    const x = await ptCall('/api/fpga/ioplan/save', { project: name, assign });
    if (x) { d.close(); refreshProjects(); }
  };
  check();
  d.showModal();
}

/* ---------------- wiring ---------------- */
(function ptStart() {
  // the file list and the project list: right-click menus; a "..." button on the project's file panel
  document.addEventListener('contextmenu', e => {
    const f = e.target.closest('#projectFiles .file:not(.bin)');
    const p = e.target.closest('#projectList .item');
    if (f) { e.preventDefault(); fileMenu(S.project, f.dataset.f, e.clientX, e.clientY); }
    else if (p) { e.preventDefault(); projectMenu(p.dataset.p, e.clientX, e.clientY); }
  });
  const renderFiles0 = window.renderFiles;
  window.renderFiles = () => {
    renderFiles0();
    const h = $('projectFiles').querySelector('h3');
    if (h && S.project && !h.querySelector('.ptmore')) {
      const b = document.createElement('button');
      b.className = 'ghost small ptmore';
      b.title = T('Project: rename, duplicate, archive, delete, I/O planning, build report (also: right-click a project or a file)');
      b.textContent = '⋯';
      b.onclick = e => { e.preventDefault(); const r = b.getBoundingClientRect(); projectMenu(S.project, r.left, r.bottom + 4); };
      h.appendChild(b);
    }
  };
  const ready = setInterval(() => {
    if (!S.cm) return;
    clearInterval(ready);
    S.cm.addKeyMap({ 'Ctrl-T': () => autoFormat() });
    if ($('edFormat')) $('edFormat').onclick = e => { e.preventDefault(); autoFormat(); };
  }, 300);
})();
