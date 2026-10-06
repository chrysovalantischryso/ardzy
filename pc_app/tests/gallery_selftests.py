"""Runs the self-test of every ready project (fpga_projects/NN_name) on a real board, the way the app's
Projects page does it (the prebuilt .bit and the programs, with selftest.py as main.py), and prints the
RESULT line of each.

    python gallery_selftests.py [board] [names...]      (default ardzy.local, all projects)
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

args = [a for a in sys.argv[1:]]
BOARD = 'http://' + (args.pop(0) if args and not re.match(r'^\d\d_', args[0]) else 'ardzy.local')
HERE = os.path.dirname(os.path.abspath(__file__))
GAL = os.path.normpath(os.path.join(HERE, '..', '..', 'fpga_projects'))
SKIP = ('guide.md', 'guide.html', 'pins.xdc', 'top.v', 'selftest.py', 'project.json')


def call(method, path, data=None, timeout=120):
    req = urllib.request.Request(BOARD + path, data=data, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    try:
        return json.loads(body)
    except ValueError:
        return body


def run(name):
    d = os.path.join(GAL, name)
    q = urllib.parse.quote
    files = [f for f in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, f)) and f not in SKIP
             and not f.startswith('make_') and (f == name + '.bit' or f.endswith(('.py', '.json', '.s', '.txt', '.csv')))]
    for f in files:
        src = 'selftest.py' if f == 'main.py' else f
        call('PUT', '/api/upload?p=%s&f=%s' % (q(name), q(f)), open(os.path.join(d, src), 'rb').read())
    cur = call('GET', '/api/log')['cursor']
    r = call('POST', '/api/load?p=' + q(name), b'')
    if not r.get('ok'):
        return 'LOAD FAILED: ' + r.get('out', '')
    log, t0 = '', time.time()
    while time.time() - t0 < 240:
        time.sleep(1)
        x = call('GET', '/api/log?cursor=' + q(cur))
        log += x.get('log', '')
        cur = x.get('cursor', cur)
        m = re.search(r'RESULT: (\d+) of (\d+) ok', log)
        if m or 'Traceback' in log:
            break
    fails = [l.strip() for l in log.splitlines() if l.strip().startswith('FAIL') or 'Error' in l]
    m = re.search(r'RESULT: (\d+) of (\d+) ok', log)
    if os.path.isfile(os.path.join(d, 'main.py')):       # the real program back (it starts at the next load)
        call('PUT', '/api/upload?p=%s&f=main.py' % q(name), open(os.path.join(d, 'main.py'), 'rb').read())
    return (m.group(0) if m else 'NO RESULT') + ''.join('\n      ' + f for f in fails[:6])


names = args or sorted(n for n in os.listdir(GAL) if re.match(r'^\d\d_', n))
total_ok = True
for n in names:
    t = time.time()
    res = run(n)
    ok = res.startswith('RESULT') and re.match(r'RESULT: (\d+) of \1 ok', res) is not None
    total_ok &= ok
    print('%-16s %-24s %5.0f s' % (n, res, time.time() - t), flush=True)
print('ALL PASSED' if total_ok else 'SOME FAILED')
