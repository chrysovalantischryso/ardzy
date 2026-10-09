/* Ardzy - Projects view: the ready FPGA projects (fpga_projects), each with a prebuilt design, a demo,
   a self-test and a guide. Helpers from app.js / board.js: $, esc, api, out, S, BV, showView. */
const GAL = { list: [], cat: 'All', find: '' };

async function galleryShow() {
  const r = await api('/api/gallery');
  GAL.list = r.projects || [];
  if (!GAL.list.length) {
    $('galBody').innerHTML = '<div class="empty">The ready projects were not found (folder fpga_projects next to the app).</div>';
    return;
  }
  const cats = ['All', ...new Set(GAL.list.map(p => p.category))];
  $('galCat').innerHTML = cats.map(c => `<button data-c="${esc(c)}" class="${c === GAL.cat ? 'on' : ''}">${esc(c)}</button>`).join('');
  $('galCat').querySelectorAll('button').forEach(b => b.onclick = () => { GAL.cat = b.dataset.c; galleryShow(); });
  galleryRender();
}

function galleryRender() {
  const cur = (S.status && S.status.current) || (S.board && S.board.current);
  const f = GAL.find.toLowerCase();
  const shown = GAL.list.filter(p => (GAL.cat === 'All' || p.category === GAL.cat) &&
    (!f || (p.title + ' ' + p.summary + ' ' + p.category + ' ' + p.name).toLowerCase().includes(f)));
  $('galState').textContent = TF('{0} projects, each ready to upload: a prebuilt FPGA design, a demo, a self-test and a guide', GAL.list.length);
  $('galBody').innerHTML = shown.map(p => `
    <div class="dcard gcard" data-name="${esc(p.name)}">
      <div class="gmeta"><span>${esc(p.category)}</span><span>${esc(p.level)}</span><span class="grow"></span>
        ${cur === p.name ? '<span class="badge run">on the board now</span>' : ''}</div>
      <h4>${esc(p.title)}</h4>
      <p>${esc(p.summary)}</p>
      <details><summary>What you need, wiring</summary>
        <ul>${(p.parts || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        ${(p.wiring || []).length ? '<ul>' + p.wiring.map(w => `<li><b>${esc(w[0])}</b> to ${esc(w[1])}${w[2] ? ' (' + esc(w[2]) + ')' : ''}</li>`).join('') + '</ul>' : ''}
      </details>
      <div class="gbtns">
        ${p.name === '12_fm_radio' ? '<button class="primary small" data-a="radio" title="The radio station: frequency, songs, RDS text, digital modes">Open</button>' : ''}
        ${p.name === '16_digit_ai' ? '<button class="primary small" data-a="ai" title="Draw digits and watch the FPGA read them">Open</button>' : ''}
        ${p.name === '17_text_ai' ? '<button class="primary small" data-a="aiw" title="Let the language model write">Open</button>' : ''}
        ${p.name === '18_image_ai' ? '<button class="primary small" data-a="aid" title="Let the FPGA draw digits">Open</button>' : ''}
        ${p.guide ? '<button class="small" data-a="guide">Guide</button>' : ''}
        <button class="${['12_fm_radio', '16_digit_ai', '17_text_ai', '18_image_ai'].includes(p.name) ? '' : 'primary '}small" data-a="run" ${p.bit ? '' : 'disabled title="no prebuilt design yet"'}>Upload and run</button>
        ${p.test ? '<button class="small" data-a="test" title="Upload and run the self-test: every part is measured on your board">Self-test</button>' : ''}
        <button class="ghost small" data-a="copy" title="Copy into your projects to change the design or the program">Copy to my projects</button>
      </div>
    </div>`).join('') || '<div class="empty">Nothing matches.</div>';
  $('galBody').querySelectorAll('.gcard button[data-a]').forEach(b => b.onclick = () => galleryAction(b.closest('.gcard').dataset.name, b.dataset.a));
}

async function galleryAction(name, a) {
  if (a === 'guide') return galleryGuide(name);
  if (a === 'radio') return showView('radio');
  if (a === 'ai') return aiOpen('read');
  if (a === 'aiw') return aiOpen('write');
  if (a === 'aid') return aiOpen('draw');
  if (a === 'copy') {
    const as = prompt('Name of the copy in your projects (letters, digits, _ . -):', name.replace(/^\d\d_/, ''));
    if (!as) return;
    const r = await api('/api/gallery/copy', { name, as });
    if (!r.ok) out(r.out || 'copy failed', 'err');
    else if (window.refreshProjects) refreshProjects();
    return;
  }
  if (!S.connected) { out('No board connected: click Scan, then choose your board.', 'err'); return; }
  const r = await api('/api/gallery/upload', { name, test: a === 'test' });
  if (!r.ok) out(r.out || 'busy', 'err');
  else if (a === 'test') showTab('monitor');
}

async function galleryGuide(name) {
  const r = await api('/api/gallery/guide?name=' + encodeURIComponent(name));
  if (!r.ok) { out(r.out || 'no guide', 'err'); return; }
  const p = GAL.list.find(x => x.name === name) || { title: name };
  $('guideTitle').textContent = p.title;
  $('guideFrame').srcdoc = r.html;
  $('dlgGuide').showModal();
}

$('galFind').oninput = e => { GAL.find = e.target.value; galleryRender(); };
$('guideClose').onclick = () => $('dlgGuide').close();
window.galleryShow = galleryShow;
window.galleryGuide = galleryGuide;
