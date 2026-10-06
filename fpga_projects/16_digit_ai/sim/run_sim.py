"""Simulation test of nn_engine.v with Icarus Verilog (PC only).

    python sim/run_sim.py

Loads two networks into the simulated engine (random weights with large biases, and the trained one
from nn_model.py) and checks every result, every score and every hidden value against nn_reference()
in blocks.py: the hardware must give exactly the same integers.
"""
import os, random, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'common'))
sys.path.insert(0, os.path.join(HERE, '..'))
from blocks import nn_reference, nn_load_model   # noqa: E402


def find_iverilog():
    """Icarus Verilog: ARDZY_IVERILOG, else the copy the Ardzy app makes (%LOCALAPPDATA%\\Ardzy\\icarus),
    else iverilog on the PATH. (Icarus can not work from folders with spaces.)"""
    import shutil
    for d in (os.environ.get('ARDZY_IVERILOG'), os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Ardzy', 'icarus', 'bin')):
        if d and os.path.exists(os.path.join(d, 'iverilog.exe')):
            return d
    exe = shutil.which('iverilog')
    if exe:
        return os.path.dirname(exe)
    sys.exit('Icarus Verilog not found: open Simulation once in the Ardzy app, or set ARDZY_IVERILOG')


def random_model(rs, shift):
    return {'hid': 64, 'shift': shift, 'w1': rs.randint(-127, 128, (64, 784)).astype(np.int8),
            'b1': rs.randint(-100000, 100000, 64).astype(np.int64),
            'w2': rs.randint(-127, 128, (10, 64)).astype(np.int8), 'b2': rs.randint(-20000, 20000, 10).astype(np.int64)}


def main():
    IVERILOG = find_iverilog()
    rs = np.random.RandomState(16)
    models = [('random', random_model(rs, 12)), ('saturating', random_model(rs, 8))]
    try:
        import nn_model
        m = nn_load_model(nn_model)
        models.append(('trained', m))
    except ImportError:
        m = None
    L, cases = [], []
    def wr(i, v): L.append("    wr(%d, 32'h%08x);" % (i, int(v) & 0xFFFFFFFF))
    def rd(i, tag): L.append('    rd(%d); $display("%s %%08x", rdata);' % (i, tag))
    for name, mod in models:
        for lane in range(16):
            wr(6, lane * 1024)
            for v in np.concatenate([mod['w1'][r * 16 + lane] for r in range(4)]).view('<u4'):
                wr(7, v)
        wr(6, 0x8000)
        for v in np.ascontiguousarray(mod['w2']).reshape(-1).view('<u4'):
            wr(7, v)
        for j in range(64):
            wr(128 + j, mod['b1'][j])
        for k in range(10):
            wr(192 + k, mod['b2'][k])
        wr(4, mod['shift'])
        pics = [rs.randint(0, 256, 784).astype(np.uint8) for _ in range(3)]
        if name == 'trained':
            pics += [mod['test'][i] for i in range(0, len(mod['test']), 7)]
        for n, x in enumerate(pics):
            tag = '%s%d' % (name[0], n)
            for i, v in enumerate(x.view('<u4')):
                wr(256 + i, v)
            wr(0, 1)
            L.append('    waitdone;')
            rd(2, tag + '_R'); rd(3, tag + '_C')
            for k in range(10):
                rd(16 + k, '%s_S%d' % (tag, k))
            for i in range(16):
                rd(64 + i, '%s_H%d' % (tag, i))
            cases.append((tag, mod, x))
    rd(1023, 'ID')
    tb = open(os.path.join(HERE, 'tb.v.in')).read().replace('__STEPS__', '\n'.join(L))
    open(os.path.join(HERE, 'tb.v'), 'w').write(tb)
    env = dict(os.environ, PATH=IVERILOG + os.pathsep + os.environ['PATH'])
    subprocess.run([os.path.join(IVERILOG, 'iverilog.exe'), '-g2005', '-o', os.path.join(HERE, 'tb.vvp'), os.path.join(HERE, 'tb.v'),
                    os.path.join(HERE, '..', 'nn_engine.v')], check=True, env=env)
    r = subprocess.run([os.path.join(IVERILOG, 'vvp.exe'), '-n', os.path.join(HERE, 'tb.vvp')], capture_output=True, text=True, env=env)
    got = {}
    for l in r.stdout.splitlines():
        p = l.split()
        if len(p) == 2:
            try:
                got[p[0]] = int(p[1], 16)
            except ValueError:
                got[p[0]] = None
    ok = []
    def check(name, cond, detail=''):
        ok.append(cond)
        print('%-4s %-50s %s' % ('ok' if cond else 'FAIL', name, detail))
    sgn = lambda v: v - (1 << 32) if v is not None and v & 0x80000000 else v
    for tag, mod, x in cases:
        d, s, h = nn_reference(mod, x)
        hs = []
        for i in range(16):
            v = got.get('%s_H%d' % (tag, i)) or 0
            hs += [(v >> (8 * b)) & 255 for b in range(4)]
        ss = [sgn(got.get('%s_S%d' % (tag, k))) for k in range(10)]
        good = got.get(tag + '_R') == d and ss == s and hs == h
        check('%s picture %s: digit, 10 scores, 64 hidden values' % ({'r': 'random', 's': 'saturating', 't': 'trained'}[tag[0]], tag[1:]), good,
              'digit %s (math %d), %s clocks' % (got.get(tag + '_R'), d, got.get(tag + '_C')))
    check('ID "NNET"', got.get('ID') == 0x4E4E4554)
    print('RESULT: %d of %d ok' % (sum(ok), len(ok)))


if __name__ == '__main__':
    main()
