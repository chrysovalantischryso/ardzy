"""Simulation test of life.v with Icarus Verilog (PC only):  python sim/run_sim.py

A random grid written by the "ARM", 1 and then 7 more generations, compared with the Python rules
(including the population), and a glider that must be back, moved by 1 row and 1 column, after 4.
"""
import os, random, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))


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


def step(g):
    """One generation on a 64 x 64 torus; g = 64 ints (row r, bit c = column c)."""
    new = []
    for r in range(64):
        row = 0
        for c in range(64):
            n = sum((g[(r + dr) % 64] >> ((c + dc) % 64)) & 1 for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc)
            alive = (g[r] >> c) & 1
            if n == 3 or (alive and n == 2):
                row |= 1 << c
        new.append(row)
    return new


def main():
    random.seed(15)
    g = [random.getrandbits(64) for _ in range(64)]
    g1 = step(g)
    g8 = g1
    for _ in range(7):
        g8 = step(g8)
    glider = [0] * 64
    for r, c in ((0, 1), (1, 2), (2, 0), (2, 1), (2, 2)):
        glider[r] |= 1 << c
    L = []
    def wr(i, v): L.append("    wr(%d, 32'h%08x);" % (i, v & 0xFFFFFFFF))
    def rd(i, tag): L.append('    rd(%d); $display("%s %%08x", rdata);' % (i, tag))
    def put(grid):
        for r in range(64):
            wr(64 + 2 * r, grid[r] & 0xFFFFFFFF); wr(65 + 2 * r, grid[r] >> 32)
    def get(tag):
        for r in range(64):
            rd(64 + 2 * r, '%s_%d_L' % (tag, r)); rd(65 + 2 * r, '%s_%d_H' % (tag, r))
    wr(0, 1); L.append('    repeat (80) @(posedge clk);')
    put(g)
    get('G0')
    wr(2, 1); L.append('    repeat (100) @(posedge clk);')
    get('G1'); rd(4, 'POP1'); rd(3, 'GEN1')
    wr(2, 7); L.append('    repeat (7 * 80) @(posedge clk);')
    get('G8'); rd(3, 'GEN8')
    wr(0, 1); L.append('    repeat (80) @(posedge clk);')
    put(glider)
    wr(2, 4); L.append('    repeat (4 * 80) @(posedge clk);')
    get('GL'); rd(1023, 'ID')
    tb = open(os.path.join(HERE, 'tb.v.in')).read().replace('__STEPS__', '\n'.join(L))
    open(os.path.join(HERE, 'tb.v'), 'w').write(tb)
    env = dict(os.environ, PATH=IVERILOG + os.pathsep + os.environ['PATH'])
    subprocess.run([os.path.join(IVERILOG, 'iverilog.exe'), '-g2005', '-o', os.path.join(HERE, 'tb.vvp'), os.path.join(HERE, 'tb.v'),
                    os.path.join(HERE, '..', 'life.v')], check=True, env=env)
    r = subprocess.run([os.path.join(IVERILOG, 'vvp.exe'), '-n', os.path.join(HERE, 'tb.vvp')], capture_output=True, text=True, env=env)
    got = {}
    for l in r.stdout.splitlines():
        p = l.split()
        if len(p) == 2:
            try:
                got[p[0]] = int(p[1], 16)
            except ValueError:
                got[p[0]] = None
    grid = lambda tag: [((got.get('%s_%d_H' % (tag, r)) or 0) << 32) | (got.get('%s_%d_L' % (tag, r)) or 0) for r in range(64)]
    ok = []
    def check(name, cond, detail=''):
        ok.append(cond)
        print('%-4s %-50s %s' % ('ok' if cond else 'FAIL', name, detail))
    check('the grid written = the grid read', grid('G0') == g)
    check('1 generation = the rules', grid('G1') == g1)
    check('population = live cells', got.get('POP1') == sum(bin(x).count('1') for x in g1), '%s' % got.get('POP1'))
    check('8 generations = the rules', grid('G8') == g8 and got.get('GEN8') == 8, 'gen %s' % got.get('GEN8'))
    moved = [0] * 64
    for rr in range(64):
        moved[(rr + 1) % 64] = ((glider[rr] << 1) | (glider[rr] >> 63)) & ((1 << 64) - 1)
    check('a glider after 4 generations: 1 down, 1 right', grid('GL') == moved)
    check('ID "LIFE"', got.get('ID') == 0x4C494645)
    print('RESULT: %d of %d ok' % (sum(ok), len(ok)))


if __name__ == '__main__':
    main()
