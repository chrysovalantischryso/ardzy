"""The Learn course's lesson projects on a real board: build each design (the .bit is kept in the template, so
the lesson projects come prebuilt), upload it with its main.py, run it, and read its CHECK lines and RESULT.

    python learn_lessons_test.py [--nobuild] [names...]      (default: all pc_app/templates/learn_*)

The board's project "learn_test" is used and removed at the end.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.normpath(os.path.join(HERE, '..'))
TPL = os.path.join(APP, 'templates')
BOARD = 'http://ardzy.local'
PROJ = 'learn_test'
sys.path.insert(0, APP)

args = sys.argv[1:]
NOBUILD = '--nobuild' in args
names = [a for a in args if not a.startswith('--')] or sorted(n for n in os.listdir(TPL) if n.startswith('learn_'))


def call(method, path, data=None, timeout=120):
    req = urllib.request.Request(BOARD + path, data=data, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    try:
        return json.loads(body)
    except ValueError:
        return body


def build(d, name):
    from fpga import flow
    lines = []
    for old in [f for f in os.listdir(d) if f.endswith('.bit')]:
        os.remove(os.path.join(d, old))
    flow.build(d, log=lambda s, c=None: lines.append(s), out_name=name)
    timing = [l.strip() for l in lines if 'MHz' in l and ('PASS' in l or 'FAIL' in l)]
    res = [l.strip() for l in lines if 'LUTs' in l]
    passed = any('PASS' in l for l in timing)
    return passed, (res[0] if res else '') + ' | ' + (timing[-1] if timing else 'no timing line')


def run(d):
    q = urllib.parse.quote
    bit = [f for f in os.listdir(d) if f.endswith('.bit')][0]
    for f in ('main.py', bit):
        call('PUT', '/api/upload?p=%s&f=%s' % (PROJ, q(f)), open(os.path.join(d, f), 'rb').read())
    cur = call('GET', '/api/log')['cursor']
    r = call('POST', '/api/load?p=' + PROJ, b'')
    if not r.get('ok'):
        return False, 'LOAD FAILED: ' + str(r.get('out', ''))[:200], []
    log, t0 = '', time.time()
    while time.time() - t0 < 90:
        time.sleep(1)
        x = call('GET', '/api/log?cursor=' + q(cur))
        log += x.get('log', '')
        cur = x.get('cursor', cur)
        if re.search(r'RESULT: (\d+) of (\d+) ok', log) or 'Traceback' in log:
            break
    call('POST', '/api/stop', b'')
    checks = [l.strip() for l in log.splitlines() if 'CHECK' in l or 'Error' in l or 'Traceback' in l]
    m = re.search(r'RESULT: (\d+) of (\d+) ok', log)
    ok = bool(m) and m.group(1) == m.group(2)
    return ok, m.group(0) if m else 'NO RESULT', checks


all_ok = True
for n in names:
    d = os.path.join(TPL, n)
    t = time.time()
    tok, tinfo = (True, 'not rebuilt') if NOBUILD and any(f.endswith('.bit') for f in os.listdir(d)) else build(d, n)
    rok, res, checks = run(d)
    all_ok &= tok and rok
    print('%-20s %-22s timing %-4s %5.0f s   %s' % (n, res, 'ok' if tok else 'FAIL', time.time() - t, tinfo), flush=True)
    for c in checks:
        print('      ' + c[c.find('CHECK'):] if 'CHECK' in c else '      ' + c, flush=True)
try:
    call('POST', '/api/delete?p=' + PROJ, b'')
except Exception:
    pass
print('ALL PASSED' if all_ok else 'SOME FAILED')
