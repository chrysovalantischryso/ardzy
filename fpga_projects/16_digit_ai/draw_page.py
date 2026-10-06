# 16 AI in the FPGA: the drawing page main.py serves (http://<board>.local:8080). Draw a digit, the FPGA reads it.
PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ardzy AI: draw a digit</title>
<style>
:root { --bg: #f3f5f4; --panel: #fff; --text: #18211c; --muted: #5b6a62; --line: #d6ddd9; --accent: #13894a; --bar: #cfe9da; }
@media (prefers-color-scheme: dark) { :root { --bg: #101512; --panel: #151c18; --text: #e2ebe6; --muted: #92a39a; --line: #26312b; --accent: #2fbf6c; --bar: #224031; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 "Segoe UI", system-ui, sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 16px; }
h1 { font-size: 22px; margin: 4px 0 2px; } h1 small { font-size: 12px; color: var(--accent); border: 1px solid var(--accent); border-radius: 6px; padding: 1px 6px; vertical-align: 3px; }
p.sub { color: var(--muted); margin: 0 0 14px; }
.grid { display: grid; grid-template-columns: minmax(260px, 340px) 1fr; gap: 16px; }
@media (max-width: 720px) { .grid { grid-template-columns: 1fr; } }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px; }
canvas#pad { width: 100%; aspect-ratio: 1; background: #000; border-radius: 8px; touch-action: none; cursor: crosshair; display: block; }
.row { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
button { font: inherit; padding: 7px 14px; border-radius: 8px; border: 1px solid var(--line); background: var(--panel); color: var(--text); cursor: pointer; }
button.main { background: var(--accent); border-color: var(--accent); color: #fff; }
.answer { display: flex; align-items: center; gap: 18px; }
.big { font-size: 84px; font-weight: 700; line-height: 1; min-width: 70px; text-align: center; color: var(--accent); }
.conf { color: var(--muted); }
.bars { margin-top: 12px; }
.bar { display: grid; grid-template-columns: 18px 1fr 52px; gap: 8px; align-items: center; margin: 3px 0; font-variant-numeric: tabular-nums; }
.bar .t { height: 14px; background: var(--bar); border-radius: 4px; overflow: hidden; }
.bar .t i { display: block; height: 100%; background: var(--accent); width: 0; transition: width .2s; }
.bar span:last-child { text-align: right; color: var(--muted); font-size: 13px; }
.see { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 14px; align-items: flex-start; }
.see canvas { image-rendering: pixelated; border: 1px solid var(--line); border-radius: 6px; background: #000; }
.see b { display: block; font-size: 13px; margin-bottom: 4px; }
.hint { color: var(--muted); font-size: 13px; margin: 6px 0 0; }
.speed { margin-top: 12px; font-size: 14px; }
.speed b { color: var(--accent); }
</style></head><body><main>
<h1>Draw a digit <small>AI in the FPGA</small></h1>
<p class="sub">A neural network inside the Zynq's FPGA reads what you draw: 64 multipliers at once, about 10 microseconds per digit.</p>
<div class="grid">
  <div class="card">
    <canvas id="pad" width="280" height="280"></canvas>
    <div class="row"><button class="main" id="clear">Clear</button><button id="example">Show an example</button></div>
    <p class="hint">Draw one digit, 0 to 9, big and in the middle. The FPGA answers when you lift the pen.</p>
  </div>
  <div class="card">
    <div class="answer"><div class="big" id="digit">?</div><div><div id="what">Waiting for a drawing.</div><div class="conf" id="conf"></div></div></div>
    <div class="bars" id="bars"></div>
    <div class="see">
      <div><b>What the network sees (28 x 28)</b><canvas id="seen" width="28" height="28" style="width:112px;height:112px"></canvas></div>
      <div><b>Its 64 hidden neurons</b><canvas id="hid" width="8" height="8" style="width:112px;height:112px"></canvas></div>
    </div>
    <div class="speed" id="speed"></div>
  </div>
</div>
</main>
<script>
const pad = document.getElementById('pad'), g = pad.getContext('2d');
let drawing = false, last = null, timer = null, busy = false, again = false;
function clearPad() { g.fillStyle = '#000'; g.fillRect(0, 0, 280, 280); }
clearPad();
function pos(e) { const r = pad.getBoundingClientRect(); return [(e.clientX - r.left) * 280 / r.width, (e.clientY - r.top) * 280 / r.height]; }
function dot(p) { g.fillStyle = '#fff'; g.beginPath(); g.arc(p[0], p[1], 10, 0, 7); g.fill(); }
pad.addEventListener('pointerdown', e => { drawing = true; last = pos(e); dot(last); clearTimeout(timer); try { pad.setPointerCapture(e.pointerId); } catch (x) {} });
pad.addEventListener('pointermove', e => {
  if (!drawing) return;
  const p = pos(e);
  g.strokeStyle = '#fff'; g.lineWidth = 20; g.lineCap = 'round'; g.lineJoin = 'round';
  g.beginPath(); g.moveTo(last[0], last[1]); g.lineTo(p[0], p[1]); g.stroke();
  last = p;
});
function up() { if (!drawing) return; drawing = false; clearTimeout(timer); timer = setTimeout(ask, 250); }
pad.addEventListener('pointerup', up); pad.addEventListener('pointercancel', up);
document.getElementById('clear').onclick = () => { clearPad(); show(null); };
document.getElementById('example').onclick = async () => {
  const r = await (await fetch('example')).json();
  clearPad();
  const im = g.createImageData(28, 28);
  for (let i = 0; i < 784; i++) { im.data[4 * i] = im.data[4 * i + 1] = im.data[4 * i + 2] = r.pixels[i]; im.data[4 * i + 3] = 255; }
  const c = document.createElement('canvas'); c.width = c.height = 28; c.getContext('2d').putImageData(im, 0, 0);
  g.imageSmoothingEnabled = true; g.drawImage(c, 0, 0, 280, 280);
  ask();
};
function pixels() {                        // 112 x 112 grey levels, as base64
  const c = document.createElement('canvas'); c.width = c.height = 112;
  const cg = c.getContext('2d'); cg.imageSmoothingEnabled = true; cg.imageSmoothingQuality = 'high';
  cg.drawImage(pad, 0, 0, 112, 112);
  const d = cg.getImageData(0, 0, 112, 112).data, b = new Uint8Array(112 * 112);
  for (let i = 0; i < b.length; i++) b[i] = d[4 * i];
  let s = ''; for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
  return btoa(s);
}
async function ask() {
  if (busy) { again = true; return; }
  busy = true;
  try {
    const r = await (await fetch('guess', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ px: pixels() }) })).json();
    show(r);
  } catch (e) { document.getElementById('what').textContent = 'No answer from the board: is main.py still running?'; }
  busy = false;
  if (again) { again = false; ask(); }
}
function show(r) {
  const $ = id => document.getElementById(id);
  if (!r || r.empty) {
    $('digit').textContent = '?'; $('what').textContent = 'Waiting for a drawing.'; $('conf').textContent = ''; $('bars').innerHTML = ''; $('speed').innerHTML = '';
    paint($('seen'), 28, null); paint($('hid'), 8, null); return;
  }
  $('digit').textContent = r.digit;
  $('what').textContent = 'The FPGA reads a ' + r.digit + '.';
  $('conf').textContent = 'sure: ' + Math.round(100 * r.prob[r.digit]) + ' %';
  $('bars').innerHTML = r.prob.map((p, k) => '<div class="bar"><span>' + k + '</span><div class="t"><i style="width:' + (100 * p).toFixed(1) +
    '%"></i></div><span>' + (100 * p).toFixed(p < .1 ? 1 : 0) + ' %</span></div>').join('');
  paint($('seen'), 28, r.pixels); paint($('hid'), 8, r.hidden);
  $('speed').innerHTML = 'The FPGA needed <b>' + r.fpga_us.toFixed(1) + ' &micro;s</b> (' + r.cycles + ' clocks at 100 MHz); the same math on the ARM with numpy: ' +
    r.arm_us.toFixed(0) + ' &micro;s. Digits read so far: ' + r.count + '.';
}
function paint(c, n, v) {
  const cg = c.getContext('2d'), im = cg.createImageData(n, n);
  for (let i = 0; i < n * n; i++) { const x = v ? v[i] : 0; im.data[4 * i] = im.data[4 * i + 1] = im.data[4 * i + 2] = x; im.data[4 * i + 3] = 255; }
  cg.putImageData(im, 0, 0);
}
</script></body></html>
'''
