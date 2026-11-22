/* Ardzy - Radio view, part 2: the signals made on the board's ARM (project 12_fm_radio, main.py GEN modes):
   a picture in an SDR's waterfall (paint.py), radiofax (WEFAX), APRS packets and DTMF, and the listening
   notes of the new text modes (QRSS, Hell, WSPR, PSK63 .. 250). radio.js calls radioMoreCards() while it
   builds the page, radioMoreWire() after, radioMoreInfo(cfg) when settings change, radioMoreLive(status). */

const PT_BIN = 100e6 / 2048 / 8192;                  // the painter's tone grid: 5.96 Hz
const PT_DEFAULT = { kind: 'iq', width_hz: 20000, offset_hz: 0, line_ms: 40, contrast_db: 30, black: 0.06, gamma: 1,
  invert: false, mirror: false, bottom_first: true, edge_ms: 4, level: 0.95, repeat_s: 0, id: 0, image: 'paint_image.pgm' };
const PT_UI_DEFAULT = { src: 'test', columns: 160, stretch: 1, normalize: true, text: 'ARDZY', sdr_rate: 2.4, sdr_fft: 65536 };
// ready settings: [name, kind, width Hz, columns, line ms, contrast dB]
const PT_PRESETS = [
  ['SDR# / SDR++, quick (20 kHz wide, 128 columns, 30 ms a line)', 'iq', 20000, 128, 30, 30],
  ['SDR# / SDR++, detailed (24 kHz, 200 columns, 50 ms)', 'iq', 24000, 200, 50, 35],
  ['SDR# / SDR++, big and slow (26 kHz, 256 columns, 80 ms)', 'iq', 26000, 256, 80, 40],
  ['Narrow (8 kHz, 64 columns, 60 ms): for a small zoom', 'iq', 8000, 64, 60, 30],
  ['Receiver in USB, its audio waterfall (2.4 kHz, 64 columns, 100 ms)', 'usb', 2400, 64, 100, 30],
  ['WebSDR / slow waterfall (2 kHz, 40 columns, 400 ms)', 'usb', 2000, 40, 400, 25]];
const WEFAX_DEFAULT = { image: 'fax_image.pgm', lpm: 120, ioc: 576, phasing_s: 30, via: 'usb', repeat_s: 0, id: 0 };
const PACKET_DEFAULT = { call: 'N0CALL', dest: 'APZARD', path: 'WIDE1-1', text: '>Ardzy radio test', position: false,
  lat: 0, lon: 0, symbol: '/-', deviation_khz: 3, repeat_s: 60, id: 0 };
const DTMF_DEFAULT = { digits: '123A', tone_ms: 100, gap_ms: 100, deviation_khz: 3, repeat_s: 0, id: 0 };
const DIG_LISTEN = {
  cw: 'Any receiver in CW or SSB mode.',
  rtty: 'An SDR in USB, about 1 kHz below the frequency; decode with fldigi (RTTY 45.45 baud, 170 Hz shift).',
  psk31: 'An SDR in USB, about 1 kHz below the frequency; decode with fldigi (BPSK31).',
  psk63: 'fldigi in BPSK63. Twice as fast as PSK31, 63 Hz wide.',
  psk125: 'fldigi in BPSK125. 125 Hz wide.', psk250: 'fldigi in BPSK250. 250 Hz wide, quick.',
  qrss: 'A waterfall that runs very slowly: Argo, Spectrum Lab, or SDR# with a high FFT resolution and the slowest speed. ' +
    'The dots and dashes are read off the screen.',
  hell: 'fldigi in Feld Hell (USB, about 1 kHz below the frequency): the letters appear as a picture, twice, one above the other. ' +
    'The "Offset" moves the signal inside the receiver\'s pass band.',
  wspr: 'WSJT-X in WSPR mode: a USB receiver whose dial is 1500 Hz below the frequency + offset. Set "Offset" to 1400 .. 1600 Hz ' +
    'and the frequency to a WSPR dial (for example 14.0956 MHz on 20 m). The board\'s clock must be right: the Ardzy app sets it.',
  beacon: 'A receiver in USB or CW: the melody is heard as tones.', sweep: 'A spectrum display: the carrier walks across.'};

function ptCfg() { RAD.cfg.paint = Object.assign({}, PT_DEFAULT, RAD.cfg.paint || {}); return RAD.cfg.paint; }
function ptUi() { RAD.cfg.paint_ui = Object.assign({}, PT_UI_DEFAULT, RAD.cfg.paint_ui || {}); return RAD.cfg.paint_ui; }

function radioMoreCards() {
  const c = RAD.cfg;
  ptCfg(); ptUi();
  c.wefax = Object.assign({}, WEFAX_DEFAULT, c.wefax || {});
  c.packet = Object.assign({}, PACKET_DEFAULT, c.packet || {});
  c.dtmf = Object.assign({}, DTMF_DEFAULT, c.dtmf || {});
  return `
  <div class="dcard wide" id="radPaintCard"><h3>Picture in the waterfall<span class="grow"></span>
      <span class="seg" id="ptSrc"><button data-s="image">Picture</button><button data-s="text">Text</button><button data-s="test">Test picture</button></span></h3>
    <p class="rnote">Many tones side by side, one for each column of the picture, each as strong as its pixel is bright, one line
    after the other: an SDR program's waterfall (SDR#, SDR++, HDSDR, GQRX, a WebSDR) draws the picture as it scrolls.</p>
    <div class="pt-wrap">
      <div class="pt-prev">
        <div class="hint">What is sent (<span id="ptDims"></span>)</div><canvas id="ptCanvas" class="pt-cv"></canvas>
        <div class="hint">How a waterfall shows it</div><canvas id="ptWater" class="pt-cv"></canvas>
      </div>
      <div class="grow">
        <div class="rctl">
          <label class="pt-img">Picture</label><div class="row pt-img"><input type="file" id="ptFile" accept="image/*" style="max-width:260px"></div>
          <label class="pt-txt">Text</label><div class="pt-txt"><textarea id="ptText" rows="2" style="width:100%;font:inherit" maxlength="80"></textarea>
            <div class="hint">one or two short lines; big letters read best</div></div>
          <label>Ready settings</label><select id="ptPreset"><option value="">(choose to fill in the settings below)</option>
            ${PT_PRESETS.map((p, i) => `<option value="${i}">${esc(p[0])}</option>`).join('')}</select>
          <label>Send as</label><div class="row"><span class="seg" id="ptKind"><button data-v="iq">I/Q: up to 28 kHz wide</button><button data-v="usb">USB: 2.4 kHz</button></span>
            <span class="hint" id="ptKindNote"></span></div>
          <label>Width</label><div class="row">${inp('paint.width_hz', 'step="100" min="100" max="28000" style="width:90px"', 'number')} Hz
            <span class="hint" id="ptWidthNote"></span></div>
          <label>Centre</label><div class="row">${inp('paint.offset_hz', 'step="100" min="-14000" max="14000" style="width:90px"', 'number')} Hz
            <span class="hint" id="ptOffNote">from the frequency (0 = the picture's middle is on the frequency)</span></div>
          <label>Columns</label><div class="row"><input type="range" data-k="paint_ui.columns" data-t="num" min="16" max="400" step="1" class="grow">
            <span id="ptColsTxt" class="pv"></span></div>
          <label>Line height</label><div class="row"><input type="range" data-k="paint_ui.stretch" data-t="num" min="0.25" max="4" step="0.05" class="grow">
            <span id="ptStretchTxt" class="pv"></span></div>
          <label>Speed</label><div class="row">${inp('paint.line_ms', 'step="5" min="5" max="5000" style="width:80px"', 'number')} ms a line
            <span class="hint" id="ptSpeedNote"></span></div>
          <label>Contrast</label><div class="row"><input type="range" data-k="paint.contrast_db" data-t="num" min="10" max="60" step="1" class="grow">
            <span id="ptConTxt" class="pv"></span></div>
          <label>Black level</label><div class="row"><input type="range" data-k="paint.black" data-t="num" min="0" max="0.6" step="0.01" class="grow">
            <span id="ptBlackTxt" class="pv"></span></div>
          <label>Gamma</label><div class="row"><input type="range" data-k="paint.gamma" data-t="num" min="0.3" max="3" step="0.05" class="grow">
            <span id="ptGamTxt" class="pv"></span></div>
          <label>Options</label><div class="row" style="flex-wrap:wrap">${chk('paint_ui.normalize', 'stretch the greys', 'Darkest pixel black, brightest white')}
            ${chk('paint.invert', 'negative')}${chk('paint.mirror', 'mirror', 'Left and right swapped (for a receiver in LSB)')}
            ${chk('paint.bottom_first', 'bottom line first', 'Waterfalls scroll down: the line sent first ends at the bottom. Off for a waterfall that scrolls up.')}</div>
          <label>Soft edges</label><div class="row">${inp('paint.edge_ms', 'step="0.5" min="0.5" max="50" style="width:70px"', 'number')} ms
            <span class="hint">between two lines (less splash across the spectrum)</span></div>
          <label>Repeat</label><div class="row">every ${inp('paint.repeat_s', 'step="5" min="0" style="width:70px"', 'number')} s <span class="hint">(0 = once)</span></div>
        </div>
        <div class="row" style="margin-top:10px"><button class="primary" id="ptSend">Send to the waterfall</button>
          <span class="hint" id="ptOnNote"></span></div>
      </div>
    </div>
    <div class="bar" id="ptProg"><i style="width:0%"></i></div><div class="hint" id="ptState"></div>
    <div class="kv" id="ptFacts" style="margin-top:8px"></div>
    <details class="pt-help"><summary>Your SDR program: settings that make the picture sharp</summary>
      <div class="rctl">
        <label>Receiver rate</label><div class="row"><input type="number" data-k="paint_ui.sdr_rate" data-t="num" step="0.048" min="0.048" max="20" style="width:80px"> MS/s
          <span class="hint">RTL-SDR: 2.4 or 2.048 MS/s</span></div>
        <label>FFT size</label><div class="row"><select data-k="paint_ui.sdr_fft" data-t="int">${[4096, 8192, 16384, 32768, 65536, 131072, 262144].map(n => `<option value="${n}">${n}</option>`).join('')}</select>
          <span class="hint">SDR#: FFT Display, Resolution. SDR++: Display, FFT size.</span></div>
      </div>
      <div class="kv" id="ptSdr" style="margin-top:6px"></div>
      <ol class="rnote">
        <li>Tune the SDR to the radio's frequency (the picture's middle is the frequency plus "Centre"). In USB, the picture is 300 to 2700 Hz above it.</li>
        <li>FFT size as above, window Blackman-Harris. Zoom in until the picture's width fills about half the screen.</li>
        <li>Turn the waterfall speed up, and the range down to about 40 dB with the noise just dark (SDR#: Contrast / Range / Offset).
          The picture should lie 20 to 40 dB above the noise: lower the radio's power or the receiver's gain if it splashes.</li>
        <li>Squashed (too flat)? Make the lines slower (more ms), or the waterfall slower. Stretched? The other way round, or less "Line height".</li>
        <li>The pin also sends at 3x, 5x the frequency: the picture is there too, weaker. Use the resistor and the attenuator of the guide, not an antenna.</li>
      </ol>
    </details>
  </div>

  <div class="dcard" id="radFaxCard"><h3>Radiofax (WEFAX)<span class="grow"></span><button class="small primary" id="fxSend">Send this picture</button></h3>
    <div class="row" style="align-items:flex-start">
      <canvas id="fxCanvas" class="pt-cv" style="width:220px"></canvas>
      <div class="grow rctl" style="margin-top:0">
        <label>Picture</label><div class="row"><input type="file" id="fxFile" accept="image/*" style="max-width:200px"></div>
        <label>Speed</label><select data-k="wefax.lpm" data-t="int"><option value="60">60 lines a minute</option><option value="90">90</option>
          <option value="120">120 (weather maps)</option><option value="240">240 (quick)</option></select>
        <label>IOC</label><select data-k="wefax.ioc" data-t="int"><option value="576">576 (usual)</option><option value="288">288</option></select>
        <label>Phasing</label><div class="row">${inp('wefax.phasing_s', 'step="5" min="0" max="60" style="width:60px"', 'number')} s <span class="hint">lines that let the receiver find the line start</span></div>
        <label>Sent in</label><select data-k="wefax.via"><option value="usb">USB (short wave, the real way)</option><option value="fm">NFM</option></select>
        <label>Repeat</label><div class="row">every ${inp('wefax.repeat_s', 'step="10" min="0" style="width:70px"', 'number')} s</div>
      </div>
    </div>
    <div class="bar" id="fxProg"><i style="width:0%"></i></div><div class="hint" id="fxState"></div>
    <p class="rnote">A grey picture sent the way weather maps go out on short wave: 1500 Hz black to 2300 Hz white, the start tone
    (300 Hz), phasing lines, the picture, the stop tone (450 Hz). Receive with fldigi (WEFAX mode), HamFax or an SDR# fax plugin,
    the receiver in USB 1.9 kHz below the frequency. The picture is sent 1810 dots wide.</p>
  </div>

  <div class="dcard" id="radAprsCard"><h3>APRS packet<span class="grow"></span><button class="small primary" id="apSend">Send now</button></h3>
    <div class="rctl">
      <label>From</label><div class="row">${inp('packet.call', 'maxlength="9" style="width:110px;font-family:var(--mono);text-transform:uppercase"')}
        <span class="hint">your call sign, -SSID (for example -9 in a car)</span></div>
      <label>To</label><div class="row">${inp('packet.dest', 'maxlength="9" style="width:110px;font-family:var(--mono)"')} <span class="hint">APZARD (an experimental program)</span></div>
      <label>Path</label>${inp('packet.path', 'style="width:100%;font-family:var(--mono)" placeholder="WIDE1-1 (empty = none)"')}
      <label>Text</label>${inp('packet.text', 'maxlength="200" style="width:100%"')}
      <label>Position</label><div class="row">${chk('packet.position', 'send a position')} lat ${inp('packet.lat', 'step="0.0001" style="width:90px"', 'number')}
        lon ${inp('packet.lon', 'step="0.0001" style="width:100px"', 'number')}</div>
      <label>Deviation</label><div class="row">${inp('packet.deviation_khz', 'step="0.5" min="1" max="5" style="width:60px"', 'number')} kHz (NFM)</div>
      <label>Repeat</label><div class="row">every ${inp('packet.repeat_s', 'step="10" min="0" style="width:70px"', 'number')} s</div>
    </div>
    <div class="bar" id="apProg"><i style="width:0%"></i></div><div class="hint" id="apState"></div>
    <p class="rnote">AX.25 at 1200 baud (1200 / 2200 Hz tones) in NFM, as APRS uses. Decode with Direwolf, multimon-ng (AFSK1200),
    the SDR# / SDR++ packet plugins or APRSdroid. APRS frequencies (144.800 MHz in Europe, 144.390 in North America) are for
    licensed radio amateurs: test on a free frequency into an SDR, through the attenuator.</p>
  </div>

  <div class="dcard" id="radDtmfCard"><h3>DTMF tones<span class="grow"></span><button class="small primary" id="dtSend">Send now</button></h3>
    <div class="rctl">
      <label>Keys</label>${inp('dtmf.digits', 'maxlength="64" style="width:100%;font-family:var(--mono)" placeholder="0-9 * # A-D, a space = a pause"')}
      <label>Tone</label><div class="row">${inp('dtmf.tone_ms', 'step="10" min="40" max="1000" style="width:70px"', 'number')} ms, pause
        ${inp('dtmf.gap_ms', 'step="10" min="40" max="1000" style="width:70px"', 'number')} ms</div>
      <label>Deviation</label><div class="row">${inp('dtmf.deviation_khz', 'step="0.5" min="1" max="5" style="width:60px"', 'number')} kHz (NFM)</div>
      <label>Repeat</label><div class="row">every ${inp('dtmf.repeat_s', 'step="1" min="0" style="width:70px"', 'number')} s</div>
    </div>
    <div class="bar" id="dtProg"><i style="width:0%"></i></div><div class="hint" id="dtState"></div>
    <p class="rnote">Each key is two tones at once (697 .. 941 Hz with 1209 .. 1633 Hz). Decode with multimon-ng (DTMF) or listen
    with a scanner in NFM.</p>
  </div>`;
}

/* ---------------------------------------------------------------- the picture for the waterfall */
RAD.ptImg = null; RAD.fxImg = null;
function ptSize() {
  const u = ptUi(), cols = Math.max(16, Math.min(400, Math.round(+u.columns || 160)));
  let ar = 0.75;                                      // lines / columns
  if (u.src === 'image' && RAD.ptImg) ar = RAD.ptImg.height / RAD.ptImg.width;
  if (u.src === 'text') ar = ptTextLines().length > 1 ? 0.5 : 0.3;
  const lines = Math.max(4, Math.min(1200, Math.round(cols * ar * (+u.stretch || 1))));
  return [cols, lines];
}
function ptTextLines() { return (ptUi().text || 'ARDZY').split('\n').map(x => x.trim()).filter(x => x).slice(0, 3); }
function ptDraw() {
  const cv = $('ptCanvas');
  if (!cv) return null;
  const [W, H] = ptSize(), u = ptUi();
  cv.width = W; cv.height = H;
  const g = cv.getContext('2d');
  g.fillStyle = '#000'; g.fillRect(0, 0, W, H);
  if (u.src === 'image' && RAD.ptImg) {              // the whole picture, black bars where it does not fill
    const im = RAD.ptImg, k = Math.min(W / im.width, H / im.height);
    g.imageSmoothingQuality = 'high';
    g.drawImage(im, (W - im.width * k) / 2, (H - im.height * k) / 2, im.width * k, im.height * k);
  } else if (u.src === 'text') {
    const ls = ptTextLines(), n = ls.length || 1;
    let size = H / n * 0.8;
    g.font = `bold ${size}px Segoe UI, Arial, sans-serif`;
    const wmax = Math.max(...ls.map(l => g.measureText(l).width), 1);
    if (wmax > W * 0.94) size *= W * 0.94 / wmax;
    g.font = `bold ${size}px Segoe UI, Arial, sans-serif`;
    g.fillStyle = '#fff'; g.textAlign = 'center'; g.textBaseline = 'middle';
    ls.forEach((l, i) => g.fillText(l, W / 2, H * (i + 0.5) / n));
  } else {                                           // the test picture: frame, diagonal, grey ramp, a word
    g.strokeStyle = '#fff'; g.lineWidth = 1; g.strokeRect(0.5, 0.5, W - 1, H - 1);
    g.strokeStyle = '#ccc'; g.beginPath(); g.moveTo(0, H); g.lineTo(W, 0); g.stroke();
    const grd = g.createLinearGradient(4, 0, W - 4, 0); grd.addColorStop(0, '#222'); grd.addColorStop(1, '#fff');
    g.fillStyle = grd; g.fillRect(4, H - Math.max(4, H * 0.12) - 3, W - 8, Math.max(4, H * 0.12));
    g.fillStyle = '#fff'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.font = `bold ${Math.min(H * 0.32, W / 4.2)}px Segoe UI, Arial, sans-serif`; g.fillText('ARDZY', W / 2, H * 0.4);
  }
  const d = g.getImageData(0, 0, W, H).data, gray = new Uint8Array(W * H);
  for (let i = 0; i < W * H; i++) gray[i] = Math.round(0.299 * d[4 * i] + 0.587 * d[4 * i + 1] + 0.114 * d[4 * i + 2]);
  if (u.normalize && u.src === 'image') {
    let lo = 255, hi = 0;
    for (const v of gray) { if (v < lo) lo = v; if (v > hi) hi = v; }
    if (hi > lo) for (let i = 0; i < gray.length; i++) gray[i] = Math.round((gray[i] - lo) * 255 / (hi - lo));
  }
  const out = g.createImageData(W, H);
  for (let i = 0; i < W * H; i++) { out.data[4 * i] = out.data[4 * i + 1] = out.data[4 * i + 2] = gray[i]; out.data[4 * i + 3] = 255; }
  g.putImageData(out, 0, 0);
  $('ptDims').textContent = `${W} x ${H}`;
  ptWaterfall(gray, W, H);
  return { gray, W, H };
}
function ptColor(t) {                                // a waterfall palette: black, blue, cyan, yellow, red
  const st = [[0, 0, 0, 0], [0.25, 0, 0, 140], [0.5, 0, 170, 255], [0.75, 255, 230, 0], [1, 255, 40, 20]];
  for (let i = 1; i < st.length; i++) if (t <= st[i][0]) {
    const a = st[i - 1], b = st[i], f = (t - a[0]) / (b[0] - a[0]);
    return [0, 1, 2].map(k => Math.round(a[k + 1] + (b[k + 1] - a[k + 1]) * f));
  }
  return st[st.length - 1].slice(1);
}
function ptWaterfall(gray, W, H) {
  const p = ptCfg(), cv = $('ptWater');
  cv.width = W; cv.height = H;
  const g = cv.getContext('2d'), img = g.createImageData(W, H);
  const range = +p.contrast_db + 15, gam = Math.max(0.1, +p.gamma || 1);
  let seed = 7;
  const noise = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    let b = gray[y * W + (p.mirror ? W - 1 - x : x)] / 255;
    if (p.invert) b = 1 - b;
    b = Math.pow(b, gam);
    const db = b < +p.black ? -range - 3 : (b - 1) * +p.contrast_db;   // black: the noise floor only
    const lvl = Math.max(db, -range + 4 * noise() - 4);
    const [r, gg, bb] = ptColor(Math.max(0, Math.min(1, (lvl + range) / range)));
    const i = 4 * (y * W + x);
    img.data[i] = r; img.data[i + 1] = gg; img.data[i + 2] = bb; img.data[i + 3] = 255;
  }
  g.putImageData(img, 0, 0);
}
function ptLayout(cols) {                            // the same rule as paint.layout() on the board
  const p = ptCfg();
  let width = Math.abs(+p.width_hz || 0), low;
  if (p.kind === 'usb') { width = Math.min(width, 2400); low = 300 + Math.max(0, Math.min(2400 - width, +p.offset_hz || 0)); }
  else { width = Math.min(width, 28000); const mid = Math.max(-14000 + width / 2, Math.min(14000 - width / 2, +p.offset_hz || 0)); low = mid - width / 2; }
  const step = cols > 1 ? Math.max(1, Math.floor(width / (cols - 1) / PT_BIN)) : 1;
  const real = step * (cols - 1) * PT_BIN;
  return { width: real, low: Math.round((low + (width - real) / 2) / PT_BIN) * PT_BIN, spacing: step * PT_BIN, squeezed: real < width - PT_BIN * cols };
}
function ptFacts() {
  const p = ptCfg(), u = ptUi(), [W, H] = ptSize(), L = ptLayout(W), ms = Math.max(5, +p.line_ms || 40);
  const st = RAD.st || {};
  const iqOk = st.has_iq !== false;
  $('ptKind').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.v === (p.kind || 'iq')));
  $('ptKindNote').textContent = p.kind !== 'usb' && !iqOk ? 'the design on the board has no I/Q mode yet: Upload and run the radio again' : '';
  $('ptSrc').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.s === u.src));
  document.querySelectorAll('#radPaintCard .pt-img').forEach(e => e.style.display = u.src === 'image' ? '' : 'none');
  document.querySelectorAll('#radPaintCard .pt-txt').forEach(e => e.style.display = u.src === 'text' ? '' : 'none');
  $('ptOffNote').textContent = p.kind === 'usb' ? 'Hz above 300 Hz (0 = from 300 Hz up)' : 'Hz from the frequency (0 = the picture\'s middle is on the frequency)';
  $('ptColsTxt').textContent = W;
  $('ptStretchTxt').textContent = 'x' + (+u.stretch).toFixed(2) + ' = ' + H + ' lines';
  $('ptConTxt').textContent = p.contrast_db + ' dB';
  $('ptBlackTxt').textContent = Math.round(p.black * 100) + ' %';
  $('ptGamTxt').textContent = (+p.gamma).toFixed(2);
  $('ptWidthNote').textContent = L.squeezed ? `too many columns for this width: ${Math.round(L.width)} Hz used` : `${Math.round(L.width)} Hz used`;
  $('ptSpeedNote').textContent = `${(1000 / ms).toFixed(1)} lines a second, the picture takes ${fmtS(H * ms / 1000)}`;
  const f = +RAD.cfg.freq_mhz * 1e6;
  const fmt = hz => (hz / 1e6).toFixed(6).replace(/0+$/, '') + ' MHz';
  $('ptFacts').innerHTML = [['On air', `${fmt(f + L.low)} to ${fmt(f + L.low + L.width)} (${(L.width / 1000).toFixed(2)} kHz)`],
    ['Columns', `${W}, one tone every ${L.spacing.toFixed(1)} Hz`], ['Lines', `${H}, ${ms} ms each`],
    ['Time', fmtS(H * ms / 1000) + ' for the whole picture'], ['Sent as', p.kind === 'usb' ? 'USB sound (the side-band filter)' : 'I/Q from the ARM (no carrier)']]
    .map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join('');
  // the receiver's side: its FFT bin and how long one FFT lasts
  const rate = (+u.sdr_rate || 2.4) * 1e6, nfft = +u.sdr_fft || 65536, bin = rate / nfft, tfft = nfft / rate * 1000;
  const per = L.spacing / bin, ok1 = per >= 2.5, ok2 = ms >= tfft;
  $('ptSdr').innerHTML = [['FFT bin', `${bin.toFixed(1)} Hz (one FFT lasts ${tfft.toFixed(1)} ms)`],
    ['Columns', `${per.toFixed(1)} bins apart <b class="${ok1 ? '' : 'bad'}">${ok1 ? 'sharp' : 'too close: fewer columns, more width or a bigger FFT'}</b>`],
    ['Lines', `${(ms / tfft).toFixed(1)} FFTs a line <b class="${ok2 ? '' : 'bad'}">${ok2 ? 'clear' : 'too quick: lines blur together; make them at least ' + Math.ceil(tfft) + ' ms'}</b>`],
    ['Zoom to', `about ${(L.width * 2 / 1000).toFixed(1)} kHz across the screen`]]
    .map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join('');
  $('ptOnNote').textContent = RAD.cfg.on ? '' : 'then switch the transmitter on (OFF AIR button at the top)';
}
async function ptSend() {
  const d = ptDraw();
  if (!d) return;
  const r = await api('/api/radio/gray', { p: RAD.project, which: 'paint', w: d.W, h: d.H, gray: b64(d.gray) });
  if (!r.ok) { out('Picture not sent: ' + (r.out || ''), 'err'); return; }
  RAD.cfg.mode = 'paint';
  const p = ptCfg(); p.id = (p.id || 0) + 1;
  radioFill(); radioSend(0);
  out(`Picture for the waterfall sent to the board (${d.W} x ${d.H})` + (RAD.cfg.on ? ': it goes on air now.' : '. Switch the transmitter on to send it.'), 'ok');
}
function b64(u8) {
  let bin = '';
  for (let i = 0; i < u8.length; i += 0x8000) bin += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
  return btoa(bin);
}

/* ---------------------------------------------------------------- radiofax picture */
function fxDraw() {
  const cv = $('fxCanvas');
  if (!cv) return null;
  const W = 905, im = RAD.fxImg, H = im ? Math.max(20, Math.min(1200, Math.round(W * im.height / im.width))) : 600;
  cv.width = W; cv.height = H;
  const g = cv.getContext('2d');
  g.fillStyle = '#fff'; g.fillRect(0, 0, W, H);
  if (im) g.drawImage(im, 0, 0, W, H);
  else {                                             // a test chart: a grey scale and lines
    for (let i = 0; i < 8; i++) { g.fillStyle = `rgb(${i * 36},${i * 36},${i * 36})`; g.fillRect(i * W / 8, 0, W / 8, H * 0.25); }
    g.strokeStyle = '#000'; g.lineWidth = 3;
    for (let i = 1; i < 10; i++) { g.beginPath(); g.moveTo(0, H * 0.25 + i * H * 0.075); g.lineTo(W, H * 0.25 + i * H * 0.075); g.stroke(); }
    g.fillStyle = '#000'; g.font = 'bold 90px Segoe UI, Arial'; g.textAlign = 'center'; g.fillText('ARDZY FAX', W / 2, H * 0.62);
  }
  const d = g.getImageData(0, 0, W, H).data, gray = new Uint8Array(W * H);
  for (let i = 0; i < W * H; i++) gray[i] = Math.round(0.299 * d[4 * i] + 0.587 * d[4 * i + 1] + 0.114 * d[4 * i + 2]);
  const o = g.createImageData(W, H);
  for (let i = 0; i < W * H; i++) { o.data[4 * i] = o.data[4 * i + 1] = o.data[4 * i + 2] = gray[i]; o.data[4 * i + 3] = 255; }
  g.putImageData(o, 0, 0);
  return { gray, W, H };
}
async function fxSend() {
  const d = fxDraw();
  const r = await api('/api/radio/gray', { p: RAD.project, which: 'fax', w: d.W, h: d.H, gray: b64(d.gray) });
  if (!r.ok) { out('Picture not sent: ' + (r.out || ''), 'err'); return; }
  RAD.cfg.mode = 'wefax'; RAD.cfg.wefax.id = (RAD.cfg.wefax.id || 0) + 1;
  radioFill(); radioSend(0);
  out(`Radiofax picture sent to the board (${d.H} lines, ${fmtS(d.H * 60 / RAD.cfg.wefax.lpm)} of picture).`, 'ok');
}

/* ---------------------------------------------------------------- wiring and live state */
function radioMoreWire() {
  const loadImg = (f, cb) => { const im = new Image(); im.onload = () => cb(im); im.src = URL.createObjectURL(f); };
  $('ptFile').onchange = e => { const f = e.target.files[0]; if (f) loadImg(f, im => { RAD.ptImg = im; ptUi().src = 'image'; ptFacts(); ptDraw(); }); };
  $('ptText').value = ptUi().text;
  $('ptText').oninput = () => { ptUi().text = $('ptText').value; ptDraw(); radioSend(1500); };
  $('ptSrc').querySelectorAll('button').forEach(b => b.onclick = () => { ptUi().src = b.dataset.s; ptFacts(); ptDraw(); radioSend(500); });
  $('ptKind').querySelectorAll('button').forEach(b => b.onclick = () => {
    const p = ptCfg(); p.kind = b.dataset.v;
    if (p.kind === 'usb') { p.width_hz = Math.min(+p.width_hz, 2400); p.offset_hz = 0; } else if (+p.width_hz <= 2400) p.width_hz = 20000;
    radioFill(); radioSend(300);
  });
  $('ptPreset').onchange = e => {
    const x = PT_PRESETS[+e.target.value]; if (!x) return;
    const p = ptCfg(), u = ptUi();
    [p.kind, p.width_hz, u.columns, p.line_ms, p.contrast_db] = [x[1], x[2], x[3], x[4], x[5]];
    p.offset_hz = 0; e.target.value = '';
    radioFill(); radioSend(300);
  };
  $('ptSend').onclick = ptSend;
  $('fxFile').onchange = e => { const f = e.target.files[0]; if (f) loadImg(f, im => { RAD.fxImg = im; fxDraw(); }); };
  $('fxSend').onclick = fxSend;
  $('apSend').onclick = () => { RAD.cfg.packet.id = (RAD.cfg.packet.id || 0) + 1; radioSend(0); };
  $('dtSend').onclick = () => { RAD.cfg.dtmf.id = (RAD.cfg.dtmf.id || 0) + 1; radioSend(0); };
  // the preview follows every setting of the card at once
  $('radPaintCard').addEventListener('input', () => { ptFacts(); ptDraw(); });
  ptFacts(); ptDraw(); fxDraw();
}

function radioMoreInfo(c) {
  const mode = c.mode;
  if (!$('radPaintCard')) return;
  $('radPaintCard').style.display = mode === 'paint' ? '' : 'none';
  $('radFaxCard').style.display = mode === 'wefax' ? '' : 'none';
  $('radAprsCard').style.display = mode === 'aprs' ? '' : 'none';
  $('radDtmfCard').style.display = mode === 'dtmf' ? '' : 'none';
  ['csBridge', 'csSpecCard'].forEach(id => { if ($(id)) $(id).style.display = GEN_MODES.includes(mode) ? 'none' : ''; });   // (sound meters: not for these)
  if (DIG_LISTEN[mode] && $('radDigListen')) $('radDigListen').textContent = 'Listen: ' + DIG_LISTEN[mode];
  if (mode === 'paint') { ptFacts(); ptDraw(); }
}

function genProgress(st, bar, txt) {
  const g = st.generated;
  if (!g) { $(txt).textContent = RAD.cfg.on ? '' : 'transmitter off: switch it on to send'; $(bar).querySelector('i').style.width = '0%'; return; }
  $(bar).querySelector('i').style.width = g.sending && g.len_s ? Math.min(100, 100 * g.pos_s / g.len_s) + '%' : '0%';
  $(txt).textContent = !RAD.cfg.on ? 'transmitter off: switch it on to send'
    : g.preparing ? 'preparing the picture on the board ...'
    : g.sending ? `sending ${g.what}: ${fmtS(g.pos_s)} of ${fmtS(g.len_s)}`
    : g.next_in_s != null ? `sent; again in ${g.next_in_s} s` : 'sent (press the send button to send it again)';
}
function radioMoreLive(st) {
  const m = RAD.cfg.mode;
  if (m === 'paint') {
    genProgress(st, 'ptProg', 'ptState');
    const g = st.generated;
    if (g && g.hw && g.hw !== (ptCfg().kind === 'usb' ? 'usb' : 'iq')) $('ptState').textContent += ' (sent in USB: this design has no I/Q mode)';
    if (g && !g.have_image) $('ptState').textContent += ' (the test picture: press "Send to the waterfall" to put yours on the board)';
  }
  if (m === 'wefax') genProgress(st, 'fxProg', 'fxState');
  if (m === 'aprs') genProgress(st, 'apProg', 'apState');
  if (m === 'dtmf') genProgress(st, 'dtProg', 'dtState');
  const d = st.digital;
  if (m === 'wspr' && d && !d.busy && d.next_in_s != null) $('radDigTxt').textContent = `waiting for the next WSPR slot: starts in ${d.next_in_s} s (1 s after an even minute)`;
}

window.radioMoreCards = radioMoreCards;
