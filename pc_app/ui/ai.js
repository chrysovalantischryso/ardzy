/* Ardzy - AI view: the AI projects, one tab each. Read: 16_digit_ai reads handwritten digits. Write: 17_text_ai,
   a small language model. Draw: 18_image_ai draws new digits. The board runs the project's main.py (a service on
   port 8080); the engine passes the calls on (/api/ai/...), so this works over an IPv6 link-local cable too.
   Helpers from app.js / board.js: $, esc, api, out, S, T, TF, showView, showTab, galleryGuide. */
const AI = { timer: null, st: null, built: false, drawing: false, last: null, busy: false, again: false,
  hist: [], cur: null, pen: 20, tally: { right: 0, wrong: 0 } };
const AI_PROJ = { read: '16_digit_ai', write: '17_text_ai', draw: '18_image_ai' };
AI.tab = 'read';
const aiProject = () => AI_PROJ[AI.tab];
try { Object.assign(AI.tally, JSON.parse(localStorage.getItem('ardzy.ai.tally') || '{}')); } catch (e) { /* no storage */ }

function aiShow() {
  const m = location.hash.match(/ai=(read|write|draw)/);      // a link like #view=ai&ai=write opens that tab
  if (m && !AI.hashTab) { AI.hashTab = true; AI.tab = m[1]; }
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
  const onBoard = r.ok ? (r.project || '16_digit_ai') : r.current;
  const running = !!r.ok && onBoard === aiProject();
  $('aiOff').hidden = running;
  for (const [t, id] of [['read', 'aiMain'], ['write', 'aiWriteMain'], ['draw', 'aiDrawMain']]) {
    $(id).hidden = AI.tab !== t;
    $(id).classList.toggle('dim', AI.tab === t && !running);
  }
  document.querySelectorAll('#aiTabs button').forEach(b => {
    b.classList.toggle('on', b.dataset.t === AI.tab);
    b.classList.toggle('live', !!r.ok && AI_PROJ[b.dataset.t] === onBoard);
  });
  if (!S.connected) $('aiState').textContent = T('no board');
  else if (running) $('aiState').textContent = TF('running on the board, {0} runs of the network', r.count);
  const stopped = r.current === aiProject() && S.status && S.status.running === false;
  if (S.connected && !running) $('aiState').textContent = stopped ? T('stopped') : r.current === aiProject() ? T('starting ...') : T('not running on the board');
  $('aiOffText').textContent = !S.connected ? T('No board connected: click Scan.') :
    stopped ? T('The project is on the board, but its program is stopped (for example after the board was restarted). Press Upload and run.') :
    r.current === aiProject() ? T('The project is on the board, but its program is not answering yet (it needs a few seconds to start).') :
      r.ok ? TF('The board runs another AI project now ({0}). Upload this one to use it here: only one design fits in the FPGA at a time.', onBoard) :
        T('Upload the project: it loads the neural network into the FPGA and starts its service on the board.');
  if (running && AI.tab === 'read') aiStats(r);
  if (running && AI.tab === 'write') aiWriteStats(r);
  if (running && AI.tab === 'draw') aiDrawStats(r);
  if (BV.view === 'ai') AI.timer = setTimeout(aiPoll, running ? 4000 : 2000);
}

function aiBuild() {
  AI.built = true;
  $('aiBody').innerHTML = `
    <div class="seg ai-tabs" id="aiTabs"><button data-t="read" title="16 &middot; ${T('Read handwritten digits')}">${T('Read')}</button><button data-t="write"
      title="17 &middot; ${T('A language model writes text')}">${T('Write')}</button><button data-t="draw" title="18 &middot; ${T('Draw new digits')}">${T('Draw')}</button></div>
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
    </div>
    <div class="ai-grid ai-write" id="aiWriteMain" hidden></div>
    <div class="ai-grid ai-drawgen" id="aiDrawMain" hidden></div>`;
  $('aiTabs').querySelectorAll('button').forEach(b => b.onclick = () => aiOpen(b.dataset.t));
  aiBuildWrite();
  aiBuildDraw();
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

/* ---------------------------------------------------------------- Write (17_text_ai) */
function aiBuildWrite() {
  $('aiWriteMain').innerHTML = `
    <div class="dcard ai-wbox">
      <h3>${T('The start')}</h3>
      <textarea id="aiwStart" rows="3" spellcheck="false" placeholder="${T('type the start of a sentence, for example: the fpga')}">the fpga </textarea>
      <div class="ai-sliders">
        <label>${T('Length')} <input type="range" id="aiwLen" min="40" max="800" step="20" value="240"><b id="aiwLenV">240</b></label>
        <label title="${T('Low: safe and repetitive. High: surprising, then nonsense.')}">${T('Temperature')}
          <input type="range" id="aiwTemp" min="0.2" max="1.5" step="0.05" value="0.7"><b id="aiwTempV">0.70</b></label>
      </div>
      <div class="row"><button class="primary" id="aiwGo">${T('Write')}</button><button id="aiwAgain">${T('Again, differently')}</button>
        <span class="grow"></span><label class="check"><input type="checkbox" id="aiwColor" checked> ${T('show how sure it was')}</label></div>
      <p class="hint">${T('It writes one letter at a time: the FPGA scores every letter, one is picked by lot (the likely ones more often), added, and the next one is scored.')}</p>
    </div>
    <div class="dcard ai-wguess">
      <h3>${T('What comes next?')}</h3>
      <div id="aiwGuess" class="ai-bars one"></div>
      <p class="hint">${T('Its guesses for the letter after your start, updated as you type.')}</p>
    </div>
    <div class="dcard ai-wout">
      <h3>${T('What it wrote')}</h3>
      <div id="aiwText" class="ai-text"><span class="hint">${T('Press Write.')}</span></div>
      <div class="hint" id="aiwSpeed"></div>
    </div>`;
  const upd = () => { $('aiwLenV').textContent = $('aiwLen').value; $('aiwTempV').textContent = (+$('aiwTemp').value).toFixed(2); };
  $('aiwLen').oninput = upd; $('aiwTemp').oninput = upd;
  $('aiwGo').onclick = () => aiWrite(null);
  $('aiwAgain').onclick = () => aiWrite(null);
  $('aiwColor').onchange = () => { if (AI.wlast) aiWriteShow(AI.wlast); };
  $('aiwStart').oninput = () => { clearTimeout(AI.wguessT); AI.wguessT = setTimeout(aiWriteGuess, 300); };
  $('aiwStart').onkeydown = e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); aiWrite(1); } };
}

async function aiWrite(seed) {
  if (AI.wbusy) return;
  AI.wbusy = true; $('aiwGo').disabled = $('aiwAgain').disabled = true;
  const start = $('aiwStart').value;
  const r = await api('/api/ai/write', { start, length: +$('aiwLen').value, temperature: +$('aiwTemp').value,
    seed: seed === null ? Math.floor(Math.random() * 1e6) : seed });
  AI.wbusy = false; $('aiwGo').disabled = $('aiwAgain').disabled = false;
  if (!r.ok) return out(r.out || r.error || T('the AI demo does not answer'), 'err');
  AI.wlast = { start, ...r };
  aiWriteShow(AI.wlast);
  aiWriteGuess();
}

function aiWriteShow(r) {
  const color = $('aiwColor').checked;
  const letters = [...r.text].map((c, i) => {
    const p = r.sure[i];
    const ch = c === '\n' ? '<br>' : esc(c);
    return color ? `<span class="${p < 0.25 ? 'u3' : p < 0.5 ? 'u2' : p < 0.8 ? 'u1' : ''}" title="${Math.round(100 * p)} %">${ch}</span>` : ch;
  }).join('');
  $('aiwText').innerHTML = `<b>${esc(r.start)}</b>${letters}`;
  $('aiwSpeed').textContent = TF('{0} letters in {1} s ({2} per second). The FPGA scores a letter in {3} microseconds; the ARM with numpy needs {4}.',
    r.text.length, r.seconds.toFixed(2), Math.round(r.per_second), r.fpga_us.toFixed(1), Math.round(r.arm_us));
}

async function aiWriteGuess() {
  if (AI.tab !== 'write' || !AI.st || !AI.st.ok || AI.st.project !== '17_text_ai') return;
  const r = await api('/api/ai/next', { text: $('aiwStart').value });
  if (!r.ok) return;
  const show = c => c === ' ' ? T('space') : c === '\n' ? T('new line') : c;
  $('aiwGuess').innerHTML = r.next.map(([c, p], i) => `<div class="ai-bar${i === 0 ? ' top' : ''}"><b>${esc(show(c))}</b>` +
    `<span><i style="width:${(100 * p).toFixed(1)}%"></i></span><em>${(100 * p).toFixed(p < 0.1 ? 1 : 0)} %</em></div>`).join('');
}

function aiWriteStats(r) {
  if (!AI.wguessed) { AI.wguessed = true; aiWriteGuess(); if (!AI.wlast) aiWrite(1); }
  if (!AI.wlast) $('aiwSpeed').textContent = TF('The FPGA scores a letter in {0} microseconds; the ARM with numpy needs {1}.', r.fpga_us.toFixed(1), Math.round(r.arm_us));
}

/* ---------------------------------------------------------------- Draw (18_image_ai) */
function aiBuildDraw() {
  const digits = sel => [...Array(10).keys()].map(d => `<option${d === sel ? ' selected' : ''}>${d}</option>`).join('');
  $('aiDrawMain').innerHTML = `
    <div class="dcard ai-dctl">
      <h3>${T('Draw a digit')}</h3>
      <div class="seg ai-digits" id="aidDigits">${[...Array(10).keys()].map(d => `<button data-d="${d}"${d === 7 ? ' class="on"' : ''}>${d}</button>`).join('')}</div>
      <div class="ai-sliders">
        <label title="${T('0: the average digit. Higher: wilder styles.')}">${T('Variety')} <input type="range" id="aidVar" min="0" max="2.5" step="0.1" value="1"><b id="aidVarV">1.0</b></label>
        <label>${T('How many')} <select id="aidCount"><option>8</option><option selected>16</option><option>24</option></select></label>
      </div>
      <div class="row"><button class="primary" id="aidGo">${T('Draw')}</button></div>
      <h3 class="ai-sub">${T('Morph one digit into another')}</h3>
      <div class="row"><label>${T('from')} <select id="aidFrom">${digits(3)}</select></label><label>${T('to')} <select id="aidTo">${digits(8)}</select></label>
        <button id="aidMorph">${T('Morph')}</button></div>
      <h3 class="ai-sub">${T('Walk through styles')}</h3>
      <div class="row"><button id="aidStyle">${T('Same digit, changing style')}</button></div>
      <p class="hint">${T("Every picture is drawn by the FPGA from 16 random numbers (its style) and the digit you ask for. Then project 16's reader, in the same FPGA, reads it back.")}</p>
    </div>
    <div class="dcard ai-dout">
      <div class="row"><h3 id="aidTitle">${T('Its drawings')}</h3><span class="grow"></span><span class="hint" id="aidAgree"></span></div>
      <div id="aidGrid" class="ai-gen"><span class="hint">${T('Press Draw.')}</span></div>
      <div class="hint" id="aidSpeed"></div>
    </div>`;
  AI.ddigit = 7;
  $('aidDigits').querySelectorAll('button').forEach(b => b.onclick = () => {
    AI.ddigit = +b.dataset.d;
    $('aidDigits').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
    aiDraw('draw');
  });
  $('aidVar').oninput = () => { $('aidVarV').textContent = (+$('aidVar').value).toFixed(1); };
  $('aidGo').onclick = () => aiDraw('draw');
  $('aidMorph').onclick = () => aiDraw('morph');
  $('aidStyle').onclick = () => aiDraw('style');
}

async function aiDraw(kind) {
  if (AI.dbusy) return;
  AI.dbusy = true;
  const a = { variety: +$('aidVar').value, seed: Math.floor(Math.random() * 1e6) };
  if (kind === 'draw') Object.assign(a, { digit: AI.ddigit, count: +$('aidCount').value });
  if (kind === 'morph') Object.assign(a, { from: +$('aidFrom').value, to: +$('aidTo').value, steps: 11 });
  if (kind === 'style') Object.assign(a, { digit: AI.ddigit, steps: 11 });
  const r = await api('/api/ai/' + kind, a);
  AI.dbusy = false;
  if (!r.ok) return out(r.out || r.error || T('the AI demo does not answer'), 'err');
  $('aidTitle').textContent = kind === 'draw' ? TF('{0} new drawings of a {1}', r.images.length, a.digit) :
    kind === 'morph' ? TF('A {0} becoming a {1}', a.from, a.to) : TF('One {0}, its style changing', a.digit);
  $('aidGrid').innerHTML = r.images.map((im, i) => {
    const want = kind === 'morph' ? null : a.digit;
    const cls = want === null ? '' : im.read === want ? ' good' : ' bad';
    return `<figure class="ai-gitem${cls}"><canvas id="aidC${i}" width="28" height="28"></canvas>
      <figcaption title="${T("what project 16's reader says")}">${T('reads')} <b>${im.read}</b> ${Math.round(100 * im.sure)} %</figcaption></figure>`;
  }).join('');
  r.images.forEach((im, i) => {
    const b = atob(im.pixels), v = new Array(784);
    for (let k = 0; k < 784; k++) v[k] = b.charCodeAt(k);
    aiPaint('aidC' + i, 28, v);
  });
  if (kind !== 'morph') {
    const n = r.images.filter(im => im.read === a.digit).length;
    $('aidAgree').textContent = TF('the reader agrees with {0} of {1}', n, r.images.length);
  } else $('aidAgree').textContent = '';
  $('aidSpeed').textContent = TF('The FPGA draws a picture in {0} microseconds and reads it in {1}; the ARM with numpy needs {2} to draw one.',
    r.draw_us.toFixed(1), r.read_us.toFixed(1), Math.round(r.arm_us));
}

function aiDrawStats(r) {
  if (!AI.ddrawn) { AI.ddrawn = true; aiDraw('draw'); }
}

async function aiUpload(test) {
  if (!S.connected) { out(T('No board connected: click Scan.'), 'err'); return; }
  const r = await api('/api/gallery/upload', { name: aiProject(), test });
  if (!r.ok) out(r.out || 'busy', 'err');
  else if (test) showTab('monitor');
  setTimeout(aiPoll, 3000);
}

$('aiBack').onclick = () => showView('gallery');
$('aiGuide').onclick = () => galleryGuide(aiProject());
$('aiTest').onclick = () => aiUpload(true);
$('aiUpload').onclick = () => aiUpload(false);
function aiOpen(tab) {
  AI.tab = tab || AI.tab;
  if (BV.view !== 'ai') showView('ai'); else aiShow();
}
window.aiOpen = aiOpen;
window.aiShow = aiShow;
window.aiLeave = aiLeave;
