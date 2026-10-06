"""Writes Documents/07_Learn_FPGA.html: the Learn course as a document, from the same content as the app
(ui/learn_data.js, the widgets of ui/learn.js, the lesson projects in templates/learn_*).

    python learn/make_learn_doc.py

Files: Documents/07_Learn_FPGA.html and Documents/learn/ (learn_data.js, learn.js, learn_code.js, learn.css).
"""
import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.normpath(os.path.join(HERE, '..'))
DOCS = os.path.normpath(os.path.join(APP, '..', '..', '..', 'Documents'))
OUT = os.path.join(DOCS, 'learn')

PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Learn FPGA with Ardzy</title>
<link rel="stylesheet" href="docs.css"><link rel="stylesheet" href="learn/learn.css">
</head><body id="top">
<header class="top"><div class="wrap">
  <nav class="back"><a href="index.html">&larr; All documents</a></nav>
  <div class="kicker">Document 7 &middot; Project 2_Ardzy</div>
  <h1>Learn FPGA with Ardzy</h1>
  <p>Ten lessons from logic gates to your own instrument. Each lesson explains one idea with a drawing you can play with,
  has a working project on the board, its code, questions with answers and challenges. The same course is the
  <b>Learn</b> view of the Ardzy app, where each project is created and uploaded with one click.</p>
</div></header>
<main class="wrap">
  <div id="learnTabs" hidden></div>
  <div class="box info" id="intro"></div>
  <h2>The lessons</h2>
  <ol id="toc"></ol>
  <div id="lessons"></div>
  <h2 id="ideas">Ideas: what to build next</h2>
  <p>Ideas for your own projects, from an afternoon to a few weekends. "Start from" names the lesson or ready project
  (document 6) to begin with.</p>
  <div id="ideaList"></div>
  <p><a href="#top">Back to the top</a></p>
</main>
<script>
// small stand-ins for the app's helpers, so the app's widgets run here too
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[c]);
const BV = { view: 'learn' };
</script>
<script src="learn/learn_data.js"></script>
<script src="learn/learn_code.js"></script>
<script src="learn/learn.js"></script>
<script>
$('intro').innerHTML = LEARN.intro.replace('Press <b>Create the project</b>, then <b>Upload and run</b>',
  'In the app press <b>Create the project</b>, then <b>Upload and run</b>');
$('toc').innerHTML = LEARN.lessons.map(L => `<li><a href="#lesson${L.id}">${esc(L.title)}</a></li>`).join('');
$('lessons').innerHTML = LEARN.lessons.map(L => `<section class="project" id="lesson${L.id}">
  <div class="kicker">Lesson ${L.id} &middot; about ${L.minutes} minutes &middot; you need: ${esc(L.need)}</div>
  <h2>${esc(L.title)}</h2>
  <div class="box ok"><b>You will learn:</b> ${esc(L.goal)}</div>
  ${L.sections.map((s, i) => s.widget ? `<div class="lwidget" data-w="${s.widget}"></div>` : `<h3>${esc(s.h)}</h3>${s.html}`).join('')}
  <h3>Do it on the board</h3>
  <p>In the app: <b>Learn</b>, lesson ${L.id}. The project is <code>${L.template}</code> in <code>2_Ardzy/pc_app/templates</code>.</p>
  <ol>${L.steps.map(s => `<li>${s}</li>`).join('')}</ol>
  <h3>The code</h3>
  ${L.files.map(f => `<details${f === 'top.v' ? ' open' : ''}><summary>${esc(f)}</summary><pre><code>${esc((LEARN_CODE[L.template] || {})[f] || '')}</code></pre></details>`).join('')}
  <h3>Check yourself</h3>
  ${L.quiz.map((q, i) => `<p><b>${i + 1}. ${q.q}</b></p><ul>${q.options.map(o => `<li>${o}</li>`).join('')}</ul>
    <details><summary>Answer</summary><p><b>${q.options[q.answer]}</b>. ${q.why}</p></details>`).join('')}
  <h3>Challenges</h3>
  ${L.challenges.map((c, i) => `<p><b>${i + 1}.</b> ${c.task}</p><details><summary>Hint</summary><p>${c.hint}</p></details>
    <details><summary>Answer</summary><p>${c.answer}</p></details>`).join('')}
  <p><a href="#top">Back to the top</a></p></section>`).join('');
document.querySelectorAll('.lwidget').forEach(el => { try { LW[el.dataset.w](el); } catch (e) { el.textContent = e; } });
const level = ['', 'easy', 'medium', 'hard'];
$('ideaList').innerHTML = '<table><tr><th>Idea</th><th>Level</th><th>What it is</th><th>You need</th><th>You learn</th><th>Start from</th></tr>' +
  IDEAS.map(i => `<tr><td><b>${esc(i.t)}</b><br><small>${esc(i.cat)}</small></td><td>${level[i.d]}</td><td>${esc(i.how)}</td>
    <td>${esc(i.parts)}</td><td>${esc(i.learn)}</td><td>${esc(i.start)}</td></tr>`).join('') + '</table>';
</script>
</body></html>
'''


def main():
    os.makedirs(OUT, exist_ok=True)
    code = {}
    tpl = os.path.join(APP, 'templates')
    for t in sorted(os.listdir(tpl)):
        if t.startswith('learn_'):
            code[t] = {f: open(os.path.join(tpl, t, f), encoding='utf-8').read()
                       for f in os.listdir(os.path.join(tpl, t)) if f.endswith(('.v', '.py', '.xdc'))}
    open(os.path.join(OUT, 'learn_code.js'), 'w', encoding='utf-8', newline='\n').write(
        '/* generated by pc_app/learn/make_learn_doc.py: the lesson projects\' files */\nconst LEARN_CODE = %s;\n' % json.dumps(code, indent=0))
    shutil.copy(os.path.join(APP, 'ui', 'learn_data.js'), OUT)
    shutil.copy(os.path.join(APP, 'ui', 'learn.js'), OUT)
    css = open(os.path.join(APP, 'ui', 'app.css'), encoding='utf-8').read()
    block = css[css.index('/* ---------- Learn view ---------- */'):]
    nxt = block.find('/* ----------', 10)
    block = block[:nxt] if nxt > 0 else block
    head = """/* generated by pc_app/learn/make_learn_doc.py: the app's Learn widgets in the documents */
:root { --font: "Segoe UI", system-ui, sans-serif; --mono: "Cascadia Mono", Consolas, monospace; --accent: #13894a; --accent-text: #fff;
  --line: #d6ddd9; --panel: #ffffff; --hover: #e9efec; --sel: #cfe9da; --code-bg: #f6f8f7; --muted: #5b6a62; --text: #18211c;
  --warn: #9a6400; --ok: #13894a; --err: #c42b2b; --head: #1d5fa8; --side: #eef1ef; }
@media (prefers-color-scheme: dark) { :root { --accent: #2fbf6c; --accent-text: #06120b; --line: #2c3531; --panel: #161c19;
  --hover: #1f2823; --sel: #224031; --code-bg: #121915; --muted: #9aa8a0; --text: #e2ebe6; --warn: #e3ad4c; --ok: #4fd388; --err: #ff7b7b; --head: #79b4ff; } }
.lwidget button { font: inherit; font-size: 14px; color: var(--text); background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 5px 11px; cursor: pointer; }
.lwidget button.small { padding: 3px 9px; font-size: 13px; }
.lwidget button.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-text); }
.lwidget .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.lwidget .grow { flex: 1; }
.lwidget .hint { color: var(--muted); font-size: 13px; }
.lwidget input, .lwidget select { font: inherit; font-size: 14px; color: var(--text); background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 4px 8px; }
.lwidget svg { max-width: 100%; }
"""
    open(os.path.join(OUT, 'learn.css'), 'w', encoding='utf-8', newline='\n').write(head + block)
    open(os.path.join(DOCS, '07_Learn_FPGA.html'), 'w', encoding='utf-8', newline='\n').write(PAGE)
    print('wrote', os.path.join(DOCS, '07_Learn_FPGA.html'), 'and', OUT)


if __name__ == '__main__':
    main()
