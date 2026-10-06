/* Ardzy - Board view (everything about the board, with controls) and I/O view (FPGA pins, fans).
   Uses helpers from app.js: $, esc, api, out, S. All board calls go through the engine's proxy. */
const BV = { view: 'code', hw: null, hist: { temp: [], cpu: [] }, io: null, ioBuilt: false, pinInfo: null, last: 0 };
const bget = path => api('/api/board/proxy', { method: 'GET', path });
const bpost = path => api('/api/board/proxy', { method: 'POST', path });
const qs = o => Object.entries(o).map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&');
const fmtMB = mb => mb >= 1024 ? (mb / 1024).toFixed(1) + ' GB' : mb + ' MB';
const fmtUp = s => `${Math.floor(s / 86400)}d ${Math.floor(s % 86400 / 3600)}h ${Math.floor(s % 3600 / 60)}m`;
const kv = rows => '<div class="kv">' + rows.map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join('') + '</div>';
const bar = (pct, id) => `<div class="bar ${pct > 90 ? 'err' : pct > 75 ? 'warn' : ''}"${id ? ` id="${id}"` : ''}><i style="width:${Math.min(100, pct).toFixed(1)}%"></i></div>`;
const NOMINAL = { vccint: ['VCCINT (FPGA core)', 1.0], vccpint: ['VCCPINT (ARM core)', 1.0], vccbram: ['VCCBRAM (block RAM)', 1.0],
  vccaux: ['VCCAUX (FPGA aux)', 1.8], vccpaux: ['VCCPAUX (ARM aux)', 1.8], vccoddr: ['VCC_DDR (memory)', 1.5] };

const VIEW_PANES = { board: 'viewBoard', io: 'viewIO', tools: 'viewTools', gallery: 'viewGallery', learn: 'viewLearn', radio: 'viewRadio',
  map: 'viewMap', system: 'viewSystem', blocks: 'viewBlocks' };
function showView(v) {
  BV.view = v;
  const tab = v === 'radio' ? 'gallery' : v;            // the radio is a project page inside Projects
  document.querySelectorAll('.views button').forEach(b => b.classList.toggle('active', b.dataset.view === tab));
  for (const [k, id] of Object.entries(VIEW_PANES)) $(id).hidden = v !== k;
  document.querySelector('.center').classList.toggle('alt-view', v !== 'code');
  if (v === 'code' && S.cm) setTimeout(() => S.cm.refresh(), 0);
  if (v === 'board') refreshHW();
  if (v === 'io') refreshIO();
  if (v === 'tools' && window.toolsShow) toolsShow();
  if (v === 'gallery' && window.galleryShow) galleryShow();
  if (v === 'learn' && window.learnShow) learnShow();
  if (v === 'radio' && window.radioShow) radioShow();
  if (v === 'map' && window.mapShow) mapShow();
  if (v === 'system' && window.sysShow) sysShow();
  if (v === 'blocks' && window.blocksShow) blocksShow();
}
function confirmDo(msg, fn) { if (confirm(msg)) fn(); }

/* ================================================================ Board view */
async function refreshHW() {
  if (!S.connected) { $('dash').innerHTML = '<div class="empty">No board connected. Click Scan.</div>'; return; }
  const r = await bget('/api/hw');
  if (!r.ok) { $('dash').innerHTML = `<div class="empty">Board did not answer: ${esc(r.out)}</div>`; return; }
  BV.hw = r;
  const busy = $('dash').contains(document.activeElement) && document.activeElement.tagName === 'INPUT';
  if (!busy) renderDash(r);
  updateSensors(r.sensors);
  $('hwStamp').textContent = TF('updated {0}', new Date().toTimeString().slice(0, 8));
  loadMio();
}

function renderDash(h) {
  const c = h.clocks, m = h.memory, st = h.storage, n = h.net, nd = h.nand, b = h.boot, cf = h.cpu.freq;
  const cards = [];
  cards.push(`<div class="dcard" data-card="board"><h3>Board</h3>${kv([
    ['Board', esc(h.board)], ['Chip', `${esc(h.chip)} (silicon ${esc(b.ps_version)})`], ['IDCODE', esc(b.idcode)],
    ['Ardzy image', `${esc(h.image.ARDZY_VERSION || '?')} (${esc(h.image.BUILD_DATE || '')})`], ['System', esc(h.os)],
    ['Kernel', esc(h.kernel)], ['Boot from', esc(b.boot_mode)], ['Last reset', esc(b.last_reset.join(', '))],
    ['Uptime', `<span id="sUp">${fmtUp(h.sensors.uptime_s)}</span>`]])}</div>`);

  cards.push(liveCardHtml());
  cards.push(window.loggerCardHtml ? loggerCardHtml() : '');
  cards.push(`<div class="dcard" data-card="program"><h3>Program and FPGA</h3><div id="progBody" class="hint">reading ...</div></div>`);

  cards.push(`<div class="dcard" data-card="rails"><h3>Power rails (measured)</h3><table>
    <tr><th>Rail</th><th>Nominal</th><th>Now</th><th>Diff</th></tr>
    ${Object.entries(NOMINAL).map(([k, [name, nom]]) => `<tr><td>${name}</td><td class="num">${nom.toFixed(2)} V</td>
      <td class="num" id="v_${k}">-</td><td class="num" id="d_${k}">-</td></tr>`).join('')}
    </table><div class="hint">Measured inside the chip (XADC). 2.5 V and 3.3 V are not measured.</div></div>`);

  let cpuCtl = '<div class="hint">The CPU always runs at full speed. Speed switching (666 / 333 MHz) is off: its kernel driver crashed the system in testing, so it is not offered.</div>';
  if (cf.available) cpuCtl = `<div class="row">
      <select id="cpuGov">${cf.governors.map(g => `<option ${g === cf.governor ? 'selected' : ''}>${g}</option>`).join('')}</select>
      <select id="cpuKhz">${cf.freqs_khz.map(k => `<option value="${k}" ${k === cf.cur_khz ? 'selected' : ''}>${(k / 1000).toFixed(1)} MHz</option>`).join('')}</select>
      <button class="ghost small" id="btnCpuSet">Apply</button></div>
      <div class="hint">performance = always full speed, powersave = slow, ondemand = speeds up when busy. A fixed speed uses "userspace".</div>`;
  cards.push(`<div class="dcard" data-card="cpu"><h3>CPU and speed</h3>${kv([
    ['Processor', esc(h.cpu.model)], ['Cores', h.cpu.cores], ['Clock now', `${c.cpu_mhz} MHz` + (cf.available ? ` (${(cf.cur_khz / 1000).toFixed(1)} MHz, ${esc(cf.governor)})` : '')],
    ['Bus ratio', c.ratio_621 ? '6:2:1 (333 / 222 / 111 MHz)' : '4:2:1'], ['BogoMIPS', esc(h.cpu.bogomips) + ' per core']])}${cpuCtl}</div>`);

  const usedPct = 100 * m.used_mb / m.total_mb;
  cards.push(`<div class="dcard" data-card="mem"><h3>Memory (RAM)</h3>${kv([
    ['Physical', `${m.physical_mb} MB ${esc(m.type)}`], ['Speed', `DDR3-${Math.round(c.ddr_mhz * 2)} (${c.ddr_mhz} MHz)`],
    ['Linux has', `${m.total_mb} MB`], ['Used by programs', `<span id="mUsed">${m.used_mb} MB</span>`],
    ['Cache / buffers', `${m.cached_mb} MB`], ['Available', `<span id="mAvail">${m.available_mb} MB</span>`], ['Swap', m.swap_mb ? m.swap_mb + ' MB' : 'none']])}
    ${bar(usedPct, 'mBar')}<div class="hint">512 MB on 2 Gbit DDR3 chips (the upper half of the address space mirrors the lower half).</div></div>`);

  cards.push(`<div class="dcard" data-card="clocks"><h3>Clocks<span class="grow"></span>${h.fpga.io_design ? '<button class="ghost small" id="btnMeasure">Measure FCLK0</button>' : ''}</h3>
    ${kv([['Reference', c.ps_clk_mhz + ' MHz (Y1)'], ['PLLs', `ARM ${c.pll_mhz.ARM} &middot; DDR ${c.pll_mhz.DDR} &middot; IO ${c.pll_mhz.IO} MHz`],
      ['CPU / DDR', `${c.cpu_mhz} / ${c.ddr_mhz} MHz`],
      ['Peripherals', Object.entries(c.peripherals).map(([k, v]) => `${k} ${v.mhz}`).join(' &middot; ') + ' MHz']])}
    <table style="margin-top:8px"><tr><th>FPGA clock</th><th>Now</th><th>Set (MHz)</th><th></th></tr>
    ${c.fclk.map(f => `<tr><td>FCLK${f.n}${f.n === 0 ? ' (designs)' : ''}</td><td class="num">${f.mhz} MHz</td>
      <td><input type="number" min="0.5" max="250" step="0.5" id="fclk${f.n}" value="${f.mhz}"></td>
      <td><button class="ghost small" data-fclk="${f.n}">Set</button></td></tr>`).join('')}</table>
    <div class="hint" id="measureOut">FPGA clocks come from the IO PLL (1000 MHz / two dividers). Ardzy designs use FCLK0. A design built for 100 MHz may fail above it.</div></div>`);

  const rootPct = 100 * (1 - st['/'].free_mb / st['/'].size_mb), bootPct = 100 * (1 - st['/boot'].free_mb / st['/boot'].size_mb);
  cards.push(`<div class="dcard" data-card="sd"><h3>microSD card</h3>${kv([
    ['Card', `${esc(st.card.name)} (${esc(st.card.type)}, maker id ${esc(st.card.manfid)}, made ${esc(st.card.date)})`],
    ['Size', fmtMB(st.card.size_mb)], ['System (/)', `${fmtMB(st['/'].size_mb - st['/'].free_mb)} used of ${fmtMB(st['/'].size_mb)}`]])}
    ${bar(rootPct)}${kv([['Boot (/boot, FAT)', `${st['/boot'].size_mb - st['/boot'].free_mb} MB used of ${st['/boot'].size_mb} MB`]])}${bar(bootPct)}</div>`);

  const chip = nd.chip;
  let ndBody = kv([['Chip', `${esc(chip.part)}`], ['Size', `${chip.size_mb} MB ${chip.type}, ${chip.bus}`],
    ['Layout', `${chip.page} B pages + ${chip.oob} B spare, ${chip.block_kb} KB blocks`], ['Content', 'original Bitmain firmware']]);
  if (nd.enabled) ndBody += kv([['Linux device', `/dev/${esc(nd.mtd)} (${nd.read_only ? 'read-only' : 'WRITABLE'})`],
      ['Bad blocks', nd.bad_blocks], ['ECC corrected / failed', `${nd.corrected_bits} / ${nd.ecc_failures}`]]) +
    `<div class="row"><button class="ghost small" id="btnNandScan">Scan contents</button>
     <button class="ghost small" id="btnNandData">Backup (data, 256 MB)</button>
     <button class="ghost small" id="btnNandRaw">Backup (exact raw copy)</button></div><div id="nandScan" class="hint"></div>`;
  else ndBody += `<div class="hint" style="margin-top:6px">${esc(nd.note)}</div>`;
  cards.push(`<div class="dcard" data-card="nand"><h3>NAND flash</h3>${ndBody}</div>`);

  let netCtl = '<div class="hint">Link speed setting needs ethtool (in the newer image).</div>';
  if (n.supported) netCtl = `<div class="row">Speed: <span class="seg" id="netSeg">
      ${['auto', '100', '1000'].map(s => `<button data-net="${s}">${s === 'auto' ? 'Auto' : s + ' Mbit'}</button>`).join('')}</span></div>
      <div class="hint">Partner (PC/router) offers: ${esc((n.partner || []).join(', ') || '?')}. Changing it drops the link for a few seconds; a reboot restores Auto.</div>`;
  cards.push(`<div class="dcard" data-card="net"><h3>Network</h3>${kv([
    ['Name', esc(n.hostname) + '.local'], ['MAC', esc(n.mac)], ['IPv4', esc(n.ipv4.join(', ') || '-')],
    ['Link', `${esc(n.speed)} Mbit/s ${esc(n.duplex)} duplex`], ['Received / sent', `<span id="netRx">${fmtMB(Math.floor(n.rx_bytes / 1048576))}</span> / <span id="netTx">${fmtMB(Math.floor(n.tx_bytes / 1048576))}</span>`],
    ['PHY', 'Broadcom B50612, address 1, RGMII']])}${netCtl}</div>`);

  cards.push(`<div class="dcard" data-card="extras"><h3>LEDs, buzzer, buttons</h3><table>
    <tr><td>Status LED green</td><td><span class="seg" data-led="38">${segOnOff()}</span></td></tr>
    <tr><td>Status LED red</td><td><span class="seg" data-led="37">${segOnOff()}</span></td></tr>
    <tr><td>Small LED D2</td><td><span class="seg" data-led="15" data-low="1">${segOnOff()}</span></td></tr>
    <tr><td>Buzzer</td><td><button class="ghost small" id="btnBeep">Beep</button></td></tr>
    <tr><td>Button S2 "IP"</td><td><span class="lvl" id="btnIp"></span> <span id="btnIpTxt"></span></td></tr>
    <tr><td>Button S1 "Reset"</td><td><span class="lvl" id="btnRst"></span> <span id="btnRstTxt"></span></td></tr></table>
    <div class="hint">Green on = Ardzy ready, red on = safe mode (set at boot). Your programs can use them too.</div></div>`);

  cards.push(`<div class="dcard" data-card="system"><h3>System</h3>${kv([
    ['FPGA', `${esc(h.fpga.state)}${h.fpga.project ? ' (project ' + esc(h.fpga.project) + ')' : ''}`],
    ['Watchdog', `${esc(h.watchdog.device)}, timeout ${esc(h.watchdog.timeout_s)}, ${esc(h.watchdog.state)}`]])}
    <div class="row"><button class="ghost small" id="btnSysWeb">Restart board service</button>
    <button class="ghost small" id="btnSysReboot">Reboot board</button>
    <button class="ghost small" id="btnSysOff">Power off</button></div>
    <div class="hint">After "Power off" the board stays off until you switch the 12 V supply off and on.</div></div>`);

  cards.push(`<div class="dcard wide" data-card="mio"><h3>ARM pins (MIO 0-53)<span class="grow"></span><span class="hint" id="mioClk"></span></h3>
    <div id="mioTable" class="hint">loading ...</div></div>`);

  $('dash').innerHTML = cards.join('');
  dashArrange();
  wireDash();
  wireLive();
  drawChart();
  programCard();
  if (window.loggerRefresh) loggerRefresh();
}

const segOnOff = () => '<button data-v="off">Off</button><button data-v="on">On</button>';

function wireDash() {
  const set = async (path, then) => { const r = await bpost(path); if (!r.ok) out(r.out, 'err'); if (then) then(r); setTimeout(refreshHW, 300); };
  document.querySelectorAll('[data-fclk]').forEach(b => b.onclick = () => {
    const n = b.dataset.fclk, mhz = $('fclk' + n).value;
    confirmDo(`Set FCLK${n} to ${mhz} MHz?${n === '0' ? '\nA running FPGA design gets this clock at once.' : ''}`,
      () => set('/api/clocks/fclk?' + qs({ n, mhz }), r => r.ok && out(`FCLK${n} = ${r.fclk_mhz} MHz`, 'ok')));
  });
  if ($('btnMeasure')) $('btnMeasure').onclick = async () => {
    $('measureOut').textContent = 'measuring for 0.5 s ...';
    const r = await bget('/api/io/fclk0');
    $('measureOut').textContent = r.ok ? `FCLK0 measured by the FPGA: ${r.fclk0_mhz} MHz` : r.out;
  };
  if ($('btnCpuSet')) $('btnCpuSet').onclick = () => {
    const g = $('cpuGov').value;
    set('/api/cpufreq/set?' + qs(g === 'userspace' ? { governor: g, khz: $('cpuKhz').value } : { governor: g }));
  };
  if ($('netSeg')) {
    const cur = BV.hw.net.advertised || [];
    const mode = cur.some(x => /1000/.test(x)) && cur.some(x => /100base/i.test(x)) ? 'auto' : cur.some(x => /1000/.test(x)) ? '1000' : '100';
    $('netSeg').querySelectorAll('button').forEach(b => {
      b.classList.toggle('on', b.dataset.net === mode);
      b.onclick = () => confirmDo('Change the link speed? The connection drops for a few seconds.', () => set('/api/net/speed?mode=' + b.dataset.net));
    });
  }
  document.querySelectorAll('[data-led]').forEach(sg => sg.querySelectorAll('button').forEach(b => b.onclick = () => {
    const on = b.dataset.v === 'on', low = sg.dataset.low === '1';
    set('/api/mio/set?' + qs({ pin: sg.dataset.led, mode: (on !== low) ? '1' : '0' }), loadMio);
  }));
  $('btnBeep').onclick = async () => { await bpost('/api/mio/set?pin=39&mode=1'); setTimeout(() => bpost('/api/mio/set?pin=39&mode=0'), 150); };
  $('btnSysWeb').onclick = () => set('/api/system?action=restart-web');
  $('btnSysReboot').onclick = () => confirmDo('Reboot the board now? It is back in about a minute.', () => set('/api/system?action=reboot'));
  $('btnSysOff').onclick = () => confirmDo('Power the board off? To start it again you must switch its 12 V supply off and on.', () => set('/api/system?action=poweroff'));
  if ($('btnNandScan')) {
    $('btnNandScan').onclick = async () => {
      $('nandScan').textContent = 'reading the first bytes of every block ...';
      const r = await bget('/api/nand/scan');
      if (!r.ok) return $('nandScan').textContent = r.out;
      $('nandScan').innerHTML = `${r.used_mb} MB in use, ${r.empty_blocks} empty blocks, ${r.unreadable_blocks} unreadable.<br>` +
        (r.found.length ? r.found.map(f => `<code>${f.offset}</code> ${esc(f.what)}`).join('<br>') : 'no known headers found');
    };
    $('btnNandData').onclick = () => api('/api/nand/backup', { raw: false }).then(r => { showTab('output'); if (!r.ok) out(r.out, 'err'); });
    $('btnNandRaw').onclick = () => api('/api/nand/backup', { raw: true }).then(r => { showTab('output'); if (!r.ok) out(r.out, 'err'); });
  }
}

async function loadMio() {
  if (BV.view !== 'board' || !$('mioTable')) return;
  const r = await bget('/api/mio');
  if (!r.ok) return;
  BV.mio = r;
  $('mioClk').textContent = r.gpio_clock_on ? '' : '(GPIO block asleep: levels not shown)';
  const lvl = p => p.level === undefined ? '' : `<span class="lvl ${p.level ? 'h' : 'l'}"></span> ${p.level}`;
  const ctl = p => (p.can_out || p.can_in) ? `<span class="seg" data-mio="${p.pin}">` +
      ['in', '0', '1'].map(m => `<button data-m="${m}" ${(m !== 'in' && !p.can_out) ? 'disabled' : ''}
        class="${(m === 'in' && p.dir === 'in') || (m !== 'in' && p.dir === 'out' && String(p.level) === m) ? 'on' : ''}">${m === 'in' ? 'In' : m}</button>`).join('') + '</span>' : '';
  $('mioTable').innerHTML = `<table class="mio-tbl"><tr><th>Pin</th><th>Function</th><th>Mux</th><th>Bank</th><th>I/O</th><th>Dir</th><th>Level</th><th>Control</th></tr>` +
    r.pins.map(p => `<tr class="${p.can_out || p.can_in ? '' : 'used'}"><td>MIO${p.pin}</td><td>${esc(p.func)}</td><td>${p.mux}</td><td>${p.bank}</td>
      <td>${p.io}${p.pullup ? ', pull-up' : ''}</td><td>${p.dir || ''}</td><td>${lvl(p)}</td><td>${ctl(p)}</td></tr>`).join('') + '</table>';
  $('mioTable').querySelectorAll('[data-mio] button').forEach(b => b.onclick = async () => {
    const pin = b.parentElement.dataset.mio;
    const r = await bpost('/api/mio/set?' + qs({ pin, mode: b.dataset.m }));
    if (!r.ok) out(r.out, 'err');
    loadMio();
  });
  const pin = n => r.pins[n];
  const btn = (id, p) => { if (!$(id)) return; const pressed = p.level === 0; $(id).className = 'lvl ' + (pressed ? 'h' : 'l'); $(id + 'Txt').textContent = pressed ? 'pressed' : 'released'; };
  btn('btnIp', pin(51)); btn('btnRst', pin(47));
  document.querySelectorAll('[data-led]').forEach(sg => {
    const p = pin(+sg.dataset.led), low = sg.dataset.low === '1';
    const on = p.dir === 'out' && (low ? p.level === 0 : p.level === 1);
    sg.querySelectorAll('button').forEach(b => b.classList.toggle('on', (b.dataset.v === 'on') === on));
  });
}

function updateSensors(s) {
  if (!s || !$('sTemp')) return;
  $('sTemp').textContent = s.temp_c !== undefined ? s.temp_c.toFixed(1) + ' °C' : '-';
  $('sCpu').textContent = s.cpu_pct === null || s.cpu_pct === undefined ? '-' : s.cpu_pct.toFixed(0) + ' %';
  $('sLoad').textContent = s.load.join(' / ');
  $('sMem').textContent = `${s.mem.used_mb} MB of ${s.mem.total_mb} MB`;
  if ($('sUp')) $('sUp').textContent = fmtUp(s.uptime_s);
  for (const k of Object.keys(NOMINAL)) if ($('v_' + k) && s[k] !== undefined) {
    $('v_' + k).textContent = s[k].toFixed(3) + ' V';
    const d = 100 * (s[k] - NOMINAL[k][1]) / NOMINAL[k][1];
    $('d_' + k).textContent = (d >= 0 ? '+' : '') + d.toFixed(1) + ' %';
    $('d_' + k).style.color = Math.abs(d) > 5 ? 'var(--err)' : '';
  }
  bpSample(s);
}

/* ---------------------------------------------------------------- Board view: layout, health, live chart */
const BC_DEFAULT = { order: [], hidden: [], collapsed: [], cols: 'auto', density: 'comfy', rate: 1500, histMin: 5, alarm: 75, alarmBeep: false,
  series: { temp: true, cpu: true, mem: false, vccint: false, vccaux: false, vccoddr: false } };
const BC = (() => { try { return Object.assign({}, BC_DEFAULT, JSON.parse(pref('board', '{}')) || {}); } catch (e) { return Object.assign({}, BC_DEFAULT); } })();
const bcSave = () => setPref('board', JSON.stringify(BC));
const CARDS = {   // id: [title, what it tells you]
  board: ['Board', 'Which board, chip, Ardzy image and Linux this is, where it booted from and why it last restarted.'],
  live: ['Live', 'Temperature, CPU, memory and supply voltages over time. Pick the lines to draw; point at the chart for the values at that moment.'],
  program: ['Program and FPGA', 'What runs on the board now: the project, its program, the FPGA design, and what starts at power-on.'],
  rails: ['Power rails', 'The chip measures its own supplies (XADC). More than 5 % away from nominal is shown in red: check the 12 V supply and the board.'],
  cpu: ['CPU and speed', 'The two ARM Cortex-A9 cores. Clock speeds are fixed by the boot loader.'],
  mem: ['Memory (RAM)', 'The 512 MB DDR3. "Available" is what new programs can still get (cache is given back when needed).'],
  clocks: ['Clocks', 'Every clock of the chip, from the 33.3 MHz crystal. FCLK0 is the clock of your FPGA design; you can change it here.'],
  sd: ['microSD card', 'The card Ardzy runs from: Linux (/) and the boot files (/boot).'],
  nand: ['NAND flash', 'The original Bitmain firmware on the board\'s own flash. Ardzy only reads it (backup).'],
  net: ['Network', 'The Ethernet link to your PC: address, speed and traffic.'],
  extras: ['LEDs, buzzer, buttons', 'The board\'s own status LEDs, buzzer and the two buttons: switch and read them here.'],
  system: ['System', 'Watchdog, restart of the board service, reboot and power-off.'],
  logger: ['Data logger', 'The board records its sensors, pins and your program\'s values to the SD card by itself, for hours, also with the PC off. Draw the logs or save them as CSV.'],
  mio: ['ARM pins (MIO 0-53)', 'The 54 pins of the ARM side: what each one does, its level, and control of the free ones.'],
};
const SERIES = {
  temp: { name: 'Temperature', unit: ' °C', color: '#e8743b', dec: 1, get: s => s.temp_c },
  cpu: { name: 'CPU', unit: ' %', color: '#4f8fe0', dec: 0, get: s => s.cpu_pct, lo: 0, hi: 100 },
  mem: { name: 'Memory used', unit: ' %', color: '#a35ad8', dec: 1, get: s => s.mem ? 100 * s.mem.used_mb / s.mem.total_mb : undefined, lo: 0, hi: 100 },
  vccint: { name: 'VCCINT', unit: ' V', color: '#2fbf6c', dec: 3, get: s => s.vccint },
  vccaux: { name: 'VCCAUX', unit: ' V', color: '#d0a020', dec: 3, get: s => s.vccaux },
  vccoddr: { name: 'VCC_DDR', unit: ' V', color: '#20a3a3', dec: 3, get: s => s.vccoddr },
};
BV.samples = [];

function dashArrange() {
  const dash = $('dash'), cards = [...dash.querySelectorAll('.dcard[data-card]')];
  const byId = Object.fromEntries(cards.map(c => [c.dataset.card, c]));
  const order = BC.order.filter(id => byId[id]).concat(cards.map(c => c.dataset.card).filter(id => !BC.order.includes(id)));
  order.forEach(id => dash.appendChild(byId[id]));
  dash.classList.toggle('compact', BC.density === 'compact');
  dash.style.gridTemplateColumns = BC.cols === 'auto' ? '' : `repeat(${BC.cols}, minmax(0, 1fr))`;
  for (const c of cards) {
    const id = c.dataset.card, h = c.querySelector('h3');
    c.hidden = BC.hidden.includes(id);
    c.classList.toggle('collapsed', BC.collapsed.includes(id));
    if (!h || h.querySelector('.cardctl')) continue;
    h.draggable = true;
    h.title = 'Drag to move this card';
    const ctl = document.createElement('span');
    ctl.className = 'cardctl';
    ctl.innerHTML = `<button class="ghost tiny" data-c="info" title="${esc(CARDS[id] ? CARDS[id][1] : '')}">?</button>` +
      `<button class="ghost tiny" data-c="fold" title="Fold or open this card">${c.classList.contains('collapsed') ? '+' : '-'}</button>` +
      `<button class="ghost tiny" data-c="hide" title="Hide this card (Customize shows it again)">&times;</button>`;
    h.appendChild(ctl);
    ctl.querySelector('[data-c=info]').onclick = e => { e.stopPropagation(); const n = c.querySelector('.cardinfo');
      if (n) n.remove(); else h.insertAdjacentHTML('afterend', `<div class="cardinfo">${esc(CARDS[id][1])}</div>`); };
    ctl.querySelector('[data-c=fold]').onclick = e => { e.stopPropagation();
      BC.collapsed = c.classList.toggle('collapsed') ? BC.collapsed.concat(id) : BC.collapsed.filter(x => x !== id);
      e.target.textContent = c.classList.contains('collapsed') ? '+' : '-'; bcSave(); if (id === 'live') drawChart(); };
    ctl.querySelector('[data-c=hide]').onclick = e => { e.stopPropagation(); BC.hidden = BC.hidden.concat(id); bcSave(); c.hidden = true;
      out(`Card "${CARDS[id][0]}" hidden: Customize shows it again.`, 'ok'); };
    h.ondragstart = e => { e.dataTransfer.setData('text/plain', id); c.classList.add('dragging'); };
    h.ondragend = () => c.classList.remove('dragging');
    c.ondragover = e => { e.preventDefault(); c.classList.add('dropto'); };
    c.ondragleave = () => c.classList.remove('dropto');
    c.ondrop = e => {
      e.preventDefault(); c.classList.remove('dropto');
      const from = byId[e.dataTransfer.getData('text/plain')];
      if (!from || from === c) return;
      const r = c.getBoundingClientRect(), after = e.clientY > r.top + r.height / 2;
      dash.insertBefore(from, after ? c.nextSibling : c);
      BC.order = [...dash.querySelectorAll('.dcard[data-card]')].map(x => x.dataset.card); bcSave();
      if (from.dataset.card === 'live' || c.dataset.card === 'live') drawChart();
    };
  }
}

function dashCustomize() {
  const ids = [...$('dash').querySelectorAll('.dcard[data-card]')].map(c => c.dataset.card);
  const list = ids.length ? ids : Object.keys(CARDS);
  const opt = (v, t, cur) => `<option value="${v}" ${String(v) === String(cur) ? 'selected' : ''}>${t}</option>`;
  $('bcForm').innerHTML = `
    <div class="ed-grid">
      <label>Columns <select data-bc="cols">${['auto', 1, 2, 3, 4].map(v => opt(v, v === 'auto' ? 'as many as fit' : v, BC.cols)).join('')}</select></label>
      <label>Density <select data-bc="density">${opt('comfy', 'comfortable', BC.density)}${opt('compact', 'compact', BC.density)}</select></label>
      <label>Update every <select data-bc="rate">${[[1000, '1 s'], [1500, '1.5 s'], [3000, '3 s'], [5000, '5 s'], [0, 'paused']].map(([v, t]) => opt(v, t, BC.rate)).join('')}</select></label>
      <label>Chart shows the last <select data-bc="histMin">${[2, 5, 15, 30, 60].map(v => opt(v, v + ' minutes', BC.histMin)).join('')}</select></label>
      <label>Temperature alarm at <select data-bc="alarm">${[60, 65, 70, 75, 80, 85].map(v => opt(v, v + ' °C', BC.alarm)).join('')}</select></label>
      <label class="check" style="flex-direction:row;align-items:center;margin-top:24px"><input type="checkbox" data-bc="alarmBeep" ${BC.alarmBeep ? 'checked' : ''}> beep on the alarm</label>
    </div>
    <h3 class="bc-h">Cards <span class="hint">(tick to show, arrows to move; or drag a card by its title)</span></h3>
    <div class="bc-cards">${list.map((id, i) => `<div class="bc-row"><label class="check"><input type="checkbox" data-show="${id}" ${BC.hidden.includes(id) ? '' : 'checked'}> ${esc(CARDS[id][0])}</label>
      <span class="hint">${esc(CARDS[id][1])}</span>
      <button class="ghost tiny" data-mv="${id}" data-d="-1" ${i ? '' : 'disabled'}>&uarr;</button><button class="ghost tiny" data-mv="${id}" data-d="1" ${i < list.length - 1 ? '' : 'disabled'}>&darr;</button></div>`).join('')}</div>
    <div class="row"><button class="ghost small" id="bcReset">Back to the standard layout</button></div>`;
  const redo = () => { bcSave(); dashArrange(); drawChart(); };
  $('bcForm').querySelectorAll('[data-bc]').forEach(el => el.onchange = () => {
    const k = el.dataset.bc;
    BC[k] = el.type === 'checkbox' ? el.checked : (k === 'cols' && el.value !== 'auto') || ['rate', 'histMin', 'alarm'].includes(k) ? +el.value : el.value;
    if (k === 'rate') pollSensorsRestart();
    redo();
  });
  $('bcForm').querySelectorAll('[data-show]').forEach(el => el.onchange = () => {
    const id = el.dataset.show;
    BC.hidden = el.checked ? BC.hidden.filter(x => x !== id) : BC.hidden.concat(id);
    redo();
  });
  $('bcForm').querySelectorAll('[data-mv]').forEach(b => b.onclick = e => {
    e.preventDefault();
    const o = list.slice(), i = o.indexOf(b.dataset.mv), j = i + +b.dataset.d;
    [o[i], o[j]] = [o[j], o[i]];
    BC.order = o; redo(); dashCustomize();
  });
  $('bcReset').onclick = e => { e.preventDefault(); Object.assign(BC, JSON.parse(JSON.stringify(BC_DEFAULT))); pollSensorsRestart(); redo(); refreshHW(); dashCustomize(); };
  if (!$('dlgBoardCfg').open) $('dlgBoardCfg').showModal();
}

// the Live card: chart with chosen lines, now / min / average / max, hover readout, CSV
function liveCardHtml() {
  return `<div class="dcard" data-card="live"><h3>Live</h3>
    <div class="live-series" id="liveSeries">${Object.entries(SERIES).map(([k, s]) =>
      `<label class="chip ${BC.series[k] ? 'on' : ''}" style="--c:${s.color}"><input type="checkbox" data-ser="${k}" ${BC.series[k] ? 'checked' : ''}>${s.name}</label>`).join('')}</div>
    <div class="live-chart"><canvas id="spark"></canvas><div class="live-tip" id="liveTip" hidden></div></div>
    <table class="live-stats" id="liveStats"></table>
    <div class="row"><span class="hint" id="liveSpan"></span><span class="grow"></span>
      <button class="ghost small" id="liveClear" title="Start the history again">Clear</button>
      <button class="ghost small" id="liveCsv" title="Save the history as a CSV file (spreadsheet)">Save CSV</button></div>
    ${kv([['Load (1/5/15 min)', '<span id="sLoad">-</span>'], ['Memory used', '<span id="sMem">-</span>']])}
    <span id="sTemp" hidden></span><span id="sCpu" hidden></span></div>`;
}
function wireLive() {
  if (!$('liveSeries')) return;
  $('liveSeries').querySelectorAll('[data-ser]').forEach(c => c.onchange = () => {
    BC.series[c.dataset.ser] = c.checked; c.parentElement.classList.toggle('on', c.checked); bcSave(); drawChart();
  });
  $('liveClear').onclick = () => { BV.samples = []; drawChart(); };
  $('liveCsv').onclick = async () => {
    const keys = Object.keys(SERIES);
    const csv = ['time,' + keys.map(k => SERIES[k].name + SERIES[k].unit.trim().replace('°', ' deg')).join(',')]
      .concat(BV.samples.map(s => new Date(s.t).toTimeString().slice(0, 8) + ',' + keys.map(k => s[k] === undefined ? '' : (+s[k]).toFixed(SERIES[k].dec)).join(','))).join('\n');
    const r = await api('/api/savelog', { name: 'board_history', ext: 'csv', text: csv + '\n' });
    out(r.ok ? 'History saved: ' + r.path : 'Not saved: ' + r.out, r.ok ? 'ok' : 'err');
  };
  const cv = $('spark');
  cv.onmousemove = e => { BV.hoverX = (e.clientX - cv.getBoundingClientRect().left) / cv.clientWidth; drawChart(); };
  cv.onmouseleave = () => { BV.hoverX = null; drawChart(); };
}
function bpSample(s) {
  const now = Date.now(), smp = { t: now };
  for (const [k, d] of Object.entries(SERIES)) { const v = d.get(s); if (v !== undefined && v !== null) smp[k] = +v; }
  BV.samples.push(smp);
  const keep = now - BC.histMin * 60000;
  while (BV.samples.length && BV.samples[0].t < keep) BV.samples.shift();
  bpHealth(s);
  drawChart();
}
function drawChart() {
  const cv = $('spark');
  if (!cv || !cv.clientWidth) return;
  const dpr = window.devicePixelRatio || 1, cw = Math.round(cv.clientWidth * dpr), ch = Math.round(cv.clientHeight * dpr);
  if (cv.width !== cw || cv.height !== ch) { cv.width = cw; cv.height = ch; }
  const g = cv.getContext('2d'), W = cv.width, H = cv.height, css = getComputedStyle(document.body);
  const span = BC.histMin * 60000, now = Date.now(), t0 = now - span, pad = 6 * dpr;
  g.clearRect(0, 0, W, H);
  g.strokeStyle = css.getPropertyValue('--line'); g.lineWidth = 1;
  for (let i = 0; i <= 4; i++) { const y = Math.round(pad + (H - 2 * pad) * i / 4) + .5; g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
  for (let m = 1; m < BC.histMin; m++) {                        // a light tick each minute
    const x = Math.round(W * (1 - m * 60000 / span)) + .5; g.globalAlpha = .5; g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke(); g.globalAlpha = 1;
  }
  const on = Object.keys(SERIES).filter(k => BC.series[k]);
  const stats = {};
  for (const k of on) {
    const pts = BV.samples.filter(s => s[k] !== undefined);
    if (!pts.length) continue;
    const vals = pts.map(s => s[k]), d = SERIES[k];
    let lo = d.lo !== undefined ? d.lo : Math.min(...vals), hi = d.hi !== undefined ? d.hi : Math.max(...vals);
    if (d.lo === undefined) { const m = Math.max((hi - lo) * .15, Math.abs(hi) * .002 + 1e-6); lo -= m; hi += m; }
    stats[k] = { now: vals[vals.length - 1], min: Math.min(...vals), max: Math.max(...vals), avg: vals.reduce((a, b) => a + b, 0) / vals.length, lo, hi };
    g.strokeStyle = d.color; g.lineWidth = 2 * dpr; g.lineJoin = 'round'; g.beginPath();
    pts.forEach((s, i) => { const x = W * (s.t - t0) / span, y = H - pad - (H - 2 * pad) * (s[k] - lo) / (hi - lo); i ? g.lineTo(x, y) : g.moveTo(x, y); });
    g.stroke();
  }
  if (BV.hoverX !== null && BV.hoverX !== undefined && BV.samples.length) {     // the readout where the mouse is
    const tx = t0 + BV.hoverX * span;
    let best = BV.samples[0];
    for (const s of BV.samples) if (Math.abs(s.t - tx) < Math.abs(best.t - tx)) best = s;
    const x = W * (best.t - t0) / span;
    g.strokeStyle = css.getPropertyValue('--muted'); g.lineWidth = dpr; g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke();
    const tip = $('liveTip');
    tip.hidden = false;
    tip.innerHTML = `<b>${new Date(best.t).toTimeString().slice(0, 8)}</b>` + on.filter(k => best[k] !== undefined)
      .map(k => `<div><i style="background:${SERIES[k].color}"></i>${SERIES[k].name} ${best[k].toFixed(SERIES[k].dec)}${SERIES[k].unit}</div>`).join('');
    tip.style.left = Math.min(cv.clientWidth - 170, Math.max(0, x / dpr + 10)) + 'px';
  } else if ($('liveTip')) $('liveTip').hidden = true;
  if ($('liveStats')) $('liveStats').innerHTML = on.length ? '<tr><th></th><th>now</th><th>min</th><th>average</th><th>max</th></tr>' +
    on.map(k => { const s = stats[k], d = SERIES[k], f = v => s ? v.toFixed(d.dec) + d.unit : '-';
      return `<tr><td><i style="background:${d.color}"></i>${d.name}</td><td class="num">${s ? f(s.now) : '-'}</td><td class="num">${s ? f(s.min) : '-'}</td><td class="num">${s ? f(s.avg) : '-'}</td><td class="num">${s ? f(s.max) : '-'}</td></tr>`; }).join('')
    : '<tr><td class="hint">Tick a line above to draw it.</td></tr>';
  if ($('liveSpan')) $('liveSpan').textContent = `last ${BC.histMin} min, ${BV.samples.length} samples` + (BC.rate ? `, every ${BC.rate / 1000} s` : ', paused');
}

// the health strip: everything important at one glance
function bpHealth(s) {
  const h = BV.hw, st = BV.status || S.status || {};
  if (!$('health') || !h) return;
  const chip = (id, lvl, label, val, card) => `<button class="hchip ${lvl}" data-go="${card}" title="Go to the card"><span class="hl">${label}</span><span class="hv">${val}</span></button>`;
  const t = s.temp_c, tl = t >= BC.alarm ? 'bad' : t >= BC.alarm - 10 ? 'warn' : 'good';
  const memPct = s.mem ? 100 * s.mem.used_mb / s.mem.total_mb : 0;
  const worst = Math.max(...Object.keys(NOMINAL).filter(k => s[k] !== undefined).map(k => Math.abs(100 * (s[k] - NOMINAL[k][1]) / NOMINAL[k][1])));
  const sd = h.storage['/'], sdFree = 100 * sd.free_mb / sd.size_mb;
  const fpga = h.fpga.state === 'operating';
  const items = [
    chip('t', tl, 'Temperature', t !== undefined ? t.toFixed(1) + ' °C' : '-', 'live'),
    chip('c', s.cpu_pct > 90 ? 'warn' : 'good', 'CPU', s.cpu_pct !== null && s.cpu_pct !== undefined ? s.cpu_pct.toFixed(0) + ' %' : '-', 'live'),
    chip('m', memPct > 85 ? 'warn' : 'good', 'Memory', memPct.toFixed(0) + ' %', 'mem'),
    chip('r', worst > 5 ? 'bad' : worst > 3 ? 'warn' : 'good', 'Supplies', worst > 5 ? 'out of range' : 'OK (' + worst.toFixed(1) + ' %)', 'rails'),
    chip('s', sdFree < 10 ? 'bad' : sdFree < 25 ? 'warn' : 'good', 'SD card', TF('{0} % free', sdFree.toFixed(0)), 'sd'),
    chip('f', fpga ? 'good' : 'idle', 'FPGA', fpga ? (h.fpga.project || 'loaded') : 'empty', 'program'),
    chip('p', st.running ? 'good' : 'idle', 'Program', st.current ? (st.running ? 'running' : 'stopped') : 'none', 'program'),
    chip('n', h.net.carrier ? 'good' : 'bad', 'Link', h.net.carrier ? h.net.speed + ' Mbit/s' : 'down', 'net'),
    chip('u', 'idle', 'Up for', fmtUp(s.uptime_s), 'board'),
  ];
  $('health').innerHTML = items.join('');
  $('health').querySelectorAll('[data-go]').forEach(b => b.onclick = () => {
    const c = $('dash').querySelector(`[data-card="${b.dataset.go}"]`);
    if (!c) return;
    if (c.hidden) { BC.hidden = BC.hidden.filter(x => x !== b.dataset.go); bcSave(); c.hidden = false; }
    c.scrollIntoView({ behavior: 'smooth', block: 'center' }); c.classList.add('flash'); setTimeout(() => c.classList.remove('flash'), 1200);
  });
  // the temperature alarm (once per crossing)
  if (t >= BC.alarm && !BV.alarmOn) {
    BV.alarmOn = true;
    out(`Board temperature ${t.toFixed(1)} °C reached the alarm level (${BC.alarm} °C). Check the airflow or turn the fans up (I/O view).`, 'warn');
    if (BC.alarmBeep) { bpost('/api/mio/set?pin=39&mode=1'); setTimeout(() => bpost('/api/mio/set?pin=39&mode=0'), 400); }
  } else if (t < BC.alarm - 2) BV.alarmOn = false;
}

// the Program and FPGA card
async function programCard() {
  const r = await api('/api/board/status');
  if (!r.ok || !$('progBody')) return;
  const st = r.status; BV.status = st;
  $('progBody').innerHTML = kv([
    ['Project on the board', st.current ? `<b>${esc(st.current)}</b>` : 'none'],
    ['Its program', st.current ? (st.running ? '<span class="good-t">running</span>' : 'stopped') : '-'],
    ['FPGA', `${esc(BV.hw.fpga.state)}${BV.hw.fpga.project ? ' (' + esc(BV.hw.fpga.project) + ')' : ''}${BV.hw.fpga.io_design ? ', pin-control design' : ''}`],
    ['Starts at power-on', st.default ? esc(st.default) : 'nothing (Ardzy waits for the app)'],
    ['Safe mode', st.safemode ? '<span class="bad-t">ON</span> (no project starts)' : 'off'],
    ['Projects on the board', (st.projects || []).length]]) +
    `<div class="row"><button class="ghost small" id="pgStop" ${st.running ? '' : 'disabled'}>Stop</button>
     <button class="ghost small" id="pgRestart" ${st.current ? '' : 'disabled'}>Restart</button>
     <button class="ghost small" id="pgMon">Open the Monitor</button></div>`;
  $('pgStop').onclick = () => boardAction('stop').then(programCard);
  $('pgRestart').onclick = () => boardAction('restart').then(programCard);
  $('pgMon').onclick = () => { showTab('monitor'); const b = $('bottom'); if (b.classList.contains('collapsed')) S.panelToggle(); };
}

async function dashReport() {
  const h = BV.hw;
  if (!h) return;
  const s = h.sensors, lines = [`Ardzy board report, ${new Date().toLocaleString()}`, '',
    `Board: ${h.board}`, `Chip: ${h.chip} (silicon ${h.boot.ps_version}), IDCODE ${h.boot.idcode}`,
    `Ardzy image: ${h.image.ARDZY_VERSION} (${h.image.BUILD_DATE}), ${h.os}, kernel ${h.kernel}`,
    `Boot: ${h.boot.boot_mode}, last reset: ${h.boot.last_reset.join(', ')}, up ${fmtUp(s.uptime_s)}`, '',
    `Temperature: ${s.temp_c} C, CPU ${s.cpu_pct} %, load ${s.load.join(' / ')}`,
    ...Object.entries(NOMINAL).map(([k, [n, v]]) => `${n}: ${s[k]} V (nominal ${v} V)`), '',
    `Memory: ${h.memory.used_mb} MB used of ${h.memory.total_mb} MB, available ${h.memory.available_mb} MB`,
    `Clocks: CPU ${h.clocks.cpu_mhz} MHz, DDR ${h.clocks.ddr_mhz} MHz, FCLK ${h.clocks.fclk.map(f => f.n + '=' + f.mhz).join(' ')} MHz`,
    `SD card: ${h.storage.card.name}, ${h.storage['/'].free_mb} MB free of ${h.storage['/'].size_mb} MB`,
    `Network: ${h.net.hostname}.local, MAC ${h.net.mac}, ${h.net.speed} Mbit/s ${h.net.duplex}, IPv4 ${h.net.ipv4.join(', ') || '-'}`,
    `FPGA: ${h.fpga.state}${h.fpga.project ? ' (' + h.fpga.project + ')' : ''}`,
    `NAND: ${h.nand.chip.part}, ${h.nand.enabled ? h.nand.bad_blocks + ' bad blocks' : 'not enabled'}`,
    `Watchdog: ${h.watchdog.device}, ${h.watchdog.timeout_s}, ${h.watchdog.state}`];
  const r = await api('/api/savelog', { name: 'board_report', ext: 'txt', text: lines.join('\n') + '\n' });
  out(r.ok ? 'Board report saved: ' + r.path : 'Not saved: ' + r.out, r.ok ? 'ok' : 'err');
}

let pollTimer = null;
function pollSensorsRestart() { clearTimeout(pollTimer); pollTimer = setTimeout(pollSensors, 200); }

async function pollSensors() {
  clearTimeout(pollTimer);
  if (BV.view === 'board' && S.connected && BV.hw && BC.rate) {
    const r = await bget('/api/sensors');
    if (r.ok) updateSensors(r);
    if (Date.now() - BV.last > 4000) {
      BV.last = Date.now(); loadMio(); programCard();
      if (typeof LG !== 'undefined' && LG.status && LG.status.running) loggerRefresh();     // (a recording: its numbers grow)
    }
  }
  pollTimer = setTimeout(pollSensors, BC.rate || 1500);
}

/* ================================================================ I/O view */
async function refreshIO() {
  if (!S.connected) { $('ioState').textContent = 'no board'; $('ioBody').innerHTML = '<div class="empty">No board connected.</div>'; BV.ioBuilt = false; return; }
  const r = await bget('/api/io');
  if (!r.ok) {
    $('ioState').textContent = 'pin-control design not loaded';
    $('btnIoLoad').textContent = 'Load pin-control design';
    $('ioBody').innerHTML = `<div class="dcard wide"><h3>${T('Pin control')}</h3><p>${esc(T(r.out))}.</p>
      <p class="hint">${TF('The pin-control design (project {0}) connects every FPGA pin to registers, so this page can read and drive each pin, the LEDs and the fans. Press {1}. It replaces the current FPGA design until you upload another project.', '<b>ardzy_io</b>', '<b>' + T('Load pin-control design') + '</b>')}</p></div>`;
    BV.ioBuilt = false;
    return;
  }
  $('ioState').textContent = TF('pin-control design running ({0})', r.id);
  $('btnIoLoad').textContent = 'Reload pin-control design';
  if (!BV.ioBuilt) await buildIO(r);
  updateIO(r);
}

async function buildIO(r) {
  if (!BV.pinInfo) BV.pinInfo = await (await fetch('pins.json')).json();
  const cinfo = {}; BV.pinInfo.connectors.forEach(c => cinfo[c.port] = c);
  const row = (p, label, sub, opts = 'in01') => `<div class="pinrow" data-name="${esc(p.name)}">
      <span class="p">${esc(p.pin)}</span><span>${label}<small>${sub}</small></span><span class="lvl" data-l="${esc(p.name)}"></span>
      <span class="seg" data-io="${esc(p.name)}">${opts.includes('in') ? '<button data-m="in">In</button>' : ''}${opts.includes('01') ? '<button data-m="0">0</button><button data-m="1">1</button>' : ''}</span></div>`;
  const by = {}; r.pins.forEach(p => by[p.name] = p);
  const cards = [];
  for (let n = 1; n <= 9; n++) {
    cards.push(`<div class="dcard conn"><h3>${TF('Connector J{0}', n)}</h3>` + [0, 1, 2, 3].map(b => {
      const p = by[`j${n}[${b}]`], c = cinfo[`j${n}[${b}]`] || {};
      return row(p, `j${n}[${b}] &middot; pin ${c.cpin}`, TF('Bitmain name {0}', c.bitmain));
    }).join('') + '</div>');
  }
  cards.push(`<div class="dcard conn"><h3>On-board LEDs (active low)</h3>` + [0, 1, 2, 3].map(i =>
    row(by[`leds[${i}]`], `LED ${i}`, '0 = on, In = off')).join('') + '</div>');
  cards.push(`<div class="dcard conn"><h3>I2C lines, test point</h3>` +
    [['i2c1_scl', 'I2C1 SCL', 'J1-J8 pin 4, 1k pull-up'], ['i2c1_sda', 'I2C1 SDA', 'J1-J8 pin 3'], ['i2c2_scl', 'I2C2 SCL', 'J9 pin 4'],
     ['i2c2_sda', 'I2C2 SDA', 'J9 pin 3'], ['tp1', 'TP1', 'test point (CLOCK_OUT)']].map(([k, l, s]) => row(by[k], l, s)).join('') + '</div>');
  cards.push(`<div class="dcard conn"><h3>Board ID (read only)</h3>` + [0, 1, 2, 3].map(i =>
    row(by[`board_id[${i}]`], `ID${i}`, 'fixed strap', 'in')).join('') + '<div class="hint" id="boardIdVal"></div></div>');
  cards.push(`<div class="dcard"><h3>Fans (6 headers)</h3>
    <div class="row"><span class="seg" id="fanOn"><button data-v="0">Full speed</button><button data-v="1">PWM</button></span>
      <label class="hint">duty <input type="range" min="0" max="100" step="1" id="fanDuty" style="vertical-align:middle"> <b id="fanDutyTxt"></b></label></div>
    <div class="row"><label class="hint">PWM frequency <input type="number" id="fanHz" min="100" max="100000" step="100" style="width:100px"> Hz</label>
      <button class="ghost small" id="fanHzSet">Set</button></div>
    <div class="fanrpm" id="fanRpm"></div>
    <div class="hint">4-pin fans: PWM on pin 4 (J18, shared), speed from pin 3. "Full speed" holds PWM high. 2 pulses per turn.</div></div>`);
  cards.push(`<div class="dcard"><h3>FPGA clock</h3><div class="kv"><span>FCLK0 measured</span><span id="ioFclk">-</span></div>
    <div class="row"><button class="ghost small" id="ioMeasure">Measure</button></div>
    <div class="hint">Counted by the FPGA against Linux time (0.5 s). Change it in the Board view, Clocks card.</div></div>`);
  $('ioBody').innerHTML = cards.join('');
  $('ioBody').querySelectorAll('[data-io] button').forEach(b => b.onclick = async () => {
    const name = b.parentElement.dataset.io;
    const r = await bpost('/api/io/set?' + qs({ name, mode: b.dataset.m }));
    if (!r.ok) out(r.out, 'err');
    refreshIO();
  });
  $('fanOn').querySelectorAll('button').forEach(b => b.onclick = () => bpost('/api/io/fan?on=' + b.dataset.v).then(refreshIO));
  $('fanDuty').onchange = () => bpost('/api/io/fan?duty=' + $('fanDuty').value).then(refreshIO);
  $('fanDuty').oninput = () => $('fanDutyTxt').textContent = $('fanDuty').value + ' %';
  $('fanHzSet').onclick = () => bpost('/api/io/fan?hz=' + $('fanHz').value).then(refreshIO);
  $('ioMeasure').onclick = async () => { $('ioFclk').textContent = 'measuring ...'; const m = await bget('/api/io/fclk0'); $('ioFclk').textContent = m.ok ? m.fclk0_mhz + ' MHz' : m.out; };
  BV.ioBuilt = true;
}

function updateIO(r) {
  r.pins.forEach(p => {
    const l = document.querySelector(`[data-l="${CSS.escape(p.name)}"]`); if (l) l.className = 'lvl ' + (p.level ? 'h' : 'l');
    const sg = document.querySelector(`[data-io="${CSS.escape(p.name)}"]`);
    if (sg) sg.querySelectorAll('button').forEach(b => b.classList.toggle('on', p.mode === 'in' ? b.dataset.m === 'in' : b.dataset.m === String(p.level)));
  });
  const id = [0, 1, 2, 3].map(i => r.pins.find(p => p.name === `board_id[${i}]`).level);
  if ($('boardIdVal')) $('boardIdVal').textContent = `ID3..ID0 = ${id.slice().reverse().join('')} (value ${id.reduce((a, v, i) => a + (v << i), 0)})`;
  const f = r.fan;
  $('fanOn').querySelectorAll('button').forEach(b => b.classList.toggle('on', (b.dataset.v === '1') === f.on));
  if (document.activeElement !== $('fanDuty')) { $('fanDuty').value = f.duty_pct; $('fanDutyTxt').textContent = f.duty_pct + ' %'; }
  if (document.activeElement !== $('fanHz')) $('fanHz').value = f.pwm_hz;
  $('fanRpm').innerHTML = f.rpm.map((v, i) => `<div>FAN${i + 1}<b>${v} rpm</b></div>`).join('');
}

async function pollIO() {
  if (BV.view === 'io' && S.connected && BV.ioBuilt) {
    const r = await bget('/api/io');
    if (r.ok) updateIO(r); else refreshIO();
  }
  setTimeout(pollIO, 500);
}

/* ================================================================ wiring */
document.querySelectorAll('.views button').forEach(b => b.onclick = () => showView(b.dataset.view));
$('btnHwRefresh').onclick = refreshHW;
$('btnHwCustom').onclick = dashCustomize;
$('btnHwReport').onclick = dashReport;
window.addEventListener('resize', () => { if (BV.view === 'board') drawChart(); });
$('btnIoLoad').onclick = async () => {
  showTab('output');
  const r = await api('/api/io/load', {});
  if (!r.ok) return out(r.out, 'err');
  const wait = setInterval(async () => { if (!S.busy) { clearInterval(wait); BV.ioBuilt = false; refreshIO(); } }, 700);
};
pollSensors();
pollIO();
