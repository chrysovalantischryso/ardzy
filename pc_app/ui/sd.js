/* Ardzy - SD card writer dialog: image, card, board settings, write with progress. */
const SD = { disks: [], disk: null, timer: null, busy: false };
const gb = b => (b / 1e9).toFixed(b >= 1e10 ? 0 : 1) + ' GB';

async function openSd() {
  $('sdProg').hidden = true;
  $('sdGo').disabled = false;
  document.querySelectorAll('[data-sd]').forEach(el => {
    const d = { hostname: 'ardzy', network: 'auto', timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC', ssh: 'on', at_boot: 'pin-control' }[el.dataset.sd];
    if (el.tagName === 'SELECT') { if (d && [...el.options].some(o => o.value === d)) el.value = d; }
    else el.value = d || '';
  });
  $('dlgSd').showModal();
  await Promise.all([sdImages(), sdDisks()]);
}

async function sdImages(extra) {
  const r = await api('/api/sd/images');
  const imgs = r.images || [];
  if (extra && !imgs.some(i => i.path === extra.path)) imgs.unshift(extra);
  $('sdImg').innerHTML = imgs.map(i => `<option value="${esc(i.path)}">${esc(i.name)} (${(i.size / 2 ** 20).toFixed(0)} MB${i.date ? ', ' + i.date : ''})</option>`).join('')
    || '<option value="">no Ardzy image found: Choose file</option>';
  if (extra) $('sdImg').value = extra.path;
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
  if (!img) return alert('Choose an Ardzy image first.');
  if (!SD.disk) return alert('Choose the microSD card.');
  const settings = {};
  document.querySelectorAll('[data-sd]').forEach(el => settings[el.dataset.sd] = el.value.trim());
  if (!/^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$/.test(settings.hostname)) return alert('Board name: small letters, digits and -');
  if (settings.network === 'static' && !/^\d+\.\d+\.\d+\.\d+\/\d+$/.test(settings.address)) return alert('Fixed address like 192.168.1.50/24');
  const d = SD.disk;
  if (!confirm(`EVERYTHING on this card will be erased:\n\n    ${d.name}  (${gb(d.size)}, ${d.bus}${d.letters.length ? ', ' + d.letters.join(' ') : ''})\n\nWrite ${img.split(/[\\/]/).pop()} to it?`)) return;
  const r = await api('/api/sd/flash', { disk: d.number, name: d.name, size: d.size, image: img, verify: $('sdVerify').checked, settings });
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
      if (p.phase === 'done') $('sdText').textContent += '. Put the card in the board, set the boot jumpers to SD, and power on: after about 2 minutes Ardzy finds it as ' + settings.hostname + '.local';
      sdDisks();
      return;
    }
    SD.timer = setTimeout(poll, 700);
  };
  poll();
}

$('btnSd').onclick = openSd;
$('sdDiskRefresh').onclick = e => { e.preventDefault(); sdDisks(); };
$('sdImgPick').onclick = async e => {
  e.preventDefault();
  const r = await api('/api/sd/pick', {});
  if (r.ok) sdImages({ path: r.path, name: r.path.split(/[\\/]/).pop(), size: r.size });
};
$('sdGo').onclick = sdGo;
$('sdClose').onclick = e => { if (SD.busy && !confirm('The card is still being written (in its own window). Close this dialog anyway?')) e.preventDefault(); };
