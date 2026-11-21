/* Ardzy - split editor: a second editor beside (or below) the first one.
   It shows any open file (the same file too: both views edit one text, like two windows on it).
   Ctrl+\ opens / closes it, Ctrl+Alt+\ turns it (side by side <-> one above the other),
   the bar between them can be dragged. The second editor has its own file list on top.
   Uses app.js (S, $, esc, T, TF, saveTab, renderTabs, closeTab, activate). */

const SP = { cm: null, key: null, open: false, dir: 'v', pos: 50 };

function spPrefs() {
  try { Object.assign(SP, JSON.parse(localStorage.getItem('ardzy.split') || '{}'), { open: false }); } catch (e) { }
}
function spKeep() { localStorage.setItem('ardzy.split', JSON.stringify({ dir: SP.dir, pos: SP.pos })); }

function spEnsure() {
  if (SP.cm) return;
  const wrap = $('editor').parentElement;
  const box = document.createElement('div');
  box.id = 'editor2box';
  box.innerHTML = `<div class="sp-bar"><select id="spFile" title="${esc(T('The file in the second editor'))}"></select>
      <button class="ghost small" id="spSwap" title="${esc(T('Swap: this file to the first editor'))}">&#8644;</button>
      <button class="ghost small" id="spTurn" title="${esc(T('Side by side or one above the other (Ctrl+Alt+\\)'))}">&#8635;</button>
      <button class="ghost small" id="spClose" title="${esc(T('Close the second editor (Ctrl+\\)'))}">&times;</button></div>
    <div id="editor2"></div>`;
  const grip = document.createElement('div');
  grip.id = 'spGrip';
  wrap.appendChild(grip);
  wrap.appendChild(box);
  const o = S.cm.options;
  SP.cm = CodeMirror($('editor2'), {
    lineNumbers: true, indentUnit: o.indentUnit, tabSize: o.tabSize, indentWithTabs: o.indentWithTabs,
    matchBrackets: true, autoCloseBrackets: true, styleActiveLine: true, lineWrapping: o.lineWrapping,
    rulers: o.rulers, foldGutter: o.foldGutter, gutters: o.gutters,
    extraKeys: Object.assign({}, o.extraKeys, {
      'Ctrl-S': () => { const t = spTab(); if (t) saveTab(t); },
    }),
  });
  SP.cm.on('change', () => {                    // the dirty mark of the file's tab
    const t = spTab();
    if (t && !t.loading && !SP.loading) { t.dirty = t.doc.getValue() !== t.saved; renderTabs(); }
  });
  SP.cm.on('focus', () => wrap.classList.add('sp-focus2'));
  SP.cm.on('blur', () => wrap.classList.remove('sp-focus2'));
  $('spFile').onchange = () => spShow($('spFile').value);
  $('spClose').onclick = () => spToggle(false);
  $('spTurn').onclick = () => { SP.dir = SP.dir === 'v' ? 'h' : 'v'; spKeep(); spLayout(); };
  $('spSwap').onclick = () => {
    const a = S.active, b = SP.key;
    if (!b) return;
    activate(b);
    if (a && a !== b) spShow(a);
  };
  grip.onpointerdown = e => {
    e.preventDefault();
    grip.setPointerCapture(e.pointerId);
    const r = wrap.getBoundingClientRect();
    grip.onpointermove = ev => {
      const p = SP.dir === 'v' ? (ev.clientX - r.left) / r.width : (ev.clientY - r.top) / r.height;
      SP.pos = Math.max(15, Math.min(85, p * 100));
      spLayout(true);
    };
    grip.onpointerup = () => { grip.onpointermove = null; spKeep(); spLayout(); };
  };
}

function spTab() { return S.tabs.find(t => t.key === SP.key); }

// follow the first editor's settings (font, colours, wrap ...) when they change
function spSync() {
  if (!SP.cm) return;
  ['indentUnit', 'tabSize', 'indentWithTabs', 'lineWrapping', 'lineNumbers', 'styleActiveLine', 'matchBrackets',
    'autoCloseBrackets', 'rulers', 'foldGutter', 'gutters'].forEach(k => {
    if (SP.cm.getOption(k) !== S.cm.getOption(k)) SP.cm.setOption(k, S.cm.getOption(k));
  });
  // colours, font and cursor come from classes and a CSS variable on the first editor's box (codeplus.js)
  const a = $('editor'), b = $('editor2');
  if (b.className !== a.className) b.className = a.className;
  const f = a.style.getPropertyValue('--ed-font');
  if (f !== b.style.getPropertyValue('--ed-font')) { b.style.setProperty('--ed-font', f); SP.cm.refresh(); }
}

function spLayout(fast) {
  const wrap = $('editor').parentElement;
  wrap.classList.toggle('sp-on', SP.open);
  wrap.classList.toggle('sp-h', SP.dir === 'h');
  wrap.style.setProperty('--sp', SP.pos + '%');
  const r = () => { S.cm.refresh(); if (SP.cm) SP.cm.refresh(); };
  if (fast) r(); else setTimeout(r, 0);
}

function spList() {
  if (!SP.cm) return;
  $('spFile').innerHTML = S.tabs.map(t => `<option value="${esc(t.key)}" ${t.key === SP.key ? 'selected' : ''}>${esc(t.name)}${t.dirty ? ' *' : ''}   (${esc(t.project)})</option>`).join('');
}

function spShow(key) {
  const t = S.tabs.find(x => x.key === key);
  if (!t) return;
  if (!t.link || t.link.__gone) t.link = t.doc.linkedDoc({ sharedHist: true });
  SP.key = key;
  SP.loading = true; SP.cm.swapDoc(t.link); SP.loading = false;
  spList(); spSync();
  setTimeout(() => SP.cm.refresh(), 0);
}

function spToggle(on) {
  if (on === undefined) on = !SP.open;
  if (on && !S.tabs.length) return out(T('Open a file first: the second editor shows one of the open files.'), 'warn');
  spEnsure();
  SP.open = on;
  if (on) {
    // a second file if there is one, else the same file (two places of one long file)
    const other = S.tabs.filter(t => t.key !== S.active).pop();
    spShow((SP.key && spTab() && SP.key !== S.active) ? SP.key : (other ? other.key : S.active));
    spSync();
  }
  spLayout();
  (on ? SP.cm : S.cm).focus();
  const b = $('edSplit');
  if (b) b.classList.toggle('sp-active', on);
}

(function spStart() {
  spPrefs();
  const ready = setInterval(() => {
    if (!S.cm || !$('edTools')) return;
    clearInterval(ready);
    // a button in the editor's tool bar, before the settings
    const b = document.createElement('button');
    b.className = 'ghost small'; b.id = 'edSplit';
    b.title = T('Split: a second editor beside this one, for another file or another place of the same file (Ctrl+\\)');
    b.textContent = T('Split');
    b.onclick = e => { e.preventDefault(); spToggle(); };
    $('edTools').insertBefore(b, $('edSet') || null);
    S.cm.addKeyMap({ 'Ctrl-\\': () => spToggle(), 'Ctrl-Alt-\\': () => { SP.dir = SP.dir === 'v' ? 'h' : 'v'; spKeep(); spLayout(); } });
    S.cm.on('optionChange', () => spSync());
    // keep the second editor's list and file right when tabs open / close / change
    const renderTabs0 = window.renderTabs;
    window.renderTabs = () => { renderTabs0(); if (SP.open) spList(); };
    const closeTab0 = window.closeTab;
    window.closeTab = key => {
      const t = S.tabs.find(x => x.key === key);
      closeTab0(key);
      if (S.tabs.find(x => x.key === key)) return;                  // not closed (unsaved, "cancel")
      if (t && t.link) { t.doc.unlinkDoc(t.link); t.link.__gone = true; }
      if (SP.key === key) {
        SP.key = null;
        if (SP.open) { if (S.tabs.length) spShow(S.tabs[S.tabs.length - 1].key); else spToggle(false); }
      }
    };
  }, 300);
  document.addEventListener('keydown', e => {          // also when the focus is outside the editors
    if (e.ctrlKey && e.key === '\\' && !e.target.closest('.CodeMirror')) { e.preventDefault(); spToggle(); }
  });
})();
