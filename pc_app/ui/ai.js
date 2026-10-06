/* Ardzy - AI view: project 16_digit_ai, a neural network in the FPGA that reads handwritten digits.
   The board runs the project's main.py (it serves /state, /guess and /example on port 8080); the engine passes
   the calls on (/api/ai/...), so this works over an IPv6 link-local cable too.
   Helpers from app.js / board.js: $, esc, api, out, S, T, TF, showView, showTab, galleryGuide. */
const AI = { timer: null, st: null, built: false, drawing: false, last: null, busy: false, again: false,
  hist: [], cur: null, pen: 20, tally: { right: 0, wrong: 0 } };
const AI_PROJECT = '16_digit_ai';
try { Object.assign(AI.tally, JSON.parse(localStorage.getItem('ardzy.ai.tally') || '{}')); } catch (e) { /* no storage */ }

function aiShow() {
  if (!AI.built) aiBuild();
  aiPoll().then(() => {             // a link like #view=ai&example=1 opens with one of the test digits drawn
    if (/example=1/.test(location.hash) && AI.st && AI.st.ok && !AI.cur) $('aiExample').click();
  });
}
function aiLeave() { clearTimeout(AI.timer); }

async function aiPoll() {
  clearTimeout(AI.timer);
  const r = S.connected ? await api('/api/ai/state') : { ok: false };
  AI.st = r;
  const running = !!r.ok;
  $('aiOff').hidden = running;
  $('aiMain').classList.toggle('dim', !running);
  if (!S.connected) $('aiState').textContent = T('no board');
  else if (running) $('aiState').textContent = TF('running on the board, {0} digits read', r.count);
  else $('aiState').textContent = r.current === AI_PROJECT ? T('starting ...') : T('not running on the board');
  $('aiOffText').textContent = !S.connected ? T('No board connected: click Scan.') :
    r.current === AI_PROJECT ? T('The project is on the board, but its program is not answering yet (it needs a few seconds to start).') :
      T('Upload the project: it loads the neural network into the FPGA and starts the drawing service on the board.');
  if (running) aiStats(r);
  if (BV.view === 'ai') AI.timer = setTimeout(aiPoll, running ? 4000 : 2000);
}

function aiBuild() {
  AI.built = true;
  $('aiBody').innerHTML = `
    <div class="dcard ai-off" id="aiOff" hidden><h3>${T('The AI is not running')}</h3><p id="aiOffText"></p>
      <button class="primary" id="aiStart">${T('Upload and run')}</button></div>
    <div class="ai-grid" id="aiMain">
      <div class="dcard ai-draw">
        <h3>${T('Draw a digit')}</h3>
        <canvas id="aiPad" width="280" height="280" title="${T('Draw one digit, 0 to 9, big and in the middle')}"></canvas>
        <div class="row">
          <button class="primary small" id="aiClear" title="Esc">${T('Clear')}</button>
          <button class="small" id="aiExample">${T('Show an example')}</button>
          <span class="grow"></span>
          <label class="ai-pen">${T('Pen')} <input type="range" id="aiPen" min="10" max="34" step="2" value="${AI.pen}"></label>
        </div>
        <p class="hint">${T('Draw one digit, 0 to 9, big and in the middle. The FPGA answers when you lift the pen.')}</p>
      </div>
      <div class="dcard ai-answer">
        <div class="ai-top">
          <div class="ai-big" id="aiDigit">?</div>
          <div class="ai-say"><div id="aiWhat">${T('Waiting for a drawing.')}</div><div class="hint" id="aiSure"></div>
            <div class="row ai-judge" id="aiJudge" hidden><span class="hint">${T('Was it right?')}</span>
              <button class="small" id="aiRight">${T('Right')}</button><button class="small" id="aiWrong">${T('Wrong')}</button></div></div>
        </div>
        <div id="aiBars" class="ai-bars"></div>
      </div>
      <div class="dcard ai-inside">
        <h3>${T('Inside the network')}</h3>
        <div class="ai-pics">
          <figure><canvas id="aiSeen" width="28" height="28"></canvas><figcaption>${T('What it sees: 28 x 28 pixels')}</figcaption></figure>
          <figure><canvas id="aiHid" width="8" height="8"></canvas><figcaption>${T('Its 64 hidden neurons (bright = active)')}</figcaption></figure>
        </div>
      </div>
      <div class="dcard ai-speed">
        <h3>${T('Speed for one digit')}</h3>
        <div id="aiRace"></div>
        <div class="hint" id="aiFacts"></div>
      </div>
      <div class="dcard ai-hist">
        <div class="row"><h3>${T('Your drawings')}</h3><span class="grow"></span><span class="hint" id="aiTally"></span>
          <button class="ghost small" id="aiReset" title="${T('Start counting again')}">${T('Reset')}</button></div>
        <div id="aiList" class="ai-list"><span class="hint">${T('The digits you draw appear here.')}</span></div>
      </div>
    </div>`;
  const pad = $('aiPad'), g = pad.getContext('2d');
  const clear = () => { g.fillStyle = '#000'; g.fillRect(0, 0, 280, 280); };
  clear();
  const pos = e => { const r = pad.getBoundingClientRect(); return [(e.clientX - r.left) * 280 / r.width, (e.clientY - r.top) * 280 / r.height]; };
  pad.addEventListener('pointerdown', e => {
    AI.drawing = true; AI.last = pos(e); clearTimeout(AI.askT);
    g.fillStyle = '#fff'; g.beginPath(); g.arc(AI.last[0], AI.last[1], AI.pen / 2, 0, 7); g.fill();
    try { pad.setPointerCapture(e.pointerId); } catch (x) { /* synthetic events */ }
  });
  pad.addEventListener('pointermove', e => {
    if (!AI.drawing) return;
    const p = pos(e);
    g.strokeStyle = '#fff'; g.lineWidth = AI.pen; g.lineCap = 'round'; g.lineJoin = 'round';
    g.beginPath(); g.moveTo(AI.last[0], AI.last[1]); g.lineTo(p[0], p[1]); g.stroke();
    AI.last = p;
  });
  const up = () => { if (!AI.drawing) return; AI.drawing = false; clearTimeout(AI.askT); AI.askT = setTimeout(aiAsk, 250); };
  pad.addEventListener('pointerup', up); pad.addEventListener('pointercancel', up);
  $('aiClear').onclick = () => { clear(); aiShowResult(null); };
  $('aiPen').oninput = e => { AI.pen = +e.target.value; };
  $('aiExample').onclick = async () => {
    const r = await api('/api/ai/example');
    if (!r.ok) return out(r.out || T('the AI demo does not answer'), 'err');
    const c = document.createElement('canvas'); c.width = c.height = 28;
    const im = c.getContext('2d').createImageData(28, 28);
    r.pixels.forEach((v, i) => { im.data.set([v, v, v, 255], 4 * i); });
    c.getContext('2d').putImageData(im, 0, 0);
    clear(); g.imageSmoothingEnabled = true; g.drawImage(c, 0, 0, 280, 280);
    aiAsk();
  };
  $('aiRight').onclick = () => aiJudge(true);
  $('aiWrong').onclick = () => aiJudge(false);
  $('aiReset').onclick = () => { AI.tally = { right: 0, wrong: 0 }; AI.hist = []; aiSaveTally(); aiHistory(); };
  $('aiStart').onclick = () => aiUpload(false);
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && BV.view === 'ai' && !document.querySelector('dialog[open]')) $('aiClear').click(); });
  aiShowResult(null);
  aiHistory();
}

function aiPixels() {                       // the drawing as 112 x 112 grey levels (base64), like the training data
  const c = document.createElement('canvas'); c.width = c.height = 112;
  const cg = c.getContext('2d'); cg.imageSmoothingEnabled = true; cg.imageSmoothingQuality = 'high';
  cg.drawImage($('aiPad'), 0, 0, 112, 112);
  const d = cg.getImageData(0, 0, 112, 112).data;
  let s = '';
  for (let i = 0; i < 112 * 112; i++) s += String.fromCharCode(d[4 * i]);
  return btoa(s);
}

async function aiAsk() {
  if (AI.busy) { AI.again = true; return; }
  AI.busy = true;
  const r = await api('/api/ai/guess', { px: aiPixels() });
  AI.busy = false;
  if (!r.ok) out(r.out || r.error || T('the AI demo does not answer'), 'err');
  else aiShowResult(r);
  if (AI.again) { AI.again = false; aiAsk(); }
}

function aiPaint(id, n, v) {
  const c = $(id), cg = c.getContext('2d'), im = cg.createImageData(n, n);
  for (let i = 0; i < n * n; i++) { const x = v ? v[i] : 0; im.data.set([x, x, x, 255], 4 * i); }
  cg.putImageData(im, 0, 0);
}

function aiShowResult(r) {
  AI.cur = r && !r.empty ? r : null;
  $('aiJudge').hidden = !AI.cur;
  if (!AI.cur) {
    $('aiDigit').textContent = '?'; $('aiWhat').textContent = T('Waiting for a drawing.'); $('aiSure').textContent = '';
    $('aiBars').innerHTML = [...Array(10).keys()].map(k => `<div class="ai-bar"><b>${k}</b><span><i></i></span><em></em></div>`).join('');
    aiPaint('aiSeen', 28, null); aiPaint('aiHid', 8, null);
    return;
  }
  const d = r.digit, p = r.prob;
  $('aiDigit').textContent = d;
  $('aiWhat').textContent = TF('The FPGA reads a {0}.', d);
  $('aiSure').textContent = TF('sure: {0} %', Math.round(100 * p[d]));
  $('aiBars').innerHTML = p.map((v, k) => `<div class="ai-bar${k === d ? ' top' : ''}"><b>${k}</b><span><i style="width:${(100 * v).toFixed(1)}%"></i></span>` +
    `<em>${(100 * v).toFixed(v < 0.1 ? 1 : 0)} %</em></div>`).join('');
  aiPaint('aiSeen', 28, r.pixels); aiPaint('aiHid', 8, r.hidden);
  aiRace(r.fpga_us, r.arm_us, r.cycles);
  AI.hist.unshift({ d, pixels: r.pixels, ok: null });
  AI.hist.length = Math.min(AI.hist.length, 16);
  aiHistory();
}

function aiJudge(right) {
  const h = AI.hist[0];
  if (!h || h.ok !== null) return;
  h.ok = right;
  AI.tally[right ? 'right' : 'wrong']++;
  aiSaveTally();
  $('aiJudge').hidden = true;
  aiHistory();
}
function aiSaveTally() { try { localStorage.setItem('ardzy.ai.tally', JSON.stringify(AI.tally)); } catch (e) { /* no storage */ } }

function aiHistory() {
  const n = AI.tally.right + AI.tally.wrong;
  $('aiTally').textContent = n ? TF('your handwriting: {0} of {1} right ({2} %)', AI.tally.right, n, Math.round(100 * AI.tally.right / n)) : '';
  if (!AI.hist.length) { $('aiList').innerHTML = `<span class="hint">${T('The digits you draw appear here.')}</span>`; return; }
  $('aiList').innerHTML = AI.hist.map((h, i) => `<div class="ai-item${h.ok === false ? ' bad' : h.ok ? ' good' : ''}"><canvas id="aiH${i}" width="28" height="28"></canvas><b>${h.d}</b></div>`).join('');
  AI.hist.forEach((h, i) => aiPaint('aiH' + i, 28, h.pixels));
}

function aiRace(fpga, arm, cycles) {
  if (!fpga || !arm) return;
  const w = v => Math.max(0.6, 100 * Math.log10(1 + v) / Math.log10(1 + Math.max(fpga, arm)));
  $('aiRace').innerHTML = `
    <div class="ai-race"><b>FPGA</b><span><i style="width:${w(fpga)}%"></i></span><em>${fpga.toFixed(1)} &micro;s</em></div>
    <div class="ai-race arm"><b>ARM</b><span><i style="width:${w(arm)}%"></i></span><em>${Math.round(arm)} &micro;s</em></div>
    <div class="ai-x">${TF('The FPGA is {0} x faster', Math.round(arm / fpga))}</div>`;
  $('aiFacts').textContent = TF('{0} clocks at 100 MHz, 64 multiplications in every clock. The ARM runs the same math with numpy.', cycles);
}

function aiStats(r) {
  if (!AI.cur && r.fpga_us) aiRace(r.fpga_us, r.arm_us, r.cycles);
}

async function aiUpload(test) {
  if (!S.connected) { out(T('No board connected: click Scan.'), 'err'); return; }
  const r = await api('/api/gallery/upload', { name: AI_PROJECT, test });
  if (!r.ok) out(r.out || 'busy', 'err');
  else if (test) showTab('monitor');
  setTimeout(aiPoll, 3000);
}

$('aiBack').onclick = () => showView('gallery');
$('aiGuide').onclick = () => galleryGuide(AI_PROJECT);
$('aiTest').onclick = () => aiUpload(true);
$('aiUpload').onclick = () => aiUpload(false);
window.aiShow = aiShow;
window.aiLeave = aiLeave;
