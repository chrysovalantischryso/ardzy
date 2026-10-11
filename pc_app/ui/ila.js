/* Ardzy - the signal analyzer inside the FPGA (like Vivado's ILA), shown in the Simulation tab.
   Mark signals in the Verilog with (* mark_debug *), Build FPGA, Upload; then here: a trigger, Capture, and the
   samples from the chip appear as waves (cursor A on the trigger). Uses app.js, simview.js (SV, simLayout), projtools.js (ptDialog). */

const ILA = { busy: false, stop: false, last: { signal: '', cond: 'now', value: '', pre: 50 } };

async function ilaOpen() {
  if (!S.project) return out(T('Choose a project first.'), 'warn');
  const r = await api('/api/ila/info?project=' + encodeURIComponent(S.project));
  const d = ptDialog('dlgIla', TF('Signal analyzer: {0}', S.project));
  const body = d.querySelector('.ptbody'), foot = d.querySelector('.ptfoot');
  if (!r.ok) {
    body.innerHTML = `<p class="hint">${esc(r.out)}</p><pre class="ila-ex">(* mark_debug *) reg [7:0] state;
(* mark_debug *) wire       busy = (state != 0);</pre>
      <p class="hint">${T('The build adds the analyzer for the marked signals; it keeps up to 4096 samples of them, one per clock tick, around the moment you choose (the trigger).')}</p>`;
    foot.innerHTML = `<button value="close" class="primary">${T('Close')}</button>`;
    return d.showModal();
  }
  const g = r.debug, L = ILA.last;
  if (!g.signals.some(s => s.name === L.signal)) L.signal = g.signals[0].name;
  const bst = r.board;
  const bmsg = !bst ? T('No board connected.') : bst.ok === false ? esc(bst.out)
    : !bst.present ? T('The FPGA on the board has no analyzer now: Upload this project first.')
    : bst.width !== g.width || bst.depth !== g.depth ? T('The FPGA holds the analyzer of another design: Upload this project first.')
    : TF('Ready on the board{0}.', bst.armed && !bst.done ? ' (' + T('waiting for a trigger') + ')' : '');
  body.innerHTML = `<p class="hint">${esc(TF('{0} signals ({1} bits), {2} samples per capture, one per tick of {3}.', g.signals.length, g.width, g.depth, g.clock))}</p>
    <div class="ila-sigs">${g.signals.map(s => `<span class="mono">${esc(s.name)}${s.width > 1 ? `<span class="hint"> [${s.width - 1}:0]</span>` : ''}</span>`).join('')}</div>
    <h4>${T('Trigger')}</h4>
    <div class="row wrap ila-trig">
      <select id="ilaCond">
        <option value="now">${T('at once (no condition)')}</option>
        <option value="eq">${T('when the signal is')}</option>
        <option value="becomes">${T('when the signal becomes')}</option>
        <option value="changes">${T('when the signal changes')}</option>
      </select>
      <select id="ilaSig">${g.signals.map(s => `<option value="${esc(s.name)}">${esc(s.name)}</option>`).join('')}</select>
      <input id="ilaVal" placeholder="12, 0x1f, b1010" spellcheck="false" autocomplete="off" size="12">
    </div>
    <label class="inl">${T('Samples before the trigger')} <select id="ilaPre">${[0, 10, 25, 50, 75, 90].map(p => `<option value="${p}">${p} %</option>`).join('')}</select></label>
    <p class="hint" id="ilaBoard">${bmsg}</p>
    <p class="hint" id="ilaState"></p>`;
  foot.innerHTML = `<button value="close">${T('Close')}</button><button type="button" id="ilaNow" disabled>${T('Trigger now')}</button>
    <button type="button" id="ilaStop" disabled>${T('Stop')}</button><button type="button" class="primary" id="ilaGo">${T('Capture')}</button>`;
  $('ilaCond').value = L.cond; $('ilaSig').value = L.signal; $('ilaVal').value = L.value; $('ilaPre').value = L.pre;
  const sync = () => { const c = $('ilaCond').value; $('ilaSig').disabled = c === 'now'; $('ilaVal').disabled = c === 'now' || c === 'changes'; };
  $('ilaCond').onchange = sync; sync();
  $('ilaGo').onclick = () => ilaCapture(d);
  $('ilaVal').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); ilaCapture(d); } };
  $('ilaNow').onclick = async () => { const x = await api('/api/ila/now', {}); if (x.ok === false) $('ilaState').textContent = x.out; };
  $('ilaStop').onclick = async () => { ILA.stop = true; await api('/api/ila/stop', {}); };
  d.showModal();
}

async function ilaCapture(d) {
  if (ILA.busy) return;
  const L = ILA.last;
  L.cond = $('ilaCond').value; L.signal = $('ilaSig').value; L.value = $('ilaVal').value.trim(); L.pre = +$('ilaPre').value;
  const st = $('ilaState'), btns = on => { $('ilaGo').disabled = on; $('ilaNow').disabled = $('ilaStop').disabled = !on; };
  ILA.busy = true; ILA.stop = false; btns(true);
  st.className = 'hint'; st.textContent = T('Arming ...');
  try {
    let r = await api('/api/ila/capture', { project: S.project, signal: L.signal, cond: L.cond, value: L.value, pre: L.pre, wait: 2 });
    while (r.ok !== false && r.waiting && !ILA.stop) {
      st.textContent = T('Waiting for the trigger ... (Trigger now takes the samples at once)');
      r = await api('/api/ila/read', { project: S.project, pre: r.pre, wait: 2 });
    }
    if (r.ok === false) { st.className = 'hint l-err'; st.textContent = r.out; return; }
    if (r.waiting) { st.textContent = T('Stopped.'); return; }
    ilaShow(r);
    d.close();
  } finally { ILA.busy = false; btns(false); }
}

function ilaShow(r) {
  SV.project = S.project;
  SV.data = r;
  SV.byName = Object.fromEntries(r.signals.map(s => [s.name, s]));
  SV.sel = r.signals.map(s => s.name);
  SV.t0 = 0; SV.t1 = Math.max(1, r.end);
  SV.curA = r.trigger; SV.curB = null;
  showTab('simulation');
  simLayout();
  $('simInfo').textContent = TF('Signal analyzer on the board · {0} samples · trigger at cursor A · {1} · saved as {2}', r.end + 1, r.when, r.file);
}

(function ilaStart() {
  const b = $('simIla');
  if (b) b.onclick = ilaOpen;
})();
