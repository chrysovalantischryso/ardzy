/* Ardzy - the radio's studio console: the studio clock, the timers, the LED meter bridge, the goniometer,
   the real-time analyzer (RTA), the MPX spectrum with its peak hold and the waterfall.
   radio.js builds the page and calls csStatus(st) for every status (twice a second); the clock, the timers
   and the meter ballistics run on their own 40 ms tick while the radio page is open, so they move smoothly
   between the statuses. */
const CS = {
  tick: null, last: 0, stAt: 0, st: null, delta: 0,
  m: {},                                   // meters: {target, disp, hold, holdT}
  sw: { run: false, t0: 0, acc: 0 },       // stopwatch
  cd: { set: 180, run: false, end: 0, left: 180 },   // countdown
  rtaHold: null, specHold: null, water: [],
};
const csPad = n => String(Math.floor(n)).padStart(2, '0');
function csHms(s) {
  if (s == null || !isFinite(s) || s < 0) return '--:--:--';
  return csPad(s / 3600) + ':' + csPad(s / 60 % 60) + ':' + csPad(s % 60);
}
function csMs(s, tenths) {
  if (s == null || !isFinite(s)) return '--:--';
  const neg = s < 0; s = Math.abs(s);
  return (neg ? '-' : '') + csPad(s / 60) + ':' + csPad(s % 60) + (tenths ? '.' + Math.floor(s * 10 % 10) : '');
}
function csColors() {
  const css = getComputedStyle($('viewRadio'));
  const v = n => css.getPropertyValue(n).trim();
  return { text: v('--text'), muted: v('--muted'), line: v('--line'), panel: v('--panel'), bg: v('--code-bg'),
    green: v('--led-green'), amber: v('--led-amber'), red: v('--led-red'), blue: v('--led-blue'), off: v('--led-off') };
}
function csCanvas(cv) {
  const W = cv.clientWidth, H = cv.clientHeight, dpr = window.devicePixelRatio || 1;
  if (!W || !H) return null;
  if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  const g = cv.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { g, W, H };
}

/* ---------------------------------------------------------------- the tick */
function csStart() {
  if (CS.tick) return;
  CS.last = Date.now();
  CS.tick = setInterval(() => {
    if (BV.view !== 'radio' || !$('csClock')) { clearInterval(CS.tick); CS.tick = null; return; }
    const now = Date.now(), dt = Math.min(0.2, (now - CS.last) / 1000);
    CS.last = now;
    csBallistics(dt);
    csMeters();
    csClock();
    csTimers();
  }, 40);
}

/* ---------------------------------------------------------------- a new status */
function csStatus(st) {
  CS.st = st;
  CS.stAt = Date.now();
  CS.delta = Date.now() / 1000 - st.time;          // the PC's clock minus the board's (the app keeps them close)
  const ch = st.chain || {}, act = ch.active && ch.samples;
  const lin = v => v > 0.00003 ? 20 * Math.log10(v) : -100;
  const set = (k, v) => { (CS.m[k] = CS.m[k] || { target: -100, disp: -100, hold: -100, holdT: 0 }).target = v; };
  set('inL', act ? ch.in_peak[0] : -100); set('inR', act ? ch.in_peak[1] : -100);
  set('outL', act ? ch.out_peak[0] : -100); set('outR', act ? ch.out_peak[1] : -100);
  const pk = st.peaks || {};
  set('airL', st.on ? lin(pk.left || 0) : -100); set('airR', st.on ? lin(pk.right || 0) : -100);
  set('mpx', st.on ? 100 * (pk.mpx || 0) : 0);
  set('gr', act && ch.limiter_db < 0 ? ch.limiter_db : 0);
  csLamps(st);
  csGonio(ch.scope && ch.scope.out);
  csCorr(ch.rta && ch.rta.corr, act);
  csRta(ch.rta, act);
  csStart();
}

/* ---------------------------------------------------------------- status lamps */
function csLamps(st) {
  const c = RAD.cfg, ch = st.chain || {}, rv = (st.network || {}).receiver, seen = st.rds_seen || {};
  const outPk = ch.active && ch.samples ? Math.max(...ch.out_peak) : -100;
  const air = st.on && st.mode !== 'off';
  const gapsNow = st.gaps != null && CS.gaps != null && st.gaps > CS.gaps;
  CS.gaps = st.gaps;
  if (gapsNow) CS.gapT = Date.now();
  const L = [
    ['ON AIR', air ? 'red' : ''],
    ['CARRIER', st.rf_hz ? 'green' : st.on ? 'amber' : ''],
    ['PLL', st.locked ? 'green' : 'red'],
    ['STEREO', air && st.mode === 'fm' && c.fm.stereo ? 'green' : ''],
    ['RDS', air && st.mode === 'fm' && c.rds.on ? (seen.groups ? 'green' : 'amber') : ''],
    ['TA', air && c.rds.on && c.rds.ta ? 'amber' : ''],
    ['AUDIO', outPk > -50 || (air && (st.peaks || {}).left > 0.01) ? 'green' : ''],
    ['CLIP', outPk > -0.3 || (air && (st.peaks || {}).mpx > 1.0) ? 'red' : ''],
    ['NET', c.audio.source === 'network' ? (rv && rv.receiving ? 'green' : 'amber') : ''],
    ['DELAY', (c.delay_s || 0) > 0 ? (ch.filling ? 'amber' : 'blue') : ''],
    ['GAPS', CS.gapT && Date.now() - CS.gapT < 5000 ? 'red' : st.gaps != null ? 'green' : ''],
  ];
  const el = $('csLamps');
  if (!el) return;
  if (el.childElementCount !== L.length) el.innerHTML = L.map(([t]) => `<span class="lamp">${t}</span>`).join('');
  [...el.children].forEach((s, i) => { s.className = 'lamp ' + L[i][1]; });
}

/* ---------------------------------------------------------------- the studio clock */
function csClock() {
  const cv = $('csClock'); if (!cv) return;
  const k = csCanvas(cv); if (!k) return;
  const { g, W, H } = k, C = csColors(), d = new Date();
  const cx = W / 2, cy = H / 2, r = Math.min(W, H) / 2 - 6, s = d.getSeconds();
  g.clearRect(0, 0, W, H);
  for (let i = 0; i < 60; i++) {
    const a = (i / 60) * 2 * Math.PI - Math.PI / 2, big = i % 5 === 0;
    g.beginPath();
    g.arc(cx + Math.cos(a) * r, cy + Math.sin(a) * r, big ? 3.2 : 2.2, 0, 2 * Math.PI);
    g.fillStyle = i <= s ? C.red : C.off;
    g.fill();
    if (big) {
      g.beginPath();
      g.arc(cx + Math.cos(a) * (r - 11), cy + Math.sin(a) * (r - 11), 2.4, 0, 2 * Math.PI);
      g.fillStyle = C.red; g.fill();
    }
  }
  g.fillStyle = C.red; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.font = `600 ${Math.round(r * 0.46)}px ${getComputedStyle(document.body).getPropertyValue('--mono')}`;
  g.fillText(csPad(d.getHours()) + ':' + csPad(d.getMinutes()), cx, cy - r * 0.06);
  g.font = `600 ${Math.round(r * 0.22)}px ${getComputedStyle(document.body).getPropertyValue('--mono')}`;
  g.fillText(csPad(s), cx, cy + r * 0.33);
  g.fillStyle = C.muted; g.font = `${Math.max(10, Math.round(r * 0.13))}px Segoe UI, sans-serif`;
  g.fillText(d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }), cx, cy - r * 0.42);
}

/* ---------------------------------------------------------------- the timers */
function csTimers() {
  const el = $('csTimers'); if (!el || !RAD.cfg) return;
  const st = CS.st || {}, c = RAD.cfg, now = Date.now() / 1000, since = (Date.now() - CS.stAt) / 1000;
  const T = {};
  T.onair = st.on && st.on_since ? csHms(now - CS.delta - st.on_since) : '--:--:--';
  let pos = null, len = null, live = false, what = '';
  const src = c.audio.source;
  if (st.digital && DIGITAL_MODES.includes(c.mode) && st.digital.length_s) {
    len = st.digital.length_s; pos = len - Math.max(0, st.digital.left_s - since); what = 'message';
  } else if (st.track && st.track_len_s) {
    pos = Math.max(0, Math.min(st.track_len_s, st.track_pos_s + since)); len = st.track_len_s; what = src === 'sstv' ? 'picture' : 'song';
  } else if (src === 'network' && st.track) { live = true; pos = st.track_pos_s + since; }
  else if (src === 'tones') live = true;
  const rem = len != null && pos != null ? len - pos : null;
  T.elapsed = pos != null ? csMs(pos) : '--:--';
  T.remain = live ? 'LIVE' : rem != null ? csMs(-rem) : '--:--';
  const remCls = live ? 'live' : rem == null ? '' : rem < 10 ? 'red blink' : rem < 20 ? 'amber' : '';
  const toHour = 3600 - (Math.floor(Date.now() / 1000) % 3600);
  T.hour = csMs(toHour);
  const a = st.rds_on_air || {};
  const nx = v => v == null ? '-' : Math.max(0, v - since).toFixed(0) + ' s';
  T.rds = c.mode === 'fm' && c.rds.on ? `${nx(a.ps_next_s)} / ${nx(a.rt_next_s)}` : '-';
  const swT = CS.sw.acc + (CS.sw.run ? now - CS.sw.t0 : 0);
  T.sw = csMs(swT, true);
  if (CS.cd.run) CS.cd.left = Math.max(0, CS.cd.end - now);
  const cdLeft = CS.cd.left;
  if (CS.cd.run && cdLeft <= 0) CS.cd.run = false;
  T.cd = csMs(cdLeft);
  const next = st.next_track ? st.next_track.replace(/\.wav$/i, '') : src === 'playlist' ? (c.audio.loop ? '-' : 'end of the list') : '-';
  if (!el.dataset.built) {
    el.dataset.built = 1;
    const tile = (id, t, cls = '') => `<div class="tm ${cls}" id="tm_${id}"><b>${t}</b><span class="v"></span><span class="sub"></span></div>`;
    el.innerHTML = tile('onair', 'On air', 'wide') + tile('elapsed', 'Elapsed') + tile('remain', 'Remaining', 'big') +
      tile('next', 'Next', 'text') + tile('hour', 'To the hour') + tile('rds', 'RDS name / text') +
      `<div class="tm ctl" id="tm_sw"><b>Stopwatch</b><span class="v"></span><span class="sub"><button class="ghost small" data-sw="go">start</button><button class="ghost small" data-sw="reset">reset</button></span></div>` +
      `<div class="tm ctl" id="tm_cd"><b>Countdown</b><span class="v"></span><span class="sub"><input id="cdSet" value="03:00" title="minutes:seconds" spellcheck="false"><button class="ghost small" data-cd="go">start</button><button class="ghost small" data-cd="reset">reset</button></span></div>`;
    el.querySelector('[data-sw="go"]').onclick = e => {
      if (CS.sw.run) { CS.sw.acc += Date.now() / 1000 - CS.sw.t0; CS.sw.run = false; } else { CS.sw.t0 = Date.now() / 1000; CS.sw.run = true; }
      e.target.textContent = CS.sw.run ? 'stop' : 'start';
    };
    el.querySelector('[data-sw="reset"]').onclick = () => { CS.sw.acc = 0; CS.sw.t0 = Date.now() / 1000; };
    const parse = () => { const p = $('cdSet').value.split(':').map(Number); const s = p.length > 1 ? p[0] * 60 + p[1] : p[0]; return isFinite(s) && s > 0 ? s : 180; };
    el.querySelector('[data-cd="go"]').onclick = e => {
      if (CS.cd.run) { CS.cd.run = false; } else { if (CS.cd.left <= 0) CS.cd.left = parse(); CS.cd.end = Date.now() / 1000 + CS.cd.left; CS.cd.run = true; }
      e.target.textContent = CS.cd.run ? 'stop' : 'start';
    };
    el.querySelector('[data-cd="reset"]').onclick = () => { CS.cd.run = false; CS.cd.left = parse(); el.querySelector('[data-cd="go"]').textContent = 'start'; };
    $('cdSet').onchange = () => { if (!CS.cd.run) CS.cd.left = parse(); };
  }
  const put = (id, v, sub, cls) => {
    const t = $('tm_' + id);
    t.querySelector('.v').textContent = v;
    if (sub != null) t.querySelector('.sub').textContent = sub;
    if (cls != null) t.dataset.state = cls;
  };
  put('onair', T.onair, st.on ? (+c.freq_mhz).toFixed(2) + ' MHz ' + (c.mode || '').toUpperCase() : 'transmitter off', st.on ? 'red' : '');
  put('elapsed', T.elapsed, what || (live ? 'live source' : ''), '');
  put('remain', T.remain, len ? 'of ' + csMs(len) : '', remCls);
  put('next', next, null, '');
  $('tm_next').querySelector('.sub').textContent = st.next_track ? 'in ' + (rem != null ? csMs(rem) : '-') : '';
  put('hour', T.hour, 'top of the hour', toHour <= 60 ? 'amber' : '');
  put('rds', T.rds, 'next change in', '');
  put('sw', T.sw, null, CS.sw.run ? 'run' : '');
  put('cd', T.cd, null, CS.cd.run ? (cdLeft < 10 ? 'red blink' : 'run') : cdLeft <= 0 ? 'red' : '');
}

/* ---------------------------------------------------------------- the LED meter bridge */
const CS_DB = [0, -1, -2, -3, -4, -5, -6, -7, -8, -9, -10, -12, -14, -16, -18, -20, -23, -26, -30, -35, -40, -45, -50, -55, -60];
const CS_PCT = [120, 115, 110, 105, 100, 95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 25, 20, 15, 10, 5, 0.5];
const CS_GR = [0, -0.5, -1, -1.5, -2, -3, -4, -5, -6, -8, -10, -12, -14, -16, -18, -20, -22, -24, -26, -28, -30, -32, -34, -36, -40];
function csBallistics(dt) {
  const now = Date.now();
  for (const [k, m] of Object.entries(CS.m)) {
    const fall = k === 'mpx' ? 45 : k === 'gr' ? 8 : 13;          // dB (or %) per second
    if (k === 'gr') {                                               // gain reduction: fast down, slow back
      m.disp = m.target < m.disp ? m.target : Math.min(m.target, m.disp + fall * dt);
    } else {
      m.disp = m.target > m.disp ? m.target : Math.max(m.target, m.disp - fall * dt);
    }
    const better = k === 'gr' ? m.disp <= m.hold : m.disp >= m.hold;
    if (better || now - m.holdT > 2000) { m.hold = m.disp; m.holdT = now; }
  }
}
function csMeters() {
  const cv = $('csMeters'); if (!cv) return;
  const k = csCanvas(cv); if (!k) return;
  const { g, W, H } = k, C = csColors();
  const groups = [['IN', ['inL', 'inR'], 'db'], ['OUT', ['outL', 'outR'], 'db'], ['ON AIR', ['airL', 'airR'], 'db'],
    ['MPX', ['mpx'], 'pct'], ['GR', ['gr'], 'gr']];
  const T = 18, B = 34, segs = CS_DB.length, sh = (H - T - B) / segs;
  const SCALE = 30, colW = Math.max(14, Math.min(30, (W - SCALE - 12 - 4 * 18) / 9)), gap = 4;
  g.clearRect(0, 0, W, H);
  g.font = '11px Segoe UI, sans-serif'; g.textAlign = 'right'; g.textBaseline = 'middle'; g.fillStyle = C.muted;
  CS_DB.forEach((d, i) => { if ([0, -3, -6, -9, -12, -18, -30, -40, -60].includes(d)) g.fillText(String(d), SCALE - 4, T + i * sh + sh / 2); });
  let x = SCALE + 4;
  for (const [title, keys, kind] of groups) {
    const x0 = x;
    keys.forEach((key, j) => {
      const m = CS.m[key] || { disp: kind === 'pct' ? 0 : kind === 'gr' ? 0 : -100, hold: -100 };
      const scale = kind === 'db' ? CS_DB : kind === 'pct' ? CS_PCT : CS_GR;
      for (let i = 0; i < segs; i++) {
        const v = scale[i];
        let on, col;
        if (kind === 'gr') { on = v >= m.disp && v < 0 && m.disp < -0.2; col = C.amber; }
        else { on = m.disp >= v; col = kind === 'db' ? (v > -3 ? C.red : v > -9 ? C.amber : C.green) : (v > 100 ? C.red : v > 90 ? C.amber : C.green); }
        const holdHere = kind !== 'gr' && Math.abs(i - scale.findIndex(s => m.hold >= s)) === 0 && m.hold > (kind === 'db' ? -60 : 0.5);
        g.fillStyle = on || holdHere ? col : C.off;
        g.fillRect(x, T + i * sh + 1, colW, Math.max(1, sh - 2));
      }
      g.fillStyle = C.muted; g.textAlign = 'center';
      g.fillText(keys.length > 1 ? (j ? 'R' : 'L') : '', x + colW / 2, H - B + 10);
      g.fillStyle = C.text; g.font = '600 11px ' + getComputedStyle(document.body).getPropertyValue('--mono');
      const hv = kind === 'pct' ? Math.round(m.hold) : m.hold;
      g.fillText(kind === 'pct' ? (hv > 0.5 ? hv + '' : '-') : (hv > -59.5 || (kind === 'gr' && hv < -0.2) ? hv.toFixed(kind === 'gr' ? 1 : 0) : '-'), x + colW / 2, T - 9);
      g.font = '11px Segoe UI, sans-serif';
      x += colW + gap;
    });
    g.fillStyle = C.muted; g.textAlign = 'center';
    g.fillText(title + (kind === 'pct' ? ' %' : kind === 'gr' ? ' dB' : ''), (x0 + x - gap) / 2, H - B + 25);
    x += 14;
  }
}

/* ---------------------------------------------------------------- goniometer and correlation */
function csGonio(data) {
  const cv = $('csGonio'); if (!cv) return;
  const k = csCanvas(cv); if (!k) return;
  const { g, W, H } = k, C = csColors(), cx = W / 2, cy = H / 2, r = Math.min(W, H) / 2 - 14;
  g.fillStyle = C.bg; g.globalAlpha = 0.55; g.fillRect(0, 0, W, H); g.globalAlpha = 1;
  g.strokeStyle = C.line; g.lineWidth = 1;
  g.beginPath(); g.moveTo(cx - r, cy - r); g.lineTo(cx + r, cy + r); g.moveTo(cx + r, cy - r); g.lineTo(cx - r, cy + r);
  g.moveTo(cx, cy - r); g.lineTo(cx, cy + r); g.stroke();
  g.fillStyle = C.muted; g.font = '10px Segoe UI, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText('M', cx, 7); g.fillText('L', cx - r + 4, cy - r + 6); g.fillText('R', cx + r - 4, cy - r + 6);
  if (!data || !data[0] || !data[0].length) return;
  const [Lc, Rc] = data;
  g.fillStyle = C.green;
  for (let i = 0; i < Lc.length; i++) {
    const l = Lc[i] / 100, rr = Rc[i] / 100;
    const sx = (rr - l) * 0.7071, sy = (l + rr) * 0.7071;
    g.fillRect(cx + sx * r - 1, cy - sy * r - 1, 2.2, 2.2);
  }
}
function csCorr(v, act) {
  const el = $('csCorr'); if (!el) return;
  const i = el.querySelector('i');
  if (v == null || !act) { i.style.left = '50%'; i.className = ''; $('csCorrV').textContent = '-'; return; }
  i.style.left = (50 + v * 50) + '%';
  i.className = v < 0 ? 'neg' : v < 0.3 ? 'mid' : '';
  $('csCorrV').textContent = (v > 0 ? '+' : '') + v.toFixed(2) + (v > 0.95 ? ' (mono)' : v < 0 ? ' (out of phase!)' : '');
}

/* ---------------------------------------------------------------- the real-time analyzer (1/3 octave) */
function csRta(rta, act) {
  const cv = $('csRta'); if (!cv) return;
  const k = csCanvas(cv); if (!k) return;
  const { g, W, H } = k, C = csColors();
  const L = 34, R = 8, T = 10, B = 22, D0 = 0, D1 = -72, y = d => T + (H - T - B) * (D0 - Math.max(D1, Math.min(D0, d))) / (D0 - D1);
  g.clearRect(0, 0, W, H);
  g.font = '10.5px Segoe UI, sans-serif'; g.textBaseline = 'middle';
  for (let d = 0; d >= D1; d -= 12) {
    g.strokeStyle = C.line; g.beginPath(); g.moveTo(L, y(d)); g.lineTo(W - R, y(d)); g.stroke();
    g.fillStyle = C.muted; g.textAlign = 'right'; g.fillText(d, L - 5, y(d));
  }
  const bands = (rta && rta.bands) || [20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000];
  const n = bands.length, bw = (W - L - R) / n;
  const out = act && rta && rta.out, inn = act && rta && rta.in;
  if (!CS.rtaHold || CS.rtaHold.length !== n) CS.rtaHold = new Array(n).fill(-100);
  g.textAlign = 'center'; g.fillStyle = C.muted;
  bands.forEach((f, i) => {
    if ([31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000].includes(f)) g.fillText(f >= 1000 ? f / 1000 + 'k' : f, L + i * bw + bw / 2, H - 9);
  });
  if (!out) { g.fillStyle = C.muted; g.fillText('no sound passing the processing (test tones are made in the FPGA)', (L + W) / 2, H / 2); return; }
  for (let i = 0; i < n; i++) {
    const v = out[i];
    CS.rtaHold[i] = Math.max(v, CS.rtaHold[i] - 1.5);
    const x = L + i * bw + 1.5, top = y(v), bot = y(D1);
    const grad = g.createLinearGradient(0, y(0), 0, bot);
    grad.addColorStop(0, C.red); grad.addColorStop(0.12, C.amber); grad.addColorStop(0.3, C.green); grad.addColorStop(1, C.green);
    g.fillStyle = grad; g.globalAlpha = 0.85; g.fillRect(x, top, bw - 3, bot - top); g.globalAlpha = 1;
    g.fillStyle = C.text; g.fillRect(x, y(CS.rtaHold[i]) - 1, bw - 3, 2);
  }
  if (inn) {
    g.strokeStyle = C.blue; g.lineWidth = 1.5; g.beginPath();
    inn.forEach((v, i) => { const x = L + i * bw + bw / 2; i ? g.lineTo(x, y(v)) : g.moveTo(x, y(v)); });
    g.stroke();
  }
}

/* ---------------------------------------------------------------- the MPX spectrum and its waterfall */
function csSpectrum(mag, fs, n, pilotDb) {
  const cv = $('radSpec'); if (!cv) return;
  const k = csCanvas(cv); if (!k) return;
  const { g, W, H } = k, C = csColors();
  const FMAX = 80000, DB0 = 0, DB1 = -100, L = 44, R = 10, T = 10, B = 24;
  const x = f => L + (W - L - R) * f / FMAX, y = db => T + (H - T - B) * (DB0 - Math.max(DB1, Math.min(DB0, db))) / (DB0 - DB1);
  // the spectrum in 1 pixel columns (the largest bin of each)
  const cols = Math.floor(W - L - R), col = new Float32Array(cols).fill(DB1);
  for (let i = 1; i < n / 2; i++) {
    const f = i * fs / n; if (f > FMAX) break;
    const c = Math.min(cols - 1, Math.floor((x(f) - L)));
    const db = 20 * Math.log10(mag[i] + 1e-12);
    if (db > col[c]) col[c] = db;
  }
  if (!CS.specHold || CS.specHold.length !== cols) CS.specHold = Float32Array.from(col);
  for (let i = 0; i < cols; i++) CS.specHold[i] = Math.max(col[i], CS.specHold[i] - 2);
  g.clearRect(0, 0, W, H);
  const bands = [[30, 15000, 'L+R', C.blue], [18800, 19200, 'pilot', C.amber], [23000, 53000, 'L-R stereo', C.blue], [54600, 59400, 'RDS', C.green]];
  g.font = '11px Segoe UI, sans-serif'; g.textBaseline = 'alphabetic';
  for (const [a, b, t, c] of bands) {
    g.globalAlpha = 0.12; g.fillStyle = c; g.fillRect(x(a), T, Math.max(2, x(b) - x(a)), H - T - B); g.globalAlpha = 1;
    g.fillStyle = C.muted; g.textAlign = 'left'; g.fillText(t, x(a) + 3, T + 12 + (t === 'pilot' ? 14 : 0));
  }
  g.strokeStyle = C.line; g.lineWidth = 1; g.fillStyle = C.muted;
  for (let db = 0; db >= DB1; db -= 20) { g.beginPath(); g.moveTo(L, y(db)); g.lineTo(W - R, y(db)); g.stroke(); g.textAlign = 'right'; g.fillText(db + '', L - 6, y(db) + 4); }
  g.textAlign = 'center';
  for (let f = 0; f <= FMAX; f += 10000) g.fillText(f / 1000 + 'k', x(f), H - 7);
  // filled trace
  const grad = g.createLinearGradient(0, T, 0, H - B);
  grad.addColorStop(0, C.green); grad.addColorStop(1, 'transparent');
  g.beginPath(); g.moveTo(L, y(DB1));
  for (let i = 0; i < cols; i++) g.lineTo(L + i, y(col[i]));
  g.lineTo(L + cols, y(DB1)); g.closePath();
  g.globalAlpha = 0.35; g.fillStyle = grad; g.fill(); g.globalAlpha = 1;
  g.strokeStyle = C.green; g.lineWidth = 1.2; g.beginPath();
  for (let i = 0; i < cols; i++) i ? g.lineTo(L + i, y(col[i])) : g.moveTo(L, y(col[i]));
  g.stroke();
  g.strokeStyle = C.amber; g.lineWidth = 1; g.globalAlpha = 0.8; g.beginPath();
  for (let i = 0; i < cols; i++) i ? g.lineTo(L + i, y(CS.specHold[i])) : g.moveTo(L, y(CS.specHold[i]));
  g.stroke(); g.globalAlpha = 1;
  // the 19 kHz marker
  if (pilotDb != null) {
    g.fillStyle = C.amber; g.textAlign = 'left';
    g.fillText('pilot ' + pilotDb.toFixed(1) + ' dB', x(19000) + 6, y(pilotDb) - 4);
  }
  csWater(col);
}
function csWater(col) {
  const cv = $('csWater'); if (!cv) return;
  const k = csCanvas(cv); if (!k) return;
  const { g, W, H } = k, L = 44, R = 10;
  CS.water.unshift(col);
  const rows = Math.max(10, Math.floor(H / 3));
  CS.water.length = Math.min(CS.water.length, rows);
  g.clearRect(0, 0, W, H);
  const rh = H / rows;
  const heat = db => {                                  // -100 .. 0 dB -> dark blue, blue, green, yellow, red
    const t = Math.max(0, Math.min(1, (db + 100) / 90));
    const stops = [[0, [8, 12, 30]], [0.35, [20, 70, 160]], [0.6, [40, 190, 120]], [0.8, [255, 200, 40]], [1, [255, 60, 50]]];
    for (let i = 1; i < stops.length; i++) if (t <= stops[i][0]) {
      const [t0, a] = stops[i - 1], [t1, b] = stops[i], u = (t - t0) / (t1 - t0);
      return `rgb(${a.map((v, j) => Math.round(v + (b[j] - v) * u)).join(',')})`;
    }
    return 'rgb(255,60,50)';
  };
  CS.water.forEach((c, r) => {
    for (let i = 0; i < c.length; i += 2) { g.fillStyle = heat(Math.max(c[i], c[i + 1] ?? -100)); g.fillRect(L + i, r * rh, 2, Math.ceil(rh)); }
  });
  g.fillStyle = getComputedStyle($('viewRadio')).getPropertyValue('--muted'); g.font = '10.5px Segoe UI, sans-serif'; g.textAlign = 'right';
  g.fillText('now', L - 6, 10); g.fillText('older', L - 6, H - 4);
}
