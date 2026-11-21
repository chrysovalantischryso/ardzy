/* Ardzy - versions of a project (engine: versions.py, /api/versions/*).
   Save a version with a note, see what changed (against now or the version before), take one file
   or the whole project back. Every going-back saves the files first, so it can be undone.
   An automatic version is saved before each upload (Settings in this window: on / off).
   Uses app.js (S, $, esc, api, out, T, TF, refreshProjects, openFile) and projtools.js (ptDialog). */

const VS = { project: '', list: null, sel: null, other: 'now' };

async function vsOpen(project) {
  project = project || S.project;
  if (!project) return out(T('Choose a project first.'), 'warn');
  VS.project = project; VS.sel = null; VS.other = 'now';
  const d = ptDialog('dlgVersions', TF('Versions: {0}', project));
  d.classList.add('vs-dlg');
  d.querySelector('.ptbody').innerHTML = `
    <div class="vs-save row">
      <input id="vsMsg" placeholder="${esc(T('What did you change? (a short note, optional)'))}" maxlength="200">
      <button class="primary" id="vsSaveBtn">${T('Save a version')}</button>
    </div>
    <p class="hint" id="vsNow"></p>
    <div class="vs-main">
      <div class="vs-list" id="vsList"></div>
      <div class="vs-view">
        <div class="vs-head row" id="vsHead"></div>
        <div class="vs-diff" id="vsDiff"><p class="hint">${T('Choose a version on the left to see what is different.')}</p></div>
      </div>
    </div>`;
  d.querySelector('.ptfoot').innerHTML = `<label class="vs-auto"><input type="checkbox" id="vsAuto"> ${T('Save a version by itself before each upload')}</label>
    <span style="flex:1"></span><button value="close" class="primary">${T('Close')}</button>`;
  $('vsSaveBtn').onclick = e => { e.preventDefault(); vsSave(); };
  $('vsMsg').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); vsSave(); } };
  $('vsAuto').onchange = () => api('/api/versions/auto', { project, on: $('vsAuto').checked ? 1 : 0 });
  if (!d.open) d.showModal();
  await vsLoad();
  $('vsMsg').focus();
}

async function vsLoad() {
  const r = await api('/api/versions/list', { project: VS.project });
  if (!r.ok) { $('vsList').innerHTML = `<p class="l-err">${esc(r.out)}</p>`; return; }
  VS.list = r.versions;
  $('vsAuto').checked = !!r.auto;
  const n = r.now, changes = n.added.length + n.removed.length + n.changed.length;
  $('vsNow').innerHTML = !r.versions.length ? esc(T('No versions yet. Save one now: you can always come back to it.'))
    : r.clean ? `<span class="l-ok">${esc(T('The files are the same as the newest version.'))}</span>`
    : (r.same_as ? esc(TF('The files are the same as v{0}.', r.same_as)) + ' ' : '') +
      esc(TF('Changed since the newest version: {0}', vsChangeText(n))) +
      ` <a href="#" id="vsSeeNow">${T('show')}</a>`;
  const see = $('vsSeeNow');
  if (see) see.onclick = e => { e.preventDefault(); vsSelect(r.versions[0].id, 'now'); };
  $('vsList').innerHTML = r.versions.map(v => `<div class="vs-item ${v.id === VS.sel ? 'sel' : ''} ${v.auto ? 'auto' : ''}" data-id="${v.id}">
      <div class="vs-top"><b>v${v.id}</b>${v.pinned ? ` <span class="vs-tag pin" title="${esc(T('kept: never removed by itself'))}">${T('kept')}</span>` : ''}
        ${v.auto ? `<span class="vs-tag">${T('auto')}</span>` : ''}<span class="hint vs-time">${esc(v.time)}</span></div>
      <div class="vs-msg">${esc(v.message || T('(no note)'))}</div>
      <div class="hint vs-cnt">${esc(vsChangeText(v))}</div></div>`).join('') ||
    `<p class="hint">${T('No versions yet.')}</p>`;
  $('vsList').querySelectorAll('.vs-item').forEach(el => el.onclick = () => vsSelect(+el.dataset.id, VS.other));
  $('vsList').title = TF('{0} KB stored', Math.ceil(r.size / 1024));
  if (VS.sel && r.versions.some(v => v.id === VS.sel)) vsSelect(VS.sel, VS.other);
}

function vsChangeText(c) {
  const p = [];
  if (c.changed.length) p.push(TF('{0} changed', c.changed.length));
  if (c.added.length) p.push(TF('{0} new', c.added.length));
  if (c.removed.length) p.push(TF('{0} removed', c.removed.length));
  return p.join(', ') || T('no file changed');
}

async function vsSave() {
  const message = $('vsMsg').value;
  await vsSaveOpenTabs();
  const r = await api('/api/versions/save', { project: VS.project, message });
  if (!r.ok) return alert(r.out);
  if (!r.id) out(T(r.out), 'warn');
  $('vsMsg').value = '';
  VS.sel = r.id || VS.sel;
  await vsLoad();
}

// unsaved editor changes belong in a version too
async function vsSaveOpenTabs() {
  const dirty = S.tabs.filter(t => t.project === VS.project && t.dirty);
  for (const t of dirty) await saveTab(t);
}

async function vsSelect(id, other) {
  VS.sel = id; VS.other = other || 'now';
  $('vsList').querySelectorAll('.vs-item').forEach(el => el.classList.toggle('sel', +el.dataset.id === id));
  const idx = VS.list.findIndex(v => v.id === id), prev = VS.list[idx + 1];
  const v = VS.list[idx];
  $('vsHead').innerHTML = `<span><b>v${id}</b> ${T('against')}</span>
    <select id="vsOther"><option value="now">${T('the files now')}</option>
      ${prev ? `<option value="${prev.id}">${TF('the version before (v{0})', prev.id)}</option>` : ''}
      ${VS.list.filter(x => x.id !== id && (!prev || x.id !== prev.id)).map(x => `<option value="${x.id}">v${x.id} ${esc((x.message || '').slice(0, 30))}</option>`).join('')}</select>
    <span style="flex:1"></span>
    <button class="ghost small" id="vsNote" title="${esc(T('Change the note'))}">${T('Note')}</button>
    <button class="ghost small" id="vsPin">${v.pinned ? T('Do not keep') : T('Keep')}</button>
    <button class="ghost small" id="vsDel">${T('Remove')}</button>
    <button class="primary small" id="vsBack">${TF('Go back to v{0}', id)}</button>`;
  $('vsOther').value = String(VS.other);
  if ($('vsOther').value !== String(VS.other)) { VS.other = 'now'; $('vsOther').value = 'now'; }
  $('vsOther').onchange = () => vsSelect(id, $('vsOther').value);
  $('vsNote').onclick = async e => {
    e.preventDefault();
    const m = prompt(T('Note of this version:'), v.message || '');
    if (m !== null && (await api('/api/versions/edit', { project: VS.project, id, message: m })).ok) vsLoad();
  };
  $('vsPin').onclick = async e => { e.preventDefault(); if ((await api('/api/versions/edit', { project: VS.project, id, pinned: !v.pinned })).ok) vsLoad(); };
  $('vsDel').onclick = async e => {
    e.preventDefault();
    if (!confirm(TF('Remove version v{0}? Its files are gone after this (the project folder does not change).', id))) return;
    if ((await api('/api/versions/delete', { project: VS.project, id })).ok) { VS.sel = null; $('vsHead').innerHTML = ''; $('vsDiff').innerHTML = ''; vsLoad(); }
  };
  $('vsBack').onclick = e => { e.preventDefault(); vsRestore(id); };
  $('vsDiff').innerHTML = `<p class="hint">${T('Comparing ...')}</p>`;
  const r = await api('/api/versions/diff', { project: VS.project, id, other: VS.other });
  if (VS.sel !== id) return;
  if (!r.ok) { $('vsDiff').innerHTML = `<p class="l-err">${esc(r.out)}</p>`; return; }
  if (!r.files.length) { $('vsDiff').innerHTML = `<p class="hint l-ok">${esc(TF('{0} and {1} have the same files.', r.a, r.b === 'now' ? T('the files now') : r.b))}</p>`; return; }
  $('vsDiff').innerHTML = r.files.map((f, i) => `<details class="vs-file" ${r.files.length <= 4 || i === 0 ? 'open' : ''}>
      <summary><span class="vs-st ${f.state}">${esc(T(f.state))}</span> <span class="mono">${esc(f.file)}</span>
        ${f.lines ? `<span class="vs-pm"><span class="l-ok">+${f.plus}</span> <span class="l-err">-${f.minus}</span></span>` : `<span class="hint">${T('(not a text file)')}</span>`}
        <span style="flex:1"></span>
        ${f.state !== 'added' || VS.other !== 'now' ? `<button class="ghost small vs-take" data-f="${esc(f.file)}" ${f.state === 'added' ? 'disabled' : ''}>${TF('Take this file from v{0}', id)}</button>` : ''}
        ${f.state !== 'added' && /\.(py|c|h|v|sv|ino|cpp|hpp|json|txt|xdc|sh|js|lua|go|rs|md|S|s|pl)$/.test(f.file) ? `<button class="ghost small vs-show" data-f="${esc(f.file)}">${T('Show')}</button>` : ''}
      </summary>${f.lines ? vsDiffHtml(f.lines) : ''}</details>`).join('');
  $('vsDiff').querySelectorAll('.vs-take').forEach(b => b.onclick = e => { e.preventDefault(); vsRestore(id, b.dataset.f); });
  $('vsDiff').querySelectorAll('.vs-show').forEach(b => b.onclick = e => { e.preventDefault(); vsShow(id, b.dataset.f); });
}

function vsDiffHtml(lines) {
  let a = 0, b = 0;
  return '<pre class="vs-code">' + lines.map(l => {
    const m = l.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
    if (m) { a = +m[1]; b = +m[2]; return `<div class="vs-hunk">${esc(l)}</div>`; }
    const c = l[0], body = esc(l.slice(1)) || ' ';
    if (c === '+') return `<div class="vs-add"><i></i><i>${b++}</i>+${body}</div>`;
    if (c === '-') return `<div class="vs-del"><i>${a++}</i><i></i>-${body}</div>`;
    return `<div><i>${a++}</i><i>${b++}</i> ${body}</div>`;
  }).join('') + '</pre>';
}

async function vsShow(id, file) {
  const r = await api('/api/versions/file', { project: VS.project, id, file });
  if (!r.ok) return alert(r.out);
  const lines = r.text.split('\n');
  $('vsDiff').innerHTML = `<p class="row"><a href="#" id="vsBackDiff">&larr; ${T('back to the differences')}</a>
      <span class="hint">${esc(TF('{0} as it was in v{1} ({2} lines)', file, id, lines.length))}</span></p>
    <pre class="vs-code">${lines.map((l, i) => `<div><i>${i + 1}</i>${esc(l) || ' '}</div>`).join('')}</pre>`;
  $('vsBackDiff').onclick = e => { e.preventDefault(); vsSelect(id, VS.other); };
}

async function vsRestore(id, file) {
  const what = file ? TF('{0} as it was in v{1}', file, id) : TF('all files of {0} as they were in v{1}', VS.project, id);
  if (!confirm(TF('Bring back {0}? The files as they are now are saved first as a version, so you can come back.', what))) return;
  await vsSaveOpenTabs();
  const r = await api('/api/versions/restore', { project: VS.project, id, file: file || '' });
  if (!r.ok) return alert(r.out);
  out(r.saved_before ? TF('Back as in v{0}. The files before are v{1}.', id, r.saved_before) : TF('Back as in v{0}.', id), 'ok');
  await vsReloadTabs(file);
  await refreshProjects();
  await vsLoad();
}

// open editor tabs of the project show the files as they are now on the disk
async function vsReloadTabs(file) {
  for (const t of S.tabs.filter(t => t.project === VS.project && (!file || t.name === file))) {
    const r = await api('/api/file?project=' + encodeURIComponent(t.project) + '&name=' + encodeURIComponent(t.name));
    if (!r.ok) { t.dirty = false; closeTab(t.key); continue; }       // the file is not in that version
    t.loading = true; t.doc.setValue(r.text); t.loading = false;
    t.saved = r.text; t.dirty = false;
  }
  renderTabs();
}

(function vsStart() {
  // Ctrl+Alt+S: save a version of the open project at once (no window)
  document.addEventListener('keydown', async e => {
    if (e.ctrlKey && e.altKey && !e.shiftKey && (e.key === 's' || e.key === 'S')) {
      e.preventDefault();
      if (!S.project) return;
      VS.project = S.project;
      await vsSaveOpenTabs();
      const r = await api('/api/versions/save', { project: S.project, message: '' });
      out(r.ok ? (r.id ? TF('{0}: version {1} saved (Versions window: Ctrl+Alt+V).', S.project, r.id) : T(r.out)) : r.out, r.ok ? 'ok' : 'err');
    } else if (e.ctrlKey && e.altKey && (e.key === 'v' || e.key === 'V')) {
      e.preventDefault(); vsOpen();
    }
  });
})();
