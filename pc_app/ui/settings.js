/* Ardzy - App settings: language, look (theme, accent colour, background, size, font, density, corners, motion),
   text (Monitor / Output), behaviour (start view, tooltips, sounds, bottom panel), and the engine settings
   (workspace, Vivado, board names, FPGA tool). Everything here is kept in this PC's app storage (ardzy.app).
   Uses app.js (S, $, esc, api, out, pref, setPref, setTheme, editorFont, editorWrap) and i18n.js (T, I18N_LANGS). */

const APP_DEFAULT = { accent: '', palette: 'ardzy', zoom: 100, font: 'Segoe UI', density: 'comfy', corners: 'normal', calm: false,
  termSize: 13.5, termFont: 'Cascadia Mono', termLh: 1.5, startView: 'last', tips: true, sound: false, panel: 'keep' };
const APP = (() => { try { return Object.assign({}, APP_DEFAULT, JSON.parse(pref('app', '{}')) || {}); } catch (e) { return Object.assign({}, APP_DEFAULT); } })();
const appSave = () => setPref('app', JSON.stringify(APP));

const APP_ACCENTS = ['#2fbf6c', '#13894a', '#3d8fe0', '#6c63ff', '#9b6be0', '#d65a9c', '#e05050', '#e8743b', '#d4a020', '#20a3a3', '#64748b'];
const APP_FONTS = ['Segoe UI', 'Segoe UI Variable', 'system-ui', 'Arial', 'Verdana', 'Tahoma', 'Calibri', 'Bahnschrift', 'Trebuchet MS', 'Georgia'];
const APP_TERM_FONTS = ['Cascadia Mono', 'Cascadia Code', 'Consolas', 'Lucida Console', 'Courier New'];
// background palettes: [light, dark]; empty = the built-in one
const APP_PALETTES = {
  ardzy: ['Ardzy (green-grey)', null, null],
  neutral: ['Neutral grey',
    { bg: '#f4f4f5', panel: '#ffffff', side: '#efeff1', line: '#dadade', hover: '#e7e7ea', sel: '#d6e4f5', 'code-bg': '#fcfcfd' },
    { bg: '#141416', panel: '#1b1b1e', side: '#161618', line: '#2b2b30', hover: '#232327', sel: '#2b3a52', 'code-bg': '#18181b' }],
  blue: ['Blue night',
    { bg: '#f1f5fb', panel: '#ffffff', side: '#eaf0f8', line: '#d3dcea', hover: '#e2eaf5', sel: '#cfe0f7', 'code-bg': '#fafcff' },
    { bg: '#0f1520', panel: '#151d2a', side: '#111823', line: '#233044', hover: '#1b2535', sel: '#23395a', 'code-bg': '#121a26' }],
  warm: ['Warm sand',
    { bg: '#f7f3ec', panel: '#fffdf9', side: '#f1ebe1', line: '#e0d6c6', hover: '#ece4d6', sel: '#efdcc0', 'code-bg': '#fffcf6' },
    { bg: '#17130f', panel: '#1f1a14', side: '#1a1611', line: '#332a20', hover: '#2a231b', sel: '#4a3a24', 'code-bg': '#1b1712' }],
  contrast: ['High contrast',
    { bg: '#ffffff', panel: '#ffffff', side: '#f2f2f2', line: '#000000', hover: '#e6e6e6', sel: '#ffe680', 'code-bg': '#ffffff', text: '#000000', muted: '#222222' },
    { bg: '#000000', panel: '#000000', side: '#000000', line: '#ffffff', hover: '#222222', sel: '#1d4a8a', 'code-bg': '#000000', text: '#ffffff', muted: '#dddddd' }],
};
const APP_VARS = ['bg', 'panel', 'side', 'line', 'hover', 'sel', 'code-bg', 'text', 'muted', 'accent', 'accent-2', 'accent-text'];

const appDark = () => document.documentElement.dataset.theme === 'dark' ||
  (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
function appShade(hex, k) {                                       // k < 0 darker, k > 0 lighter
  const n = parseInt(hex.slice(1), 16), c = [n >> 16, n >> 8 & 255, n & 255].map(v => Math.round(k < 0 ? v * (1 + k) : v + (255 - v) * k));
  return '#' + c.map(v => v.toString(16).padStart(2, '0')).join('');
}
function appLuma(hex) { const n = parseInt(hex.slice(1), 16); return (0.299 * (n >> 16) + 0.587 * (n >> 8 & 255) + 0.114 * (n & 255)) / 255; }

function appApply() {
  const r = document.documentElement.style, dark = appDark();
  APP_VARS.forEach(v => r.removeProperty('--' + v));
  const pal = APP_PALETTES[APP.palette] && APP_PALETTES[APP.palette][dark ? 2 : 1];
  if (pal) Object.entries(pal).forEach(([k, v]) => r.setProperty('--' + k, v));
  if (APP.accent) {
    r.setProperty('--accent', APP.accent);
    r.setProperty('--accent-2', appShade(APP.accent, dark ? 0.12 : -0.15));
    r.setProperty('--accent-text', appLuma(APP.accent) > 0.55 ? '#06120b' : '#ffffff');
  }
  r.setProperty('--font', `"${APP.font}", "Segoe UI", system-ui, sans-serif`);
  r.setProperty('--term-size', APP.termSize + 'px');
  r.setProperty('--term-lh', String(APP.termLh));
  r.setProperty('--term-font', `"${APP.termFont}", Consolas, monospace`);
  document.body.style.zoom = APP.zoom === 100 ? '' : String(APP.zoom / 100);
  document.body.classList.toggle('dense', APP.density === 'compact');
  document.body.classList.toggle('calm', !!APP.calm);
  document.body.classList.remove('corners-sharp', 'corners-round');
  if (APP.corners !== 'normal') document.body.classList.add('corners-' + APP.corners);
  if (!APP.tips) appTipsOff(document.body);
  setTimeout(() => window.dispatchEvent(new Event('resize')), 0);   // (charts and the editor measure again)
}
// tooltips off: the title attributes move aside (they come back when tips are on again and the window reloads)
function appTipsOff(root) {
  if (root.nodeType !== 1) return;
  if (root.hasAttribute('title')) { root.dataset.tip = root.getAttribute('title'); root.removeAttribute('title'); }
  root.querySelectorAll('[title]').forEach(e => { e.dataset.tip = e.getAttribute('title'); e.removeAttribute('title'); });
}

// a short sound when a job ends: higher = done, lower = failed
function appSound(ok) {
  if (!APP.sound) return;
  try {
    const a = new (window.AudioContext || window.webkitAudioContext)(), o = a.createOscillator(), g = a.createGain();
    o.frequency.value = ok ? 880 : 300; o.type = 'sine';
    g.gain.setValueAtTime(0.0001, a.currentTime); g.gain.exponentialRampToValueAtTime(0.15, a.currentTime + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, a.currentTime + (ok ? 0.25 : 0.45));
    o.connect(g); g.connect(a.destination); o.start(); o.stop(a.currentTime + 0.5);
  } catch (e) { }
}

// ------------------------------------------------------------------ the window
const APP_SECTIONS = [['general', 'General'], ['look', 'Look'], ['text', 'Text'], ['behavior', 'Behavior'], ['board', 'Board and FPGA'], ['about', 'About']];
let appSection = 'general', appEngine = null;
async function appOpen(section) {
  if (section) appSection = section;
  appEngine = await api('/api/app');
  const tc = await api('/api/fpga/toolchain');
  appEngine.toolInfo = tc.builtin ? 'Built-in toolchain: ' + tc.dir : 'Built-in toolchain not found (tools/fpga).';
  appRender();
  if (!$('dlgApp').open) $('dlgApp').showModal();
}
function appRender() {
  $('appNav').innerHTML = APP_SECTIONS.map(([k, t]) => `<button class="${k === appSection ? 'on' : ''}" data-s="${k}">${esc(T(t))}</button>`).join('');
  $('appNav').querySelectorAll('button').forEach(b => b.onclick = e => { e.preventDefault(); appSection = b.dataset.s; appRender(); });
  const opt = (v, t, cur) => `<option value="${esc(v)}" ${String(v) === String(cur) ? 'selected' : ''}>${esc(t)}</option>`;
  const chk = (k, t) => `<label class="check"><input type="checkbox" data-app="${k}" ${APP[k] ? 'checked' : ''}> ${esc(T(t))}</label>`;
  const set = appEngine.settings || {};
  let h = '';
  if (appSection === 'general') {
    h = `<label>${T('Language')} <select id="appLang">${Object.entries(I18N_LANGS).map(([k, t]) => opt(k, t, I18N_LANG)).join('')}</select></label>
      <p class="hint">${T('The window reloads to change the language.')}</p>
      <label>${T('Theme')} <select id="appTheme">${opt('', T('same as Windows'), pref('theme', ''))}${opt('light', T('light'), pref('theme', ''))}${opt('dark', T('dark'), pref('theme', ''))}</select></label>
      <label>${T('Projects folder (workspace)')} <input id="appWs" value="${esc(set.workspace || '')}" spellcheck="false"></label>
      <label>${T('Board names to try (comma separated)')} <input id="appHosts" value="${esc((set.manual_hosts || []).join(', '))}" spellcheck="false"></label>
      <div class="row"><button class="primary small" id="appSaveEngine">${T('Save')}</button><span class="hint" id="appSaved"></span></div>`;
  } else if (appSection === 'look') {
    h = `<label>${T('Accent colour')}</label>
      <div class="app-swatches">${['', ...APP_ACCENTS].map(c => `<button class="sw ${c === APP.accent ? 'on' : ''}" data-c="${c}" style="--c:${c || 'var(--ok)'}" title="${c || 'Ardzy'}">${c ? '' : 'A'}</button>`).join('')}
        <label class="sw-custom">${T('your own colour')} <input type="color" id="appColor" value="${APP.accent || '#2fbf6c'}"></label></div>
      <div class="ed-grid">
        <label>${T('Background')} <select data-app="palette">${Object.entries(APP_PALETTES).map(([k, p]) => opt(k, T(p[0]), APP.palette)).join('')}</select></label>
        <label>${T('App size')} <select data-app="zoom">${[80, 90, 100, 110, 125, 150].map(n => opt(n, n + ' %', APP.zoom)).join('')}</select></label>
        <label>${T('Font')} <select data-app="font">${APP_FONTS.map(f => opt(f, f, APP.font)).join('')}</select></label>
        <label>${T('Density')} <select data-app="density">${opt('comfy', T('comfortable'), APP.density)}${opt('compact', T('compact'), APP.density)}</select></label>
        <label>${T('Corners')} <select data-app="corners">${opt('sharp', T('sharp'), APP.corners)}${opt('normal', T('normal'), APP.corners)}${opt('round', T('round'), APP.corners)}</select></label>
      </div>
      ${chk('calm', 'less motion (no animations)')}
      <div class="app-preview"><b>${T('Preview')}</b> <button class="ghost small" onclick="return false">${T('A button')}</button>
        <button class="primary small" onclick="return false">${T('Main button')}</button> <span class="seg"><button class="on">1</button><button>2</button></span>
        <span class="hint">hint text</span> <code>code</code></div>`;
  } else if (appSection === 'text') {
    h = `<div class="ed-grid">
        <label>${T('Monitor and Output text')} <select data-app="termSize">${[11, 12, 12.5, 13, 13.5, 14, 15, 16, 18].map(n => opt(n, n + ' px', APP.termSize)).join('')}</select></label>
        <label>${T('Monitor font')} <select data-app="termFont">${APP_TERM_FONTS.map(f => opt(f, f, APP.termFont)).join('')}</select></label>
        <label>${T('Line spacing')} <select data-app="termLh">${[1.25, 1.35, 1.5, 1.65, 1.8].map(n => opt(n, n, APP.termLh)).join('')}</select></label>
      </div>
      <pre class="app-term">12:00:01  RESULT: 8 of 8 ok\n12:00:02  temp:54.2 fan:1200</pre>
      <div class="row"><button class="ghost small" id="appEditor">${T('Code editor: font, size, colours')}</button></div>`;
  } else if (appSection === 'behavior') {
    const views = [['last', T('the view I used last')], ['code', T('Code')], ['board', T('Board')], ['io', T('I/O')], ['tools', T('Tools')], ['gallery', T('Ready projects')],
      ['blocks', T('Blocks')], ['learn', T('Learn')], ['map', T('Map')], ['system', T('System')]];
    h = `<div class="ed-grid">
        <label>${T('Open at start')} <select data-app="startView">${views.map(([k, t]) => opt(k, t, APP.startView)).join('')}</select></label>
        <label>${T('Bottom panel at start')} <select data-app="panel">${opt('keep', T('as I left it'), APP.panel)}${opt('open', T('shown'), APP.panel)}${opt('hidden', T('hidden'), APP.panel)}</select></label>
      </div>
      ${chk('tips', 'Show tooltips (help when pointing at a button)')}${chk('sound', 'Sound when a job ends (upload, build, simulation)')}`;
  } else if (appSection === 'board') {
    h = `<label>${T('FPGA build tool')} <select id="appTool">${opt('builtin', T('Built-in (Yosys + nextpnr, no Vivado needed)'), set.fpga_tool || 'builtin')}${opt('vivado', 'Vivado (build.tcl)', set.fpga_tool)}</select></label>
      <p class="hint">${esc(appEngine.toolInfo)}</p>
      <label>Vivado (vivado.bat) <input id="appViv" value="${esc(set.vivado || '')}" spellcheck="false"></label>
      <div class="row"><button class="primary small" id="appSaveEngine">${T('Save')}</button><span class="hint" id="appSaved"></span></div>`;
  } else {
    h = `<p><b>Ardzy ${esc(appEngine.version || '0.2a')} ${esc(appEngine.stage || 'BETA')}</b>: ${T('the Antminer S9 control board used like an Arduino.')}</p>
      <p class="hint">${T('This is a BETA version: it works, but some parts may still change. Please report problems on GitHub.')}</p>
      <p class="hint">${T('Made by chryso. Open source under the GNU GPL version 3.')}</p>
      <p class="hint">${esc(appEngine.settings_file || '')}</p>
      <div class="row"><button class="ghost small" id="appExport">${T('Export settings')}</button>
        <label class="ghost small btnlike">${T('Import settings')}<input type="file" id="appImport" accept=".json" hidden></label>
        <button class="ghost small" id="appReset">${T('Reset all settings')}</button></div>
      <p class="hint" id="appSaved"></p>`;
  }
  $('appBody').innerHTML = h;
  // wiring
  $('appBody').querySelectorAll('[data-app]').forEach(el => el.onchange = () => {
    const k = el.dataset.app;
    APP[k] = el.type === 'checkbox' ? el.checked : ['zoom', 'termSize', 'termLh'].includes(k) ? +el.value : el.value;
    appSave(); appApply();
    if (k === 'tips' && APP.tips) location.reload();
  });
  if ($('appLang')) $('appLang').onchange = () => { try { localStorage.setItem('ardzy.lang', $('appLang').value); } catch (e) { } location.reload(); };
  if ($('appTheme')) $('appTheme').onchange = () => { setTheme($('appTheme').value); appApply(); };
  $('appBody').querySelectorAll('.sw').forEach(b => b.onclick = e => { e.preventDefault(); APP.accent = b.dataset.c; appSave(); appApply(); appRender(); });
  if ($('appColor')) $('appColor').oninput = () => { APP.accent = $('appColor').value; appSave(); appApply(); };
  if ($('appEditor')) $('appEditor').onclick = e => { e.preventDefault(); $('dlgApp').close(); $('edSet').click(); };
  if ($('appSaveEngine')) $('appSaveEngine').onclick = async e => {
    e.preventDefault();
    const s = appEngine.settings || {}, body = { workspace: s.workspace, vivado: s.vivado, manual_hosts: s.manual_hosts || [], fpga_tool: s.fpga_tool || 'builtin' };
    if ($('appWs')) body.workspace = $('appWs').value.trim();
    if ($('appHosts')) body.manual_hosts = $('appHosts').value.split(',').map(x => x.trim()).filter(Boolean);
    if ($('appViv')) body.vivado = $('appViv').value.trim();
    if ($('appTool')) body.fpga_tool = $('appTool').value;
    const r = await api('/api/settings', body);
    $('appSaved').textContent = r.ok === false ? r.out : T('Saved.');
    appEngine = await api('/api/app');
    refreshProjects();
  };
  if ($('appExport')) $('appExport').onclick = async e => {
    e.preventDefault();
    const all = {};
    try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k.startsWith('ardzy.')) all[k] = localStorage.getItem(k); } } catch (x) { }
    const r = await api('/api/savelog', { name: 'ardzy_settings', ext: 'txt', text: JSON.stringify(all, null, 1) });
    $('appSaved').textContent = r.ok ? r.path : r.out;
  };
  if ($('appImport')) $('appImport').onchange = async () => {
    const f = $('appImport').files[0]; if (!f) return;
    try { const all = JSON.parse(await f.text()); Object.entries(all).forEach(([k, v]) => { if (k.startsWith('ardzy.')) localStorage.setItem(k, v); }); location.reload(); }
    catch (x) { $('appSaved').textContent = 'not a settings file: ' + x.message; }
  };
  if ($('appReset')) $('appReset').onclick = e => {
    e.preventDefault();
    if (!confirm('Reset every look, text and behaviour setting of the app on this PC? (Projects and board settings stay.)')) return;
    try { Object.keys(localStorage).filter(k => k.startsWith('ardzy.')).forEach(k => localStorage.removeItem(k)); } catch (x) { }
    location.reload();
  };
}

// ------------------------------------------------------------------ start
(function appStart() {
  appApply();
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', appApply);
  const t0 = window.setTheme;
  window.setTheme = t => { t0(t); appApply(); };
  if (!APP.tips) new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(appTipsOff))).observe(document.body, { childList: true, subtree: true });
  // remember the view; open the chosen one at start (a link with #view= wins)
  const sv0 = window.showView;
  window.showView = v => { sv0(v); try { localStorage.setItem('ardzy.lastView', v); } catch (e) { } };
  window.appStartView = () => APP.startView === 'last' ? (pref('lastView', 'code') || 'code') : APP.startView;
  const t0start = Date.now();
  window.onJobEnd = (name, state) => { if (Date.now() - t0start > 5000) appSound(state === 'ok'); };   // (not for the jobs replayed at start)
  if (APP.panel !== 'keep') {
    const hidden = $('bottom').classList.contains('collapsed');
    if ((APP.panel === 'hidden') !== hidden && S.panelToggle) S.panelToggle();
  }
  $('btnSettings').onclick = () => appOpen();
  document.addEventListener('keydown', e => { if (e.ctrlKey && e.key === ',') { e.preventDefault(); appOpen(); } });   // Ctrl+, = App settings
  const hs = (location.hash.match(/settings=(\w+)/) || [])[1];         // a link that opens a section: #settings=look
  if (hs) setTimeout(() => appOpen(hs), 800);
})();

i18nStart();
