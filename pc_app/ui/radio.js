/* Ardzy - Radio view: the FM / AM / digital-mode transmitter of project 12_fm_radio.
   The board runs the radio service (main.py of the project): this page writes its settings (radio.json)
   and shows its status (status.json), the RDS data as a receiver decodes it, and the MPX spectrum.
   Helpers from app.js / board.js: $, esc, api, out, S, BV, showView, showTab. */
const RAD = { cfg: null, st: null, running: false, built: false, timer: null, sendT: null, rev: 0,
  pendingAdd: new Set(), specAuto: true, specBusy: false, lastSpec: 0 };
const RADIO_PROJECT = '12_fm_radio';
RAD.project = RADIO_PROJECT;                 // or a renamed copy of it, when that one runs on the board
const PTY_NAMES = ['None', 'News', 'Current affairs', 'Information', 'Sport', 'Education', 'Drama', 'Culture', 'Science',
  'Varied', 'Pop music', 'Rock music', 'Easy listening', 'Light classical', 'Serious classical', 'Other music', 'Weather',
  'Finance', "Children's", 'Social affairs', 'Religion', 'Phone-in', 'Travel', 'Leisure', 'Jazz', 'Country',
  'National music', 'Oldies', 'Folk', 'Documentary', 'Alarm test', 'Alarm'];
const RMODES = [['fm', 'WFM: FM broadcast (stereo / mono, RDS)'], ['nfm', 'NFM: narrow FM (walkie-talkie style)'],
  ['am', 'AM (medium and short wave)'], ['usb', 'USB: upper side band'], ['lsb', 'LSB: lower side band'],
  ['dsb', 'DSB: double side band, no carrier'], ['carrier', 'Carrier only (tuning, tests)'], ['cw', 'CW: Morse code'],
  ['rtty', 'RTTY: radio teletype'], ['psk31', 'PSK31'], ['beacon', 'Beacon: a melody for SSB receivers'],
  ['sweep', 'Sweep: steps across a range']];
const DIGITAL_MODES = ['cw', 'rtty', 'psk31', 'beacon', 'sweep'];
const SOUND_MODES = ['fm', 'nfm', 'am', 'usb', 'lsb', 'dsb'];
const SSTV_MODES = [['martin1', 'Martin 1 (114 s, the most used)'], ['scottie1', 'Scottie 1 (110 s)'], ['robot36', 'Robot 36 (36 s, quick)']];
const LISTEN = {
  fm: 'Any FM radio. Stereo, station name and text on radios with RDS.',
  nfm: 'A scanner, a walkie-talkie or an SDR in NFM. Mono, voice band (300 to 2700 Hz), 5 kHz deviation.',
  am: 'An AM radio (medium wave 531 to 1602 kHz) or a short-wave receiver; an SDR in AM.',
  usb: 'A short-wave receiver or an SDR in USB, tuned to the frequency above. Only the upper side band is sent: half the width of AM, no carrier.',
  lsb: 'A receiver or an SDR in LSB (the usual mode below 10 MHz for radio amateurs).',
  dsb: 'An SDR in DSB, or in USB / LSB (one half is enough). Both side bands, the carrier is left out.'};

const getK = (o, k) => k.split('.').reduce((a, p) => (a == null ? a : a[p]), o);
function setK(o, k, v) { const ps = k.split('.'); let a = o; ps.slice(0, -1).forEach(p => { a[p] = a[p] || {}; a = a[p]; }); a[ps[ps.length - 1]] = v; }
const pct = v => Math.round(v * 100) + ' %';
const fmtS = s => s == null ? '' : Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0');

async function radioShow() {
  clearTimeout(RAD.timer);
  radioPoll();
}

async function radioPoll() {
  clearTimeout(RAD.timer);
  if (BV.view !== 'radio') return;
  if (!S.connected) {
    $('radState').textContent = 'no board';
    $('radBody').innerHTML = '<div class="empty">No board connected.</div>';
    RAD.built = false;
    RAD.timer = setTimeout(radioPoll, 2000);
    return;
  }
  let r;
  const cur = S.status && S.status.current;
  try {
    r = null;
    if (cur && cur !== RADIO_PROJECT) {                // a renamed copy of the radio project?
      const c = await api('/api/radio/state?p=' + encodeURIComponent(cur));
      if (c.ok && c.running) { r = c; RAD.project = cur; }
    }
    if (!r) { r = await api('/api/radio/state?p=' + RADIO_PROJECT); RAD.project = RADIO_PROJECT; }
  } catch (e) { r = { ok: false, out: String(e) }; }
  $('radBoot').checked = !!(S.status && S.status.default === RAD.project);
  if (!r.ok) {
    $('radState').textContent = r.out || 'board not answering';
  } else if (!r.running) {
    if (RAD.built || !$('radStart')) radioNotRunning();
    RAD.built = false;
  } else {
    RAD.st = r.status;
    if (!RAD.built) {
      // the service's own copy is complete (older radio.json files lack newer settings)
      RAD.cfg = JSON.parse(JSON.stringify((r.status && r.status.config) || r.config));
      RAD.cfg.capture = 0;
      RAD.rev = RAD.cfg.rev || 0;
      radioBuild();
      radioSend(500);                                 // (also tells the board the PC's time)
    } else if (r.status && r.status.config && (r.status.config.rev || 0) > RAD.rev) {
      // the settings were changed somewhere else (the board's web page, radio.json): show them, unless
      // a text field here is being edited right now
      const a = document.activeElement;
      if (!(a && $('radBody').contains(a) && /INPUT|TEXTAREA|SELECT/.test(a.tagName) && a.type !== 'range' && a.type !== 'checkbox')) {
        RAD.cfg = JSON.parse(JSON.stringify(r.status.config));
        RAD.cfg.capture = 0;
        RAD.rev = RAD.cfg.rev || 0;
        radioFill();
        rdsEditors();
      }
    }
    radioLive();
  }
  RAD.timer = setTimeout(radioPoll, 500);
}

function radioNotRunning() {
  const cur = (S.status && S.status.current) || (S.board && S.board.current) || 'nothing';
  $('radState').textContent = 'the radio is not running';
  $('radBody').innerHTML = `<div class="dcard wide"><h3>FM radio transmitter</h3>
    <p>The radio lives in the FPGA project <b>12_fm_radio</b>: an FM stereo transmitter with RDS (your station name and text on the
    radio's display), AM, Morse code, RTTY, PSK31, beacons and sweeps, all made inside the FPGA on one pin (J9 pin 11).
    The board now runs <b>${esc(cur)}</b>.</p>
    <div class="row"><button class="primary" id="radStart">Start the radio on the board</button>
      <button class="ghost" id="radGuide2">Read the guide first</button></div>
    <p class="rnote">Starting uploads the prebuilt design and the radio service (a few seconds). Your settings and songs on the board stay.
    A new radio starts with the transmitter off.</p></div>`;
  $('radStart').onclick = async () => {
    const x = await api('/api/gallery/upload', { name: RADIO_PROJECT });
    if (!x.ok) out(x.out || 'busy', 'err'); else $('radState').textContent = 'starting ...';
  };
  $('radGuide2').onclick = () => galleryGuide(RADIO_PROJECT);
}

/* ---------------------------------------------------------------- the page */
function inp(k, attrs = '', type = 'text') { return `<input data-k="${k}" type="${type}" ${attrs}>`; }
function chk(k, label, title = '') { return `<label class="check" title="${esc(title)}"><input type="checkbox" data-k="${k}"> ${label}</label>`; }

function radioBuild() {
  RAD.built = true;
  $('radBody').innerHTML = `
  <div class="console wide">
    <div class="cs-top">
      <button class="onair" id="radOnAir" title="Switch the transmitter on or off">OFF AIR</button>
      <div class="cs-freq">
        <div class="cs-lbl">Frequency</div>
        <div class="freq" id="radFreqBig">--</div>
        <div class="cs-mode" id="radModeTxt"></div>
      </div>
      <div class="cs-tune">
        <div class="row"><span class="cs-lbl">Tune</span>${inp('freq_mhz', 'step="0.05" min="0.1" max="200" class="grow cs-fin"', 'number')}<span class="cs-lbl">MHz</span></div>
        <div class="row steps">
          <button class="small" data-step="-0.1">-0.1</button><button class="small" data-step="-0.05">-0.05</button>
          <button class="small" data-step="0.05">+0.05</button><button class="small" data-step="0.1">+0.1</button>
        </div>
        <div class="row"><select data-k="mode" class="grow">${RMODES.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join('')}</select></div>
        <div class="row"><span class="cs-lbl">Power</span><input type="range" data-k="power" data-t="num" min="0" max="1" step="0.01" class="grow">
          <span id="radPowTxt" class="pv"></span></div>
        <div class="hint" id="radPowNote"></div><div class="hint" id="radBandHint"></div>
      </div>
      <div class="cs-status">
        <div class="lamps" id="csLamps"></div>
        <div class="cs-facts"><div class="rfacts" id="radFacts"></div><div class="rfacts" id="radFacts2"></div></div>
      </div>
      <canvas class="cs-clock" id="csClock" title="Studio clock (this PC's time)"></canvas>
    </div>
    <div class="cs-timers" id="csTimers"></div>
    <p class="rnote">The pin sends a square wave (it also sends harmonics). Use a frequency nobody uses where you live, the lowest
    power that works and a short wire (10 to 20 cm). Most countries allow only very weak transmitters without a licence (in the EU,
    small FM transmitters for a car stereo may use up to 50 nW). For tests into an SDR use an attenuator, not an antenna.</p>
  </div>

  <div class="dcard wide bridge" id="csBridge"><h3>Meter bridge<span class="grow"></span>
      <span class="hint">peak meters with a 2 s peak hold; GR = how much the limiter turns the sound down</span></h3>
    <div class="mb">
      <canvas id="csMeters" class="mb-meters"></canvas>
      <div class="mb-side">
        <div class="mb-t">Stereo image</div>
        <canvas id="csGonio" class="gonio" title="Goniometer: a vertical line is mono, a wide cloud is wide stereo, a horizontal line is out of phase"></canvas>
        <div class="mb-t">Correlation <span class="hint" id="csCorrV">-</span></div>
        <div class="corr" id="csCorr"><span>-1</span><span>0</span><span>+1</span><i></i></div>
      </div>
      <div class="mb-side wide">
        <div class="mb-t">Real-time analyzer <span class="hint">1/3 octave, after the processing (blue line: before)</span></div>
        <canvas id="csRta" class="rta"></canvas>
      </div>
    </div>
  </div>

  <div class="dcard wide" id="csSpecCard"><h3>MPX spectrum and waterfall<span class="grow"></span>
      <label class="check"><input type="checkbox" id="specAuto"> live</label><button class="small" id="specGo">Capture</button></h3>
    <canvas id="radSpec" class="spec"></canvas>
    <canvas id="csWater" class="water"></canvas>
    <div class="hint" id="specInfo">The FM transmitter is driven by this one signal (390625 samples per second): the sound L+R up to 15 kHz,
      the 19 kHz pilot, the stereo difference L-R around 38 kHz, and RDS around 57 kHz. Green: now, amber: the peaks of the last seconds.</div>
  </div>

  <div class="dcard" id="radAudioCard"><h3>Sound<span class="grow"></span><span class="seg" id="radSrc">
      <button data-src="tones">Test tones</button><button data-src="playlist">Songs</button><button data-src="sstv">Picture</button><button data-src="network">Network</button><button data-src="silence">Silence</button></span></h3>
    <p class="rnote" id="radListen"></p>
    <div class="rctl">
      <label>Volume</label><div class="row"><input type="range" data-k="audio.volume" data-t="num" min="0" max="3" step="0.05" class="grow"><span id="radVolTxt" style="width:46px"></span></div>
      <label class="srcTones">Left tone</label><div class="row srcTones">${inp('audio.tone_l', 'step="1" min="0" max="20000" style="width:90px"', 'number')} Hz</div>
      <label class="srcTones">Right tone</label><div class="row srcTones">${inp('audio.tone_r', 'step="1" min="0" max="20000" style="width:90px"', 'number')} Hz
        <span class="hint">different tones show which speaker is which</span></div>
    </div>
    <div class="srcList">
      <div class="row" style="margin-top:8px"><b class="grow" id="radNow">Nothing playing</b><span class="hint" id="radPos"></span></div>
      <div class="bar" id="radProg"><i style="width:0%"></i></div>
      <div class="row"><span class="hint grow">Playlist (plays in this order)</span>${chk('audio.loop', 'repeat')}${chk('audio.shuffle', 'shuffle')}</div>
      <ul class="plist" id="radPlaylist"></ul>
      <div class="row"><span class="hint grow">Songs on the board</span><button class="small" id="radAddWav">Send a WAV file ...</button></div>
      <ul class="plist" id="radFiles"></ul>
      <p class="rnote">WAV files (PCM, any rate, mono or stereo, up to 63 MB). Convert MP3 with Audacity or VLC. The FPGA resamples to 48.8 kHz.</p>
    </div>
    <div class="srcNet">
      <div class="row" style="margin-top:8px"><b class="grow">From this PC</b><button class="ghost small" id="pcRefresh">Refresh devices</button></div>
      <div class="row"><select id="pcDev" class="grow" style="min-width:220px"><option>loading ...</option></select>
        <button class="primary small" id="pcSend">Send this PC's sound</button><button class="ghost small" id="pcStop">Stop</button></div>
      <div class="kv" id="pcState" style="margin-top:6px"></div>
      <div class="row" style="margin-top:8px"><b class="grow">AES67 streams this PC hears</b><span class="hint" id="pcHeardCount"></span></div>
      <ul class="plist" id="pcHeard"></ul>
      <p class="rnote">The app sends straight to the board over the cable it already uses, so it does not matter which network
      card Windows would choose. "Everything this PC plays" takes the sound of an output (your speakers or VB-CABLE); any AES67
      program on this PC (or on another network this PC is on) appears in the list above and can be passed on to the radio.</p>
      <div class="row" style="margin-top:8px"><b class="grow">AES67 streams the board hears</b><span class="hint" id="netCount"></span></div>
      <ul class="plist" id="netList"></ul>
      <div class="rctl">
        <label>Or by hand</label><div class="row">${inp('network.address', 'style="width:130px;font-family:var(--mono)" placeholder="239.69.83.67"')} port
          ${inp('network.port', 'step="1" min="1" max="65535" style="width:80px"', 'number')}</div>
        <label>Format</label><div class="row"><select data-k="network.encoding"><option>L24</option><option>L16</option></select>
          ${inp('network.rate', 'step="1" min="8000" max="96000" style="width:80px"', 'number')} Hz,
          ${inp('network.channels', 'step="1" min="1" max="8" style="width:50px"', 'number')} channels</div>
      </div>
      <div class="rctl"><label>Buffer</label><div class="row"><input type="range" data-k="network.buffer_ms" data-t="num" min="20" max="2000" step="10" class="grow">
        <span id="netBufTxt" style="width:70px"></span></div></div>
      <p class="rnote">The buffer is sound kept in hand: network packets come in bursts and the board is sometimes busy for a
      moment. If you hear clicks, make it bigger (150 to 300 ms); the sound then comes that much later.</p>
      <div class="kv" id="netState" style="margin-top:8px"></div>
      <p class="rnote">AES67 is uncompressed sound over the network (RTP): studio consoles and RAVENNA devices, Dante in AES67 mode,
      PipeWire, ffmpeg. The radio follows the sender's clock and keeps about 40 ms of sound in hand. From this PC:
      <code>python aes67_send.py song.wav</code> or <code>--tone 1000</code> (in the project folder); for live sound use ffmpeg (see the guide).</p>
    </div>
    <div class="srcPic">
      <div class="row" style="margin-top:8px;align-items:flex-start">
        <canvas id="picCanvas" width="320" height="256" style="width:240px;height:192px;border:1px solid var(--line);border-radius:6px;background:#000"></canvas>
        <div class="grow" style="min-width:180px">
          <div class="row"><input type="file" id="picFile" accept="image/*" style="max-width:230px"></div>
          <div class="row">${inp('_caption', 'id="picText" placeholder="text on the picture (call sign, name)" maxlength="24" style="width:100%"')}</div>
          <div class="row">SSTV mode <select data-k="sstv.mode">${SSTV_MODES.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join('')}</select></div>
          <div class="row">again every ${inp('sstv.repeat_s', 'step="10" min="0" style="width:70px"', 'number')} s <span class="hint">(0 = once)</span></div>
          <div class="row"><button class="primary small" id="picSend">Send this picture</button></div>
        </div>
      </div>
      <div class="bar" id="picProg"><i style="width:0%"></i></div><div class="hint" id="picState"></div>
      <p class="rnote">The picture goes out as sound (slow-scan TV): 1500 Hz black to 2300 Hz white, line by line. In FM put a phone
      with the free <b>Robot36</b> app next to the radio's speaker; with an SDR use MMSSTV or QSSTV. It works in every sound mode.</p>
    </div>
  </div>

  <div class="dcard" id="radRdsCard"><h3>RDS: what radios show<span class="grow"></span>${chk('rds.on', 'on')}</h3>
    <div class="lcd"><div class="ps" id="lcdPs">--------</div><div class="rt" id="lcdRt"></div>
      <div class="info"><span id="lcdPty"></span><span id="lcdCt"></span><span id="lcdPi"></span></div></div>
    <p class="rnote">Decoded on the board from the bits the FPGA really sent, the way a car radio does.</p>
    <div class="rdsSec"><div class="row"><b class="grow">Station name (PS)</b><span class="seg" id="psMode">
        <button data-m="fixed">Fixed</button><button data-m="list">List</button><button data-m="scroll">Scrolling</button><button data-m="words">Word by word</button></span></div>
      <div class="psFixed row">${inp('rds.ps', 'maxlength="8" style="width:130px;font-family:var(--mono)"')}<span class="chars" id="psChars"></span></div>
      <div class="psList"><ul class="plist ed" id="psListEd"></ul><button class="ghost small" id="psAdd">+ add a name</button>
        <span class="hint">each up to 8 characters, shown for its seconds, then the next, round and round</span></div>
      <div class="psScroll">${inp('rds.scroll', 'maxlength="160" style="width:100%" placeholder="a longer text, for example: Ardzy FM {song}"')}
        <div class="row">a step every ${inp('rds.scroll_s', 'step="0.1" min="0.3" max="10" style="width:64px"', 'number')} s
        <span class="hint">(many receivers show a new name only every 1 to 2 s)</span></div></div>
      <div class="onair" id="psPreview"></div>
    </div>
    <div class="rdsSec"><div class="row"><b class="grow">Radio text (RT)</b><span class="seg" id="rtMode">
        <button data-m="one">One text</button><button data-m="loop">Loop of texts</button></span></div>
      <div class="rtOne">${inp('rds.rt', 'maxlength="64" style="width:100%"')}<div class="chars" id="rtChars"></div></div>
      <div class="rtLoop"><ul class="plist ed" id="rtListEd"></ul><button class="ghost small" id="rtAdd">+ add a text</button>
        <span class="hint">each up to 64 characters and shown for its seconds; receivers clear the old one</span></div>
      <div class="onair" id="rtPreview"></div>
    </div>
    <div class="row vars"><span class="hint">Insert:</span>${['{title}', '{artist}', '{song}', '{time}', '{date}', '{freq}', '{station}'].map(v => `<button class="chip" data-var="${v}">${v}</button>`).join('')}</div>
    <p class="rnote">{title} / {artist}: the song heard now ("Artist - Title.wav" gives both), {song}: both, {time} {date}: the board's clock,
    {freq}: the frequency, {station}: the fixed name.</p>
    <div class="rctl">
      <label>Programme type</label><select data-k="rds.pty" data-t="int">${PTY_NAMES.map((n, i) => `<option value="${i}">${i}: ${esc(n)}</option>`).join('')}</select>
      <label>PI code</label><div class="row">${inp('rds.pi', 'maxlength="4" style="width:70px;font-family:var(--mono)"')}<span class="hint">4 hex digits, the station's ID</span></div>
      <label>Flags</label><div class="row">${chk('rds.ct', 'clock time', 'Sends the time and date once a minute: car radios set their clock')}
        ${chk('rds.music', 'music', 'Music (on) or speech (off)')}${chk('rds.tp', 'traffic programme')}${chk('rds.ta', 'traffic announcement now')}</div>
      <label>Other frequencies</label>${inp('rds.af', 'placeholder="(none) for example 98.5, 101.2" data-t="list"')}
      <label>Type name (PTYN)</label><div class="row">${inp('rds.ptyn', 'maxlength="8" style="width:130px;font-family:var(--mono)" placeholder="(none)"')}<span class="hint">your own name for the programme type, 8 characters</span></div>
      <label>Country (ECC)</label><div class="row">${inp('rds.ecc', 'maxlength="2" style="width:50px;font-family:var(--mono)" placeholder="--"')}<span class="hint">2 hex digits: E1 for Greece (with a PI starting with 1); empty = not sent</span></div>
      <label>RT+</label><div class="row">${chk('rds.rtplus', 'mark the title and the artist in the text (car radios show them apart)')}</div>
    </div>
  </div>

  <div class="dcard wide" id="radChainCard"><h3>Sound in and out<span class="grow"></span><span class="hint" id="chainNote"></span></h3>
    <div class="flow" id="chainFlow"></div>
    <div class="chain3">
      <div><div class="ch-t">In <span class="hint">before the processing</span></div>
        <div id="vuIn"></div><canvas class="scope" id="scopeIn"></canvas>
        <div class="kv" id="inStats"></div></div>
      <div><div class="ch-t">Processing <span class="hint">on the board, for songs, pictures and network sound</span></div>
        <div class="rctl">
          <label>Gain</label><div class="row"><input type="range" data-k="process.gain_db" data-t="num" min="-24" max="24" step="0.5" class="grow"><span id="pGainTxt" class="pv"></span></div>
          <label>Balance</label><div class="row"><input type="range" data-k="process.balance" data-t="num" min="-1" max="1" step="0.05" class="grow"><span id="pBalTxt" class="pv"></span></div>
          <label>Channels</label><div class="row">${chk('process.mono', 'mono')}${chk('process.swap', 'swap left and right')}</div>
          <label>AGC</label><div class="row">${chk('process.agc', '', 'An automatic level: quiet sound is brought up, loud sound down, slowly')}<input type="range" data-k="process.agc_target_db" data-t="num" min="-30" max="-6" step="1" class="grow"><span id="pAgcTxt" class="pv"></span></div>
          <label>Limiter</label><div class="row">${chk('process.limiter', '', 'Never louder than the ceiling: no over-modulation')}<input type="range" data-k="process.ceiling_db" data-t="num" min="-12" max="0" step="0.5" class="grow"><span id="pCeilTxt" class="pv"></span></div>
          <label>Delay</label><div class="row"><input type="range" data-k="delay_s" data-t="num" min="0" max="10" step="0.1" class="grow"><span id="pDelayTxt" class="pv"></span></div>
          <label>Bypass</label><div class="row">${chk('process.bypass', 'the sound as it comes (no processing)')}</div>
        </div></div>
      <div><div class="ch-t">Out <span class="hint">after the processing</span></div>
        <div id="vuOut"></div><canvas class="scope" id="scopeOut"></canvas>
        <div class="kv" id="outStats"></div></div>
    </div>
    <canvas class="hist" id="chainHist"></canvas>
    <div class="hint">The last 30 s: the sound coming in (grey) and going out (colour), peaks in dB.</div>
  </div>

  <div class="dcard" id="radFmCard"><h3>FM sound</h3>
    <div class="rctl">
      <label>Stereo</label><div class="row">${chk('fm.stereo', 'stereo (19 kHz pilot, 38 kHz L-R)')}</div>
      <label>Pre-emphasis</label><select data-k="fm.preemph" data-t="int"><option value="50">50 us (Europe, Asia, Australia)</option>
        <option value="75">75 us (Americas, Korea)</option><option value="0">off</option></select>
      <label>Deviation</label><div class="row">${inp('fm.deviation_khz', 'step="0.5" min="1" max="100" style="width:80px"', 'number')} kHz
        <span class="hint">75 broadcast, 5 or 2.5 narrow FM</span></div>
      <label>Shares of the MPX</label><div class="row">sound ${inp('fm.audio', 'step="1" min="0" max="100" style="width:64px" data-t="pct"', 'number')} %
        pilot ${inp('fm.pilot', 'step="1" min="0" max="20" style="width:56px" data-t="pct"', 'number')} %
        RDS ${inp('fm.rds_level', 'step="0.5" min="0" max="10" style="width:56px" data-t="pct"', 'number')} %</div>
    </div>
    <p class="rnote" id="radShareNote"></p>
  </div>

  <div class="dcard" id="radNfmCard"><h3>NFM</h3>
    <div class="rctl"><label>Deviation</label><div class="row">${inp('nfm.deviation_khz', 'step="0.5" min="1" max="10" style="width:70px"', 'number')} kHz
      <span class="hint">5 (25 kHz channels) or 2.5 (12.5 kHz channels)</span></div></div>
    <p class="rnote">Narrow FM is what walkie-talkies and scanners use: mono, the voice band only (300 to 2700 Hz, the same
    256-tap filter as SSB), no pilot and no RDS.</p>
  </div>

  <div class="dcard" id="radSsbCard"><h3>Side band (USB / LSB / DSB)</h3>
    <p class="rnote">The FPGA splits the sound into I and Q with a 256-tap filter pair (the other side band is about 70 dB down),
    then a CORDIC turns I and Q into the carrier's strength and phase, 390625 times a second. The voice band is sent:
    300 to 2700 Hz. Best on short wave (a few MHz): there the pulses are long enough to shape the strength finely.</p>
  </div>

  <div class="dcard" id="radAmCard"><h3>AM</h3>
    <div class="rctl"><label>Depth</label><div class="row"><input type="range" data-k="am.depth" data-t="num" min="0" max="0.98" step="0.01" class="grow"><span id="radDepthTxt" style="width:46px"></span></div>
      <label>Voice filter</label><div class="row">${chk('am.voice', '300 to 2700 Hz (a narrow AM signal)')}</div></div>
    <p class="rnote">The sound changes the strength of the carrier. AM radios: medium wave 531 to 1602 kHz (Europe) or 530 to 1700 kHz
    (Americas), short wave from 2.3 MHz. A long wire works much better there than a short one.</p>
  </div>

  <div class="dcard" id="radDigCard"><h3>Digital modes<span class="grow"></span><button class="small primary" id="radSendNow">Send now</button></h3>
    <div class="rctl">
      <label class="dg dg-cw dg-rtty dg-psk31">Message</label><textarea class="dg dg-cw dg-rtty dg-psk31" data-k="digital.text" rows="3" style="width:100%;font:inherit"></textarea>
      <label class="dg dg-cw">Speed</label><div class="row dg dg-cw">${inp('digital.wpm', 'step="1" min="5" max="60" style="width:64px"', 'number')} words per minute</div>
      <label class="dg dg-rtty">RTTY</label><div class="row dg dg-rtty">${inp('digital.baud', 'step="0.01" min="10" max="300" style="width:80px"', 'number')} baud,
        shift ${inp('digital.shift', 'step="1" min="10" max="1000" style="width:70px"', 'number')} Hz</div>
      <label class="dg dg-beacon">Melody</label><div class="dg dg-beacon">${inp('digital.melody', 'style="width:100%" placeholder="C4 E4 G4 C5*2 - G4"')}
        <div class="hint">notes A4 = 440 Hz, # or b, *2 longer, /2 shorter, - a rest</div></div>
      <label class="dg dg-beacon">Tempo</label><div class="row dg dg-beacon">${inp('digital.tempo', 'step="5" min="30" max="400" style="width:70px"', 'number')} beats per minute</div>
      <label class="dg dg-sweep">Sweep</label><div class="row dg dg-sweep">${inp('digital.sweep_start_khz', 'step="1" style="width:70px"', 'number')} to
        ${inp('digital.sweep_stop_khz', 'step="1" style="width:70px"', 'number')} kHz, step ${inp('digital.sweep_step_khz', 'step="0.1" min="0.01" style="width:60px"', 'number')} kHz,
        ${inp('digital.sweep_dwell_ms', 'step="1" min="1" style="width:60px"', 'number')} ms each</div>
      <label>Offset</label><div class="row">${inp('digital.offset_hz', 'step="10" style="width:90px"', 'number')} Hz from the frequency above</div>
      <label>Repeat</label><div class="row">every ${inp('digital.repeat_s', 'step="1" min="0" style="width:70px"', 'number')} s <span class="hint">(0 = once)</span></div>
    </div>
    <div class="bar" id="radDigProg"><i style="width:0%"></i></div><div class="hint" id="radDigTxt"></div>
    <p class="rnote">Listen with an SDR (RTL-SDR with SDR# or SDR++) in USB mode, about 1 kHz below the frequency, and decode
    RTTY and PSK31 with fldigi. CW: any receiver in CW or SSB mode.</p>
  </div>

  <div class="dcard wide"><h3>How it works</h3>
    <p class="hint">All of it is digital, inside the FPGA: the ARM writes settings, sound samples and RDS data into the block's registers.
    The FPGA filters the sound (15 kHz low-pass, pre-emphasis), builds the stereo multiplex at 390625 samples per second, and moves a
    32-bit carrier synthesizer that runs at 500 million samples per second (250 MHz, two samples per clock). The pin is high for the
    first half of each carrier period: a square wave at the carrier frequency. FM changes the frequency with the MPX signal,
    AM changes the width of the pulses, the digital modes are lists of (frequency, time, strength, phase) steps.
    <a href="#" id="radGuide3">The guide</a> explains every part, the rules and how to listen with an SDR.</p>
  </div>`;
  radioFill();
  radioWire();
}

function radioFill() {
  const c = RAD.cfg;
  $('radBody').querySelectorAll('[data-k]').forEach(el => {
    if (el.dataset.k.startsWith('_')) return;
    let v = getK(c, el.dataset.k);
    if (el.dataset.t === 'pct') v = +(v * 100).toFixed(1);
    if (el.dataset.t === 'list') v = (v || []).join(', ');
    if (el.type === 'checkbox') el.checked = !!v; else el.value = v ?? '';
  });
  radioFormInfo();
}

function radioWire() {
  $('radBody').querySelectorAll('[data-k]').forEach(el => {
    if (el.dataset.k.startsWith('_')) return;
    el.addEventListener('input', () => {
      let v;
      if (el.type === 'checkbox') v = el.checked;
      else if (el.dataset.t === 'pct') v = (+el.value || 0) / 100;
      else if (el.dataset.t === 'list') v = el.value.split(/[ ,;]+/).filter(x => x).map(Number).filter(x => x >= 87.6 && x <= 107.9);
      else if (el.type === 'number' || el.type === 'range' || el.dataset.t === 'num') v = +el.value;
      else if (el.dataset.t === 'int') v = parseInt(el.value, 10);
      else v = el.value;
      if (el.dataset.k === 'rds.pi') { if (!/^[0-9A-Fa-f]{4}$/.test(v)) return; v = v.toUpperCase(); }
      if (el.type === 'number' && !isFinite(v)) return;
      setK(RAD.cfg, el.dataset.k, v);
      radioFormInfo();
      radioSend(el.type === 'text' || el.tagName === 'TEXTAREA' ? 700 : 300);
    });
  });
  $('radOnAir').onclick = () => { RAD.cfg.on = !RAD.cfg.on; radioFormInfo(); radioSend(0); };
  $('radBody').querySelectorAll('[data-step]').forEach(b => b.onclick = () => {
    RAD.cfg.freq_mhz = Math.round((+RAD.cfg.freq_mhz + +b.dataset.step) * 1000) / 1000;
    $('radBody').querySelector('[data-k="freq_mhz"]').value = RAD.cfg.freq_mhz;
    radioFormInfo(); radioSend(250);
  });
  $('radSrc').querySelectorAll('button').forEach(b => b.onclick = () => { RAD.cfg.audio.source = b.dataset.src; radioFormInfo(); radioSend(0); });
  $('radAddWav').onclick = async () => {
    const r = await api('/api/radio/wav', {});
    if (!r.ok) { if (r.out !== 'no file chosen') out(r.out, 'err'); return; }
    RAD.pendingAdd.add(r.name);
    out('Sending ' + r.name + ' to the board: it joins the playlist when it has arrived.', 'head');
  };
  $('radSendNow').onclick = () => { RAD.cfg.digital.id = (RAD.cfg.digital.id || 0) + 1; radioSend(0); };
  $('picFile').onchange = e => { const f = e.target.files[0]; if (f) picLoad(f); };
  $('pcRefresh').onclick = pcDevices;
  $('psMode').querySelectorAll('button').forEach(b => b.onclick = () => { RAD.cfg.rds.ps_mode = b.dataset.m;
    if (b.dataset.m === 'list' && !(RAD.cfg.rds.ps_list || []).length) RAD.cfg.rds.ps_list = [{ text: RAD.cfg.rds.ps, s: 4 }];
    radioFormInfo(); radioSend(200); });
  $('rtMode').querySelectorAll('button').forEach(b => b.onclick = () => {
    if (b.dataset.m === 'loop' && !(RAD.cfg.rds.rt_list || []).length) RAD.cfg.rds.rt_list = [{ text: RAD.cfg.rds.rt, s: 15 }];
    if (b.dataset.m === 'one') RAD.cfg.rds.rt_list = [];
    radioFormInfo(); radioSend(200); });
  $('psAdd').onclick = () => { RAD.cfg.rds.ps_list = [...(RAD.cfg.rds.ps_list || []), { text: '', s: 4 }]; radioFormInfo(); };
  $('rtAdd').onclick = () => { RAD.cfg.rds.rt_list = [...(RAD.cfg.rds.rt_list || []), { text: '', s: 15 }]; radioFormInfo(); };
  $('radRdsCard').addEventListener('focusin', e => { if (e.target.tagName === 'INPUT' && e.target.type === 'text') RAD.lastText = e.target; });
  $('radRdsCard').querySelectorAll('[data-var]').forEach(b => b.onmousedown = e => { e.preventDefault(); insertVar(b.dataset.var); });
  $('pcSend').onclick = async () => {
    const r = await api('/api/aes67/send', { id: +$('pcDev').value });
    if (!r.ok) { out('PC sound not started: ' + (r.out || ''), 'err'); return; }
    pcUse(r.config);
  };
  $('pcStop').onclick = async () => { await api('/api/aes67/stop', {}); pcLive(); };
  $('picText').oninput = () => picDraw();
  $('picSend').onclick = picSend;
  picDraw();
  $('specAuto').checked = RAD.specAuto;
  $('specGo').onclick = () => radioSpectrum();
  $('specAuto').onchange = e => { RAD.specAuto = e.target.checked; if (RAD.specAuto) radioSpectrum(); };
  $('radGuide3').onclick = e => { e.preventDefault(); galleryGuide(RADIO_PROJECT); };
}

function radioSend(delay) {
  clearTimeout(RAD.sendT);
  RAD.sendT = setTimeout(async () => {
    RAD.rev = Math.max(RAD.rev, (RAD.st && RAD.st.rev) || 0) + 1;
    RAD.cfg.rev = RAD.rev;
    RAD.cfg.clock_checked = Date.now() / 1000;          // lets the board trust its clock for RDS clock time
    const cfg = JSON.parse(JSON.stringify(RAD.cfg));
    RAD.cfg.delete = [];
    const r = await api('/api/radio/config', { p: RAD.project, config: cfg });
    if (!r.ok) out('Radio settings not sent: ' + (r.out || ''), 'err');
  }, delay);
}

function radioFormInfo() {
  const c = RAD.cfg, mode = c.mode;
  $('radOnAir').textContent = c.on ? 'ON AIR' : 'OFF AIR';
  $('radOnAir').classList.toggle('on', !!c.on);
  const fv = +c.freq_mhz >= 1 ? (+c.freq_mhz).toFixed(+c.freq_mhz >= 100 ? 2 : 3) : (c.freq_mhz * 1000).toFixed(1);
  const fd = fv.padStart(7, ' ');                     // LED digits: the unlit segments show behind (8.8.8)
  $('radFreqBig').innerHTML = `<span class="seg7"><span class="ghost">${fd.replace(/[0-9 ]/g, '8')}</span><span class="lit">${fd.replace(/ /g, '&nbsp;')}</span></span>`
    + `<small>${+c.freq_mhz >= 1 ? 'MHz' : 'kHz'}</small>`;
  $('radFreqBig').classList.toggle('on', !!c.on);
  $('radModeTxt').textContent = (RMODES.find(m => m[0] === mode) || ['', mode])[1];
  $('radPowTxt').textContent = pct(c.power);
  $('radVolTxt').textContent = 'x' + (+c.audio.volume).toFixed(2);
  $('radDepthTxt').textContent = pct(c.am.depth);
  const f = +c.freq_mhz;
  $('radBandHint').textContent = mode === 'fm' && (f < 87.5 || f > 108) ? 'outside the FM band (87.5 to 108 MHz): an FM radio will not hear it'
    : (mode === 'am' || ['usb', 'lsb', 'dsb'].includes(mode)) && f > 30 ? 'this mode is meant for medium and short wave (below 30 MHz)' : '';
  $('radSrc').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.src === c.audio.source));
  document.querySelectorAll('#radAudioCard .srcTones').forEach(e => e.style.display = c.audio.source === 'tones' ? '' : 'none');
  $('radAudioCard').querySelector('.srcList').style.display = c.audio.source === 'playlist' ? '' : 'none';
  $('radAudioCard').querySelector('.srcPic').style.display = c.audio.source === 'sstv' ? '' : 'none';
  $('radAudioCard').querySelector('.srcNet').style.display = c.audio.source === 'network' ? '' : 'none';
  $('radListen').textContent = LISTEN[mode] ? 'Listen: ' + LISTEN[mode] : '';
  const dig = DIGITAL_MODES.includes(mode);
  $('radAudioCard').style.display = SOUND_MODES.includes(mode) ? '' : 'none';
  $('radNfmCard').style.display = mode === 'nfm' ? '' : 'none';
  $('radSsbCard').style.display = ['usb', 'lsb', 'dsb'].includes(mode) ? '' : 'none';
  $('radRdsCard').style.display = mode === 'fm' ? '' : 'none';
  $('radChainCard').style.display = SOUND_MODES.includes(mode) ? '' : 'none';
  rdsEditors();
  chainTexts();
  $('radFmCard').style.display = mode === 'fm' ? '' : 'none';
  $('radAmCard').style.display = mode === 'am' ? '' : 'none';
  $('radDigCard').style.display = dig ? '' : 'none';
  document.querySelectorAll('#radDigCard .dg').forEach(e => e.style.display = e.classList.contains('dg-' + mode) ? '' : 'none');
  $('psChars').textContent = (c.rds.ps || '').length + ' of 8';
  $('rtChars').textContent = (c.rds.rt || '').length + ' of 64';
  const tot = c.fm.audio + (c.fm.stereo ? c.fm.pilot : 0) + (c.rds.on ? c.fm.rds_level : 0);
  $('radShareNote').textContent = `Together ${pct(tot)} of the deviation at the loudest moment` +
    (tot > 1.0 ? ': above 100 %, the signal gets wider than a channel. Lower the sound share.' : '.');
  radioPlaylist();
}

function radioPlaylist() {
  const c = RAD.cfg, st = RAD.st || {};
  const pl = c.audio.playlist || [];
  $('radPlaylist').innerHTML = pl.map((n, i) => `<li class="${st.track === n ? 'now' : ''}"><span class="grow">${i + 1}. ${esc(n)}</span>
      <button class="ghost" data-up="${i}" title="earlier">&uarr;</button><button class="ghost" data-down="${i}" title="later">&darr;</button>
      <button class="ghost" data-rm="${i}" title="take out of the playlist">&times;</button></li>`).join('') ||
    '<li><span class="hint">Empty: add songs from the list below.</span></li>';
  const files = st.files || [];
  $('radFiles').innerHTML = files.map(n => `<li><span class="grow">${esc(n)}</span>
      <button class="ghost" data-add="${esc(n)}" title="add to the playlist">+ play</button>
      <button class="ghost" data-del="${esc(n)}" title="delete from the board">delete</button></li>`).join('') ||
    '<li><span class="hint">No songs on the board yet.</span></li>';
  const swap = (i, j) => { if (j < 0 || j >= pl.length) return; [pl[i], pl[j]] = [pl[j], pl[i]]; radioPlaylist(); radioSend(200); };
  $('radPlaylist').querySelectorAll('[data-up]').forEach(b => b.onclick = () => swap(+b.dataset.up, +b.dataset.up - 1));
  $('radPlaylist').querySelectorAll('[data-down]').forEach(b => b.onclick = () => swap(+b.dataset.down, +b.dataset.down + 1));
  $('radPlaylist').querySelectorAll('[data-rm]').forEach(b => b.onclick = () => { pl.splice(+b.dataset.rm, 1); radioPlaylist(); radioSend(200); });
  $('radFiles').querySelectorAll('[data-add]').forEach(b => b.onclick = () => { pl.push(b.dataset.add); c.audio.playlist = pl; radioPlaylist(); radioSend(200); });
  $('radFiles').querySelectorAll('[data-del]').forEach(b => b.onclick = () => {
    if (!confirm('Delete ' + b.dataset.del + ' from the board?')) return;
    c.audio.playlist = pl.filter(x => x !== b.dataset.del);
    c.delete = [b.dataset.del];
    radioPlaylist(); radioSend(0);
  });
}

function radioLive() {
  const st = RAD.st, c = RAD.cfg;
  if (!st) return;
  const pending = (c.rev || 0) > (st.rev || 0);
  $('radState').textContent = (st.error ? 'problem: ' + st.error : pending ? 'sending settings ...' : 'radio service running') +
    (st.on ? '' : ', transmitter off');
  const meas = st.rf_hz ? (st.rf_hz / 1e6).toFixed(st.rf_hz >= 1e8 ? 4 : 5) + ' MHz' : (st.on ? 'no carrier' : 'off');
  const low = st.power_used != null && Math.abs(st.power_used - c.power) > 0.005 && c.power > 0;
  $('radPowTxt').textContent = pct(low ? st.power_used : c.power);
  $('radPowNote').textContent = low ? `Power ${pct(st.power_used)}: the lowest clean power at this frequency.` : '';
  $('radFacts').innerHTML = `<span>At the pin</span><span>${meas}${st.rf_hz > 125e6 ? ' (above 125 MHz the counter cannot follow)' : ''}</span>
    <span>RF clock</span><span>${st.locked ? '250 MHz, locked' : 'NOT locked'}</span>
    <span>Mode</span><span>${esc(st.mode)}</span>`;
  $('radFacts2').innerHTML = `<span>Sound buffer</span><span>${st.audio_fifo} samples</span>
    <span>Gaps</span><span>${st.underruns_per_s && c.audio.source === 'playlist' && st.track ? st.underruns_per_s + ' samples/s' : 'none'}</span>
    <span>Settings</span><span>${pending ? 'sending' : 'applied (' + (st.rev ?? '-') + ')'}</span>`;
  csStatus(st);
  chainLive(st);
  rdsLive(st);
  $('radNow').textContent = st.track ? 'Playing: ' + st.track : 'Nothing playing';
  $('radPos').textContent = st.track ? fmtS(st.track_pos_s) + ' / ' + fmtS(st.track_len_s) : '';
  $('radProg').querySelector('i').style.width = st.track && st.track_len_s ? Math.min(100, 100 * st.track_pos_s / st.track_len_s) + '%' : '0%';
  const seen = st.rds_seen || {};
  $('lcdPs').textContent = c.rds.on && st.mode === 'fm' ? (seen.ps || '        ') : 'RDS off ';
  $('lcdRt').textContent = c.rds.on && st.mode === 'fm' ? (seen.rt || '') : '';
  $('lcdPty').textContent = seen.pty != null ? PTY_NAMES[seen.pty] : '';
  $('lcdCt').textContent = seen.ct ? 'clock ' + seen.ct : '';
  $('lcdPi').textContent = seen.pi ? 'PI ' + seen.pi + ', ' + seen.groups + ' groups' : '';
  // songs that finished arriving join the playlist
  for (const n of [...RAD.pendingAdd]) if ((st.files || []).includes(n)) {
    RAD.pendingAdd.delete(n);
    c.audio.playlist = [...(c.audio.playlist || []), n];
    if (c.audio.source !== 'playlist') c.audio.source = 'playlist';
    radioFormInfo(); radioSend(0);
  }
  radioPlaylistLive();
  const net = st.network;
  if (c.audio.source === 'network') pcLive();
  if (net && c.audio.source === 'network') {
    const key = x => x.address + ':' + x.port;
    const list = net.streams || [];
    const sig = list.map(key).join('|') + '#' + c.network.stream;
    if ($('netList').dataset.sig !== sig) {
      $('netList').dataset.sig = sig;
      $('netList').innerHTML = list.map(x => `<li class="${c.network.stream === key(x) ? 'now' : ''}"><span class="grow">${esc(x.name || '(no name)')}
        <span class="hint">${esc(key(x))}, ${esc(x.encoding)}/${x.rate}/${x.channels}, from ${esc(x.from)}</span></span>
        <button class="ghost" data-net="${esc(key(x))}">${c.network.stream === key(x) ? 'playing' : 'play'}</button></li>`).join('') +
        `<li class="${c.network.stream ? '' : 'now'}"><span class="grow">By hand (the address below)</span><button class="ghost" data-net="">${c.network.stream ? 'use' : 'in use'}</button></li>`;
      $('netList').querySelectorAll('[data-net]').forEach(b => b.onclick = () => { c.network.stream = b.dataset.net; $('netList').dataset.sig = ''; radioSend(0); });
    }
    $('netCount').textContent = list.length ? list.length + ' found' : 'none announced yet (listening)';
    const rv = net.receiver;
    $('netState').innerHTML = rv ? [['Stream', `${esc(rv.address)}:${rv.port} ${esc(rv.format)}`], ['Receiving', rv.receiving ? `yes, from ${esc(rv.from)}` : 'no packets'],
      ['Packets', `${rv.packets_per_s} per second, ${rv.lost} lost, ${rv.late} late`], ['Buffer', rv.buffer_ms + ' ms'],
      ['Clock follow', (rv.rate_adjust_ppm >= 0 ? '+' : '') + rv.rate_adjust_ppm + ' ppm']].map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join('')
      : `<span>Receiver</span><span>${esc(net.error || 'not started (switch the transmitter on)')}</span>`;
  }
  const pic = st.picture;
  if (!pic && c.audio.source === 'sstv') $('picState').textContent = 'choose a picture (or keep the test picture) and press Send this picture';
  if (pic) {
    $('picProg').querySelector('i').style.width = pic.sending && pic.len_s ? Math.min(100, 100 * pic.pos_s / pic.len_s) + '%' : '0%';
    $('picState').textContent = pic.sending ? `sending: SSTV ${pic.mode}, ${fmtS(pic.pos_s)} of ${fmtS(pic.len_s)}`
      : pic.next_in_s != null ? `sent; again in ${pic.next_in_s} s` : pic.have_image ? 'sent (press Send this picture to send it again)'
      : 'no picture on the board yet: choose one and press Send this picture (until then the test picture is sent)';
  }
  const d = st.digital;
  if (d) {
    $('radDigProg').querySelector('i').style.width = (d.length_s ? 100 * (1 - d.left_s / d.length_s) : 0).toFixed(1) + '%';
    $('radDigTxt').textContent = d.busy ? `sending: ${d.length_s} s message, about ${d.left_s} s still to queue`
      : d.next_in_s != null ? `sent; again in ${d.next_in_s} s` : 'sent (press Send now to send it again)';
  }
  if (RAD.specAuto && Date.now() - RAD.lastSpec > 1200 && !document.hidden) radioSpectrum();
}

function radioPlaylistLive() {
  const st = RAD.st || {};
  $('radPlaylist').querySelectorAll('li').forEach((li, i) => li.classList.toggle('now', (RAD.cfg.audio.playlist || [])[i] === st.track));
  const have = [...$('radFiles').querySelectorAll('[data-add]')].map(b => b.dataset.add).join('|');
  if (have !== (st.files || []).join('|')) radioPlaylist();
}

/* ---------------------------------------------------------------- MPX spectrum */
function fftMag(x) {
  const n = x.length, re = new Float64Array(n), im = new Float64Array(n);
  for (let i = 0; i < n; i++) re[i] = x[i] * (0.5 - 0.5 * Math.cos(2 * Math.PI * i / (n - 1)));
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { [re[i], re[j]] = [re[j], re[i]]; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = -2 * Math.PI / len, wr = Math.cos(ang), wi = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0;
      for (let k = 0; k < len / 2; k++) {
        const a = i + k, b = a + len / 2;
        const tr = re[b] * cr - im[b] * ci, ti = re[b] * ci + im[b] * cr;
        re[b] = re[a] - tr; im[b] = im[a] - ti; re[a] += tr; im[a] += ti;
        const t = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = t;
      }
    }
  }
  const m = new Float64Array(n / 2);
  for (let i = 0; i < n / 2; i++) m[i] = Math.hypot(re[i], im[i]) / (n / 4) / 32767;
  return m;
}

async function radioSpectrum() {
  if (RAD.specBusy) return;
  RAD.specBusy = true;
  RAD.lastSpec = Date.now();
  try {
    const id = Date.now() % 1e9;
    const q = await api('/api/radio/capture', { p: RAD.project, id });
    if (!q.ok) return;
    let m = null;
    for (let i = 0; i < 25 && BV.view === 'radio'; i++) {
      await new Promise(r => setTimeout(r, 300));
      const r = await api('/api/radio/mpx?p=' + encodeURIComponent(RAD.project));
      if (r.ok && r.mpx && r.mpx.id === id) { m = r.mpx; break; }
    }
    if (m) drawSpectrum(m);
    else $('specInfo').textContent = 'No capture came back (is the radio service running?).';
  } finally { RAD.specBusy = false; RAD.lastSpec = Date.now(); }
}

function drawSpectrum(m) {
  const mag = fftMag(m.samples), fs = m.fs, n = m.samples.length;
  const at = f => 20 * Math.log10(Math.max(...[-2, -1, 0, 1, 2].map(k => mag[Math.round(f * n / fs) + k])) + 1e-12);
  const pilot = RAD.st && RAD.st.mode === 'fm' && RAD.cfg.fm.stereo ? at(19000) : null;
  csSpectrum(mag, fs, n, pilot);
  $('specInfo').textContent = (pilot != null ? `Pilot ${pilot.toFixed(1)} dB (9 % = -20.9 dB). ` : '') +
    `0 dB = a sine at full deviation. Green: now, amber: the peaks of the last seconds; the waterfall below shows the last minute. ` +
    `${new Date().toLocaleTimeString()}, 4096 samples at 390625 per second.`;
}

window.radioShow = radioShow;
$('radGuide').onclick = () => galleryGuide(RADIO_PROJECT);
$('radBack').onclick = () => showView('gallery');
$('radBoot').onchange = async e => {
  const r = await bpost('/api/default?p=' + (e.target.checked ? RAD.project : ''));
  out(e.target.checked ? 'The radio now starts at every power-on (with its last settings).' : 'The radio no longer starts at power-on.', r.ok === false ? 'err' : 'ok');
  if (S.status) S.status.default = e.target.checked ? RAD.project : null;
};
$('radUpload').onclick = async () => { const r = await api('/api/gallery/upload', { name: RADIO_PROJECT }); if (!r.ok) out(r.out || 'busy', 'err'); };
$('radTest').onclick = async () => {
  if (!confirm('The self-test sends for a few seconds on 27.12 and 40.68 MHz (no antenna needed) and replaces the radio program until you press Upload and run again. Run it?')) return;
  const r = await api('/api/gallery/upload', { name: RADIO_PROJECT, test: true });
  if (!r.ok) out(r.out || 'busy', 'err'); else showTab('monitor');
};

/* ---------------------------------------------------------------- pictures (SSTV) */
RAD.picImg = null;
function picLoad(file) {
  const img = new Image();
  img.onload = () => { RAD.picImg = img; picDraw(); };
  img.src = URL.createObjectURL(file);
}
function picDraw() {
  const cv = $('picCanvas');
  if (!cv) return;
  const g = cv.getContext('2d');
  g.fillStyle = '#000'; g.fillRect(0, 0, 320, 256);
  if (RAD.picImg) {                                  // fill the 320 x 256 frame, cut what is left over
    const im = RAD.picImg, k = Math.max(320 / im.width, 256 / im.height);
    const w = im.width * k, h = im.height * k;
    g.drawImage(im, (320 - w) / 2, (256 - h) / 2, w, h);
  } else {                                           // the test picture: colour bars and a grey ramp
    const bars = ['#fff', '#ff0', '#0ff', '#0f0', '#f0f', '#f00', '#00f', '#000'];
    bars.forEach((c, i) => { g.fillStyle = c; g.fillRect(i * 40, 0, 40, 160); });
    const grad = g.createLinearGradient(0, 0, 320, 0); grad.addColorStop(0, '#000'); grad.addColorStop(1, '#fff');
    g.fillStyle = grad; g.fillRect(0, 160, 320, 96);
  }
  const t = ($('picText') && $('picText').value || '').trim();
  if (t) {
    g.font = 'bold 26px Segoe UI, sans-serif'; g.textAlign = 'center';
    g.lineWidth = 5; g.strokeStyle = '#000'; g.strokeText(t, 160, 240);
    g.fillStyle = '#fff'; g.fillText(t, 160, 240);
  }
}
async function picSend() {
  picDraw();
  const px = $('picCanvas').getContext('2d').getImageData(0, 0, 320, 256).data;
  const rgb = new Uint8Array(320 * 256 * 3);
  for (let i = 0, j = 0; i < px.length; i += 4) { rgb[j++] = px[i]; rgb[j++] = px[i + 1]; rgb[j++] = px[i + 2]; }
  let bin = '';
  for (let i = 0; i < rgb.length; i += 0x8000) bin += String.fromCharCode.apply(null, rgb.subarray(i, i + 0x8000));
  const r = await api('/api/radio/image', { p: RAD.project, rgb: btoa(bin) });
  if (!r.ok) { out('Picture not sent: ' + (r.out || ''), 'err'); return; }
  RAD.cfg.audio.source = 'sstv';
  RAD.cfg.sstv.id = (RAD.cfg.sstv.id || 0) + 1;
  radioFormInfo(); radioSend(0);
  out('Picture sent to the board: it goes on air now (SSTV ' + RAD.cfg.sstv.mode + ').', 'ok');
}

/* ---------------------------------------------------------------- network sound from this PC */
RAD.pcDevs = null;
async function pcDevices() {
  const r = await api('/api/aes67/devices');
  if (!r.ok) { $('pcDev').innerHTML = `<option>${esc(r.out || 'no sound devices')}</option>`; return; }
  RAD.pcDevs = r.devices;
  $('pcDev').innerHTML = r.devices.map(d => `<option value="${d.id}">${d.kind === 'loopback' ? 'Everything this PC plays on: ' : 'Input: '}${esc(d.name)}${d.default ? ' (Windows default)' : ''} (${d.rate} Hz)</option>`).join('');
}
function pcUse(cfg) {
  RAD.cfg.audio.source = 'network';
  Object.assign(RAD.cfg.network, cfg);
  $('netList').dataset.sig = '';
  radioFormInfo(); radioSend(0);
}
async function pcLive() {
  if (RAD.pcBusy) return;
  RAD.pcBusy = true;
  try {
    if (!RAD.pcDevs) await pcDevices();
    const r = await api('/api/aes67/state');
    if (!r.ok) return;
    const a = r.active;
    $('pcState').innerHTML = a ? [['Sending', `${esc(a.device)}, ${esc(a.format)}`],
      ['Now', a.sending ? `${a.packets} packets sent` + (a.level != null ? `, level ${a.level > 0.0005 ? (20 * Math.log10(a.level)).toFixed(1) + ' dB' : 'silent'}` : '') + (a.from ? ', from ' + esc(a.from) : '')
        : (a.kind === 'relay' ? 'waiting for the stream' : 'waiting for sound')],
      ['To', esc(a.to)]].concat(a.error ? [['Problem', esc(a.error)]] : []).map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join('')
      : '<span>Sending</span><span>nothing from this PC</span>';
    const heard = r.heard || [];
    $('pcHeardCount').textContent = heard.length ? heard.length + ' found' : 'none announced (listening on every network card)';
    const sig = heard.map(x => x.address + ':' + x.port).join('|');
    if ($('pcHeard').dataset.sig !== sig) {
      $('pcHeard').dataset.sig = sig;
      $('pcHeard').innerHTML = heard.map((x, i) => `<li><span class="grow">${esc(x.name || '(no name)')} <span class="hint">${esc(x.address)}:${x.port},
        ${esc(x.encoding)}/${x.rate}/${x.channels}, from ${esc(x.from)}</span></span><button class="ghost" data-relay="${i}">pass on to the radio</button></li>`).join('')
        || '<li><span class="hint">AES67 programs that announce themselves (SAP) appear here.</span></li>';
      $('pcHeard').querySelectorAll('[data-relay]').forEach(b => b.onclick = async () => {
        const x = heard[+b.dataset.relay];
        const rr = await api('/api/aes67/relay', { stream: x });
        if (!rr.ok) { out('Not passed on: ' + (rr.out || ''), 'err'); return; }
        pcUse(rr.config);
      });
    }
  } finally { RAD.pcBusy = false; }
}

/* ---------------------------------------------------------------- the RDS editor */
function insertVar(v) {
  const el = RAD.lastText && document.body.contains(RAD.lastText) ? RAD.lastText : $('radBody').querySelector('[data-k="rds.rt"]');
  const a = el.selectionStart ?? el.value.length, b = el.selectionEnd ?? el.value.length;
  el.value = el.value.slice(0, a) + v + el.value.slice(b);
  el.focus(); el.setSelectionRange(a + v.length, a + v.length);
  el.dispatchEvent(new Event('input'));
}
function listEditor(ul, key, maxlen, mono) {
  const list = RAD.cfg.rds[key] || [];
  if (ul.dataset.sig === JSON.stringify(list) && ul.contains(document.activeElement)) return;
  ul.dataset.sig = JSON.stringify(list);
  ul.innerHTML = list.map((x, i) => `<li><span class="hint">${i + 1}</span>
    <input class="grow lt" maxlength="${maxlen}" value="${esc(x.text)}" style="${mono ? 'font-family:var(--mono);' : ''}min-width:0" spellcheck="false">
    <input class="ls" type="number" min="0.3" step="0.5" value="${x.s}" style="width:62px" title="seconds"> s
    <button class="ghost" data-up="${i}">&uarr;</button><button class="ghost" data-down="${i}">&darr;</button><button class="ghost" data-rm="${i}">&times;</button></li>`).join('')
    || '<li><span class="hint">empty: add one below</span></li>';
  const save = d => { RAD.cfg.rds[key] = list; ul.dataset.sig = JSON.stringify(list); radioSend(d); };
  ul.querySelectorAll('li').forEach((li, i) => {
    const t = li.querySelector('.lt'), n = li.querySelector('.ls');
    if (t) t.oninput = () => { list[i].text = t.value; save(700); };
    if (n) n.oninput = () => { if (+n.value > 0) { list[i].s = +n.value; save(700); } };
  });
  const move = (i, j) => { if (j < 0 || j >= list.length) return; [list[i], list[j]] = [list[j], list[i]]; ul.dataset.sig = ''; save(200); rdsEditors(); };
  ul.querySelectorAll('[data-up]').forEach(b => b.onclick = () => move(+b.dataset.up, +b.dataset.up - 1));
  ul.querySelectorAll('[data-down]').forEach(b => b.onclick = () => move(+b.dataset.down, +b.dataset.down + 1));
  ul.querySelectorAll('[data-rm]').forEach(b => b.onclick = () => { list.splice(+b.dataset.rm, 1); ul.dataset.sig = ''; save(200); rdsEditors(); });
}
function rdsEditors() {
  const rd = RAD.cfg.rds, m = rd.ps_mode || 'fixed', loop = (rd.rt_list || []).length > 0;
  $('psMode').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.m === m));
  $('rtMode').querySelectorAll('button').forEach(b => b.classList.toggle('on', (b.dataset.m === 'loop') === loop));
  document.querySelector('#radRdsCard .psFixed').style.display = m === 'fixed' ? '' : 'none';
  document.querySelector('#radRdsCard .psList').style.display = m === 'list' ? '' : 'none';
  document.querySelector('#radRdsCard .psScroll').style.display = m === 'scroll' || m === 'words' ? '' : 'none';
  document.querySelector('#radRdsCard .rtOne').style.display = loop ? 'none' : '';
  document.querySelector('#radRdsCard .rtLoop').style.display = loop ? '' : 'none';
  if (m === 'list') listEditor($('psListEd'), 'ps_list', 8, true);
  if (loop) listEditor($('rtListEd'), 'rt_list', 64, false);
}
function rdsLive(st) {
  const a = st.rds_on_air || {}, seen = st.rds_seen || {};
  const fr = a.ps_frames || [];
  $('psPreview').innerHTML = fr.length > 1
    ? `On air: <code>${esc(a.ps)}</code>, next in ${a.ps_next_s ?? '-'} s. Frames: ` + fr.slice(0, 24).map((f, i) => `<code class="${i === a.ps_i ? 'now' : ''}">${esc(f).replace(/ /g, '&nbsp;')}</code>`).join(' ')
    : `On air: <code>${esc(a.ps || '')}</code>`;
  const it = a.rt_items || [];
  $('rtPreview').innerHTML = (it.length > 1 ? `Text ${a.rt_i + 1} of ${it.length}, next in ${a.rt_next_s ?? '-'} s: ` : 'On air: ') + `<b>${esc(a.rt || '(no text)')}</b>`
    + ((a.rtplus || []).length ? ' &middot; RT+: ' + a.rtplus.map(t => `${t[0] === 1 ? 'title' : 'artist'} "${esc((a.rt || '').substr(t[1], t[2]))}"`).join(', ') : '');
  const ex = [];
  if (seen.ptyn) ex.push('PTYN ' + seen.ptyn.trim());
  if (seen.ecc) ex.push('ECC ' + seen.ecc);
  if (seen.rtplus) ex.push('RT+ ' + Object.entries(seen.rtplus).map(([k, v]) => k + ': ' + v).join(', '));
  $('lcdPty').textContent = (seen.pty != null ? PTY_NAMES[seen.pty] : '') + (ex.length ? ' | ' + ex.join(' | ') : '');
}

/* ---------------------------------------------------------------- the sound panel */
RAD.hist = []; RAD.hold = { in: [[-100, 0], [-100, 0]], out: [[-100, 0], [-100, 0]] };
const dbw = d => Math.max(0, Math.min(100, (d + 60) / 60 * 100));
function vu(el, kind, peak, rms) {
  if (!el.dataset.built) {
    el.dataset.built = 1;
    el.innerHTML = ['L', 'R'].map(c => `<div class="vu"><span>${c}</span><div class="vub"><i class="rms"></i><i class="pk"></i><i class="hold"></i></div><span class="vut"></span></div>`).join('');
  }
  const now = Date.now();
  el.querySelectorAll('.vu').forEach((row, c) => {
    const h = RAD.hold[kind][c];
    if (peak[c] >= h[0] || now - h[1] > 2000) { h[0] = peak[c]; h[1] = now; }
    row.querySelector('.rms').style.width = dbw(rms[c]) + '%';
    row.querySelector('.pk').style.width = dbw(peak[c]) + '%';
    row.querySelector('.hold').style.left = dbw(h[0]) + '%';
    row.querySelector('.vub').classList.toggle('hot', peak[c] > -1);
    row.querySelector('.vut').textContent = peak[c] > -99 ? peak[c].toFixed(1) : '-';
  });
}
function scope(cv, data) {
  const W = cv.clientWidth, H = cv.clientHeight, dpr = window.devicePixelRatio || 1;
  if (!W) return;
  cv.width = W * dpr; cv.height = H * dpr;
  const g = cv.getContext('2d'); g.scale(dpr, dpr);
  const css = getComputedStyle(document.body);
  g.strokeStyle = css.getPropertyValue('--line'); g.beginPath(); g.moveTo(0, H / 2); g.lineTo(W, H / 2); g.stroke();
  (data || []).forEach((ch, k) => {
    g.strokeStyle = k ? '#e0884f' : css.getPropertyValue('--accent'); g.lineWidth = 1.2; g.beginPath();
    ch.forEach((v, i) => { const x = i / (ch.length - 1) * W, y = H / 2 - v / 100 * (H / 2 - 2); i ? g.lineTo(x, y) : g.moveTo(x, y); });
    g.stroke();
  });
}
function histDraw() {
  const cv = $('chainHist'), W = cv.clientWidth, H = cv.clientHeight, dpr = window.devicePixelRatio || 1;
  if (!W) return;
  cv.width = W * dpr; cv.height = H * dpr;
  const g = cv.getContext('2d'); g.scale(dpr, dpr);
  const css = getComputedStyle(document.body), y = d => H - 4 - dbw(d) / 100 * (H - 8);
  g.fillStyle = css.getPropertyValue('--muted'); g.font = '10px Segoe UI, sans-serif';
  [0, -20, -40].forEach(d => { g.strokeStyle = css.getPropertyValue('--line'); g.beginPath(); g.moveTo(28, y(d)); g.lineTo(W, y(d)); g.stroke(); g.fillText(d + ' dB', 0, y(d) + 3); });
  const now = Date.now() / 1000, x = t => 28 + (W - 28) * (1 - (now - t) / 30);
  [[1, '#8a8f94'], [2, css.getPropertyValue('--accent')]].forEach(([k, col]) => {
    g.strokeStyle = col; g.lineWidth = 1.3; g.beginPath();
    RAD.hist.forEach((h, i) => { i ? g.lineTo(x(h[0]), y(h[k])) : g.moveTo(x(h[0]), y(h[k])); });
    g.stroke();
  });
}
function chainTexts() {
  const p = RAD.cfg.process || {}, sg = v => (v > 0 ? '+' : '') + (+v).toFixed(1) + ' dB';
  $('pGainTxt').textContent = sg(p.gain_db || 0);
  $('pBalTxt').textContent = Math.abs(p.balance || 0) < 0.01 ? 'middle' : (p.balance < 0 ? 'L ' : 'R ') + Math.round(Math.abs(p.balance) * 100) + ' %';
  $('pAgcTxt').textContent = (p.agc_target_db ?? -16) + ' dB';
  $('pCeilTxt').textContent = (p.ceiling_db ?? -1) + ' dB';
  $('pDelayTxt').textContent = (+RAD.cfg.delay_s || 0).toFixed(1) + ' s';
  $('netBufTxt').textContent = (RAD.cfg.network.buffer_ms ?? 150) + ' ms';
}
function chainLive(st) {
  const ch = st.chain, c = RAD.cfg;
  if (!ch || $('radChainCard').style.display === 'none') return;
  const src = c.audio.source;
  $('chainNote').textContent = src === 'tones' ? 'the test tones are made in the FPGA: they do not pass the processing'
    : src === 'silence' ? 'silence' : ch.filling ? `filling the delay: ${ch.delay_now_s} of ${ch.delay_set_s} s` : '';
  if (ch.active && ch.samples) { vu($('vuIn'), 'in', ch.in_peak, ch.in_rms); vu($('vuOut'), 'out', ch.out_peak, ch.out_rms); }
  else { vu($('vuIn'), 'in', [-100, -100], [-100, -100]); vu($('vuOut'), 'out', [-100, -100], [-100, -100]); }
  if (ch.scope) { scope($('scopeIn'), ch.scope.in); scope($('scopeOut'), ch.scope.out); }
  (ch.history || []).forEach(h => RAD.hist.push(h));
  const t0 = Date.now() / 1000 - 30;
  while (RAD.hist.length && RAD.hist[0][0] < t0) RAD.hist.shift();
  histDraw();
  const rv = (st.network || {}).receiver;
  $('inStats').innerHTML = `<span>Source</span><span>${esc(st.track || (src === 'tones' ? 'test tones (FPGA)' : src))}</span>`
    + (rv ? `<span>Network</span><span>${rv.packets_per_s} packets/s, ${rv.lost} lost, ${rv.late} late</span><span>Buffer</span><span>${rv.buffer_ms} ms (set ${c.network.buffer_ms ?? 150})</span>` : '');
  const gaps = st.gaps;
  $('outStats').innerHTML = `<span>Limiter</span><span>${ch.limiter_db < -0.05 ? ch.limiter_db.toFixed(1) + ' dB' : 'not working (below the ceiling)'}</span>`
    + (c.process.agc ? `<span>AGC</span><span>${ch.agc_db > 0 ? '+' : ''}${ch.agc_db.toFixed(1)} dB</span>` : '')
    + `<span>Delay</span><span>${ch.delay_now_s} s now</span>`
    + (st.deviation_khz != null ? `<span>Deviation</span><span>${st.deviation_khz} kHz peak</span>` : '')
    + `<span>Clicks</span><span class="${gaps ? 'bad' : ''}">${gaps == null ? '-' : gaps === 0 ? 'none (no gaps in the sound)' : gaps + ' samples missing since the start'}</span>`;
  const box = (t, v, cls) => `<div class="fb ${cls || ''}"><b>${t}</b><span>${v}</span></div>`;
  const ar = '<span class="fa">&rarr;</span>';
  const pr = c.process, byp = pr.bypass;
  const dev = c.mode === 'nfm' ? c.nfm.deviation_khz : c.fm.deviation_khz;
  $('chainFlow').innerHTML = [
    box('Source', esc((st.track || src).replace(/^network: /, ''))),
    box('In', ch.active ? Math.max(...ch.in_peak).toFixed(1) + ' dB' : '-'),
    box('Gain', byp ? 'off' : (pr.gain_db > 0 ? '+' : '') + pr.gain_db + ' dB', byp ? 'off' : ''),
    box('AGC', !byp && pr.agc ? (ch.agc_db > 0 ? '+' : '') + ch.agc_db.toFixed(1) + ' dB' : 'off', !byp && pr.agc ? '' : 'off'),
    box('Limiter', !byp && pr.limiter ? pr.ceiling_db + ' dB' : 'off', !byp && pr.limiter ? '' : 'off'),
    box('Delay', ch.delay_set_s > 0 ? ch.delay_set_s + ' s' : 'none', ch.delay_set_s > 0 ? '' : 'off'),
    box('Out', ch.active ? Math.max(...ch.out_peak).toFixed(1) + ' dB' : '-'),
    box('FPGA', c.mode === 'fm' ? `${c.fm.preemph ? c.fm.preemph + ' us, ' : ''}15 kHz, ${c.fm.stereo ? 'stereo' : 'mono'}` : c.mode.toUpperCase()),
    box(c.mode === 'fm' || c.mode === 'nfm' ? 'FM' : c.mode.toUpperCase(), st.deviation_khz != null ? st.deviation_khz + ' / ' + dev + ' kHz' : ''),
    box('Pin', st.on ? (+c.freq_mhz).toFixed(3) + ' MHz' : 'off air', st.on ? 'air' : 'off'),
  ].join(ar);
}
