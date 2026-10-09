"""Simulation test of the DDR network engine (mlp_ddr.v) with Icarus Verilog (PC only).

    python sim/run_sim.py

Random networks of every kind, one bigger than a memory page per port (so the page table is used), all loaded
at once and run in turn against a fake DDR that answers late and with gaps: every output must equal
mlp_reference() in blocks.py, to the bit.
"""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'common'))
from mlp_ddr_sim import simulate              # noqa: E402

ok = []


def check(name, cond, detail=''):
    ok.append(cond)
    print('%-4s %-50s %s' % ('ok' if cond else 'FAIL', name, detail))


def rnd(rs, sizes, acts, shifts):
    return [{'w': rs.randint(-127, 128, (sizes[k + 1], sizes[k])).astype(np.int8), 'b': rs.randint(-30000, 30000, sizes[k + 1]),
             'shift': shifts[k], 'act': a} for k, a in enumerate(acts)]


def main():
    rs = np.random.RandomState(19)
    nets = [('relu-sigmoid', rnd(rs, [40, 48, 30], [1, 2], [10, 9])),
            ('three layers', rnd(rs, [100, 64, 32, 20], [1, 1, 0], [11, 9, 0])),
            ('bigger than a page', rnd(rs, [200, 128, 10], [1, 0], [12, 0])),
            ('one layer', rnd(rs, [8, 16], [0], [0]))]
    for ports in (4, 2):
        print("-- %d HP ports" % ports)
        simulate(nets, check, ports=ports)
    print('RESULT: %d of %d ok' % (sum(ok), len(ok)))


if __name__ == '__main__':
    main()
