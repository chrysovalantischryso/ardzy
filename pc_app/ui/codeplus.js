/* Ardzy - Code view extras: editor settings (fonts, tabs, rulers, themes, auto-save ...), a side panel with the
   outline of the file, snippets, the API reference and search in the project, the Problems list (compiler and
   Python errors as clickable lines with markers in the editor), autocomplete, folding and a richer status bar.
   Uses app.js (S, $, esc, api, out, openFile, activate, saveActive, modeFor, pref, setPref, showTab) and code_ref.js. */

// ------------------------------------------------------------------ editor settings
const ED_DEFAULT = { font: 14, family: 'Cascadia Mono', lh: 1.55, tab: 4, tabs: false, nums: true, wrap: false, active: true,
  brackets: true, close: true, ruler: 0, ws: false, fold: true, hint: true, theme: 'ardzy', autosave: 0, cursor: 'line', outline: true };
const ED = (() => {
  let s = {};
  try { s = JSON.parse(pref('ed', '{}')) || {}; } catch (e) { s = {}; }
  const o = Object.assign({}, ED_DEFAULT, s);
  if (!s.font && pref('font', '')) o.font = +pref('font', 14);           // (the settings before 0.2 kept these two alone)
  if (s.wrap === undefined && pref('wrap', '')) o.wrap = true;
  return o;
})();
const ED_FONTS = ['Cascadia Mono', 'Cascadia Code', 'Consolas', 'JetBrains Mono', 'Fira Code', 'Source Code Pro', 'Courier New', 'Lucida Console'];
const ED_THEMES = {
  ardzy: { name: 'Ardzy (follows the app look)' },
  paper: { name: 'Paper (light)', bg: '#fdfcf8', text: '#24292f', muted: '#8a8f87', sel: '#d7e6f7', act: '#f2efe4', gut: '#f6f4ec',
    kw: '#a626a4', def: '#4078f2', str: '#50a14f', num: '#986801', com: '#a0a1a7', type: '#c18401', meta: '#a626a4', atom: '#0184bc', prop: '#e45649' },
  midnight: { name: 'Midnight (dark)', bg: '#0f1419', text: '#d9e1e8', muted: '#5c6773', sel: '#253340', act: '#151c23', gut: '#0f1419',
    kw: '#ff8f40', def: '#ffb454', str: '#aad94c', num: '#d2a6ff', com: '#5c6773', type: '#59c2ff', meta: '#e6b673', atom: '#d2a6ff', prop: '#95e6cb' },
  contrast: { name: 'High contrast', bg: '#000000', text: '#ffffff', muted: '#bbbbbb', sel: '#1d4a8a', act: '#1a1a1a', gut: '#000000',
    kw: '#ff79ff', def: '#7fd8ff', str: '#ffe066', num: '#7dff9a', com: '#9ad09a', type: '#7fd8ff', meta: '#ff79ff', atom: '#ffa060', prop: '#ffffff' },
  forest: { name: 'Forest (dark green)', bg: '#0e1a14', text: '#dcebe2', muted: '#6f8c7c', sel: '#1f4a35', act: '#13241b', gut: '#0e1a14',
    kw: '#7fdca4', def: '#f2cc60', str: '#e8a46a', num: '#b9a6ff', com: '#6f8c7c', type: '#6fc3df', meta: '#7fdca4', atom: '#ff9ac1', prop: '#9fd6ff' },
};
function edThemeCss() {
  let css = '';
  for (const [k, t] of Object.entries(ED_THEMES)) {
    if (!t.bg) continue;
    const p = `#editor.edth-${k}`, c = `${p} .cm-s-default`;
    css += `${p} .CodeMirror { background: ${t.bg}; color: ${t.text}; }
      ${p} .CodeMirror-gutters { background: ${t.gut}; border-right-color: ${t.sel}; }
      ${p} .CodeMirror-linenumber { color: ${t.muted}; } ${p} .CodeMirror-cursor { border-left-color: ${t.text}; }
      ${p} .CodeMirror-activeline-background { background: ${t.act}; }
      ${p} .CodeMirror-selected, ${p} .CodeMirror-focused .CodeMirror-selected { background: ${t.sel}; }
      ${c} .cm-keyword, ${c} .cm-qualifier, ${c} .cm-tag { color: ${t.kw}; } ${c} .cm-def, ${c} .cm-builtin { color: ${t.def}; }
      ${c} .cm-string, ${c} .cm-string-2 { color: ${t.str}; } ${c} .cm-number, ${c} .cm-variable-2 { color: ${t.num}; }
      ${c} .cm-comment { color: ${t.com}; } ${c} .cm-type, ${c} .cm-variable-3 { color: ${t.type}; } ${c} .cm-meta { color: ${t.meta}; }
      ${c} .cm-atom { color: ${t.atom}; } ${c} .cm-property, ${c} .cm-attribute { color: ${t.prop}; }
      ${c} .cm-variable, ${c} .cm-operator { color: ${t.text}; } ${c} .cm-bracket { color: ${t.muted}; }
      ${p} .CodeMirror-foldgutter-open, ${p} .CodeMirror-foldgutter-folded { color: ${t.muted}; }\n`;
  }
  const st = document.createElement('style');
  st.textContent = css;
  document.head.appendChild(st);
}

const WS_OVERLAY = { token: s => {                                 // shows spaces as dots and tabs as arrows
  if (s.peek() === ' ') { s.next(); return 'ws'; }
  if (s.peek() === '\t') { s.next(); return 'wstab'; }
  s.match(/^[^ \t]+/) || s.next();
  return null;
} };

function edApply() {
  const cm = S.cm, o = ED;
  setPref('ed', JSON.stringify(o));
  setPref('font', o.font); setPref('wrap', o.wrap ? '1' : '');
  const box = $('editor');
  box.className = 'edth-' + o.theme + (o.cursor === 'block' ? ' edcur-block' : '');
  box.style.setProperty('--ed-font', `${o.font}px/${o.lh} "${o.family}", Consolas, monospace`);
  cm.setOption('tabSize', +o.tab);
  cm.setOption('indentUnit', +o.tab);
  cm.setOption('indentWithTabs', !!o.tabs);
  cm.setOption('lineNumbers', !!o.nums);
  cm.setOption('lineWrapping', !!o.wrap);
  cm.setOption('styleActiveLine', !!o.active);
  cm.setOption('matchBrackets', !!o.brackets);
  cm.setOption('autoCloseBrackets', !!o.close);
  cm.setOption('rulers', o.ruler ? [{ column: +o.ruler, className: 'ed-ruler' }] : []);
  cm.setOption('foldGutter', !!o.fold);
  cm.setOption('gutters', ['cp-problems', 'CodeMirror-linenumbers'].concat(o.fold ? ['CodeMirror-foldgutter'] : []));
  cm.removeOverlay(WS_OVERLAY);
  if (o.ws) cm.addOverlay(WS_OVERLAY);
  cm.refresh();
  cpStatus();
}
// the old font / wrap commands (keys Ctrl +/-/0, Alt+Z and the Settings dialog) now go through these settings
window.editorFont = px => { ED.font = Math.max(10, Math.min(28, +px || 14)); edApply(); };
window.editorWrap = on => { ED.wrap = !!on; edApply(); };

function edDialog() {
  const o = ED, opt = (v, t, cur) => `<option value="${esc(v)}" ${String(v) === String(cur) ? 'selected' : ''}>${esc(t)}</option>`;
  const chk = (k, t) => `<label class="check"><input type="checkbox" data-ed="${k}" ${o[k] ? 'checked' : ''}> ${t}</label>`;
  $('edForm').innerHTML = `
    <div class="ed-grid">
      <label>Font <select data-ed="family">${ED_FONTS.map(f => opt(f, f, o.family)).join('')}</select></label>
      <label>Size <select data-ed="font">${[11, 12, 13, 14, 15, 16, 17, 18, 20, 22, 24].map(n => opt(n, n + ' px', o.font)).join('')}</select></label>
      <label>Line height <select data-ed="lh">${[1.3, 1.4, 1.5, 1.55, 1.65, 1.8, 2].map(n => opt(n, n, o.lh)).join('')}</select></label>
      <label>Colours <select data-ed="theme">${Object.entries(ED_THEMES).map(([k, t]) => opt(k, t.name, o.theme)).join('')}</select></label>
      <label>Indent <select data-ed="tab">${[2, 3, 4, 8].map(n => opt(n, n + ' columns', o.tab)).join('')}</select></label>
      <label>Indent with <select data-ed="tabs">${opt('', 'spaces', o.tabs ? '1' : '')}${opt('1', 'tab characters', o.tabs ? '1' : '')}</select></label>
      <label>Ruler at column <select data-ed="ruler">${[0, 72, 80, 100, 120].map(n => opt(n, n ? n : 'none', o.ruler)).join('')}</select></label>
      <label>Auto-save <select data-ed="autosave">${[[0, 'off (Ctrl+S)'], [1000, 'after 1 s'], [3000, 'after 3 s'], [10000, 'after 10 s']].map(([v, t]) => opt(v, t, o.autosave)).join('')}</select></label>
      <label>Cursor <select data-ed="cursor">${opt('line', 'thin line', o.cursor)}${opt('block', 'block', o.cursor)}</select></label>
    </div>
    <div class="ed-checks">
      ${chk('nums', 'line numbers')}${chk('wrap', 'wrap long lines')}${chk('active', 'highlight the current line')}
      ${chk('brackets', 'show the matching bracket')}${chk('close', 'close brackets and quotes by itself')}
      ${chk('ws', 'show spaces and tabs')}${chk('fold', 'fold blocks (arrows next to the line numbers)')}
      ${chk('hint', 'suggest words while typing (Ctrl+Space any time)')}${chk('outline', 'open the side panel with new files')}
    </div>
    <pre class="ed-preview" id="edPreview"></pre>`;
  $('edForm').querySelectorAll('[data-ed]').forEach(el => el.onchange = () => {
    const k = el.dataset.ed;
    ED[k] = el.type === 'checkbox' ? el.checked : (k === 'family' || k === 'theme' || k === 'cursor') ? el.value
      : k === 'tabs' ? el.value === '1' : +el.value;
    edApply(); edPreview();
  });
  edPreview();
  $('dlgEditor').showModal();
}
function edPreview() {
  const p = $('edPreview');
  if (!p) return;
  p.style.font = `${ED.font}px/${ED.lh} "${ED.family}", Consolas, monospace`;
  p.textContent = 'void loop() {\n' + ' '.repeat(+ED.tab) + 'digitalWrite(LED0, HIGH);   // 0O 1lI {}[]\n}';
}

// ------------------------------------------------------------------ language of the open file
function cpLang(name) {
  if (!name) return null;
  if (/\.(ino|cpp|hpp|h)$/.test(name)) return 'ino';
  if (/\.py$/.test(name)) return 'py';
  if (/\.s?v$/.test(name)) return 'v';
  if (/\.c$/.test(name)) return 'c';
  return null;
}
const LANG_NAME = { ino: 'Arduino C++', py: 'Python', v: 'Verilog', c: 'C' };
const cpTab = () => S.tabs.find(t => t.key === S.active);

// ------------------------------------------------------------------ status bar
function cpStatus() {
  const t = cpTab();
  if (!$('stLang')) return;
  if (!t) { $('stLang').textContent = ''; $('stInfo').textContent = ''; return; }
  const ext = (t.name.match(/\.(\w+)$/) || [, ''])[1];
  $('stLang').textContent = LANG_NAME[cpLang(t.name)] || (ext ? ext.toUpperCase() : 'text');
  const d = t.doc, n = d.lineCount(), size = new Blob([d.getValue()]).size;
  $('stInfo').textContent = `${TF('{0} lines', n)} · ${size < 1024 ? size + ' B' : (size / 1024).toFixed(1) + ' KB'} · ${T(ED.tabs ? 'tabs' : 'spaces')}: ${ED.tab}`;
}

// ------------------------------------------------------------------ side panel: outline, snippets, reference, search
const CP = { side: pref('side', ED.outline ? 'outline' : ''), problems: [], outT: null, refAll: false, find: { q: '', re: false, cs: false } };

function cpSide(which) {
  CP.side = which === CP.side ? '' : which;
  setPref('side', CP.side);
  cpSideRender();
}
function cpSideRender() {
  const open = !!CP.side;
  $('codeSide').hidden = !open;
  document.querySelectorAll('#edTools [data-side]').forEach(b => b.classList.toggle('on', b.dataset.side === CP.side));
  if (S.cm) setTimeout(() => S.cm.refresh(), 0);
  if (!open) return;
  $('csHead').textContent = { outline: 'Outline', snippets: 'Snippets', ref: 'Reference', search: 'Search in the project' }[CP.side];
  if (CP.side === 'outline') cpOutline();
  if (CP.side === 'snippets') cpSnippets();
  if (CP.side === 'ref') cpRef();
  if (CP.side === 'search') cpSearchUi();
}

// outline: the parts of the file you can jump to
function cpSymbols(text, lang) {
  const out = [], lines = text.split('\n');
  const add = (kind, name, line, depth = 0) => out.push({ kind, name, line, depth });
  const CKW = /^(if|for|while|switch|return|else|do|sizeof|case)$/;
  lines.forEach((l, i) => {
    let m;
    if (lang === 'py') {
      if ((m = l.match(/^(\s*)(def|class)\s+(\w+)/))) add(m[2] === 'class' ? 'class' : 'func', m[3], i, m[1].length ? 1 : 0);
      else if ((m = l.match(/^([A-Z][A-Z0-9_]+)\s*=/))) add('const', m[1], i);
      else if ((m = l.match(/^\s*#\s*-{3,}\s*(.+?)\s*-*$/))) add('section', m[1], i);
    } else if (lang === 'ino' || lang === 'c') {
      if ((m = l.match(/^#define\s+(\w+)/))) add('const', m[1], i);
      else if ((m = l.match(/^#include\s*"([^"]+)/))) add('include', m[1], i);     // (own files only, not <stdio.h> ...)
      else if ((m = l.match(/^(?:class|struct|enum)\s+(\w+)/))) add('class', m[1], i);
      else if ((m = l.match(/^[A-Za-z_][\w:<>,\s\*&]*?[\s\*&]([A-Za-z_]\w*(?:::\w+)?)\s*\([^;]*$/)) && !CKW.test(m[1])) add('func', m[1], i);
      else if ((m = l.match(/^\s*\/\/\s*-{3,}\s*(.+?)\s*-*$/))) add('section', m[1], i);
    } else if (lang === 'v') {
      if ((m = l.match(/^\s*module\s+(\w+)/))) add('class', m[1], i);
      else if ((m = l.match(/^\s*(input|output|inout)\b[^;,)]*?(\w+)\s*[,;)]?\s*(\/\/.*)?$/))) add('port', m[2] + '  (' + m[1] + ')', i, 1);
      else if ((m = l.match(/^\s*(?:localparam|parameter)\s+(?:\[[^\]]*\]\s*)?(\w+)/))) add('const', m[1], i, 1);
      else if ((m = l.match(/^\s*(?:reg|wire)\s+(?:signed\s+)?(?:\[[^\]]*\]\s*)?(\w+)/))) add('signal', m[1], i, 1);
      else if ((m = l.match(/^\s*always\s*@\s*\(([^)]*)\)/))) add('func', 'always @(' + m[1].trim() + ')', i, 1);
      else if ((m = l.match(/^\s*(function|task)\s+(?:\[[^\]]*\]\s*)?(\w+)/))) add('func', m[2], i, 1);
      else if ((m = l.match(/^\s*([a-z_]\w*)\s*(?:#\s*\(.*?\))?\s+(u_\w+|\w+_i|inst\w*|\w+)\s*\(/)) &&
               !/^(module|if|for|case|assign|always|initial|function|task|begin|wire|reg|input|output|inout|localparam|parameter|else)$/.test(m[1]))
        add('inst', m[2] + ': ' + m[1], i, 1);
    } else if ((m = l.match(/^(#{1,4})\s+(.+)/))) add('section', m[2], i, m[1].length - 1);
  });
  return out;
}
const SYM_ICON = { func: 'ƒ', class: '◆', const: 'π', include: '⤓', section: '§', port: '⇄', signal: '∿', inst: '▣' };
function cpOutline() {
  if (CP.side !== 'outline') return;
  const t = cpTab();
  if (!t) { $('csBody').innerHTML = '<p class="hint">Open a file to see its parts here.</p>'; return; }
  const lang = cpLang(t.name) || (t.name.endsWith('.md') ? 'md' : null);
  const syms = cpSymbols(t.doc.getValue(), lang), q = (($('csFilter') || {}).value || '').toLowerCase();
  const cur = t.doc.getCursor().line;
  let here = -1;
  syms.forEach((s, i) => { if (s.line <= cur) here = i; });
  $('csBody').innerHTML = `<input type="search" id="csFilter" placeholder="filter (Ctrl+Shift+O)" value="${esc(q)}" spellcheck="false">
    <div class="cs-list">${syms.filter(s => !q || s.name.toLowerCase().includes(q)).map(s => `
      <div class="cs-sym k-${s.kind}${syms.indexOf(s) === here ? ' here' : ''}" data-line="${s.line}" style="padding-left:${8 + s.depth * 14}px">
        <span class="ic">${SYM_ICON[s.kind] || '·'}</span><span class="nm">${esc(s.name)}</span><span class="ln">${s.line + 1}</span></div>`).join('')
      || `<p class="hint">${lang ? 'Nothing found.' : 'No outline for this kind of file.'}</p>`}</div>
    <p class="hint">${syms.length} parts · click to jump</p>`;
  const f = $('csFilter');
  f.oninput = () => { const pos = f.selectionStart; cpOutline(); $('csFilter').focus(); $('csFilter').setSelectionRange(pos, pos); };
  $('csBody').querySelectorAll('.cs-sym').forEach(el => el.onclick = () => cpJump(+el.dataset.line));
}
function cpJump(line, ch = 0) {
  const cm = S.cm;
  cm.focus();
  cm.setCursor({ line, ch });
  cm.scrollIntoView({ line, ch }, cm.getScrollInfo().clientHeight / 3);
  const h = cm.addLineClass(line, 'background', 'cp-flash');
  setTimeout(() => cm.removeLineClass(h, 'background', 'cp-flash'), 1200);
}

// snippets
function cpInsert(code) {
  const cm = S.cm, t = cpTab();
  if (!t) { out('Open a file first, then insert.', 'warn'); return; }
  const cur = cm.getCursor(), lineText = cm.getLine(cur.line), ind = (lineText.match(/^\s*/) || [''])[0];
  const unit = ED.tabs ? '\t' : ' '.repeat(+ED.tab);
  let text = code.replace(/^( {2})+/gm, m => unit.repeat(m.length / 2));     // the snippets use 2 spaces per level
  text = text.split('\n').map((l, i) => i && l ? ind + l : l).join('\n');
  const at = text.indexOf('|');
  text = text.replace('|', '');
  const from = cm.indexFromPos(cur);
  cm.replaceRange(text, cur);
  cm.setCursor(cm.posFromIndex(from + (at < 0 ? text.length : at)));
  cm.focus();
}
function cpSnippets() {
  const t = cpTab(), lang = t ? cpLang(t.name) : null;
  const list = CODE_SNIPPETS.filter(s => !lang || s[1] === lang);
  $('csBody').innerHTML = `<p class="hint">${lang ? 'For ' + LANG_NAME[lang] + ' files.' : 'Open a file to insert into it.'} Click to insert at the cursor.</p>` +
    list.map(([n, l, code], i) => `<div class="cs-snip" data-i="${CODE_SNIPPETS.indexOf(list[i])}"><b>${esc(n)}</b><span class="tag">${LANG_NAME[l]}</span>
      <pre>${esc(code.replace('|', '').split('\n').slice(0, 5).join('\n'))}${code.split('\n').length > 5 ? '\n...' : ''}</pre></div>`).join('');
  $('csBody').querySelectorAll('.cs-snip').forEach(el => el.onclick = () => cpInsert(CODE_SNIPPETS[+el.dataset.i][2]));
}

// reference
function cpRef() {
  const t = cpTab(), lang = t ? cpLang(t.name) : null;
  const q = (($('csRefQ') || {}).value || '').toLowerCase();
  const list = CODE_REF.filter(r => (CP.refAll || !lang || r[3] === lang) &&
    (!q || (r[0] + ' ' + r[1] + ' ' + r[2]).toLowerCase().includes(q)));
  $('csBody').innerHTML = `<input type="search" id="csRefQ" placeholder="search the reference" value="${esc(q)}" spellcheck="false">
    <label class="check"><input type="checkbox" id="csRefAll" ${CP.refAll || !lang ? 'checked' : ''} ${lang ? '' : 'disabled'}> all languages</label>
    <div class="cs-list">${list.map(r => `<div class="cs-ref"><div class="rn">${esc(r[0])}<span class="tag">${LANG_NAME[r[3]]}</span></div>
      <code>${esc(r[1])}</code><div class="rd">${esc(r[2])}</div>
      ${r[4] ? `<pre>${esc(r[4])}</pre><button class="ghost small" data-ins="${CODE_REF.indexOf(r)}">Insert example</button>` : ''}</div>`).join('')
      || '<p class="hint">Nothing found.</p>'}</div>`;
  const qi = $('csRefQ');
  qi.oninput = () => { const pos = qi.selectionStart; cpRef(); $('csRefQ').focus(); $('csRefQ').setSelectionRange(pos, pos); };
  $('csRefAll').onchange = () => { CP.refAll = $('csRefAll').checked; cpRef(); };
  $('csBody').querySelectorAll('[data-ins]').forEach(b => b.onclick = () => cpInsert(CODE_REF[+b.dataset.ins][4] + '|'));
}
// show the reference entry of the word under the cursor (F2)
function cpRefWord() {
  const cm = S.cm, w = cm.findWordAt(cm.getCursor()), word = cm.getRange(w.anchor, w.head);
  if (CP.side !== 'ref') cpSide('ref');
  $('csRefQ').value = word; cpRef();
}

// search in the project
function cpSearchUi() {
  const f = CP.find;
  $('csBody').innerHTML = `<input type="search" id="csFindQ" placeholder="text to find in every file" value="${esc(f.q)}" spellcheck="false">
    <div class="row"><label class="check"><input type="checkbox" id="csFindCs" ${f.cs ? 'checked' : ''}> match case</label>
    <label class="check"><input type="checkbox" id="csFindRe" ${f.re ? 'checked' : ''}> regular expression</label></div>
    <div id="csFindOut" class="cs-list"></div>`;
  const go = () => { f.q = $('csFindQ').value; f.cs = $('csFindCs').checked; f.re = $('csFindRe').checked; cpSearch(); };
  $('csFindQ').onkeydown = e => { if (e.key === 'Enter') go(); };
  $('csFindQ').oninput = () => { clearTimeout(CP.findT); CP.findT = setTimeout(go, 350); };
  $('csFindCs').onchange = go; $('csFindRe').onchange = go;
  $('csFindQ').focus();
  if (f.q) cpSearch();
}
async function cpSearch() {
  const f = CP.find, box = $('csFindOut');
  if (!box) return;
  const p = S.projects.find(p => p.name === S.project);
  if (!p || !f.q) { box.innerHTML = p ? '' : '<p class="hint">Choose a project first.</p>'; return; }
  let re;
  try { re = new RegExp(f.re ? f.q : f.q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), f.cs ? 'g' : 'gi'); }
  catch (e) { box.innerHTML = `<p class="hint">Not a valid expression: ${esc(e.message)}</p>`; return; }
  box.innerHTML = '<p class="hint">searching ...</p>';
  const res = [];
  let hits = 0;
  for (const name of p.files.filter(n => EDITABLE.test(n))) {
    const open = S.tabs.find(t => t.key === p.name + '/' + name);
    let text = open ? open.doc.getValue() : null;
    if (text === null) { const r = await api('/api/file?project=' + encodeURIComponent(p.name) + '&name=' + encodeURIComponent(name)); text = r.ok ? r.text : ''; }
    const lines = [];
    text.split('\n').forEach((l, i) => {
      re.lastIndex = 0;
      const m = re.exec(l);
      if (m && lines.length < 200) lines.push({ i, ch: m.index, len: m[0].length || 1, l });
    });
    if (lines.length) { res.push({ name, lines }); hits += lines.length; }
  }
  const mark = (l, ch, len) => esc(l.slice(Math.max(0, ch - 30), ch)) + '<mark>' + esc(l.substr(ch, len)) + '</mark>' + esc(l.slice(ch + len, ch + len + 60));
  box.innerHTML = `<p class="hint">${hits} line${hits === 1 ? '' : 's'} in ${res.length} file${res.length === 1 ? '' : 's'}</p>` +
    res.map(r => `<div class="cs-file">${esc(r.name)} <span class="ln">${r.lines.length}</span></div>` +
      r.lines.map(x => `<div class="cs-hit" data-f="${esc(r.name)}" data-l="${x.i}" data-c="${x.ch}"><span class="ln">${x.i + 1}</span>${mark(x.l.trimEnd(), x.ch, x.len)}</div>`).join('')).join('');
  box.querySelectorAll('.cs-hit').forEach(el => el.onclick = async () => {
    await openFile(S.project, el.dataset.f);
    cpJump(+el.dataset.l, +el.dataset.c);
  });
}

// ------------------------------------------------------------------ problems: compiler / Python / Verilog errors
const PROB_RES = [
  // gcc / Arduino:  name.ino:12:5: error: ...
  [/^\s*([\w.\-\/]+\.(?:ino|cpp|c|h|hpp|cc)):(\d+):(?:(\d+):)?\s*(fatal error|error|warning|note):\s*(.*)$/, m => ({ file: m[1], line: +m[2], col: +(m[3] || 1), kind: m[4], msg: m[5] })],
  // Yosys / Icarus:  top.v:12: ERROR: ...   top.v:12.5-12.9: ERROR: ...
  // (only lines that say error / warning: "top_tb.v:17: $finish called at ..." is not a problem)
  [/^\s*(?:ERROR:\s*)?([\w.\-\/]+\.s?v):(\d+)(?:[.\d-]*)?:\s*(ERROR|error|Warning|warning|syntax error|sorry)[:,]?\s*(.*)$/, m => ({ file: m[1], line: +m[2], col: 1,
    kind: /warn/i.test(m[3]) ? 'warning' : 'error', msg: (/syntax|sorry/.test(m[3]) ? m[3] + ' ' : '') + m[4] })],
  // Yosys:  ERROR: ... at top.v:12   and Icarus messages that name the file later in the line
  [/^\s*ERROR:\s*(.*?)\s+(?:at\s+)?([\w.\-\/]+\.s?v):(\d+)/, m => ({ file: m[2], line: +m[3], col: 1, kind: 'error', msg: m[1] })],
  // Python check:  main.py: ... (main.py, line 5)
  [/\(([\w.\-]+\.py), line (\d+)\)/, (m, l) => ({ file: m[1], line: +m[2], col: 1, kind: 'error', msg: l.replace(/^\s*[\w.\-]+\.py:\s*/, '').trim() })],
];
function cpProblemLine(text, from) {
  const t = text.replace(/^\s*\d\d:\d\d:\d\d\s+/, '');
  for (const [re, mk] of PROB_RES) {
    const m = t.match(re);
    if (m) { const p = mk(m, t); if (p.kind === 'note') return; p.file = p.file.split('/').pop(); p.from = from; cpAddProblem(p); return; }
  }
  // Python traceback in the Monitor:  File "/opt/ardzy/projects/x/main.py", line 12, in <module>  ...  NameError: ...
  let m = t.match(/File "([^"]+\.py)", line (\d+)/);
  if (m && /\/opt\/ardzy\/projects\/|^[\w.\-]+\.py$/.test(m[1])) { CP.pyLast = { file: m[1].split('/').pop(), line: +m[2], col: 1, kind: 'error', msg: 'Python error', from }; return; }
  m = t.match(/^(\w+(?:Error|Exception|Interrupt)):?\s*(.*)$/);
  if (m && CP.pyLast) { CP.pyLast.msg = m[1] + (m[2] ? ': ' + m[2] : ''); cpAddProblem(CP.pyLast); CP.pyLast = null; }
}
function cpAddProblem(p) {
  if (CP.problems.some(q => q.file === p.file && q.line === p.line && q.msg === p.msg)) return;
  CP.problems.push(p);
  clearTimeout(CP.probT);
  CP.probT = setTimeout(cpProblemsRender, 150);
}
function cpClearProblems(from) {
  CP.problems = CP.problems.filter(p => from && p.from !== from);
  cpProblemsRender();
}
function cpProblemsRender() {
  const errs = CP.problems.filter(p => p.kind !== 'warning').length, warns = CP.problems.length - errs;
  const b = document.querySelector('.bottom-tabs button[data-tab="problems"]');
  if (b) b.innerHTML = 'Problems' + (CP.problems.length ? ` <span class="pcount ${errs ? 'e' : 'w'}">${CP.problems.length}</span>` : '');
  if (CP.problems.length && errs) markNew('problems');
  $('probList').innerHTML = CP.problems.length ? `<div class="prob-sum">${errs} error${errs === 1 ? '' : 's'}, ${warns} warning${warns === 1 ? '' : 's'} · click a line to open the file there</div>` +
    CP.problems.map((p, i) => `<div class="prob ${p.kind === 'warning' ? 'w' : 'e'}" data-i="${i}"><span class="pi">${p.kind === 'warning' ? '!' : '×'}</span>
      <span class="pf">${esc(p.file)}:${p.line}</span><span class="pm">${esc(p.msg)}</span></div>`).join('')
    : '<div class="prob-sum">No problems. Check (Ctrl+R) or Upload shows compiler and Python errors here, with marks in the editor.</div>';
  $('probList').querySelectorAll('.prob').forEach(el => el.onclick = async () => {
    const p = CP.problems[+el.dataset.i], proj = S.projects.find(x => x.name === S.project);
    const name = proj && (proj.files.includes(p.file) ? p.file : proj.files.find(f => f.endsWith(p.file)));
    if (!name) { out(`${p.file} is not a file of project ${S.project}.`, 'warn'); return; }
    await openFile(S.project, name);
    cpJump(p.line - 1, Math.max(0, p.col - 1));
  });
  cpMarks();
}
function cpMarks() {                                            // red / yellow marks next to the lines of the open file
  const cm = S.cm, t = cpTab();
  if (!cm) return;
  cm.clearGutter('cp-problems');
  (CP.marked || []).forEach(h => cm.removeLineClass(h, 'background', 'cp-errline'));
  CP.marked = [];
  if (!t) return;
  for (const p of CP.problems.filter(p => p.file === t.name)) {
    const ln = p.line - 1;
    if (ln < 0 || ln >= cm.lineCount()) continue;
    const el = document.createElement('div');
    el.className = 'cp-mark ' + (p.kind === 'warning' ? 'w' : 'e');
    el.textContent = p.kind === 'warning' ? '!' : '●';
    el.title = p.msg;
    cm.setGutterMarker(ln, 'cp-problems', el);
    if (p.kind !== 'warning') CP.marked.push(cm.addLineClass(ln, 'background', 'cp-errline'));
  }
}

// ------------------------------------------------------------------ autocomplete
function cpHint(cm) {
  const cur = cm.getCursor(), line = cm.getLine(cur.line);
  let s = cur.ch;
  while (s && /[\w.$]/.test(line[s - 1])) s--;
  const word = line.slice(s, cur.ch);
  if (!word) return null;
  const t = cpTab(), lang = t ? cpLang(t.name) : null, seen = new Set(), list = [];
  const add = (text, hint, cls) => {
    if (seen.has(text) || text === word || !text.toLowerCase().startsWith(word.toLowerCase())) return;
    seen.add(text); list.push({ text, displayText: hint ? `${text}   ${hint}` : text, className: cls });
  };
  CODE_REF.filter(r => r[3] === lang && /^[\w.]+$/.test(r[0])).forEach(r => add(r[0], r[1].length < 60 ? r[1] : '', 'cp-h-api'));
  (CODE_WORDS[lang] || []).forEach(w => add(w, '', 'cp-h-kw'));
  if (lang === 'ino') for (let n = 1; n <= 9; n++) [5, 11, 12, 15].forEach(p => add(`J${n}_${p}`, `connector J${n} pin ${p}`, 'cp-h-pin'));
  const words = cm.getValue().match(/[A-Za-z_][\w]{2,}/g) || [];
  words.forEach(w => add(w, '', 'cp-h-doc'));
  if (!list.length) return null;
  return { list: list.slice(0, 60), from: CodeMirror.Pos(cur.line, s), to: cur };
}

// ------------------------------------------------------------------ wiring
function cpInit() {
  edThemeCss();
  const cm = S.cm;
  cm.setOption('foldOptions', { widget: '⋯', minFoldSize: 1 });
  cm.setOption('extraKeys', Object.assign({}, cm.getOption('extraKeys'), {
    'Ctrl-Space': c => c.showHint({ hint: cpHint, completeSingle: false }),
    'Ctrl-Q': c => c.foldCode(c.getCursor()),
    'Ctrl-Shift-O': () => { if (CP.side !== 'outline') cpSide('outline'); setTimeout(() => $('csFilter') && $('csFilter').focus(), 0); },
    'Ctrl-Shift-F': () => { if (CP.side !== 'search') cpSide('search'); const w = S.cm.getSelection(); if (w && $('csFindQ')) { $('csFindQ').value = w; CP.find.q = w; cpSearch(); } },
    'F2': () => cpRefWord(),
    'Ctrl-D': c => { const p = c.getCursor(), l = c.getLine(p.line); c.replaceRange('\n' + l, { line: p.line, ch: l.length }); c.setCursor({ line: p.line + 1, ch: p.ch }); },
    'Alt-Up': c => cpMoveLine(c, -1), 'Alt-Down': c => cpMoveLine(c, 1),
  }));
  edApply();
  cm.on('inputRead', (c, ch) => {
    if (!ED.hint || c.state.completionActive || !/[\w.]/.test(ch.text.join(''))) return;
    const cur = c.getCursor(), before = c.getLine(cur.line).slice(0, cur.ch);
    if (/[A-Za-z_][\w.]{1,}$/.test(before) && !/^\s*(\/\/|#)/.test(before)) c.showHint({ hint: cpHint, completeSingle: false });
  });
  cm.on('changes', () => {
    clearTimeout(CP.outT);
    CP.outT = setTimeout(() => { cpOutline(); cpStatus(); }, 400);
    if (ED.autosave) {
      clearTimeout(CP.saveT);
      CP.saveT = setTimeout(() => { const t = cpTab(); if (t && t.dirty) saveActive().then(() => cpSaved()); }, ED.autosave);
    }
  });
  cm.on('cursorActivity', () => { if (CP.side === 'outline') { clearTimeout(CP.curT); CP.curT = setTimeout(cpOutline, 250); } });
  cm.on('swapDoc', () => setTimeout(() => { cpMarks(); cpStatus(); if (CP.side) cpSideRender(); }, 0));
  // the outputs feed the Problems list; a new Check / Upload / Build starts a fresh list
  const app0 = window.appendLine;
  window.appendLine = function (pre, text, cls, time) {
    app0(pre, text, cls, time);
    if (pre === $('out')) {
      if (/^> (Check|Upload|Build FPGA|Simulate)/.test(text)) { cpClearProblems(); CP.pyLast = null; }
      else cpProblemLine(String(text), 'out');
    }
  };
  const mon0 = window.monAdd;
  if (mon0) window.monAdd = function (text, cls) { mon0(text, cls); if (/=== .*: starting program ===/.test(text)) cpClearProblems('mon'); cpProblemLine(String(text), 'mon'); };
  // the Save state in the status bar
  const save0 = window.saveTab;
  window.saveTab = async t => { const ok = await save0(t); if (ok) cpSaved(); return ok; };
  $('edTools').querySelectorAll('[data-side]').forEach(b => b.onclick = () => cpSide(b.dataset.side));
  $('edSet').onclick = edDialog;
  $('edBigger').onclick = () => window.editorFont(ED.font + 1);
  $('edSmaller').onclick = () => window.editorFont(ED.font - 1);
  $('stInfo').onclick = edDialog;
  $('csClose').onclick = () => cpSide(CP.side);
  cpProblemsRender();
  cpSideRender();
}
function cpSaved() { $('stSaved').textContent = 'saved ' + new Date().toTimeString().slice(0, 5); }
function cpMoveLine(cm, dir) {
  const p = cm.getCursor(), a = p.line, b = a + dir;
  if (b < 0 || b >= cm.lineCount()) return;
  const la = cm.getLine(a), lb = cm.getLine(b);
  cm.operation(() => {
    cm.replaceRange(lb, { line: a, ch: 0 }, { line: a, ch: la.length });
    cm.replaceRange(la, { line: b, ch: 0 }, { line: b, ch: lb.length });
    cm.setCursor({ line: b, ch: p.ch });
  });
}
cpInit();
