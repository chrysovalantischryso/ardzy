/* Ardzy - the board over a USB-UART cable (serial link), and a Linux terminal in the app.
   Link: the Boards dialog (board button, top right) has "Or over a USB-UART cable": port, speed, password.
         The engine logs in on the board's console and starts the link (ardzy_link.py); then every view works
         as over the network.
   Terminal: bottom tab Terminal: a real bash shell on the board (xterm.js), over the network or the cable.
         The shell keeps running when the window reloads (the tab finds it again).
   Uses app.js (S, $, esc, api, out, T, TF, setBoard, showTab). */

const TM = { term: null, id: null, since: 0, gen: 0, queue: '', sendT: null, sending: Promise.resolve(), fitT: null, host: '' };

/* ---------------- the terminal ---------------- */
function tmTheme() {
  const cs = getComputedStyle(document.documentElement);
  const v = (n, d) => (cs.getPropertyValue(n) || '').trim() || d;
  return { background: v('--term-bg', '#0b0f0d'), foreground: v('--term-text', '#c4ecd5'), cursor: v('--accent', '#3ddc84'),
    selectionBackground: 'rgba(120, 200, 160, 0.35)' };
}

function tmEnsure() {
  if (TM.term) return true;
  if (typeof Terminal === 'undefined') { $('termBox').textContent = T('The terminal could not load (vendor/xterm).'); return false; }
  const size = +(localStorage.getItem('ardzy.termFont') || 14);
  TM.term = new Terminal({ fontFamily: '"Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace', fontSize: size, cursorBlink: true,
    scrollback: 5000, theme: tmTheme(), allowProposedApi: false, convertEol: false });
  TM.term.open($('termBox'));
  TM.term.onData(d => tmType(d));
  TM.term.onBinary && TM.term.onBinary(d => tmType(d));
  new ResizeObserver(() => { clearTimeout(TM.fitT); TM.fitT = setTimeout(tmFit, 120); }).observe($('termBox'));
  // copy with Ctrl+Shift+C, paste with Ctrl+Shift+V (Ctrl+C stays "stop the program", like any terminal)
  TM.term.attachCustomKeyEventHandler(e => {
    if (e.type !== 'keydown' || !e.ctrlKey || !e.shiftKey) return true;
    if (e.code === 'KeyC') { const s = TM.term.getSelection(); if (s) navigator.clipboard.writeText(s); return false; }
    if (e.code === 'KeyV') { navigator.clipboard.readText().then(t => t && tmType(t)); return false; }
    return true;
  });
  new MutationObserver(() => { if (TM.term) TM.term.options.theme = tmTheme(); })
    .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'class', 'style'] });
  tmFit();
  return true;
}

// columns and rows that fit the panel (xterm.js has no "fit" without its add-on: measured here)
function tmFit() {
  const t = TM.term, box = $('termBox');
  if (!t || !box.clientWidth || !box.clientHeight) return;
  const dims = t._core && t._core._renderService && t._core._renderService.dimensions;
  let cw = dims && dims.css && dims.css.cell.width, ch = dims && dims.css && dims.css.cell.height;
  if (!cw || !ch) {
    const p = document.createElement('span');
    p.style.cssText = `position:absolute;visibility:hidden;white-space:pre;font-family:${t.options.fontFamily};font-size:${t.options.fontSize}px`;
    p.textContent = 'W'.repeat(40);
    box.appendChild(p);
    cw = p.getBoundingClientRect().width / 40; ch = p.getBoundingClientRect().height * 1.02;
    p.remove();
  }
  const cols = Math.max(20, Math.floor((box.clientWidth - 14) / cw)), rows = Math.max(5, Math.floor((box.clientHeight - 6) / ch));
  if (cols !== t.cols || rows !== t.rows) {
    t.resize(cols, rows);
    if (TM.id) api('/api/term/resize', { id: TM.id, cols, rows });
  }
}

function tmStatus(text, cls) { const s = $('termState'); if (s) { s.textContent = text; s.className = 'hint ' + (cls || ''); } }

async function tmShow() {
  if (!tmEnsure()) return;
  setTimeout(() => { tmFit(); TM.term.focus(); }, 30);
  if (!S.connected) { tmStatus(T('No board connected: connect over the network or a USB-UART cable (board button, top right).'), 'l-warn'); return; }
  if (TM.id && TM.host === (S.board && S.board.host)) return;
  await tmStart(false);
}

async function tmStart(fresh) {
  const gen = ++TM.gen;
  TM.host = S.board ? S.board.host : '';
  const keep = (() => { try { return JSON.parse(localStorage.getItem('ardzy.termSession') || '{}'); } catch (e) { return {}; } })();
  TM.id = null; TM.since = 0;
  if (!fresh && keep.id && keep.host === TM.host) {                   // the shell from before the reload
    const r = await api('/api/term/read', { id: keep.id, since: 0, wait: 0 });
    if (r.ok && r.alive) {
      TM.id = keep.id;
      TM.term.reset();
      TM.term.write(tmBytes(r.data));
      TM.since = r.next;
    }
  }
  if (!TM.id) {
    const r = await api('/api/term/open', { cols: TM.term.cols, rows: TM.term.rows });
    if (!r.ok) {
      tmStatus(r.out || T('the board did not open a terminal'), 'l-err');
      if (r.old_board) TM.term.write('\r\n\x1b[33m' + r.out + '\x1b[0m\r\n');
      return;
    }
    TM.id = r.id;
    if (fresh || !keep.id) TM.term.reset();
    localStorage.setItem('ardzy.termSession', JSON.stringify({ id: TM.id, host: TM.host }));
  }
  tmStatus(TF('bash on {0} ({1})', S.board.hostname || 'the board', TM.host.startsWith('serial:') ? TF('cable {0}', TM.host.slice(7)) : T('network')), 'l-ok');
  api('/api/term/resize', { id: TM.id, cols: TM.term.cols, rows: TM.term.rows });
  tmPoll(gen);
}

function tmBytes(b64) {
  const s = atob(b64 || ''), u = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
  return u;
}

async function tmPoll(gen) {
  let errors = 0;
  while (gen === TM.gen && TM.id) {
    if (!S.connected) { tmStatus(T('board disconnected'), 'l-warn'); TM.id = null; return; }
    let r;
    try { r = await api('/api/term/read', { id: TM.id, since: TM.since, wait: 15 }); } catch (e) { r = { ok: false, out: String(e) }; }
    if (gen !== TM.gen) return;
    if (!r.ok) {
      if (/no terminal/.test(r.out || '')) {                         // (the board or its link started again)
        TM.term.write('\r\n\x1b[33m' + T('[the shell is gone: press Enter for a new one]') + '\x1b[0m\r\n');
        TM.id = null; tmStatus(T('no shell'), 'l-warn'); return;
      }
      if (++errors > 3) { tmStatus(r.out || T('the board does not answer'), 'l-err'); }
      await new Promise(ok => setTimeout(ok, 1500));
      continue;
    }
    errors = 0;
    if (r.next < TM.since) TM.since = 0;                               // a new session with the same number
    if (r.data) TM.term.write(tmBytes(r.data));
    TM.since = r.next;
    if (!r.alive) {
      TM.term.write('\r\n\x1b[33m' + T('[the shell has ended: press Enter for a new one]') + '\x1b[0m\r\n');
      TM.id = null; tmStatus(T('shell ended'), 'l-warn');
      return;
    }
  }
}

// keys go out in small batches, in order
function tmType(d) {
  if (!TM.id) {
    if (S.connected && (d === '\r' || d === '\n')) tmStart(true);
    return;
  }
  TM.queue += d;
  if (TM.sendT) return;
  TM.sendT = setTimeout(() => {
    const data = TM.queue; TM.queue = ''; TM.sendT = null;
    const id = TM.id;
    TM.sending = TM.sending.then(() => api('/api/term/write', { id, data })).then(r => {
      if (r && !r.ok) tmStatus(r.out, 'l-err');
    }).catch(() => { });
  }, 8);
}

function tmFont(step) {
  if (!tmEnsure()) return;
  const n = Math.max(9, Math.min(28, TM.term.options.fontSize + step));
  TM.term.options.fontSize = n;
  localStorage.setItem('ardzy.termFont', n);
  setTimeout(tmFit, 50);
}

/* ---------------- connecting over the cable ---------------- */
async function lkPorts() {
  const r = await api('/api/serial/ports');
  const sel = $('lkPort'), cur = sel.value || (r.last_link && r.last_link.serial) || '';
  sel.innerHTML = (r.ports || []).map(p => `<option value="${esc(p.port)}">${esc(p.port)}  ${esc(p.desc)}</option>`).join('') ||
    `<option value="">${esc(T('no COM ports found: plug in the USB-UART adapter'))}</option>`;
  if (cur && [...sel.options].some(o => o.value === cur)) sel.value = cur;
  if (r.last_link && r.last_link.baud) $('lkBaud').value = String(r.last_link.baud);
  const l = r.link || {};
  $('lkState').innerHTML = l.active ? `<span class="l-ok">${esc(TF('Connected over {0} at {1} baud.', l.port, l.baud))}</span>` : '';
}

async function lkConnect() {
  const port = $('lkPort').value;
  if (!port) return lkPorts();
  $('lkGo').disabled = true;
  $('lkState').innerHTML = `<span class="hint">${esc(TF('Connecting over {0} (log in, start the link) ...', port))}</span>`;
  showTab('output');
  let r;
  try { r = await api('/api/link/connect', { port, baud: +$('lkBaud').value, password: $('lkPass').value || '' }); }
  finally { $('lkGo').disabled = false; }
  if (r.ok) {
    $('lkPass').value = '';
    $('dlgBoards').close();
    setBoard(r.info, 'serial:' + port);
    out(TF('The board is connected over the cable ({0} baud). Every view works; uploads are slower than over the network.', r.baud), 'ok');
  } else {
    $('lkState').innerHTML = `<span class="l-err">${esc(r.out)}</span>`;
    if (r.password) { $('lkPassRow').hidden = false; $('lkPass').focus(); }
  }
}

(function tmStart0() {
  const tabBtn = document.querySelector('.bottom-tabs button[data-tab="term"]');
  if (tabBtn) tabBtn.addEventListener('click', () => setTimeout(tmShow, 0));
  $('termNew').onclick = () => { if (S.connected) tmStart(true); };
  $('termBigger').onclick = () => tmFont(+1);
  $('termSmaller').onclick = () => tmFont(-1);
  $('termClear').onclick = () => TM.term && TM.term.clear();
  $('lkGo').onclick = e => { e.preventDefault(); lkConnect(); };
  $('lkRefresh').onclick = e => { e.preventDefault(); lkPorts(); };
  $('lkPassShow').onclick = e => { e.preventDefault(); $('lkPassRow').hidden = !$('lkPassRow').hidden; };
  // the Boards dialog: the COM ports are read each time it opens
  new MutationObserver(() => { if ($('dlgBoards').open) lkPorts(); }).observe($('dlgBoards'), { attributes: true, attributeFilter: ['open'] });
  // another board (or none): the terminal starts again for it
  const setBoard0 = window.setBoard;
  window.setBoard = (info, host) => {
    setBoard0(info, host);
    if (host && String(host).startsWith('serial:')) {
      $('boardPill').title = TF('Board {0} over the USB-UART cable on {1}. Click to choose another board.', info ? info.hostname : '', host.slice(7));
    }
    if ((host || '') !== TM.host) { TM.gen++; TM.id = null; if (document.querySelector('.panel[data-panel="term"].active')) setTimeout(tmShow, 100); }
  };
})();
