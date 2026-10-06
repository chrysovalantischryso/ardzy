(function learnLocalize() {                       // Greek / Russian lessons over the English ones (same order)
  const tr = I18N_LANG === 'el' && typeof LEARN_TR_EL !== 'undefined' ? LEARN_TR_EL : I18N_LANG === 'ru' && typeof LEARN_TR_RU !== 'undefined' ? LEARN_TR_RU : null;
  if (!tr) return;
  const put = (dst, src, keys) => keys.forEach(k => { if (src && src[k] !== undefined) dst[k] = src[k]; });
  if (tr.intro) LEARN.intro = tr.intro;
  LEARN.lessons.forEach((L, i) => {
    const t = tr.lessons[i]; if (!t) return;
    put(L, t, ['title', 'goal', 'need', 'steps']);
    (L.sections || []).forEach((s, k) => put(s, (t.sections || [])[k], ['h', 'html']));
    (L.quiz || []).forEach((q, k) => put(q, (t.quiz || [])[k], ['q', 'options', 'why']));
    (L.challenges || []).forEach((c, k) => put(c, (t.challenges || [])[k], ['task', 'hint', 'answer']));
  });
  IDEAS.forEach((d, i) => put(d, (tr.ideas || [])[i], ['t', 'cat', 'parts', 'learn', 'start', 'how']));
})();

/* Ardzy - Learn view: the course (lessons with widgets, the lesson's project, code, quiz, challenges) and Ideas.
   Content in learn_data.js. Helpers from app.js / board.js: $, esc, api, out, S, BV, showView, showTab. */
const LV = { tab: 'course', lesson: 1, timers: [], cm: null, file: null };

function learnProgress() {
  try { return JSON.parse(localStorage.getItem('ardzy.learn') || '{}'); } catch (e) { return {}; }
}
function learnSave(p) { try { localStorage.setItem('ardzy.learn', JSON.stringify(p)); } catch (e) { } }
function learnStop() { LV.timers.forEach(t => clearInterval(t)); LV.timers = []; }
function learnEvery(ms, fn) { const t = setInterval(() => { if (BV.view !== 'learn') return; fn(); }, ms); LV.timers.push(t); }

function learnShow() {
  learnStop();
  const p = learnProgress(), done = p.done || [];
  $('learnState').textContent = TF('{0} of {1} lessons done', done.length, LEARN.lessons.length);
  $('learnTabs').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.t === LV.tab));
  if (LV.tab === 'ideas') return learnIdeas();
  const list = LEARN.lessons.map(l => `<div class="lrow ${l.id === LV.lesson ? 'active' : ''}" data-id="${l.id}">
      <span class="lnum ${done.includes(l.id) ? 'done' : ''}">${done.includes(l.id) ? '&#10003;' : l.id}</span>
      <span class="grow">${esc(l.title)}</span></div>`).join('');
  $('learnBody').innerHTML = `<aside class="llist"><div class="lintro-t">The course</div>${list}
      <div class="lnote">Lessons build on each other, but each works alone. About 4 hours in all.</div></aside>
    <article class="lpage" id="lpage"></article>`;
  $('learnBody').querySelectorAll('.lrow').forEach(r => r.onclick = () => { LV.lesson = +r.dataset.id; learnShow(); });
  learnLesson(LEARN.lessons.find(l => l.id === LV.lesson) || LEARN.lessons[0]);
}

function learnLesson(L) {
  const p = learnProgress(), done = (p.done || []).includes(L.id);
  const pg = $('lpage');
  const sec = L.sections.map((s, i) => s.widget ? `<div class="lwidget" id="lw_${i}" data-w="${s.widget}"></div>`
    : `<h3>${esc(s.h)}</h3>${s.html}`).join('');
  pg.innerHTML = `
    ${L.id === 1 ? `<div class="lbox info">${LEARN.intro}</div>` : ''}
    <div class="lkicker">${TF('Lesson {0} of {1}', L.id, LEARN.lessons.length)} &middot; ${TF('about {0} minutes', L.minutes)} &middot; ${esc(TF('you need: {0}', L.need))}</div>
    <h2>${esc(L.title)}</h2>
    <div class="lbox goal"><b>You will learn:</b> ${esc(L.goal)}</div>
    ${sec}
    <h3>Do it on the board</h3>
    <ol class="lsteps">${L.steps.map(s => `<li>${s}</li>`).join('')}</ol>
    <div class="row">
      <button class="primary" id="lCreate">Create the project</button>
      <button id="lUpload" title="Selects the lesson's project and uploads it">Upload and run</button>
      <button class="ghost" id="lOpen">Open it in Code</button>
      <span class="hint" id="lProjInfo"></span>
    </div>
    <h3>The code</h3>
    <div class="seg" id="lFiles">${L.files.map(f => `<button data-f="${esc(f)}">${esc(f)}</button>`).join('')}</div>
    <div class="lcode" id="lCode"></div>
    <h3>Check yourself</h3>
    <div id="lQuiz">${L.quiz.map((q, i) => `<div class="lq" data-i="${i}"><div class="lqq">${i + 1}. ${q.q}</div>
      ${q.options.map((o, k) => `<label class="lopt"><input type="radio" name="q${L.id}_${i}" value="${k}"> ${o}</label>`).join('')}
      <div class="lqa"></div></div>`).join('')}
      <button class="small" id="lCheck">Check my answers</button> <span class="hint" id="lScore"></span></div>
    <h3>Challenges</h3>
    ${L.challenges.map((c, i) => `<div class="lch"><b>${i + 1}.</b> ${c.task}
      <details><summary>Hint</summary>${c.hint}</details><details><summary>Answer</summary>${c.answer}</details></div>`).join('')}
    <div class="row lfoot">
      <button class="${done ? 'ghost' : 'primary'}" id="lDone">${done ? 'Done (click to undo)' : 'I did this lesson'}</button>
      <span class="grow"></span>
      ${L.id > 1 ? '<button class="ghost" id="lPrev">Previous lesson</button>' : ''}
      ${L.id < LEARN.lessons.length ? '<button id="lNext">Next lesson</button>' : '<button id="lIdeas">Ideas for your own projects</button>'}
    </div>`;
  pg.scrollTop = 0;
  pg.querySelectorAll('.lwidget').forEach(el => { try { (LW[el.dataset.w] || (() => { }))(el); } catch (e) { el.textContent = 'widget: ' + e; } });
  const projName = L.template.replace(/^learn_/, 'lesson');
  const proj = () => (S.projects || []).find(x => x.name === projName);
  const info = () => { $('lProjInfo').textContent = proj() ? TF('your project: {0}', projName) : TF('creates {0} in your projects', projName); };
  info();
  $('lCreate').onclick = async () => {
    if (proj()) { out(`${projName} already exists: opening it.`, 'head'); }
    else {
      const r = await api('/api/project/new', { name: projName, template: L.template });
      if (!r.ok) { out(r.out || 'could not create the project', 'err'); return; }
      out(`Created ${projName} (lesson ${L.id}): it has a prebuilt FPGA design, ready to upload.`, 'ok');
      await refreshProjects();
    }
    selectProject(projName); info();
  };
  $('lOpen').onclick = async () => { if (!proj()) await $('lCreate').onclick(); selectProject(projName); showView('code'); };
  $('lUpload').onclick = async () => {
    if (!S.connected) { out('No board connected: click Scan.', 'err'); return; }
    if (!proj()) await $('lCreate').onclick();
    selectProject(projName);
    await doUpload();
    showTab('monitor');
  };
  // code viewer (read-only) with the template's files
  const showFile = async f => {
    $('lFiles').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.f === f));
    const r = await api('/api/learn/file?template=' + encodeURIComponent(L.template) + '&name=' + encodeURIComponent(f));
    const text = r.ok ? r.text : '(' + (r.out || 'not found') + ')';
    if (!LV.cm || !document.body.contains(LV.cm.getWrapperElement())) {
      $('lCode').innerHTML = '';
      LV.cm = CodeMirror($('lCode'), { readOnly: true, lineNumbers: true, viewportMargin: Infinity, lineWrapping: false });
    }
    LV.cm.setOption('mode', modeFor(f));
    LV.cm.setValue(text);
    setTimeout(() => LV.cm.refresh(), 0);
  };
  $('lFiles').querySelectorAll('button').forEach(b => b.onclick = () => showFile(b.dataset.f));
  showFile(L.files[0]);
  $('lCheck').onclick = () => {
    let right = 0;
    pg.querySelectorAll('.lq').forEach((qd, i) => {
      const q = L.quiz[i], sel = qd.querySelector('input:checked'), a = qd.querySelector('.lqa');
      if (!sel) { a.className = 'lqa'; a.textContent = 'not answered'; return; }
      const ok = +sel.value === q.answer;
      right += ok;
      a.className = 'lqa ' + (ok ? 'ok' : 'bad');
      a.innerHTML = (ok ? T('Right. ') : TF('Not quite: the answer is "{0}". ', q.options[q.answer])) + q.why;
    });
    $('lScore').textContent = TF('{0} of {1} right', right, L.quiz.length);
    const pr = learnProgress(); pr.quiz = pr.quiz || {}; pr.quiz[L.id] = Math.max(pr.quiz[L.id] || 0, right); learnSave(pr);
  };
  $('lDone').onclick = () => {
    const pr = learnProgress(); pr.done = pr.done || [];
    pr.done = pr.done.includes(L.id) ? pr.done.filter(x => x !== L.id) : [...pr.done, L.id];
    learnSave(pr); learnShow();
  };
  if ($('lPrev')) $('lPrev').onclick = () => { LV.lesson = L.id - 1; learnShow(); };
  if ($('lNext')) $('lNext').onclick = () => { LV.lesson = L.id + 1; learnShow(); };
  if ($('lIdeas')) $('lIdeas').onclick = () => { LV.tab = 'ideas'; learnShow(); };
}

function learnIdeas() {
  const cats = ['All', ...new Set(IDEAS.map(i => i.cat))];
  LV.icat = LV.icat || 'All'; LV.idiff = LV.idiff || 0;
  const shown = IDEAS.filter(i => (LV.icat === 'All' || i.cat === LV.icat) && (!LV.idiff || i.d === LV.idiff));
  const stars = d => '<span class="ldiff">' + T(['', 'easy', 'medium', 'hard'][d]) + '</span>';
  $('learnBody').innerHTML = `<div class="lideas">
    <div class="row"><span class="seg" id="iCat">${cats.map(c => `<button data-c="${esc(c)}" class="${c === LV.icat ? 'on' : ''}">${esc(c)}</button>`).join('')}</span>
      <span class="seg" id="iDiff">${['any', 'easy', 'medium', 'hard'].map((t, k) => `<button data-d="${k}" class="${k === LV.idiff ? 'on' : ''}">${T(t)}</button>`).join('')}</span>
      <span class="hint">${shown.length} ideas</span></div>
    <div class="icards">${shown.map(i => `<div class="dcard icard"><div class="gmeta"><span>${esc(i.cat)}</span>${stars(i.d)}</div>
      <h4>${esc(i.t)}</h4><p>${esc(i.how)}</p>
      <div class="kv"><span>You need</span><span>${esc(i.parts)}</span><span>You learn</span><span>${esc(i.learn)}</span>
      <span>Start from</span><span>${esc(i.start)}</span></div></div>`).join('')}</div></div>`;
  $('iCat').querySelectorAll('button').forEach(b => b.onclick = () => { LV.icat = b.dataset.c; learnIdeas(); });
  $('iDiff').querySelectorAll('button').forEach(b => b.onclick = () => { LV.idiff = +b.dataset.d; learnIdeas(); });
}

/* ================================================================ widgets */
const LW = {};
const svgEl = (w, h, inner) => `<svg viewBox="0 0 ${w} ${h}" class="lsvg" xmlns="http://www.w3.org/2000/svg">${inner}</svg>`;

/* 1. logic gates and a LUT you can program */
LW.gates = el => {
  const st = { in: [0, 0, 0], lut: [0, 0, 0, 1, 0, 1, 1, 1] };             // the LUT starts as MAJ
  const NAMES = [['0', [0, 0, 0, 0, 0, 0, 0, 0]], ['1', [1, 1, 1, 1, 1, 1, 1, 1]], ['a AND b AND c', [0, 0, 0, 0, 0, 0, 0, 1]],
    ['a OR b OR c', [0, 1, 1, 1, 1, 1, 1, 1]], ['majority (2 of 3)', [0, 0, 0, 1, 0, 1, 1, 1]], ['XOR of all three (odd parity)', [0, 1, 1, 0, 1, 0, 0, 1]],
    ['a', [0, 1, 0, 1, 0, 1, 0, 1]], ['b', [0, 0, 1, 1, 0, 0, 1, 1]], ['c', [0, 0, 0, 0, 1, 1, 1, 1]], ['NOT a', [1, 0, 1, 0, 1, 0, 1, 0]],
    ['a AND b', [0, 0, 0, 1, 0, 0, 0, 1]], ['a OR b', [0, 1, 1, 1, 0, 1, 1, 1]], ['a XOR b', [0, 1, 1, 0, 0, 1, 1, 0]],
    ['NAND of all three', [1, 1, 1, 1, 1, 1, 1, 0]], ['NOR of all three', [1, 0, 0, 0, 0, 0, 0, 0]], ['c ? b : a (a multiplexer)', [0, 1, 0, 1, 0, 0, 1, 1]]];
  const draw = () => {
    const [a, b, c] = st.in, n = a | b << 1 | c << 2;
    const f = [a & b, a | b, a ^ b, (a + b + c >= 2) ? 1 : 0];
    const name = (NAMES.find(x => x[1].join('') === st.lut.join('')) || ['a function nobody named (there are 256 of them)'])[0];
    el.innerHTML = `<div class="lw-t">Try it: click the inputs</div>
      <div class="row">${['a', 'b', 'c'].map((x, i) => `<button class="lbit ${st.in[i] ? 'on' : ''}" data-i="${i}">${x} = ${st.in[i]}</button>`).join('')}</div>
      <div class="row lleds">${['AND', 'OR', 'XOR', 'MAJ'].map((x, i) => `<span class="lled ${f[i] ? 'on' : ''}"></span><span class="lledt">${x}</span>`).join('')}</div>
      <div class="lw-t" style="margin-top:12px">A 3-input LUT: click the output column to program any function</div>
      <table class="ltt"><tr><th>c</th><th>b</th><th>a</th><th>out</th></tr>
      ${st.lut.map((v, r) => `<tr class="${r === n ? 'now' : ''}"><td>${r >> 2 & 1}</td><td>${r >> 1 & 1}</td><td>${r & 1}</td>
        <td><button class="lbit small ${v ? 'on' : ''}" data-r="${r}">${v}</button></td></tr>`).join('')}</table>
      <div class="lw-r">This LUT now is: <b>${esc(name)}</b>. For the inputs above its output is <b>${st.lut[n]}</b> (the highlighted row).</div>`;
    el.querySelectorAll('[data-i]').forEach(x => x.onclick = () => { st.in[+x.dataset.i] ^= 1; draw(); });
    el.querySelectorAll('[data-r]').forEach(x => x.onclick = () => { st.lut[+x.dataset.r] ^= 1; draw(); });
  };
  draw();
};

/* 2. a counter you can watch, slowed down */
LW.counter = el => {
  const st = { n: 0, run: true, hz: 4 };
  el.innerHTML = `<div class="lw-t">An 8-bit counter, slowed down from 100 MHz to a few counts per second</div>
    <div class="row"><button class="small" id="cRun">Pause</button><button class="small" id="cStep">+1 (one clock edge)</button>
      <label class="hint">speed <input type="range" id="cHz" min="1" max="20" value="4"> <span id="cHzT"></span></label></div>
    <div class="lcount" id="cBits"></div><div class="lw-r" id="cVal"></div>
    <table class="ltt"><tr><th>bit</th><th>toggles at 100 MHz</th><th>blinks per second</th></tr>
    ${[0, 1, 2, 3, 10, 20, 23, 24, 25, 26].map(b => `<tr><td>${b}</td><td>${lfmtHz(100e6 / 2 ** (b + 1))}</td><td>${(100e6 / 2 ** (b + 1)).toPrecision(3)}</td></tr>`).join('')}</table>`;
  const draw = () => {
    $('cBits').innerHTML = [...Array(8)].map((_, i) => 7 - i).map(b => `<div class="lcb"><span class="lled ${st.n >> b & 1 ? 'on' : ''}"></span><small>bit ${b}</small></div>`).join('');
    $('cVal').innerHTML = `count = <b>${st.n}</b> = binary <code>${st.n.toString(2).padStart(8, '0')}</code>. Watch: each bit changes half as often as the one to its right.`;
    $('cHzT').textContent = st.hz + ' counts/s';
  };
  let acc = 0;
  learnEvery(50, () => { if (!st.run) return; acc += st.hz * 0.05; while (acc >= 1) { acc -= 1; st.n = (st.n + 1) & 255; } draw(); });
  $('cRun').onclick = () => { st.run = !st.run; $('cRun').textContent = st.run ? 'Pause' : 'Run'; };
  $('cStep').onclick = () => { st.n = (st.n + 1) & 255; draw(); };
  $('cHz').oninput = e => { st.hz = +e.target.value; draw(); };
  draw();
};
function lfmtHz(f) {
  return f >= 1e6 ? (f / 1e6).toPrecision(3) + ' MHz' : f >= 1e3 ? (f / 1e3).toPrecision(3) + ' kHz' : f.toPrecision(3) + ' Hz';
}

/* 3. timing diagram: an input, the synchronizer and the edge detector */
LW.timing = el => {
  const N = 16, st = { inp: [0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 0, 0] };
  const draw = () => {
    const s1 = [], s2 = [], s3 = [], edge = [];
    for (let k = 0; k < N; k++) {        // values right after the rising edge k (the input changed in the middle of cycle k-1)
      s1[k] = k ? st.inp[k - 1] : 0; s2[k] = k ? s1[k - 1] : 0; s3[k] = k ? s2[k - 1] : 0; edge[k] = s2[k] & !s3[k] ? 1 : 0;
    }
    const W = 760, X0 = 110, cw = (W - X0 - 10) / N, lanes = [['clock', null], ['input (click)', st.inp, true], ['s1 (1st flip-flop)', s1],
      ['s2 (synchronized)', s2], ['edge = s2 & !s3', edge]];
    let g = '';
    lanes.forEach(([name, v, click], li) => {
      const y = 20 + li * 44, hi = y + 4, lo = y + 30;
      g += `<text x="4" y="${y + 21}" class="lsv-t">${name}</text>`;
      if (!v) {
        let d = `M${X0} ${lo}`;
        for (let k = 0; k < N; k++) { const x = X0 + k * cw; d += ` L${x} ${lo} L${x} ${hi} L${x + cw / 2} ${hi} L${x + cw / 2} ${lo}`; }
        g += `<path d="${d} L${X0 + N * cw} ${lo}" class="lsv-w clk"/>`;
        return;
      }
      const off = click ? cw / 2 : 0;                 // the input changes in the middle of a cycle (no clock outside)
      let d = '', prev = null;
      for (let k = 0; k < N; k++) {
        const x = X0 + k * cw + off, y1 = v[k] ? hi : lo;
        d += prev === null ? `M${X0} ${y1} L${x} ${y1}` : (prev !== v[k] ? ` L${x} ${prev ? hi : lo} L${x} ${y1}` : ` L${x} ${y1}`);
        d += ` L${Math.min(X0 + N * cw, x + cw)} ${y1}`;
        prev = v[k];
        if (click) g += `<rect x="${X0 + k * cw}" y="${y - 2}" width="${cw}" height="38" class="lsv-hit" data-k="${k}"/>`;
      }
      g += `<path d="${d}" class="lsv-w ${li === 4 ? 'edge' : ''}"/>`;
    });
    for (let k = 0; k <= N; k++) g += `<line x1="${X0 + k * cw}" y1="14" x2="${X0 + k * cw}" y2="${20 + 5 * 44}" class="lsv-grid"/>`;
    el.innerHTML = `<div class="lw-t">Click the input lane to change it. The flip-flops only take a new value at the rising clock edges (grid lines).</div>
      ${svgEl(W, 245, g)}<div class="lw-r">The edge pulse is exactly one clock long, two clocks after the input changed: the price of a safe synchronizer.
      It happens ${edge.reduce((a, b) => a + b, 0)} times here: once per 0 to 1 change of the input.</div>`;
    el.querySelectorAll('.lsv-hit').forEach(r => r.onclick = () => { st.inp[+r.dataset.k] ^= 1; draw(); });
  };
  draw();
};

/* 4. PWM */
LW.pwm = el => {
  const st = { duty: 25 };
  el.innerHTML = `<div class="lw-t">Move the duty cycle: the pin is 1 for that share of each period</div>
    <div class="row"><label class="hint">duty <input type="range" id="pDuty" min="0" max="100" value="25"></label><b id="pDutyT"></b>
      <span class="grow"></span><span class="lbulb" id="pBulb"></span><span class="hint">how bright it looks</span></div>
    <div id="pWave"></div><div class="lw-r" id="pInfo"></div>`;
  const draw = () => {
    const d = st.duty / 100, W = 740, H = 120, P = 3, pw = (W - 20) / P;
    let path = 'M10 95';
    for (let k = 0; k < P; k++) {
      const x = 10 + k * pw;
      if (d > 0) path += ` L${x} 95 L${x} 25 L${x + pw * d} 25 L${x + pw * d} 95`;
      path += ` L${x + pw} 95`;
    }
    const avgY = 95 - 70 * d;
    $('pWave').innerHTML = svgEl(W, H, `<path d="${path}" class="lsv-w"/><line x1="10" y1="${avgY}" x2="${W - 10}" y2="${avgY}" class="lsv-avg"/>
      <text x="${W - 12}" y="${avgY - 5}" class="lsv-t" text-anchor="end">average = ${(3.3 * d).toFixed(2)} V</text>`);
    $('pDutyT').textContent = st.duty + ' %';
    $('pBulb').style.opacity = (0.08 + 0.92 * Math.pow(d, 1 / 2.2)).toFixed(2);
    $('pInfo').innerHTML = `In the lesson: brightness value <b>${Math.round(d * 256)}</b> of 256. On for ${(d * 41).toFixed(1)} us of each 41 us period (24 kHz).
      Your eye sees about ${Math.round(100 * Math.pow(d, 1 / 2.2))} % brightness: it is more sensitive to dim light.`;
  };
  $('pDuty').oninput = e => { st.duty = +e.target.value; draw(); };
  draw();
};

/* 5. the traffic light state machine */
LW.fsm = el => {
  const S5 = [['GREEN', 3, '#2fbf6c'], ['YELLOW', 2, '#e3ad4c'], ['RED', 1, '#e05555'], ['WALK', 4, '#4ea8ff'], ['RED+YELLOW', 1, '#e08a3c']];
  const st = { s: 2, left: 1, waiting: false, run: true, log: [] };
  const pos = [[380, 40], [600, 120], [520, 220], [240, 220], [160, 120]];
  const lamps = { 0: [0, 0, 1, 0], 1: [0, 1, 0, 0], 2: [1, 0, 0, 0], 3: [1, 0, 0, 1], 4: [1, 1, 0, 0] };
  const next = () => {
    const s = st.s;
    if (s === 0) { if (!st.waiting) return; st.s = 1; st.left = 2; }
    else if (s === 1) { st.s = 2; st.left = 1; }
    else if (s === 2) { if (st.waiting) { st.s = 3; st.left = 4; st.waiting = false; } else { st.s = 4; st.left = 1; } }
    else if (s === 3) { st.s = 4; st.left = 2; }
    else { st.s = 0; st.left = 3; }
    st.log.unshift(S5[st.s][0]); st.log.length = Math.min(st.log.length, 6);
  };
  const arrows = [[0, 1, 'press'], [1, 2, ''], [2, 3, 'waiting'], [2, 4, 'no one'], [3, 4, ''], [4, 0, '']];
  const draw = () => {
    let g = '<defs><marker id="lfa" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto"><path d="M0,0 L9,3.5 L0,7 z" class="lsv-fill"/></marker></defs>';
    arrows.forEach(([a, b, t]) => {
      const [x1, y1] = pos[a], [x2, y2] = pos[b], dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy);
      const sx = x1 + dx / L * 52, sy = y1 + dy / L * 28, ex = x2 - dx / L * 56, ey = y2 - dy / L * 30;
      g += `<line x1="${sx}" y1="${sy}" x2="${ex}" y2="${ey}" class="lsv-line" marker-end="url(#lfa)"/>`;
      if (t) g += `<text x="${(sx + ex) / 2}" y="${(sy + ey) / 2 - 6}" class="lsv-t" text-anchor="middle">${t}</text>`;
    });
    S5.forEach(([n, , c], i) => {
      const [x, y] = pos[i], on = i === st.s;
      g += `<ellipse cx="${x}" cy="${y}" rx="58" ry="28" class="lsv-state ${on ? 'on' : ''}" style="${on ? 'stroke:' + c : ''}"/>
        <text x="${x}" y="${y + 5}" class="lsv-t ${on ? 'b' : ''}" text-anchor="middle">${n}</text>`;
    });
    const l = lamps[st.s];
    ['#e05555', '#e3ad4c', '#2fbf6c', '#4ea8ff'].forEach((c, i) => {
      g += `<circle cx="${720}" cy="${50 + i * 46}" r="17" fill="${l[i] ? c : 'none'}" class="lsv-lamp"/>`;
    });
    g += `<text x="720" y="245" class="lsv-t" text-anchor="middle">LEDs 0..3</text>`;
    el.querySelector('.fsmsvg').innerHTML = svgEl(780, 260, g);
    el.querySelector('.fsminfo').innerHTML = `State <b>${S5[st.s][0]}</b>, ${st.left > 0 ? st.left + ' s left' : 'staying'}${st.waiting ? ', <b>someone is waiting</b>' : ''}.
      Recent: ${st.log.join(' &larr; ') || '-'}`;
  };
  el.innerHTML = `<div class="lw-t">The lesson's state machine, running at 1 state second per real second</div>
    <div class="row"><button class="small primary" id="fPress">Press the pedestrian button</button><button class="small" id="fRun">Pause</button>
    <button class="small" id="fStep">Timer runs out now</button></div><div class="fsmsvg"></div><div class="lw-r fsminfo"></div>`;
  learnEvery(1000, () => { if (!st.run) return; if (st.left > 0) st.left--; if (st.left === 0) next(); draw(); });
  $('fPress').onclick = () => { st.waiting = true; draw(); };
  $('fRun').onclick = () => { st.run = !st.run; $('fRun').textContent = st.run ? 'Pause' : 'Run'; };
  $('fStep').onclick = () => { st.left = 0; next(); draw(); };
  draw();
};

/* 6. the register map */
LW.regmap = el => {
  const R = [['A', 0x00, 'write', 'ctrl[31:0]'], ['B', 0x04, 'write', 'ctrl[63:32]'], ['A + B', 0x80, 'read', 'status 0'], ['A - B', 0x84, 'read', 'status 1'],
    ['A * B low', 0x88, 'read', 'status 2'], ['A * B high', 0x8C, 'read', 'status 3'], ['max', 0x90, 'read', 'status 4'], ['A AND B', 0x94, 'read', 'status 5'],
    ['writes', 0x98, 'read', 'status 6'], ['name "LREG"', 0x9C, 'read', 'status 7']];
  const show = i => {
    const [n, off, rw, sig] = R[i], adr = 0x41200000 + off;
    el.querySelector('.rmcode').innerHTML = `<b>${n}</b> at address <code>0x${adr.toString(16).toUpperCase()}</code> = base 0x4120_0000 + 0x${off.toString(16)} (register ${off / 4})
      <pre>Python:  regs = MMIO(0x41200000)
         ${rw === 'write' ? `regs.write(0x${off.toString(16).padStart(2, '0')}, 1234)` : `value = regs.read(0x${off.toString(16)})`}
C:       volatile uint32_t *r = mmap(... 0x41200000 ...);
         ${rw === 'write' ? `r[${off / 4}] = 1234;` : `uint32_t value = r[${off / 4}];`}
Verilog: ${sig}</pre>`;
    el.querySelectorAll('tr[data-i]').forEach(t => t.classList.toggle('now', +t.dataset.i === i));
  };
  el.innerHTML = `<div class="lw-t">The lesson's registers: click one to see how to reach it</div>
    <table class="ltt">${'<tr><th>name</th><th>address</th><th>ARM</th></tr>' + R.map((r, i) => `<tr data-i="${i}" class="click"><td>${r[0]}</td><td><code>0x${(0x41200000 + r[1]).toString(16).toUpperCase()}</code></td><td>${r[2]}</td></tr>`).join('')}</table>
    <div class="rmcode"></div>`;
  el.querySelectorAll('tr[data-i]').forEach(t => t.onclick = () => show(+t.dataset.i));
  show(2);
};

/* 7. a UART frame */
LW.uart = el => {
  el.innerHTML = `<div class="lw-t">Type a character and choose a speed: this is what the wire carries</div>
    <div class="row"><input id="uCh" value="A" maxlength="1" style="width:50px;text-align:center;font:600 18px var(--mono)">
    <select id="uBaud"><option>9600</option><option selected>115200</option><option>1000000</option></select><span class="hint" id="uInfo"></span></div>
    <div id="uWave"></div><div class="lw-r" id="uExp"></div>`;
  const draw = () => {
    const ch = ($('uCh').value || 'A').charCodeAt(0) & 255, baud = +$('uBaud').value, bt = 1e6 / baud;
    const bits = [0, ...[...Array(8)].map((_, i) => ch >> i & 1), 1];
    const W = 760, X0 = 50, bw = (W - X0 - 40) / 10;
    let d = `M10 30 L${X0} 30`, g = '';
    bits.forEach((b, i) => {
      const x = X0 + i * bw, y = b ? 30 : 80;
      d += ` L${x} ${y} L${x + bw} ${y}`;
      g += `<text x="${x + bw / 2}" y="105" class="lsv-t" text-anchor="middle">${i === 0 ? 'start' : i === 9 ? 'stop' : 'd' + (i - 1)}</text>
        <text x="${x + bw / 2}" y="20" class="lsv-t b" text-anchor="middle">${b}</text>
        <line x1="${x}" y1="12" x2="${x}" y2="110" class="lsv-grid"/>`;
    });
    d += ` L${W - 10} 30`;
    $('uWave').innerHTML = svgEl(W, 120, `<path d="${d}" class="lsv-w"/>${g}<text x="12" y="24" class="lsv-t">idle</text>`);
    $('uInfo').textContent = `bit time ${bt.toFixed(2)} us = ${Math.round(100e6 / baud)} clocks, a byte ${(10 * bt).toFixed(1)} us`;
    $('uExp').innerHTML = `"${esc(String.fromCharCode(ch))}" = ${ch} = 0x${ch.toString(16).toUpperCase().padStart(2, '0')} = binary <code>${ch.toString(2).padStart(8, '0')}</code>.
      On the wire the bits come in the other order (d0, the lowest, first), between a 0 start bit and a 1 stop bit.`;
  };
  $('uCh').oninput = draw; $('uBaud').onchange = draw;
  draw();
};

/* 8. block RAM: ask at one clock, the data comes at the next */
LW.memory = el => {
  const mem = [...Array(16)].map((_, i) => (i * 37 + 11) & 255);
  const st = { clk: 0, ra: 3, out: null, pending: null, log: [] };
  el.innerHTML = `<div class="lw-t">A 16-word memory. Give an address, then press Clock: the data appears one clock later</div>
    <div class="row">address <input id="mA" type="number" min="0" max="15" value="3" style="width:60px">
      <button class="small" id="mClk">Clock edge</button> <span class="grow"></span>
      write <input id="mW" type="number" min="0" max="255" value="99" style="width:70px"> <button class="small" id="mWr">Write at the address (on the next edge)</button></div>
    <div class="lmem" id="mGrid"></div><div class="lw-r" id="mLog"></div>`;
  const draw = () => {
    $('mGrid').innerHTML = mem.map((v, i) => `<div class="lmc ${i === st.ra ? 'adr' : ''}"><small>${i}</small><b>${v}</b></div>`).join('');
    $('mLog').innerHTML = `clock ${st.clk}: data output = <b>${st.out === null ? '?' : st.out}</b>
      ${st.pending !== null ? ` (address ${st.pending} was given at the last edge)` : ''}<br>${st.log.slice(0, 4).join('<br>')}`;
  };
  let wr = null;
  $('mA').oninput = e => { st.ra = Math.max(0, Math.min(15, +e.target.value || 0)); draw(); };
  $('mWr').onclick = () => { wr = [st.ra, (+$('mW').value) & 255]; st.log.unshift(`(a write of ${wr[1]} to address ${wr[0]} waits for the next edge)`); draw(); };
  $('mClk').onclick = () => {
    st.clk++;
    st.out = mem[st.ra];                       // registered read: the address given now, data valid after this edge
    st.pending = st.ra;
    if (wr) { mem[wr[0]] = wr[1]; st.log.unshift(`edge ${st.clk}: wrote ${wr[1]} to address ${wr[0]} (the read this edge saw the old value)`); wr = null; }
    st.log.unshift(`edge ${st.clk}: the RAM took address ${st.ra}, its data is out now`);
    draw();
  };
  draw();
};

/* 9. counting against timing */
LW.freq = el => {
  el.innerHTML = `<div class="lw-t">Move the frequency: compare the two ways of measuring it</div>
    <div class="row"><label class="hint">frequency <input type="range" id="qF" min="0" max="700" value="300" style="width:300px"></label><b id="qFT"></b>
      <label class="hint">gate <select id="qG"><option value="1">1 s</option><option value="0.1">0.1 s</option><option value="10">10 s</option></select></label></div>
    <table class="ltt"><tr><th></th><th>counting edges in the gate</th><th>timing one period</th></tr>
      <tr><td>raw number</td><td id="qC1"></td><td id="qP1"></td></tr>
      <tr><td>result</td><td id="qC2"></td><td id="qP2"></td></tr>
      <tr><td>resolution</td><td id="qC3"></td><td id="qP3"></td></tr>
      <tr><td>a new value every</td><td id="qC4"></td><td id="qP4"></td></tr></table><div class="lw-r" id="qW"></div>`;
  const draw = () => {
    const f = Math.pow(10, +$('qF').value / 100), gate = +$('qG').value;
    const cnt = Math.floor(f * gate), clocks = Math.round(100e6 / f);
    const resC = 1 / gate, resP = clocks > 1 ? f - 100e6 / (clocks + 1) : f;
    $('qFT').textContent = lfmtHz(f);
    $('qC1').textContent = cnt + ' edges'; $('qP1').textContent = clocks + ' clocks';
    $('qC2').textContent = (cnt / gate).toPrecision(9) + ' Hz'; $('qP2').textContent = (100e6 / clocks).toPrecision(9) + ' Hz';
    $('qC3').textContent = '+- ' + resC.toPrecision(2) + ' Hz'; $('qP3').textContent = '+- ' + resP.toPrecision(2) + ' Hz';
    $('qC4').textContent = gate + ' s'; $('qP4').textContent = (1 / f < 1e-3 ? (1e6 / f).toPrecision(3) + ' us' : (1 / f).toPrecision(3) + ' s');
    $('qW').innerHTML = resC < resP ? T('<b>Counting</b> wins here: many edges fit in the gate.') : T('<b>Timing a period</b> wins here: many clocks fit in one period.')
      + (Math.abs(resC - resP) / Math.max(resC, resP) < 0.5 ? ' (about equal: the cross-over is near 10 kHz for a 1 s gate.)' : '');
  };
  $('qF').oninput = draw; $('qG').onchange = draw;
  draw();
};

/* 10. DDS */
LW.dds = el => {
  const st = { f: 1000, t: 0 };
  el.innerHTML = `<div class="lw-t">Choose a frequency: the DDS step is computed, and the first clocks of the phase are shown</div>
    <div class="row">frequency <input id="dF" type="number" value="1000" min="0.03" max="40000000" step="any" style="width:140px"> Hz
      <span class="hint" id="dInfo"></span></div>
    <div class="row" style="align-items:flex-start"><div id="dWheel"></div><div class="grow" id="dTab"></div></div>`;
  const draw = () => {
    const f = Math.max(0.03, Math.min(40e6, +$('dF').value || 1000));
    const step = Math.round(f / 100e6 * 2 ** 32), real = step * 100e6 / 2 ** 32;
    $('dInfo').innerHTML = `step = ${step} (0x${step.toString(16).toUpperCase()}); real frequency ${real.toPrecision(10)} Hz; error ${(real - f).toPrecision(3)} Hz`;
    let rows = '<table class="ltt"><tr><th>clock</th><th>phase (32 bit)</th><th>top 10 bits = table index</th><th>sine value</th></tr>';
    for (let k = 0; k < 6; k++) {
      const ph = (step * k) % 2 ** 32, idx = Math.floor(ph / 2 ** 22);
      rows += `<tr><td>${k}</td><td><code>0x${ph.toString(16).toUpperCase().padStart(8, '0')}</code></td><td>${idx}</td><td>${Math.round(32767 * Math.sin(2 * Math.PI * idx / 1024))}</td></tr>`;
    }
    $('dTab').innerHTML = rows + '</table><div class="lw-r">At 100 MHz the phase goes round ' + real.toPrecision(6) + ' times per second. The wheel turns at 1/' +
      Math.max(1, Math.round(real / 0.5)) + ' of the real speed so you can see it.</div>';
    st.real = real;
  };
  learnEvery(40, () => {
    const turns = 0.5;                                   // shown at 0.5 turns per second whatever the real frequency
    st.t += 0.04 * turns;
    const a = 2 * Math.PI * (st.t % 1), x = 90 + 70 * Math.sin(a), y = 90 - 70 * Math.cos(a);
    const idx = Math.floor((st.t % 1) * 1024);
    $('dWheel').innerHTML = svgEl(320, 190, `<circle cx="90" cy="90" r="70" class="lsv-line" fill="none"/>
      <line x1="90" y1="90" x2="${x}" y2="${y}" class="lsv-w"/><circle cx="${x}" cy="${y}" r="5" class="lsv-fill"/>
      <text x="90" y="182" class="lsv-t" text-anchor="middle">phase = ${(st.t % 1 * 360).toFixed(0)} deg, index ${idx}</text>
      <line x1="180" y1="90" x2="310" y2="90" class="lsv-grid"/>
      <path d="${[...Array(65)].map((_, i) => (i ? 'L' : 'M') + (180 + i * 2) + ' ' + (90 - 60 * Math.sin(2 * Math.PI * ((st.t - (64 - i) / 64) % 1)))).join(' ')}" class="lsv-w"/>`);
  });
  $('dF').oninput = draw;
  draw();
};

$('learnTabs').querySelectorAll('button').forEach(b => b.onclick = () => { LV.tab = b.dataset.t; learnShow(); });
window.learnShow = learnShow;
