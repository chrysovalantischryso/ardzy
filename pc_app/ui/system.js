/* Ardzy - System view: Linux on the board. Processes, services, logs, the register explorer,
   Linux and network details, speed tests. Board API /api/sys/..., /api/regs..., /api/bench. */
const SY = { tab: 'procs', block: 'slcr', timer: null, logSrc: 'journal' };
const tbl = (head, rows) => `<table class="sys-tbl"><tr>${head.map(h => `<th>${h}</th>`).join('')}</tr>${rows.join('')}</table>`;

function sysShow() {
  if (!S.connected) { $('sysBody').innerHTML = '<div class="empty">No board connected.</div>'; return; }
  sysTab(SY.tab);
}

function sysTab(t) {
  SY.tab = t;
  $('sysSeg').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.v === t));
  clearTimeout(SY.timer);
  ({ procs: sysProcs, services: sysServices, logs: sysLogs, regs: sysRegs, info: sysInfo, bench: sysBench, settings: sysSettings })[t]();
}

/* ---- processes (live) */
async function sysProcs() {
  const r = await bget('/api/sys/procs');
  if (BV.view !== 'system' || SY.tab !== 'procs') return;
  if (!r.ok) { $('sysBody').innerHTML = `<div class="empty">${esc(r.out)}</div>`; return; }
  const age = s => s > 86400 ? Math.floor(s / 86400) + 'd' : s > 3600 ? Math.floor(s / 3600) + 'h' : s > 60 ? Math.floor(s / 60) + 'm' : s + 's';
  $('sysBody').innerHTML = `<div class="dcard wide"><h3>Processes<span class="grow"></span><span class="hint">${TF('{0} running, busiest first, updated every 3 s', r.count)}</span></h3>` +
    tbl(['PID', 'User', 'CPU %', 'Memory %', 'Memory', 'Running for', 'State', 'Program'],
      r.procs.filter(p => !/^ps -eo /.test(p.cmd)).map(p => `<tr><td class="num">${p.pid}</td><td>${esc(p.user)}</td><td class="num">${p.cpu}</td><td class="num">${p.mem}</td>
        <td class="num">${(p.rss_kb / 1024).toFixed(1)} MB</td><td>${age(p.age_s)}</td><td>${esc(p.stat)}</td><td class="mono" title="${esc(p.cmd)}">${esc(p.cmd)}</td></tr>`)) + '</div>';
  SY.timer = setTimeout(sysProcs, 3000);
}

/* ---- services */
async function sysServices() {
  const r = await bget('/api/sys/services');
  if (!r.ok) { $('sysBody').innerHTML = `<div class="empty">${esc(r.out)}</div>`; return; }
  const dot = s => `<span class="lvl ${s.active === 'active' ? 'h' : ''}" style="${s.active === 'failed' ? 'background:var(--err);border-color:var(--err)' : ''}"></span>`;
  $('sysBody').innerHTML = `<div class="dcard wide"><h3>Services<span class="grow"></span><span class="hint">${r.failed.length ? '<b style="color:var(--err)">failed: ' + esc(r.failed.join(', ')) + '</b>' : 'none failed'}</span></h3>` +
    tbl(['', 'Service', 'State', 'What it is', ''], r.services.map(s => `<tr><td>${dot(s)}</td><td class="mono">${esc(s.unit)}</td>
      <td>${esc(s.active)} (${esc(s.sub)})</td><td>${esc(s.desc)}</td>
      <td>${s.actions.map(a => `<button class="ghost small" data-svc="${esc(s.unit)}" data-act="${a}">${a}</button>`).join(' ')}
        <button class="ghost small" data-log="${esc(s.unit)}">log</button></td></tr>`)) +
    '<div class="hint">Only the services that are safe to touch can be started or stopped here. Ardzy\'s own: ardzy-app = your program, ardzy-web = this connection.</div></div>';
  $('sysBody').querySelectorAll('[data-svc]').forEach(b => b.onclick = async () => {
    if (b.dataset.svc === 'ardzy-web.service' && !confirm('Restart the board service? The app reconnects in a few seconds.')) return;
    const x = await bpost('/api/sys/service?' + qs({ name: b.dataset.svc, action: b.dataset.act }));
    out(x.out, x.ok ? 'ok' : 'err');
    setTimeout(sysServices, 800);
  });
  $('sysBody').querySelectorAll('[data-log]').forEach(b => b.onclick = () => { SY.logUnit = b.dataset.log; sysTab('logs'); });
}

/* ---- logs */
async function sysLogs() {
  $('sysBody').innerHTML = `<div class="dcard wide"><h3>Logs</h3>
    <div class="row"><span class="seg" id="logSrc"><button data-v="journal">System log</button><button data-v="dmesg">Kernel messages</button></span>
      <label class="hint">service <input id="logUnit" value="${esc(SY.logUnit || '')}" placeholder="all (or ardzy-app, ssh ...)" style="width:200px" spellcheck="false"></label>
      <label class="hint">level <select id="logPrio"><option value="">all</option><option value="3">errors</option><option value="4">warnings and errors</option><option value="6">info</option></select></label>
      <label class="hint">lines <select id="logN"><option>100</option><option selected>300</option><option>1000</option></select></label>
      <input id="logGrep" placeholder="find text" style="width:160px" spellcheck="false">
      <button class="small" id="logGo">Show</button></div>
    <pre id="logText" class="logtext"></pre></div>`;
  $('logSrc').querySelectorAll('button').forEach(b => { b.classList.toggle('on', b.dataset.v === SY.logSrc); b.onclick = () => { SY.logSrc = b.dataset.v; sysLogs(); }; });
  $('logGo').onclick = loadLog;
  $('logGrep').onkeydown = e => { if (e.key === 'Enter') loadLog(); };
  loadLog();
}

async function loadLog() {
  SY.logUnit = $('logUnit').value.trim();
  $('logText').textContent = 'loading ...';
  const r = SY.logSrc === 'dmesg' ? await bget('/api/sys/dmesg')
    : await bget('/api/sys/journal?' + qs({ unit: SY.logUnit, n: $('logN').value, prio: $('logPrio').value, grep: $('logGrep').value.trim() }));
  let text = r.ok ? r.text : r.out;
  if (SY.logSrc === 'dmesg' && $('logGrep').value.trim()) text = text.split('\n').filter(l => l.toLowerCase().includes($('logGrep').value.trim().toLowerCase())).join('\n');
  const pre = $('logText');
  pre.innerHTML = esc(text || '(empty)').split('\n').map(l => /error|fail|panic|oops|segfault/i.test(l) ? `<span class="l-err">${l}</span>` :
    /warn/i.test(l) ? `<span class="l-warn">${l}</span>` : l).join('\n');
  pre.scrollTop = pre.scrollHeight;
}

/* ---- register explorer */
async function sysRegs() {
  const list = await bget('/api/regs');
  if (!list.ok) { $('sysBody').innerHTML = `<div class="empty">${esc(list.out)}</div>`; return; }
  $('sysBody').innerHTML = `<div class="sys-split"><div class="dcard regnav"><h3>Blocks</h3>${list.blocks.map(b =>
    `<div class="item ${b.key === SY.block ? 'active' : ''}" data-b="${b.key}"><span>${esc(b.title)}<small class="hint" style="display:block">${b.base} &middot; ${b.count} registers</small></span></div>`).join('')}
    <p class="hint">Read only, and only registers that can be read safely. Values are live: Refresh to read again.</p></div>
    <div class="dcard" id="regView"></div></div>`;
  $('sysBody').querySelectorAll('[data-b]').forEach(el => el.onclick = () => { SY.block = el.dataset.b; sysRegs(); });
  const r = await bget('/api/regs/block?b=' + SY.block);
  if (!r.ok) { $('regView').innerHTML = esc(r.out); return; }
  $('regView').innerHTML = `<h3>${esc(r.title)}<span class="grow"></span><span class="hint">base ${r.base}</span></h3>` + (r.off ? `<p class="hint">${esc(r.note)}</p>` :
    `<input id="regFind" placeholder="find a register" style="width:220px;margin-bottom:6px" spellcheck="false">` +
    tbl(['Address', 'Register', 'Value', 'Means', 'What'], r.regs.map(x => `<tr><td class="num">${x.addr}</td><td class="mono">${esc(x.name)}</td>
      <td class="num">${x.value}</td><td><b>${esc(x.decoded)}</b></td><td class="hint">${esc(x.desc)}</td></tr>`)));
  if ($('regFind')) $('regFind').oninput = () => {
    const q = $('regFind').value.toLowerCase();
    $('regView').querySelectorAll('tr').forEach((tr, i) => { if (i) tr.style.display = !q || tr.textContent.toLowerCase().includes(q) ? '' : 'none'; });
  };
}

/* ---- Linux and network */
async function sysInfo() {
  $('sysBody').innerHTML = '<div class="empty">reading ...</div>';
  const r = await bget('/api/sys/info');
  if (!r.ok) { $('sysBody').innerHTML = `<div class="empty">${esc(r.out)}</div>`; return; }
  const t = r.time;
  const offset = Math.round(t.now - Date.now() / 1000);
  const cards = [];
  cards.push(`<div class="dcard"><h3>Clock and system</h3>${kv([
    ['Board time', esc(t.local) + (Math.abs(offset) > 2 ? ` <span style="color:var(--warn)">(${offset > 0 ? '+' : ''}${offset} s from this PC)</span>` : ' (same as this PC)')],
    ['Time zone', esc(t.timezone)], ['Internet time (NTP)', t.ntp_synced ? 'in sync' : 'not reached (no internet on the cable)'],
    ['Kernel', esc(r.kernel)], ['Built', esc(r.kernel_build)], ['Python', esc(r.python)], ['Compiler', esc(r.gcc)],
    ['Packages installed', r.packages], ['Logged in', esc(r.users.join(', ') || 'nobody')]])}
    <div class="row"><button class="ghost small" id="btnSetTime">Set the board clock from this PC</button></div>
    <div class="hint">The board has no battery clock: Ardzy sets it from the PC when it connects.</div></div>`);
  cards.push(`<div class="dcard"><h3>Network</h3>${tbl(['Interface', 'State', 'MAC', 'Addresses'], r.addrs.map(a =>
    `<tr><td class="mono">${esc(a.ifname)}</td><td>${esc(a.state)}</td><td class="mono">${esc(a.mac || '')}</td><td class="mono">${a.addr.map(esc).join('<br>')}</td></tr>`))}
    ${kv([['Routes', r.routes.map(esc).join('<br>') || '-'], ['DNS servers', esc(r.dns.join(', ') || '-')]])}
    <h3 style="margin-top:10px">Listening</h3>${tbl(['Proto', 'Address:port'], r.listening.map(l => `<tr><td>${esc(l.proto)}</td><td class="mono">${esc(l.local)}</td></tr>`))}</div>`);
  cards.push(`<div class="dcard"><h3>Disks and mounts</h3>${tbl(['Device', 'Mounted at', 'Type', 'Mode', 'Size', 'Free'], r.mounts.map(m =>
    `<tr><td class="mono">${esc(m.dev)}</td><td class="mono">${esc(m.at)}</td><td>${esc(m.type)}</td><td>${esc(m.opts)}</td><td class="num">${fmtMB(m.size_mb)}</td><td class="num">${fmtMB(m.free_mb)}</td></tr>`))}</div>`);
  cards.push(`<div class="dcard"><h3>Boot</h3>${kv([['Kernel command line', `<span class="mono">${esc(r.cmdline)}</span>`],
    ['Device tree model', esc(r.dt_model)], ['Compatible', esc(r.dt_compatible)], ['FPGA overlays', esc(r.overlays.join(', ') || 'none')],
    ['Kernel modules', esc(r.modules.join(', ') || 'none (all built in)')]])}
    <h3 style="margin-top:10px">U-Boot settings (uboot.env)</h3>${tbl(['Name', 'Value'], Object.entries(r.uboot_env).map(([k, v]) => `<tr><td class="mono">${esc(k)}</td><td class="mono">${esc(v)}</td></tr>`))}</div>`);
  cards.push(`<div class="dcard wide"><h3>Device tree: hardware blocks Linux knows</h3>${tbl(['Node', 'Driver match', 'Status'], r.dt_nodes.map(n =>
    `<tr class="${n.status === 'okay' ? '' : 'used'}"><td class="mono">${esc(n.node)}</td><td class="mono">${esc(n.compatible)}</td><td>${esc(n.status)}</td></tr>`))}</div>`);
  cards.push(`<div class="dcard wide"><h3>Interrupts (counts since boot)</h3>${tbl(['IRQ', 'CPU0', 'CPU1', 'Source'], r.interrupts.filter(i => i.cpu0 + i.cpu1 > 0 || isNaN(+i.irq)).map(i =>
    `<tr><td class="num">${esc(i.irq)}</td><td class="num">${i.cpu0}</td><td class="num">${i.cpu1}</td><td>${esc(i.name)}</td></tr>`))}</div>`);
  $('sysBody').innerHTML = '<div class="dash">' + cards.join('') + '</div>';
  $('btnSetTime').onclick = async () => { const x = await bpost('/api/sys/time?epoch=' + (Date.now() / 1000).toFixed(3)); out(x.ok ? (x.changed ? `board clock set (was ${x.diff_s} s off)` : 'board clock was already right') : x.out, x.ok ? 'ok' : 'err'); sysInfo(); };
}

/* ---- speed tests */
async function sysBench() {
  $('sysBody').innerHTML = `<div class="dash">
    <div class="dcard"><h3>Processor</h3><div id="bCpu" class="hint">one core: Python loop and SHA-256 hashing</div><div class="row"><button class="small" data-b="cpu">Run (2 s)</button></div></div>
    <div class="dcard"><h3>Memory</h3><div id="bMem" class="hint">copying 32 MB blocks, writing 1 GB of zeros</div><div class="row"><button class="small" data-b="mem">Run (5 s)</button></div></div>
    <div class="dcard"><h3>microSD card</h3><div id="bSd" class="hint">reads 64 MB, writes a 32 MB file (deleted after)</div><div class="row"><button class="small" data-b="sd">Run (about 20 s)</button></div></div>
    <div class="dcard"><h3>Network (this PC to the board)</h3><div id="bNet" class="hint">32 MB each way through the cable</div><div class="row"><button class="small" id="bNetGo">Run (about 10 s)</button></div></div>
  </div>`;
  const show = (id, html) => $(id).innerHTML = html;
  $('sysBody').querySelectorAll('[data-b]').forEach(b => b.onclick = async () => {
    const id = { cpu: 'bCpu', mem: 'bMem', sd: 'bSd' }[b.dataset.b];
    show(id, 'running ...'); b.disabled = true;
    const r = await bpost('/api/bench?test=' + b.dataset.b);
    b.disabled = false;
    if (!r.ok) return show(id, esc(r.out));
    if (r.test === 'cpu') show(id, kv([['Python loop', (r.python_loops_per_s / 1e6).toFixed(2) + ' million steps/s'], ['SHA-256', r.sha256_mb_s + ' MB/s']]));
    if (r.test === 'mem') show(id, kv([['Copy', r.copy_mb_s + ' MB/s'], ['Fill', (r.fill_mb_s || '?') + ' MB/s']]));
    if (r.test === 'sd') show(id, kv([['Read', (r.read_mb_s || '?') + ' MB/s'], ['Write', (r.write_mb_s || '?') + ' MB/s']]));
  });
  $('bNetGo').onclick = async () => {
    show('bNet', 'running ...');
    const r = await api('/api/bench/net', { mb: 32 });
    if (!r.ok) return show('bNet', esc(r.out));
    const wait = setInterval(async () => {
      if (S.busy) return;
      clearInterval(wait);
      const x = await api('/api/results');
      const n = x.results && x.results.net;
      show('bNet', n ? kv([['Board to PC', n.down_mbit + ' Mbit/s'], ['PC to board', n.up_mbit + ' Mbit/s']]) + '<div class="hint">The link runs at 100 Mbit/s (see Board, Network).</div>' : 'no result');
    }, 700);
  };
}

/* ---- board settings (ardzy.txt) and system update */
async function sysSettings() {
  const form = await (await fetch('settings_form.html')).text();
  $('sysBody').innerHTML = `<div class="dash">
    <div class="dcard wide"><h3>Board settings<span class="grow"></span><span class="hint">saved in /boot/ardzy.txt on the card</span></h3>
      ${form}
      <div class="row"><button class="primary small" id="setSave">Save and apply</button><span class="hint" id="setInfo"></span></div>
      <div class="hint">Name, time zone, SSH and password change at once. A new network setting restarts the network: the app finds the board again by itself
        (the direct-cable link always works). Without a newer Ardzy (1.0), install the update below first.</div></div>
    <div class="dcard wide"><h3>System update</h3><div id="updInfo" class="hint">reading ...</div>
      <div class="row"><select id="updFile" class="grow"></select><button class="ghost small" id="updPick">Choose file</button>
        <button class="primary small" id="updGo">Install update</button></div>
      <div class="hint">An update brings a new kernel, packages and Ardzy files. A new kernel is tried once: if it does not start,
        the board goes back to the old one by itself at the next power-on.</div></div></div>`;
  const cfg = await api('/api/board/config');
  if (cfg.ok) document.querySelectorAll('#sysBody [data-k]').forEach(el => { if (cfg[el.dataset.k] !== undefined && el.dataset.k !== 'password') el.value = cfg[el.dataset.k]; });
  else $('setInfo').textContent = 'This board has no settings file yet (Ardzy 0.1): install the update below.';
  $('setSave').onclick = async () => {
    const v = {};
    document.querySelectorAll('#sysBody [data-k]').forEach(el => { if (el.dataset.k !== 'password' || el.value) v[el.dataset.k] = el.value.trim(); });
    if (v.network !== (cfg.network || 'auto') && !confirm('The network setting changes: the connection drops for a moment. Go on?')) return;
    const r = await api('/api/board/config', v);
    $('setInfo').textContent = r.ok ? 'saved and applied' : r.out;
    document.querySelector('#sysBody [data-k="password"]').value = '';
  };
  const st = await api('/api/board/update/status');
  const rel = st.release || {};
  $('updInfo').innerHTML = st.ok ? kv([['Ardzy on the board', `${esc(rel.ARDZY_VERSION || '?')} (${esc(rel.BUILD_DATE || '')})`],
    ['Kernel', esc(st.kernel)], ['Last update', esc(st.last || '-')],
    ['Safe kernel update', st.trial ? '<b>a new kernel is being tried</b>' : st.old_kernel_kept ? 'previous kernel kept as a backup' : 'ready']])
    : esc(st.out || 'no board');
  $('updFile').innerHTML = (st.bundles || []).map(b => `<option value="${esc(b.path)}">${esc(b.name)} (${(b.size / 2 ** 20).toFixed(1)} MB)</option>`).join('')
    || '<option value="">no update file found: Choose file</option>';
  $('updPick').onclick = async () => {
    const r = await api('/api/sd/pick', {});
    if (r.ok) { $('updFile').insertAdjacentHTML('afterbegin', `<option value="${esc(r.path)}">${esc(r.path.split(/[\\/]/).pop())}</option>`); $('updFile').value = r.path; }
  };
  $('updGo').onclick = async () => {
    const f = $('updFile').value;
    if (!f) return alert('Choose an update file.');
    if (!confirm('Install ' + f.split(/[\\/]/).pop() + ' on the board? Programs keep running; a restart is needed at the end.')) return;
    showTab('output');
    const r = await api('/api/board/update', { path: f });
    if (!r.ok) return out(r.out, 'err');
    const wait = setInterval(async () => {
      if (S.busy) return;
      clearInterval(wait);
      const x = await api('/api/results');
      const u = x.results && x.results.update;
      if (u && u.ok && u.reboot && confirm('The update is installed. Restart the board now to finish? It is back in about a minute.'))
        bpost('/api/system?action=reboot');
      sysSettings();
    }, 1000);
  };
}

$('sysSeg').querySelectorAll('button').forEach(b => b.onclick = () => sysTab(b.dataset.v));
$('btnSysRefresh').onclick = () => sysTab(SY.tab);
window.sysShow = sysShow;
