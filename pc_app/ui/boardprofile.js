/* Ardzy - boards other than the Antminer S9 (EBAZ4205, ...): the views that were drawn for the S9 (pin tables,
   Map, I/O, ready projects, new-project templates) show this board's own pins from its profile
   (boards/<id>/board.json, through /api/board/profile). On the S9 everything stays as it was.
   Uses app.js (S, $, esc, api, out, bpost, T, TF) and wraps loadPins, mapShow, buildIO, updateIO, galleryRender. */

const BP = { profile: null, id: null };

const boardId = () => (S.board && S.board.board) || (S.board && /ebaz/i.test(S.board.model || '') ? 'ebaz4205' : null) ||
  (S.board ? 's9' : S.targetBoard || 's9');
const boardIsS9 = () => boardId() === 's9';

async function boardProfile() {
  const id = boardId();
  if (BP.profile && BP.id === id) return BP.profile;
  const r = await api('/api/board/profile?id=' + encodeURIComponent(id));
  BP.profile = r.ok ? r.profile : null;
  BP.id = id;
  return BP.profile;
}

const bpXdc = (pin, port) => `set_property -dict {PACKAGE_PIN ${pin} IOSTANDARD LVCMOS33} [get_ports {${port}}]`;

// the pin tables of a board profile (click a row: its constraint line is copied)
function bpPinTables(p) {
  const tbl = (title, head, rows) => `<h4>${esc(title)}</h4><table><tr>${head.map(h => `<th>${esc(T(h))}</th>`).join('')}</tr>${rows.join('')}</table>`;
  const row = (cells, x) => `<tr class="copy" data-x="${esc(x)}">${cells.map((c, i) => `<td class="${i === 2 ? 'pin' : i === 3 ? 'mono' : ''}">${esc(c)}</td>`).join('')}</tr>`;
  let h = `<p class="hint">${esc(TF('The {0}: {1}, {2} MB. Click a row: its line for your .xdc file is copied.', p.long_name || p.name, p.chip, p.ram_mb))}</p>`;
  for (const [hd, pins] of Object.entries(p.headers || {})) {
    if (typeof pins !== 'object') continue;
    h += tbl(TF('Header {0}', hd), ['Header', 'Pin', 'FPGA pin', 'Port'],
      Object.entries(pins).map(([n, pin]) => row([hd, n, pin, `${hd.toLowerCase()}_${n}`], bpXdc(pin, `${hd.toLowerCase()}_${n}`))));
  }
  const leds = Object.entries(p.leds || {}).map(([n, l]) => row([T('LED') + ' ' + n, l.active_low ? T('on when 0') : T('on when 1'),
    l.pin || ('GPIO ' + l.gpio), l.pin ? `led_${n}_n` : '-'], l.pin ? bpXdc(l.pin, `led_${n}_n`) : ''));
  const btns = Object.entries(p.buttons || {}).map(([n, b]) => row([T('Button') + ' ' + n, b.active_low ? T('0 while pressed') : T('1 while pressed'),
    'MIO ' + b.mio, 'GPIO ' + b.gpio], ''));
  const fans = Object.entries(p.fans || {}).flatMap(([n, f]) => [row([n + ' ' + T('fan PWM'), '', f.pwm, `${n.toLowerCase()}_pwm`], bpXdc(f.pwm, `${n.toLowerCase()}_pwm`)),
    row([n + ' ' + T('fan speed'), '', f.tach, `${n.toLowerCase()}_tach`], bpXdc(f.tach, `${n.toLowerCase()}_tach`))]);
  h += tbl(T('LEDs, buttons, fans'), ['What', 'Level', 'FPGA pin', 'Port'], [...leds, ...btns, ...fans]);
  const eth = Object.entries((p.ethernet || {}).pins || {});
  if (eth.length) h += tbl(T('Ethernet (kept by the Ardzy build in every design: do not use these pins)'), ['Signal', '', 'FPGA pin', ''],
    eth.map(([s, pin]) => `<tr><td>${esc(s)}</td><td></td><td class="pin">${esc(pin)}</td><td></td></tr>`));
  if (p.header_notes) h += `<p class="hint">${esc(p.header_notes)}</p>`;
  return h;
}

function bpWireCopy(root) {
  root.querySelectorAll('tr.copy').forEach(tr => tr.onclick = async () => {
    if (!tr.dataset.x) return;
    try { await navigator.clipboard.writeText(tr.dataset.x); out(T('Copied: ') + tr.dataset.x, 'ok'); }
    catch (e) { out(tr.dataset.x); }
  });
}

(function bpStart() {
  // ---- the Pins tab
  const loadPins0 = window.loadPins;
  window.loadPins = async () => {
    if (boardIsS9()) { if ($('pinTables').dataset.board && $('pinTables').dataset.board !== 's9') $('pinTables').dataset.done = ''; $('pinTables').dataset.board = 's9'; return loadPins0(); }
    const p = await boardProfile();
    if (!p) return;
    $('pinTables').innerHTML = bpPinTables(p);
    $('pinTables').dataset.done = '';                 // (the S9's tables are made again when an S9 is connected)
    $('pinTables').dataset.board = p.id;
    bpWireCopy($('pinTables'));
  };

  // ---- the Map view: the board's pins and how it starts
  const mapShow0 = window.mapShow;
  window.mapShow = async () => {
    if (boardIsS9()) return mapShow0();
    clearTimeout(MP.timer);
    const p = await boardProfile();
    if (!p) return;
    $('mapState').textContent = p.hardware_tested ? '' : T('support from the published pin maps: not yet tested on a real board');
    $('mapBody').innerHTML = `<div class="dcard wide"><h3>${esc(p.long_name || p.name)}</h3>
      <div class="kv"><span>${T('Chip')}</span><span>${esc(p.chip)} (${esc(p.part)})</span><span>${T('Memory')}</span><span>${p.ram_mb} MB DDR3</span>
        <span>${T('Ethernet')}</span><span>${esc((p.ethernet || {}).via || '')}</span></div>
      <h4>${T('Getting it started')}</h4><ul>${((p.boot || {}).notes || []).map(n => `<li>${esc(n)}</li>`).join('')}</ul></div>
      <div class="dcard wide">${bpPinTables(p)}</div>`;
    bpWireCopy($('mapBody'));
  };

  // ---- the I/O view: the headers of this board (the pin-control design keeps the S9's registers)
  const buildIO0 = window.buildIO, updateIO0 = window.updateIO;
  const generic = r => r.pins.some(p => /^DATA/.test(p.name));
  window.buildIO = async r => {
    if (!generic(r)) return buildIO0(r);
    const row = p => `<div class="pinrow" data-name="${esc(p.name)}"><span class="p">${esc(p.pin)}</span><span>${esc(p.name)}</span>
      <span class="lvl" data-l="${esc(p.name)}"></span><span class="seg" data-io="${esc(p.name)}"><button data-m="in">In</button><button data-m="0">0</button><button data-m="1">1</button></span></div>`;
    const groups = {};
    r.pins.filter(p => !/^nc/.test(p.name)).forEach(p => (groups[p.name.split('-')[0]] = groups[p.name.split('-')[0]] || []).push(p));
    const cards = Object.entries(groups).map(([g, ps]) => `<div class="dcard conn"><h3>${esc(g)}</h3>${ps.map(row).join('')}</div>`);
    cards.push(`<div class="dcard"><h3>${T('Fans (J3, J5)')}</h3>
      <div class="row"><span class="seg" id="fanOn"><button data-v="0">${T('Full speed')}</button><button data-v="1">PWM</button></span>
        <label class="hint">duty <input type="range" min="0" max="100" step="1" id="fanDuty" style="vertical-align:middle"> <b id="fanDutyTxt"></b></label></div>
      <div class="row"><label class="hint">${T('PWM frequency')} <input type="number" id="fanHz" min="100" max="100000" step="100" style="width:100px"> Hz</label>
        <button class="ghost small" id="fanHzSet">${T('Set')}</button></div>
      <div class="fanrpm" id="fanRpm"></div>
      <div class="hint">${T('J3: PWM out and speed in; J5: speed in, its PWM output is the pin J5-PWM above.')}</div></div>`);
    $('ioBody').innerHTML = cards.join('');
    $('ioBody').querySelectorAll('[data-io] button').forEach(b => b.onclick = async () => {
      const x = await bpost('/api/io/set?' + qs({ name: b.parentElement.dataset.io, mode: b.dataset.m }));
      if (!x.ok) out(x.out, 'err');
      refreshIO();
    });
    $('fanOn').querySelectorAll('button').forEach(b => b.onclick = () => bpost('/api/io/fan?on=' + b.dataset.v).then(refreshIO));
    $('fanDuty').onchange = () => bpost('/api/io/fan?duty=' + $('fanDuty').value).then(refreshIO);
    $('fanDuty').oninput = () => $('fanDutyTxt').textContent = $('fanDuty').value + ' %';
    $('fanHzSet').onclick = () => bpost('/api/io/fan?hz=' + $('fanHz').value).then(refreshIO);
    BV.ioBuilt = true;
  };
  window.updateIO = r => {
    if (!generic(r)) return updateIO0(r);
    r.pins.forEach(p => {
      const l = document.querySelector(`[data-l="${CSS.escape(p.name)}"]`); if (l) l.className = 'lvl ' + (p.level ? 'h' : 'l');
      const sg = document.querySelector(`[data-io="${CSS.escape(p.name)}"]`);
      if (sg) sg.querySelectorAll('button').forEach(b => b.classList.toggle('on', p.mode === 'in' ? b.dataset.m === 'in' : b.dataset.m === String(p.level)));
    });
    const f = r.fan;
    if (!f || !$('fanOn')) return;
    $('fanOn').querySelectorAll('button').forEach(b => b.classList.toggle('on', (b.dataset.v === '1') === f.on));
    if (document.activeElement !== $('fanDuty')) { $('fanDuty').value = f.duty_pct; $('fanDutyTxt').textContent = f.duty_pct + ' %'; }
    if (document.activeElement !== $('fanHz')) $('fanHz').value = f.pwm_hz;
    $('fanRpm').innerHTML = f.rpm.slice(0, 2).map((v, i) => `<div>${['J3', 'J5'][i]}<b>${v} rpm</b></div>`).join('');
  };

  // ---- the ready projects are made for the S9's pins
  const galleryRender0 = window.galleryRender;
  window.galleryRender = () => {
    galleryRender0();
    if (boardIsS9()) return;
    $('galBody').insertAdjacentHTML('afterbegin', `<div class="dcard wide io-now"><b>${esc(TF('The connected board is the {0}.', (S.board && S.board.board_name) || boardId()))}</b>
      ${esc(T('The ready projects are made for the Antminer S9 (its pins). Read their guides, or Copy to my projects, change the pins in the .xdc file for this board and press Build FPGA.'))}</div>`);
    $('galBody').querySelectorAll('.gcard button[data-a="run"], .gcard button[data-a="test"]').forEach(b => { b.disabled = true; b.title = T('made for the Antminer S9'); });
  };
})();
