/* Ardzy - Tools view: logic analyzer, PWM / signal generator, frequency meter, UART terminal, I2C.
   Everything runs in the FPGA's pin-control design (board API /api/io/..., /api/la/..., /api/i2c/...).
   Helpers from app.js / board.js: $, esc, api, out, S, BV, bget, bpost, qs. */
const TL = { built: false, signals: [], la: null, view: { start: 0, span: 4096 }, cursors: [], uartOn: false, timers: [] };
const LA_RATES = [[100e6, '100 MHz'], [50e6, '50 MHz'], [25e6, '25 MHz'], [10e6, '10 MHz'], [5e6, '5 MHz'], [1e6, '1 MHz'],
  [500e3, '500 kHz'], [100e3, '100 kHz'], [10e3, '10 kHz'], [1e3, '1 kHz']];
const LA_COLORS = ['#2f9e58', '#4f8fe0', '#e0884f', '#b65fd6', '#d6b23a', '#3ab8b8', '#e05f8a', '#8a9a2e'];
const fmtHz = f => f >= 1e6 ? (f / 1e6).toFixed(f >= 1e7 ? 2 : 3) + ' MHz' : f >= 1e3 ? (f / 1e3).toFixed(2) + ' kHz' : (+f).toFixed(f < 10 ? 3 : 1) + ' Hz';
const fmtT = s => { const a = Math.abs(s); return a >= 1 ? s.toFixed(3) + ' s' : a >= 1e-3 ? (s * 1e3).toFixed(3) + ' ms' : a >= 1e-6 ? (s * 1e6).toFixed(3) + ' us' : (s * 1e9).toFixed(0) + ' ns'; };
const pinOptions = (sel, inputs) => TL.signals.filter((s, i) => inputs || i < 41 || (i >= 45 && i < 49))
  .map(s => `<option ${s === sel ? 'selected' : ''}>${esc(s)}</option>`).join('');

async function toolsShow() {
  if (!S.connected) { $('toolsState').textContent = 'no board'; $('toolsBody').innerHTML = '<div class="empty">No board connected.</div>'; TL.built = false; return; }
  const r = await bget('/api/io');
  if (!r.ok || r.version !== 2) {
    $('toolsState').textContent = r.ok ? 'old pin-control design (version 1)' : 'pin-control design not loaded';
    $('btnToolsLoad').textContent = 'Load pin-control design';
    $('toolsBody').innerHTML = `<div class="dcard wide"><h3>${T('Instruments')}</h3><p>${esc(T(r.ok ? 'The tools need version 2 of the pin-control design.' : r.out))}</p>
      <p class="hint">${TF("The instruments live in the FPGA (the pin-control design, project ardzy_io): a 4096-sample logic analyzer over 56 signals, 8 PWM / clock generators, 4 frequency meters, a UART on any pins and I2C on the board's two buses. Press {0}.", '<b>' + T('Load pin-control design') + '</b>')}</p></div>`;
    TL.built = false;
    return;
  }
  $('toolsState').textContent = TF('pin-control design v2 running, chip {0}', r.dna || '');
  $('btnToolsLoad').textContent = 'Reload pin-control design';
  if (!TL.built) {
    TL.signals = (await bget('/api/io/signals')).signals || [];
    buildTools();
  }
  refreshTools();
}

function buildTools() {
  const sigOpts = s => `<option value="">none</option>` + TL.signals.map(x => `<option ${x === s ? 'selected' : ''}>${esc(x)}</option>`).join('');
  $('toolsBody').innerHTML = `
  <div class="dcard wide"><h3>Logic analyzer<span class="grow"></span><span class="hint" id="laState"></span></h3>
    <div class="row">
      <label class="hint">rate <select id="laRate">${LA_RATES.map(([v, t]) => `<option value="${v}" ${v === 1e6 ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
      <label class="hint">before trigger <select id="laPre">${[0, 10, 25, 50, 75, 90].map(p => `<option value="${p}" ${p === 10 ? 'selected' : ''}>${p} %</option>`).join('')}</select></label>
      <label class="hint">trigger <select id="laTrigSig">${sigOpts('')}</select>
        <select id="laTrigKind"><option value="rise">rising edge</option><option value="fall">falling edge</option><option value="1">is 1</option><option value="0">is 0</option></select></label>
      <button class="primary small" id="laStart">Start</button><button class="ghost small" id="laForce">Trigger now</button>
      <button class="ghost small" id="laStop">Stop</button><button class="ghost small" id="laCsv">Save CSV</button>
    </div>
    <div class="row"><label class="hint grow">show <input id="laShow" class="grow" style="width:70%" value="j1[0] j1[1] j1[2] j1[3] j4[0] j4[1] fan_pwm"
      title="signal names separated by spaces, for example j3[*] for all of J3" spellcheck="false"></label>
      <span class="hint">wheel = zoom, drag = move, click = cursor A then B</span></div>
    <canvas id="laCanvas" class="la-canvas"></canvas>
    <div class="hint" id="laInfo">4096 samples of 56 signals: 49 FPGA pins, 6 fan speed inputs, the fan PWM. Start, then make something happen on the pins.</div>
  </div>

  <div class="dcard wide"><h3>PWM, clock and servo generator (8 channels)</h3>
    <table class="tl-tbl"><tr><th>Ch</th><th>Pin</th><th>Frequency</th><th>Duty %</th><th>or pulse (us)</th><th>Now</th><th></th></tr>
    ${[0, 1, 2, 3, 4, 5, 6, 7].map(c => `<tr data-pwm="${c}"><td>PWM${c}</td>
      <td><select class="pwmPin"><option value="">(not on a pin)</option>${pinOptions('', false)}</select></td>
      <td><input class="pwmHz" type="number" min="0.02" step="any" value="1000" style="width:110px"> Hz</td>
      <td><input class="pwmDuty" type="number" min="0" max="100" step="any" value="50" style="width:70px"></td>
      <td><input class="pwmUs" type="number" min="0" step="any" placeholder="servo 500..2500" style="width:120px"></td>
      <td class="num pwmNow"></td>
      <td><button class="small pwmSet">Set</button> <button class="ghost small pwmOff">Off</button></td></tr>`).join('')}</table>
    <div class="hint">Up to 50 MHz (FPGA clock / 2). Servo: 50 Hz and a pulse of 1000 to 2000 us (1500 = middle). Pins become outputs while they carry a channel.</div>
  </div>

  <div class="dcard"><h3>Frequency meter<span class="grow"></span>
      <label class="hint">gate <select id="mGate">${[[0.1, '0.1 s'], [0.5, '0.5 s'], [1, '1 s'], [2, '2 s'], [5, '5 s']].map(([v, t]) => `<option value="${v}" ${v === 1 ? 'selected' : ''}>${t}</option>`).join('')}</select></label></h3>
    <table class="tl-tbl"><tr><th>Ch</th><th>Signal</th><th>Frequency</th><th>Duty</th><th>Period</th><th>Level</th></tr>
    ${[0, 1, 2, 3].map(c => `<tr data-meas="${c}"><td>${c}</td><td><select class="mSig">${TL.signals.map(x => `<option>${esc(x)}</option>`).join('')}</select></td>
      <td class="num mHz">-</td><td class="num mDuty">-</td><td class="num mPer">-</td><td><span class="lvl mLvl"></span></td></tr>`).join('')}</table>
    <div class="hint">Counts every edge in the FPGA (100 MHz): exact from below 1 Hz up to 50 MHz.</div>
  </div>

  <div class="dcard"><h3>UART terminal (any pins)<span class="grow"></span><span class="hint" id="uState"></span></h3>
    <div class="row">
      <label class="hint">baud <select id="uBaud">${[1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600, 1000000, 3000000].map(b => `<option ${b === 115200 ? 'selected' : ''}>${b}</option>`).join('')}</select></label>
      <label class="hint">TX <select id="uTx">${pinOptions('j1[1]', false)}</select></label>
      <label class="hint">RX <select id="uRx">${TL.signals.map(x => `<option ${x === 'j1[2]' ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select></label>
      <button class="small" id="uOn">Open</button>
      <label class="check"><input type="checkbox" id="uHex"> hex</label>
    </div>
    <pre id="uTerm" class="uterm"></pre>
    <div class="row"><input id="uIn" class="grow" placeholder="text to send (Enter); hex mode: 48 65 6c 6c 6f" spellcheck="false">
      <label class="check"><input type="checkbox" id="uNl" checked> + newline</label></div>
    <div class="hint">3.3 V levels. Default J1: TX = pin 11, RX = pin 12. Loop test: TX and RX on the same pin.</div>
  </div>

  <div class="dcard"><h3>I2C<span class="grow"></span><span class="seg" id="iBus"><button data-v="1" class="on">Bus 1 (J1-J8)</button><button data-v="2">Bus 2 (J9)</button></span></h3>
    <div class="row"><button class="small" id="iScan">Scan</button><span class="hint" id="iInfo">SDA = pin 3, SCL = pin 4, 1 kOhm pull-ups on the board</span></div>
    <div id="iGrid" class="i2c-grid"></div>
    <div class="row"><label class="hint">address <input id="iAddr" value="0x50" style="width:70px"></label>
      <label class="hint">register <input id="iReg" placeholder="0x00" style="width:70px"></label>
      <label class="hint">bytes <input id="iN" type="number" value="8" min="1" max="256" style="width:60px"></label>
      <button class="ghost small" id="iRead">Read</button></div>
    <div class="row"><label class="hint grow">write (hex) <input id="iData" placeholder="00 ff 12" class="grow" spellcheck="false"></label>
      <button class="ghost small" id="iWrite">Write</button></div>
    <pre id="iOut" class="uterm small"></pre>
  </div>`;
  TL.built = true;
  wireTools();
}

function wireTools() {
  // ---- logic analyzer
  $('laStart').onclick = laStart;
  $('laForce').onclick = async () => {
    const s = await bget('/api/la');
    if (!(s.ok && s.running && !s.done)) {                 // nothing armed: capture now, without waiting for a trigger
      const r = await bpost('/api/la/start?' + qs({ rate: $('laRate').value, pre: $('laPre').value, trig: '' }));
      if (!r.ok) return out(r.out, 'err');
      TL.cursors = [];
    }
    await bpost('/api/la/ctrl?action=force');
    laPoll();
  };
  $('laStop').onclick = () => bpost('/api/la/ctrl?action=stop').then(laPoll);
  $('laCsv').onclick = laCsv;
  $('laShow').onchange = laDraw;
  const cv = $('laCanvas');
  cv.onwheel = e => {
    e.preventDefault();
    if (!TL.la) return;
    const r = cv.getBoundingClientRect(), fx = Math.max(0, (e.clientX - r.left - 90) / (r.width - 90));
    const at = TL.view.start + fx * TL.view.span, k = e.deltaY < 0 ? 0.7 : 1.4;
    TL.view.span = Math.max(16, Math.min(TL.la.n, TL.view.span * k));
    TL.view.start = Math.max(0, Math.min(TL.la.n - TL.view.span, at - fx * TL.view.span));
    laDraw();
  };
  let drag = null;
  cv.onmousedown = e => drag = { x: e.clientX, start: TL.view.start, moved: false };
  cv.onmousemove = e => {
    if (!drag || !TL.la) return;
    const w = cv.getBoundingClientRect().width - 90, dx = e.clientX - drag.x;
    if (Math.abs(dx) > 3) drag.moved = true;
    TL.view.start = Math.max(0, Math.min(TL.la.n - TL.view.span, drag.start - dx / w * TL.view.span));
    laDraw();
  };
  cv.onmouseup = e => {
    if (drag && !drag.moved && TL.la) {
      const r = cv.getBoundingClientRect(), fx = (e.clientX - r.left - 90) / (r.width - 90);
      if (fx >= 0) { TL.cursors = TL.cursors.length >= 2 ? [] : TL.cursors.concat([TL.view.start + fx * TL.view.span]); laDraw(); }
    }
    drag = null;
  };
  cv.onmouseleave = () => drag = null;
  // ---- PWM
  document.querySelectorAll('[data-pwm]').forEach(tr => {
    const ch = tr.dataset.pwm;
    tr.querySelector('.pwmSet').onclick = async () => {
      const us = tr.querySelector('.pwmUs').value;
      const args = { ch, hz: tr.querySelector('.pwmHz').value, pin: tr.querySelector('.pwmPin').value };
      if (us) args.pulse_us = us; else args.duty = tr.querySelector('.pwmDuty').value;
      const r = await bpost('/api/io/pwm/set?' + qs(args));
      if (!r.ok) out(r.out, 'err');
      refreshTools();
    };
    tr.querySelector('.pwmOff').onclick = async () => { await bpost('/api/io/pwm/set?' + qs({ ch, release: 1 })); refreshTools(); };
  });
  // ---- frequency meter
  document.querySelectorAll('[data-meas] .mSig').forEach(sel => sel.onchange = () =>
    bpost('/api/io/meas/set?' + qs({ ch: sel.closest('tr').dataset.meas, signal: sel.value })));
  $('mGate').onchange = () => bpost('/api/io/meas/set?gate_s=' + $('mGate').value);
  // ---- UART
  $('uOn').onclick = async () => {
    if (TL.uartOn) {
      await bpost('/api/io/uart/config?' + qs({ baud: $('uBaud').value, enable: 0 }));
      TL.uartOn = false;
    } else {
      const r = await bpost('/api/io/uart/config?' + qs({ baud: $('uBaud').value, tx: $('uTx').value, rx: $('uRx').value }));
      if (!r.ok) return out(r.out, 'err');
      TL.uartOn = true;
    }
    $('uOn').textContent = TL.uartOn ? 'Close' : 'Open';
    $('uState').textContent = TL.uartOn ? 'open' : '';
  };
  $('uIn').onkeydown = async e => {
    if (e.key !== 'Enter') return;
    let hex;
    if ($('uHex').checked) hex = $('uIn').value.replace(/[^0-9a-fA-F]/g, '');
    else hex = [...new TextEncoder().encode($('uIn').value + ($('uNl').checked ? '\n' : ''))].map(b => b.toString(16).padStart(2, '0')).join('');
    const r = await bpost('/api/io/uart/send?hex=' + hex);
    if (!r.ok) out(r.out, 'err');
    $('uIn').value = '';
  };
  // ---- I2C
  $('iBus').querySelectorAll('button').forEach(b => b.onclick = () => $('iBus').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)));
  const bus = () => $('iBus').querySelector('.on').dataset.v;
  $('iScan').onclick = async () => {
    $('iInfo').textContent = 'scanning ...';
    const r = await bpost('/api/i2c/scan?bus=' + bus());
    if (!r.ok) { $('iInfo').textContent = r.out; return; }
    const found = new Set(r.found.map(a => parseInt(a, 16)));
    $('iInfo').textContent = `${r.count} device(s): ${r.found.join(' ') || 'none'}`;
    let g = '<span></span>' + [...Array(16).keys()].map(x => `<span class="h">${x.toString(16)}</span>`).join('');
    for (let row = 0; row < 8; row++) {
      g += `<span class="h">${row.toString(16)}0</span>`;
      for (let c = 0; c < 16; c++) {
        const a = row * 16 + c;
        g += a < 8 || a > 0x77 ? '<span class="na"></span>' : `<span class="${found.has(a) ? 'hit' : ''}" data-a="${a}" title="0x${a.toString(16)}">${found.has(a) ? a.toString(16).padStart(2, '0') : '--'}</span>`;
      }
    }
    $('iGrid').innerHTML = g;
    $('iGrid').querySelectorAll('[data-a]').forEach(el => el.onclick = () => $('iAddr').value = '0x' + (+el.dataset.a).toString(16).padStart(2, '0'));
  };
  $('iRead').onclick = async () => {
    const r = await bpost('/api/i2c/read?' + qs({ bus: bus(), addr: $('iAddr').value, reg: $('iReg').value, n: $('iN').value }));
    $('iOut').textContent = r.ok ? `${r.addr}: ${r.data_hex.match(/../g).join(' ')}\n${r.data.map(b => b >= 32 && b < 127 ? String.fromCharCode(b) : '.').join('')}` : r.out;
  };
  $('iWrite').onclick = async () => {
    const r = await bpost('/api/i2c/write?' + qs({ bus: bus(), addr: $('iAddr').value, hex: $('iData').value.replace(/[^0-9a-fA-F]/g, '') }));
    $('iOut').textContent = r.out;
  };
  window.addEventListener('resize', () => BV.view === 'tools' && laDraw());
}

async function refreshTools() {
  if (BV.view !== 'tools' || !TL.built) return;
  const [p, m] = await Promise.all([bget('/api/io/pwm'), bget('/api/io/meas')]);
  if (p.ok) p.channels.forEach(c => {
    const tr = document.querySelector(`[data-pwm="${c.ch}"]`);
    if (!tr) return;
    const busy = tr.contains(document.activeElement);
    if (!busy) {
      tr.querySelector('.pwmPin').value = c.pins[0] || '';
      tr.querySelector('.pwmHz').value = +c.hz.toFixed(3);
      tr.querySelector('.pwmDuty').value = c.duty_pct;
    }
    tr.querySelector('.pwmNow').textContent = c.pins.length ? `${fmtHz(c.hz)}, ${c.duty_pct} %, ${c.pulse_us} us on ${c.pins.join(' ')}` : 'off';
  });
  if (m.ok) {
    m.channels.forEach(c => {
      const tr = document.querySelector(`[data-meas="${c.ch}"]`);
      if (!tr) return;
      if (document.activeElement !== tr.querySelector('.mSig')) tr.querySelector('.mSig').value = c.signal;
      tr.querySelector('.mHz').textContent = c.hz_period ? fmtHz(c.hz_period) : fmtHz(c.hz);
      tr.querySelector('.mDuty').textContent = c.duty_pct + ' %';
      tr.querySelector('.mPer').textContent = c.period_us ? fmtT(c.period_us / 1e6) : '-';
      tr.querySelector('.mLvl').className = 'lvl mLvl ' + (c.level ? 'h' : 'l');
    });
    if (document.activeElement !== $('mGate')) $('mGate').value = String(m.gate_s);
  }
}

async function pollUart() {
  if (BV.view === 'tools' && TL.uartOn && S.connected) {
    const r = await bpost('/api/io/uart/read');
    if (r.ok && r.data_hex) {
      const bytes = r.data_hex.match(/../g).map(h => parseInt(h, 16));
      const t = $('uTerm');
      t.textContent += $('uHex').checked ? bytes.map(b => b.toString(16).padStart(2, '0')).join(' ') + ' ' : new TextDecoder().decode(new Uint8Array(bytes));
      if (t.textContent.length > 50000) t.textContent = t.textContent.slice(-40000);
      t.scrollTop = t.scrollHeight;
    }
    if (r.ok) $('uState').textContent = `open, ${r.baud} baud${r.overflow ? ', OVERFLOW' : ''}${r.frame_error ? ', framing error' : ''}`;
  }
  setTimeout(pollUart, 300);
}

/* ---- logic analyzer */
async function laStart() {
  const sig = $('laTrigSig').value;
  const args = { rate: $('laRate').value, pre: $('laPre').value, trig: sig ? sig + ':' + $('laTrigKind').value : '' };
  const r = await bpost('/api/la/start?' + qs(args));
  if (!r.ok) return out(r.out, 'err');
  TL.cursors = [];
  laPoll();
}

async function laPoll() {
  const s = await bget('/api/la');
  if (!s.ok) return;
  $('laState').textContent = s.done ? 'done' : s.running ? (s.triggered ? 'triggered, filling ...' : 'waiting for the trigger ...') : 'stopped';
  if (s.done) {
    const d = await bget('/api/la/data');
    if (d.ok) { TL.la = d; TL.view = { start: 0, span: d.n }; laDraw(); }
  } else if (s.running) setTimeout(laPoll, 400);
}

function laChannels() {
  const want = $('laShow').value.trim().split(/\s+/).filter(Boolean);
  const out = [];
  for (const w of want) {
    const re = new RegExp('^' + w.replace(/[.+^${}()|\\]/g, '\\$&').replace(/\[/g, '\\[').replace(/\]/g, '\\]').replace(/\*/g, '.*') + '$');
    TL.signals.forEach((s, i) => { if (re.test(s) && !out.includes(i)) out.push(i); });
  }
  return out.slice(0, 32);
}

function laLevels(sig) {
  // [[sample index, level]] at every change of this signal
  const res = [];
  let last = -1;
  for (const [i, lo, hi] of TL.la.changes) {
    const v = sig < 32 ? (lo >>> sig) & 1 : (hi >>> (sig - 32)) & 1;
    if (v !== last) { res.push([i, v]); last = v; }
  }
  return res;
}

function laDraw() {
  const cv = $('laCanvas'); if (!cv || !TL.la) return;
  const dpr = devicePixelRatio, chans = laChannels();
  const rowH = 26, H = Math.max(60, chans.length * rowH + 28);
  cv.style.height = H + 'px';
  const W = cv.width = cv.clientWidth * dpr; cv.height = H * dpr;
  const g = cv.getContext('2d'), css = getComputedStyle(document.body);
  g.scale(dpr, dpr);
  const w = cv.clientWidth, L = 90, d = TL.la, rate = d.rate_hz;
  const x = i => L + (i - TL.view.start) / TL.view.span * (w - L);
  g.clearRect(0, 0, w, H);
  g.font = '12px Segoe UI, sans-serif';
  // time axis
  g.fillStyle = css.getPropertyValue('--muted'); g.strokeStyle = css.getPropertyValue('--line');
  for (let k = 0; k <= 8; k++) {
    const i = TL.view.start + TL.view.span * k / 8, xx = x(i);
    g.beginPath(); g.moveTo(xx, 14); g.lineTo(xx, H); g.stroke();
    if (k < 8) g.fillText(fmtT((i - d.trigger_at) / rate), xx + 2, 11);
  }
  // trigger marker
  const tx = x(d.trigger_at);
  if (tx >= L && tx <= w) { g.strokeStyle = '#e05f5f'; g.setLineDash([4, 3]); g.beginPath(); g.moveTo(tx, 14); g.lineTo(tx, H); g.stroke(); g.setLineDash([]); }
  // signals
  const stats = [];
  chans.forEach((sig, row) => {
    const y0 = 22 + row * rowH, yHi = y0 + 3, yLo = y0 + rowH - 7;
    g.fillStyle = css.getPropertyValue('--text');
    g.fillText(TL.signals[sig], 4, y0 + rowH / 2 + 2);
    const lv = laLevels(sig);
    g.strokeStyle = LA_COLORS[row % LA_COLORS.length]; g.lineWidth = 1.6; g.beginPath();
    for (let k = 0; k < lv.length; k++) {
      const [i, v] = lv[k], iEnd = k + 1 < lv.length ? lv[k + 1][0] : d.n;
      const xa = Math.max(L, x(i)), xb = Math.min(w, x(iEnd)), y = v ? yHi : yLo;
      if (xb < L || xa > w) continue;
      if (k) g.lineTo(xa, y); else g.moveTo(xa, y);
      g.lineTo(xb, y);
    }
    g.stroke();
    const rises = lv.filter(([, v], k) => v && k).map(([i]) => i);
    if (rises.length >= 2) stats.push(`${TL.signals[sig]}: ${fmtHz(rate * (rises.length - 1) / (rises[rises.length - 1] - rises[0]))}`);
  });
  // cursors
  TL.cursors.forEach((c, k) => {
    const xx = x(c);
    g.strokeStyle = k ? '#e0884f' : '#4f8fe0'; g.beginPath(); g.moveTo(xx, 14); g.lineTo(xx, H); g.stroke();
    g.fillStyle = g.strokeStyle; g.fillText(k ? 'B' : 'A', xx + 3, H - 4);
  });
  let info = `${d.n} samples at ${fmtHz(rate)} = ${fmtT(d.n / rate)} window; showing ${fmtT(TL.view.span / rate)}.`;
  if (TL.cursors.length === 2) {
    const dt = Math.abs(TL.cursors[1] - TL.cursors[0]) / rate;
    info += `  A to B: ${fmtT(dt)} (${fmtHz(1 / dt)})`;
  }
  if (stats.length) info += '  |  ' + stats.join(' &middot; ');
  $('laInfo').innerHTML = info;
}

function laCsv() {
  if (!TL.la) return out('No capture yet.', 'warn');
  const chans = laChannels(), d = TL.la;
  const lines = ['time_s,' + chans.map(c => TL.signals[c]).join(',')];
  for (const [i, lo, hi] of d.changes)
    lines.push(((i - d.trigger_at) / d.rate_hz).toExponential(6) + ',' + chans.map(s => s < 32 ? (lo >>> s) & 1 : (hi >>> (s - 32)) & 1).join(','));
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' }));
  a.download = 'ardzy_capture.csv';
  a.click();
}

$('btnToolsLoad').onclick = async () => {
  showTab('output');
  const r = await api('/api/io/load', {});
  if (!r.ok) return out(r.out, 'err');
  const wait = setInterval(() => { if (!S.busy) { clearInterval(wait); TL.built = false; toolsShow(); } }, 700);
};
setInterval(() => BV.view === 'tools' && refreshTools(), 1200);
pollUart();
window.toolsShow = toolsShow;
