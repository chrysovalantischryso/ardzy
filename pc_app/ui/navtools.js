/* Ardzy: moving around the code like in an IDE.
   Go to definition (F12), find every use (Shift+F12), rename a name in every file of the project (Ctrl+Shift+R),
   Include library for sketches (like Sketch > Include Library of the Arduino IDE), and a right-click menu in the editor. */

const NAV = { libs: null };
const navWordRe = /^[A-Za-z_]\w*$/;
const navEsc = w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

// the word under the cursor (or the selected word)
function navWord() {
  const cm = S.cm, sel = cm.getSelection();
  if (sel && navWordRe.test(sel)) return sel;
  const w = cm.findWordAt(cm.getCursor()), word = cm.getRange(w.anchor, w.head);
  return navWordRe.test(word) ? word : '';
}

// the text of every file of the project that holds code: from the open tab when there is one (it may be unsaved)
async function navFiles() {
  const p = S.projects.find(p => p.name === S.project);
  if (!p) return [];
  const out = [];
  for (const name of p.files.filter(n => EDITABLE.test(n) && cpLang(n))) {
    const t = S.tabs.find(t => t.key === p.name + '/' + name);
    if (t) { out.push({ name, text: t.doc.getValue(), tab: t }); continue; }
    const r = await api('/api/file?project=' + encodeURIComponent(p.name) + '&name=' + encodeURIComponent(name));
    if (r.ok) out.push({ name, text: r.text, tab: null });
  }
  return out;
}

// the name a symbol of the outline defines ("led  (output)" -> led, "u_vga: ardzy_vga" -> u_vga)
const navSymName = s => s.kind === 'port' ? s.name.split(/\s/)[0] : s.kind === 'inst' ? s.name.split(':')[0] : s.name;

async function navOpenAt(name, line, ch = 0) {
  await openFile(S.project, name);
  setTimeout(() => cpJump(line, ch), 30);
}

// a small list of places to choose from
function navPick(title, items, word) {
  const d = ptDialog('dlgNav', title);
  d.querySelector('.ptbody').innerHTML = `<div class="navlist">${items.map((it, i) => `<button type="button" class="navhit" data-i="${i}">
      <span class="nf">${esc(it.name)}:${it.line + 1}</span><code>${navMark(it.text, word)}</code></button>`).join('')}</div>`;
  d.querySelector('.ptfoot').innerHTML = `<button value="close">${T('Close')}</button>`;
  d.querySelectorAll('.navhit').forEach(b => b.onclick = () => { d.close(); const it = items[+b.dataset.i]; navOpenAt(it.name, it.line, it.ch || 0); });
  d.showModal();
}
function navMark(text, word) {
  const t = text.trim().slice(0, 160);
  return word ? esc(t).replace(new RegExp('\\b' + navEsc(word) + '\\b', 'g'), m => `<mark>${m}</mark>`) : esc(t);
}

/* ---------------- go to definition (F12) ---------------- */
async function navDefinition() {
  const word = navWord();
  if (!word) return out(T('Put the cursor on a name first.'), 'warn');
  const hits = [];
  for (const f of await navFiles()) {
    const lines = f.text.split('\n');
    for (const s of cpSymbols(f.text, cpLang(f.name))) {
      // a Verilog instance names its module: F12 on the module goes to the module, not to the instance
      if (navSymName(s) === word && !(s.kind === 'inst' && s.name.split(':')[1].trim() === word))
        hits.push({ name: f.name, line: s.line, ch: Math.max(0, lines[s.line].indexOf(word)), text: lines[s.line] });
    }
  }
  if (!hits.length) {
    // not made in this project: the Ardzy reference may know it (digitalWrite, ardzy.pin ...)
    if (typeof CODE_REF !== 'undefined' && CODE_REF.some(r => r[0] === word || r[1].includes(word + '('))) { cpRefWord(); return; }
    return out(TF('Where {0} is made was not found in this project (it may come from a library).', word), 'warn');
  }
  if (hits.length === 1) return navOpenAt(hits[0].name, hits[0].line, hits[0].ch);
  navPick(TF('{0} is made in {1} places', word, hits.length), hits, word);
}

/* ---------------- find every use (Shift+F12) ---------------- */
async function navUses(word) {
  word = word || navWord();
  if (!word) return out(T('Put the cursor on a name first.'), 'warn');
  const hits = [], re = new RegExp('\\b' + navEsc(word) + '\\b');
  for (const f of await navFiles())
    f.text.split('\n').forEach((l, i) => { const m = l.match(re); if (m) hits.push({ name: f.name, line: i, ch: m.index, text: l }); });
  if (!hits.length) return out(TF('{0} is not used in this project.', word), 'warn');
  navPick(TF('{0}: {1} uses in {2} files', word, hits.length, new Set(hits.map(h => h.name)).size), hits, word);
}

/* ---------------- rename in every file (Ctrl+Shift+R) ---------------- */
async function navRename() {
  const word = navWord();
  if (!word) return out(T('Put the cursor on a name first.'), 'warn');
  const files = await navFiles(), re = new RegExp('\\b' + navEsc(word) + '\\b', 'g');
  const touched = files.map(f => ({ f, n: (f.text.match(re) || []).length })).filter(x => x.n);
  const d = ptDialog('dlgRename', TF('Rename {0}', word));
  d.querySelector('.ptbody').innerHTML = `<label>${T('New name:')} <input id="navNew" value="${esc(word)}" spellcheck="false" autocomplete="off"></label>
    <p class="hint">${esc(TF('Changes the whole word {0} in {1} files ({2} places): code, comments and text alike. Ctrl+Z in each file takes it back.',
      word, touched.length, touched.reduce((a, x) => a + x.n, 0)))}</p>
    <div class="navlist">${touched.map(x => `<div class="navhit"><span class="nf">${esc(x.f.name)}</span><span class="hint">${x.n}</span></div>`).join('')}</div>
    <p class="hint l-err" id="navErr"></p>`;
  d.querySelector('.ptfoot').innerHTML = `<button value="close">${T('Cancel')}</button><button value="ok" class="primary" id="navGo">${T('Rename')}</button>`;
  const inp = d.querySelector('#navNew');
  const check = () => {
    const v = inp.value.trim();
    const bad = !navWordRe.test(v) ? T('A name is letters, digits and _ and does not start with a digit.')
      : v !== word && files.some(f => new RegExp('\\b' + navEsc(v) + '\\b').test(f.text)) ? TF('{0} is used already: the two would become one.', v) : '';
    d.querySelector('#navErr').textContent = bad;
    d.querySelector('#navGo').disabled = !!bad || v === word;
  };
  inp.oninput = check; check();
  inp.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); d.querySelector('#navGo').click(); } };
  d.querySelector('#navGo').onclick = async e => {
    e.preventDefault();
    if (d.querySelector('#navGo').disabled) return;
    d.close();
    const to = inp.value.trim();
    let n = 0;
    const back = S.active;
    for (const { f } of touched) {
      // every file changes in the editor (the closed ones are opened): Ctrl+Z works, nothing is saved before you save
      let t = f.tab;
      if (!t) { await openFile(S.project, f.name); t = S.tabs.find(x => x.key === S.project + '/' + f.name); }
      const doc = t.doc, text = doc.getValue();
      const marks = [];
      text.replace(re, (m, at) => { marks.push(at); return m; });
      for (const at of marks.reverse()) doc.replaceRange(to, doc.posFromIndex(at), doc.posFromIndex(at + word.length), '+rename');
      n += marks.length;
      t.dirty = doc.getValue() !== t.saved;
    }
    if (back) activate(back);
    renderTabs();
    out(TF('Renamed {0} to {1} in {2} places. Save to keep it (Ctrl+S, or Check / Upload / Build save it).', word, to, n), 'ok');
  };
  d.showModal();
  inp.select();
}

/* ---------------- Include library (sketches) ---------------- */
async function navInclude(x, y) {
  const t = cpTab();
  if (!t || cpLang(t.name) !== 'ino') return out(T('Include library is for sketch files (.ino, .cpp, .h).'), 'warn');
  if (!NAV.libs) {
    const r = await api('/api/libs/installed');
    NAV.libs = r.ok === false ? { libraries: [], builtin: [] } : r;
  }
  const items = (NAV.libs.builtin || []).map(n => ({ label: n + '  (' + T('built in') + ')', hdr: [n + '.h'] }));
  (NAV.libs.libraries || []).filter(l => !(NAV.libs.builtin || []).includes(l.name))
    .forEach(l => items.push({ label: l.name + (l.version ? '  ' + l.version : ''), hdr: l.headers && l.headers.length ? l.headers : [l.name + '.h'] }));
  const menu = items.map(it => ({ label: it.label, run: () => navAddInclude(it.hdr) }));
  menu.push('-', { label: T('Manage libraries ...'), run: () => { const b = $('btnLibs'); if (b) b.click(); } });
  if (x === undefined) { const r = $('edInclude').getBoundingClientRect(); x = r.left; y = r.bottom + 4; }
  ptMenu(x, y, menu);
}
function navAddInclude(headers) {
  const doc = S.cm.getDoc(), lines = doc.getValue().split('\n');
  const have = new Set(lines.map(l => (l.match(/^\s*#include\s*[<"]([^>"]+)[>"]/) || [])[1]).filter(Boolean));
  const add = headers.filter(h => !have.has(h));
  if (!add.length) return out(TF('{0} is included already.', headers.join(', ')), 'warn');
  // after the last #include near the top, or at the very top
  let at = -1;
  lines.forEach((l, i) => { if (/^\s*#include\b/.test(l) && i < 200) at = i; });
  const text = add.map(h => `#include <${h}>`).join('\n') + '\n';
  doc.replaceRange(text, { line: at + 1, ch: 0 }, null, '+include');
  if (at < 0 && lines[0].trim()) doc.replaceRange('\n', { line: add.length, ch: 0 });
  cpJump(at + 1);
  out(TF('Added: {0}', add.map(h => '#include <' + h + '>').join(', ')), 'ok');
}

/* ---------------- right-click in the editor ---------------- */
function navMenu(x, y) {
  const word = navWord(), t = cpTab(), sketch = t && cpLang(t.name) === 'ino';
  const cm = S.cm, hasSel = !!cm.getSelection();
  ptMenu(x, y, [
    { label: T('Go to definition') + '  F12', disabled: !word, run: navDefinition },
    { label: T('Find every use') + '  Shift+F12', disabled: !word, run: () => navUses(word) },
    { label: T('Rename in every file ...') + '  Ctrl+Shift+R', disabled: !word, run: navRename },
    { label: T('Reference') + '  F2', disabled: !word, run: cpRefWord },
    '-',
    { label: T('Cut'), disabled: !hasSel, run: () => { navigator.clipboard.writeText(cm.getSelection()); cm.replaceSelection(''); } },
    { label: T('Copy'), disabled: !hasSel, run: () => navigator.clipboard.writeText(cm.getSelection()) },
    { label: T('Paste'), run: async () => { try { cm.replaceSelection(await navigator.clipboard.readText()); } catch (e) { out(T('Paste with Ctrl+V.'), 'warn'); } } },
    { label: T('Comment / uncomment') + '  Ctrl+/', run: () => cm.execCommand('toggleComment') },
    '-',
    { label: T('Auto Format') + '  Ctrl+T', run: autoFormat },
    ...(sketch ? [{ label: T('Include library ...'), run: () => navInclude(x, y) }] : []),
  ]);
}

/* ---------------- wiring ---------------- */
(function navStart() {
  const ready = setInterval(() => {
    if (!S.cm) return;
    clearInterval(ready);
    S.cm.addKeyMap({ 'F12': () => navDefinition(), 'Shift-F12': () => navUses(), 'Ctrl-Shift-R': () => navRename() });
    S.cm.getWrapperElement().addEventListener('contextmenu', e => {
      e.preventDefault();
      // right-click moves the cursor there first (unless it is inside the selection)
      const pos = S.cm.coordsChar({ left: e.clientX, top: e.clientY }, 'window'), sel = S.cm.listSelections()[0];
      const inSel = sel && CodeMirror.cmpPos(pos, CodeMirror.cmpPos(sel.anchor, sel.head) < 0 ? sel.anchor : sel.head) >= 0 &&
        CodeMirror.cmpPos(pos, CodeMirror.cmpPos(sel.anchor, sel.head) < 0 ? sel.head : sel.anchor) <= 0 && S.cm.getSelection();
      if (!inSel) S.cm.setCursor(pos);
      navMenu(e.clientX, e.clientY);
    });
    const b = $('edInclude');
    if (b) b.onclick = e => { e.preventDefault(); navInclude(); };
    const show = () => { const t = cpTab(); if (b) b.hidden = !(t && cpLang(t.name) === 'ino'); };
    S.cm.on('swapDoc', show); show();
  }, 300);
})();
