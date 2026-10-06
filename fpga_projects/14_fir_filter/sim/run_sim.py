"""Simulation test of fir_lab.v with Icarus Verilog (PC only):  python sim/run_sim.py

ARM mode: random coefficients and samples, every result compared with the exact integer model.
Generator mode: a 1 kHz sine at 1 MS/s through an all-pass filter (c = [1 << SHIFT]): the peak must follow.
"""
import os, random, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'pc_app', 'fpga', 'hdl'))


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


IVERILOG = find_iverilog()


def model(coef, xs, shift):
    """The filter in integers, exactly as the FPGA does it."""
    hist = [0] * 64
    out = []
    for n, x in enumerate(xs):
        hist = [x] + hist[:-1]
        acc = sum(c * h for c, h in zip(coef, hist))
        y = acc >> shift
        out.append(max(-32768, min(32767, y)))
    return out


def main():
    random.seed(14)
    taps, shift = 23, 15
    coef = [random.randint(-40000, 40000) for _ in range(taps)]
    xs = [random.randint(-32768, 32767) for _ in range(150)]
    want = model(coef, xs, shift)
    L = []
    def wr(i, v): L.append("    wr(%d, 32'h%08x);" % (i, v & 0xFFFFFFFF))
    def rd(i, tag): L.append('    rd(%d); $display("%s %%08x", rdata);' % (i, tag))
    wr(0, 1)
    wr(2, taps); wr(3, shift)
    for k, c in enumerate(coef): wr(64 + k, c & 0x3FFFF)
    for n, x in enumerate(xs):
        wr(4, x & 0xFFFF)
        if n % 8 == 7:
            L.append('    repeat (8 * 30) @(posedge clk);')
    L.append('    repeat (400) @(posedge clk);')
    rd(1, 'STATUS'); rd(13, 'SAMPLES')
    for n in range(len(xs)): rd(5, 'OUT%d' % n)
    # generator: an all-pass filter, a full-scale-half sine; the meters
    wr(0, 1); wr(2, 1); wr(3, 15); wr(64, 1 << 15)
    wr(7, int(1000 / 1e6 * 2 ** 32)); wr(8, 100); wr(9, 16384); wr(10, 0); wr(0, 2)
    L.append('    repeat (1100000) @(posedge clk);')
    rd(11, 'PIN'); rd(12, 'POUT'); rd(13, 'GSAMPLES'); rd(1023, 'ID')

    tb = open(os.path.join(HERE, 'tb.v.in')).read().replace('__STEPS__', '\n'.join(L))
    open(os.path.join(HERE, 'tb.v'), 'w').write(tb)
    env = dict(os.environ, PATH=IVERILOG + os.pathsep + os.environ['PATH'])
    subprocess.run([os.path.join(IVERILOG, 'iverilog.exe'), '-g2005', '-o', os.path.join(HERE, 'tb.vvp'), os.path.join(HERE, 'tb.v'),
                    os.path.join(HERE, '..', 'fir_lab.v'), os.path.join(LIB, 'ardzy_axis.v'), os.path.join(LIB, 'ardzy_sine_rom.v')],
                   check=True, env=env)
    r = subprocess.run([os.path.join(IVERILOG, 'vvp.exe'), '-n', os.path.join(HERE, 'tb.vvp')], capture_output=True, text=True, env=env)
    got = {}
    for l in r.stdout.splitlines():
        p = l.split()
        if len(p) == 2:
            got[p[0]] = int(p[1], 16)
    s16 = lambda v: v - 65536 if v & 0x8000 else v
    outs = [s16(got.get('OUT%d' % n, 0) >> 16) for n in range(len(xs))]
    ins = [s16(got.get('OUT%d' % n, 0) & 0xFFFF) for n in range(len(xs))]
    ok = []
    def check(name, cond, detail=''):
        ok.append(cond)
        print('%-4s %-50s %s' % ('ok' if cond else 'FAIL', name, detail))
    check('150 samples filtered', got.get('SAMPLES') == 150, str(got.get('SAMPLES')))
    check('the inputs come back with their results', ins == xs)
    bad = [n for n in range(len(xs)) if outs[n] != want[n]]
    check('every result = the integer model (23 taps)', not bad, 'first wrong at %s: %s vs %s' % (bad[0], outs[bad[0]], want[bad[0]]) if bad else '')
    check('generator: input peak about 16384', abs(got.get('PIN', 0) - 16384) < 200, str(got.get('PIN')))
    check('generator: all-pass output peak = input peak', abs(got.get('POUT', 0) - got.get('PIN', 0)) < 3, str(got.get('POUT')))
    check('generator: about 1 MS/s (11000 in 11 ms)', abs(got.get('GSAMPLES', 0) - 11000) < 30, str(got.get('GSAMPLES')))
    check('ID "FIR1"', got.get('ID') == 0x46495231)
    print('RESULT: %d of %d ok' % (sum(ok), len(ok)))


if __name__ == '__main__':
    main()
