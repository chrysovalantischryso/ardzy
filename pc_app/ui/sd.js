/* Ardzy - SD card writer dialog: board, image, card, board settings, what the app does after the first start,
   write with progress. And "Build an image": an Ardzy image made from the sources in WSL. */
const SD = { disks: [], disk: null, timer: null, busy: false, images: [], boards: [], board: null };
const gb = b => (b / 1e9).toFixed(b >= 1e10 ? 0 : 1) + ' GB';

// which board an image is for: images of other boards have the board in the name (ardzy_debian13_ebaz4205.img)
function sdImageBoard(name) {
  const n = name.toLowerCase();
  const b = SD.boards.find(x => x.id !== 's9' && n.includes(x.id));
  return b ? b.id : 's9';
}

async function openSd() {
  $('sdProg').hidden = true;
  $('sdGo').disabled = false;
  document.querySelectorAll('[data-sd]').forEach(el => {
    const d = { hostname: 'ardzy', network: 'auto', timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC', ssh: 'on', at_boot: 'pin-control' }[el.dataset.sd];
    if (el.tagName === 'SELECT') { if (d && [...el.options].some(o => o.value === d)) el.value = d; }
    else el.value = d || '';
  });
  const app = await api('/api/app');
  SD.boards = app.boards || [{ id: 's9', name: 'Antminer S9' }];
  SD.board = SD.board || app.board_id || app.target_board || 's9';
  $('sdBoard').innerHTML = SD.boards.map(b => `<option value="${esc(b.id)}" ${b.id === SD.board ? 'selected' : ''}>${esc(b.name)}</option>`).join('');
  $('dlgSd').showModal();
  await Promise.all([sdImages(), sdDisks(), sdBoardNotes(), sdFirstRun()]);
}

async function sdBoardNotes() {
  const r = await api('/api/board/profile?id=' + encodeURIComponent(SD.board));
  const p = r.ok ? r.profile : null;
  $('sdBoardNotes').innerHTML = p ? `<ul>${((p.boot || {}).notes || []).map(n => `<li>${esc(T(n))}</li>`).join('')}</ul>` +
    (p.hardware_tested ? '' : `<b>${esc(T('This board is supported from its published pin maps and tested in the emulator, not yet on a real board: please report how it goes.'))}</b>`) : '';
}

async function sdImages(extra) {
  const r = await api('/api/sd/images');
  const all = r.images || [];
  if (extra && !all.some(i => i.path === extra.path)) all.unshift(extra);
  SD.images = all;
  const imgs = all.filter(i => sdImageBoard(i.name) === SD.board || (extra && i.path === extra.path));
  $('sdImg').innerHTML = imgs.map(i => `<option value="${esc(i.path)}">${esc(i.name)} (${(i.size / 2 ** 20).toFixed(0)} MB${i.date ? ', ' + i.date : ''})</option>`).join('')
    || `<option value="">${esc(T('no image for this board: Build an image, or Choose file'))}</option>`;
  if (extra) $('sdImg').value = extra.path;
}

// what the app does when it finds the new board the first time
async function sdFirstRun() {
  const [l, p] = await Promise.all([api('/api/langs'), api('/api/projects')]);
  $('sdLangs').innerHTML = (l.langs || []).filter(x => !x.builtin).map(x =>
    `<label><input type="checkbox" value="${esc(x.id)}"> ${esc(x.name)} <small class="hint">${x.size ? x.size[0] + ' MB' : ''}</small></label>`).join('');
  const projects = (p.projects || []).map(x => x.name);
  $('sdProjects').innerHTML = projects.map(n => `<label><input type="checkbox" value="${esc(n)}"> ${esc(n)}</label>`).join('')
    || `<span class="hint">${esc(T('no projects yet'))}</span>`;
  $('sdStart').innerHTML = `<option value="">${esc(T('(as in the settings above: At power-on)'))}</option>` +
    projects.map(n => `<option value="${esc(n)}">${esc(n)}</option>`).join('');
  $('sdStart').onchange = () => {                    // the start project is sent too
    const c = $('sdProjects').querySelector(`input[value="${CSS.escape($('sdStart').value)}"]`);
    if (c) c.checked = true;
  };
}

async function sdDisks() {
  $('sdDisks').innerHTML = '<div class="hint">looking for cards ...</div>';
  const r = await api('/api/sd/disks');
  SD.disks = r.disks || [];
  const ok = SD.disks.filter(d => d.ok);
  if (SD.disk && !ok.some(d => d.number === SD.disk.number)) SD.disk = null;
  if (!SD.disk && ok.length === 1) SD.disk = ok[0];
  $('sdDisks').innerHTML = SD.disks.map(d => `<div class="item ${d.ok ? '' : 'used'} ${SD.disk && SD.disk.number === d.number ? 'active' : ''}" data-n="${d.number}">
      <span><b>${esc(d.name || 'disk ' + d.number)}</b> &middot; ${gb(d.size)} &middot; ${esc(d.bus)}${d.letters.length ? ' &middot; ' + esc(d.letters.join(' ')) : ''}</span>
      <small>${d.ok ? 'can be written' : esc(d.why)}</small></div>`).join('')
    + (ok.length ? '' : '<div class="hint">No microSD card found. Put the card in the reader (USB or built in), then Refresh.</div>');
  $('sdDisks').querySelectorAll('.item:not(.used)').forEach(el => el.onclick = () => {
    SD.disk = SD.disks.find(d => d.number === +el.dataset.n);
    sdDisks();
  });
}

async function sdGo(e) {
  e.preventDefault();
  if (SD.busy) return;
  const img = $('sdImg').value;
  if (!img) return alert(T('Choose an Ardzy image first.'));
  if (!SD.disk) return alert(T('Choose the microSD card.'));
  const ib = sdImageBoard(img.split(/[\\/]/).pop());
  if (ib !== SD.board && !confirm(TF('This image looks made for the {0}, not the {1}. A card for another board does not start. Write it anyway?',
    (SD.boards.find(b => b.id === ib) || {}).name || ib, (SD.boards.find(b => b.id === SD.board) || {}).name || SD.board))) return;
  const settings = {};
  document.querySelectorAll('[data-sd]').forEach(el => settings[el.dataset.sd] = el.value.trim());
  if (!/^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$/.test(settings.hostname)) return alert('Board name: small letters, digits and -');
  if (settings.network === 'static' && !/^\d+\.\d+\.\d+\.\d+\/\d+$/.test(settings.address)) return alert('Fixed address like 192.168.1.50/24');
  const checked = id => [...$(id).querySelectorAll('input:checked')].map(c => c.value);
  const firstrun = { languages: checked('sdLangs'), projects: checked('sdProjects'), start: $('sdStart').value };
  if (firstrun.start && !firstrun.projects.includes(firstrun.start)) firstrun.projects.push(firstrun.start);
  const d = SD.disk;
  if (!confirm(`EVERYTHING on this card will be erased:\n\n    ${d.name}  (${gb(d.size)}, ${d.bus}${d.letters.length ? ', ' + d.letters.join(' ') : ''})\n\nWrite ${img.split(/[\\/]/).pop()} to it?`)) return;
  const r = await api('/api/sd/flash', { disk: d.number, name: d.name, size: d.size, image: img, verify: $('sdVerify').checked, settings, firstrun, board: SD.board });
  if (!r.ok) return alert(r.out);
  SD.busy = true;
  $('sdGo').disabled = true;
  $('sdProg').hidden = false;
  $('sdBar').style.width = '0%';
  const poll = async () => {
    const p = await api('/api/sd/progress', { progress: r.progress });
    const pct = p.total ? 100 * p.done / p.total : (p.phase === 'done' ? 100 : 0);
    $('sdBar').style.width = pct.toFixed(1) + '%';
    $('sdBar').parentElement.className = 'bar' + (p.phase === 'error' ? ' err' : '');
    $('sdText').textContent = (p.text || p.phase) + (p.mbps ? `  (${p.mbps.toFixed(1)} MB/s)` : '');
    if (p.phase === 'done' || p.phase === 'error') {
      SD.busy = false;
      $('sdGo').disabled = false;
      if (p.phase === 'done') $('sdText').textContent += '. ' + TF('Put the card in the board and power it on (the start-up notes above): after about 2 minutes Ardzy finds it as {0}.local', settings.hostname) +
        (firstrun.languages.length || firstrun.projects.length ? ' ' + T('and then sets it up as chosen in step 4.') : '');
      sdDisks();
      return;
    }
    SD.timer = setTimeout(poll, 700);
  };
  poll();
}

/* ---------------- Build an image (WSL) ---------------- */
async function openBuild() {
  $('ibState').innerHTML = esc(T('looking for WSL and the Ardzy sources ...'));
  if (!$('dlgBuild').open) $('dlgBuild').showModal();
  const st = await api('/api/imagebuild/status');
  const yes = t => `<span class="ok">${esc(t)}</span>`, no = t => `<span class="no">${esc(t)}</span>`;
  const b = st.built || {};
  $('ibBoard').innerHTML = (st.boards || []).map(x => `<option value="${esc(x.id)}" ${x.id === SD.board ? 'selected' : ''}>${esc(x.name)}</option>`).join('');
  $('ibState').innerHTML = [
    'WSL: ' + (st.wsl ? yes(st.distro) : no(T('not installed')) + ' ' + esc(T('(administrator PowerShell: wsl --install -d Ubuntu-20.04, then restart Windows)'))),
    esc(T('Sources')) + ': ' + (st.sources ? yes(st.sources) : no(T('not found'))) +
      ` <button class="ghost small" id="ibGet">${esc(T('Get the sources'))}</button> <button class="ghost small" id="ibPick">${esc(T('Choose folder'))}</button>`,
    !st.distro ? '' : st.built === null ? no(T('WSL did not answer: ') + (st.error || '')) :
      esc(T('Already built in WSL')) + ': ' + [['tools', T('compiler')], ['sources', 'U-Boot + Linux'], ['kernel', T('kernel')], ['rootfs', 'Debian']]
        .map(([k, t]) => b[k] ? yes(t + ' ' + T('(done)')) : no(t + ' ' + T('(to build)'))).join(' &middot; '),
    st.images && st.images.length ? esc(T('Images')) + ': ' + st.images.map(i => esc(`${i.name} (${i.date})`)).join(', ') : '',
  ].filter(Boolean).join('<br>');
  $('ibGo').disabled = !st.wsl || !st.sources || st.built === null || !!S.busy;
  $('ibGet').onclick = async e => { e.preventDefault(); const r = await api('/api/imagebuild/sources', {}); if (!r.ok) return alert(r.out); showTab('output'); waitJob(openBuild); };
  $('ibPick').onclick = async e => { e.preventDefault(); const r = await api('/api/imagebuild/sources', { pick: 1 }); if (!r.ok) return alert(r.out); openBuild(); };
}

function waitJob(then) {
  const t = setInterval(() => { if (!S.busy) { clearInterval(t); then(); } }, 1500);
}

async function buildGo(e) {
  e.preventDefault();
  const opts = { board: $('ibBoard').value, steps: $('ibSteps').value, packages: $('ibPkgs').value.trim(), examples: $('ibEx').value.trim(), version: $('ibVer').value.trim() };
  const r = await api('/api/imagebuild/start', opts);
  if (!r.ok) return alert(r.out);
  showTab('output');
  $('ibGo').disabled = true;
  setTimeout(() => waitJob(() => { $('ibGo').disabled = false; SD.board = opts.board; if ($('dlgSd').open) { $('sdBoard').value = opts.board; sdImages(); } }), 2000);
}

$('btnSd').onclick = openSd;
$('sdDiskRefresh').onclick = e => { e.preventDefault(); sdDisks(); };
$('sdBoard').onchange = () => { SD.board = $('sdBoard').value; sdImages(); sdBoardNotes(); };
$('sdImgPick').onclick = async e => {
  e.preventDefault();
  const r = await api('/api/sd/pick', {});
  if (r.ok) sdImages({ path: r.path, name: r.path.split(/[\\/]/).pop(), size: r.size });
};
$('sdBuild').onclick = e => { e.preventDefault(); openBuild(); };
$('sdGo').onclick = sdGo;
$('sdClose').onclick = e => { if (SD.busy && !confirm('The card is still being written (in its own window). Close this dialog anyway?')) e.preventDefault(); };
$('ibGo').onclick = buildGo;
$('ibStop').onclick = async e => { e.preventDefault(); if (confirm(T('Stop the image build?'))) await api('/api/imagebuild/stop', {}); };
