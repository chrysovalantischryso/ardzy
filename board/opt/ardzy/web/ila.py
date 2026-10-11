"""Ardzy signal analyzer (the board side of fpga/hdl/ardzy_ila.v, like Vivado's ILA).

The Ardzy build adds the analyzer to a design when signals carry (* mark_debug *). It talks with the ARM through
EMIO GPIO only (the GPIO block of the ARM side, never the FPGA bus, so nothing can hang):
  bank 2 bits 16..31 (EMIO 16..31) = commands to the analyzer, bank 3 (EMIO 32..63) = its answers.
Bits 0..15 of bank 2 are never touched (the EBAZ4205 has its LEDs on EMIO 0 / 1).
"""
import threading, time
import ardzy

GPIO = 0xE000A000
MASK_DATA_2_MSW, DATA_2, DATA_3_RO, DIRM_2, OEN_2 = 0x014, 0x048, 0x06C, 0x284, 0x288
_lock = threading.Lock()


class Ila:
    def __init__(self):
        self.m = ardzy.MMIO(GPIO, 0x1000)
        self.t = self.m[DATA_2] >> 31                 # what ctl[15] is now: the next command changes it
        for reg in (DIRM_2, OEN_2):                   # bits 16..31 of bank 2 are outputs
            self.m[reg] = self.m[reg] | 0xFFFF0000

    def close(self):
        self.m.close()

    def cmd(self, what, value):
        """One command; returns the analyzer's answer to it (bit 31 of every answer tells which command it is for:
        the analyzer works a few FCLK0 ticks later, so wait for the answer that belongs to this command)."""
        self.t ^= 1
        self.m[MASK_DATA_2_MSW] = (self.t << 15) | ((what & 7) << 12) | (value & 0xFFF)   # (mask 0: all 16 bits)
        m, t = self.m, self.t
        for _ in range(2000):
            w = m[DATA_3_RO]
            if w >> 31 == t:
                return w
        raise OSError('the analyzer does not answer (is FCLK0 running?)')

    def status(self):
        try:
            s = self.cmd(1, 7)
        except OSError:                               # nothing answers: no analyzer in this design
            return {'present': False, 'armed': False, 'triggered': False, 'done': False, 'width': 0, 'depth': 0}
        return {'ack': s >> 31, 'armed': bool(s >> 30 & 1), 'triggered': bool(s >> 29 & 1), 'done': bool(s >> 28 & 1),
                'trigger_at': s >> 16 & 0xFFF, 'depth': 1 << (s >> 12 & 15), 'width': s & 0xFF,
                'present': (s >> 8 & 15) == 0xA and (s & 0xFF) > 0}


def _open():
    a = Ila()
    st = a.status()
    if not st['present']:
        a.close()
        raise ValueError('the design in the FPGA has no signal analyzer: mark signals with (* mark_debug *) and build it again')
    return a, st


def info(q=None):
    with _lock:
        a = Ila()
        try:
            st = a.status()
        finally:
            a.close()
        return st


def arm(q):
    """Start a capture: mode 0 at once / 1 while equal / 2 when it becomes equal / 3 when a masked bit changes;
    value and mask are hex numbers as wide as the samples; pre = samples to keep before the trigger."""
    with _lock:
        a, st = _open()
        try:
            w, depth = st['width'], st['depth']
            nb = (w + 7) // 8
            mode = int(q.get('mode', 0))
            mask = int(q.get('mask', '0') or '0', 16) & ((1 << w) - 1)
            value = int(q.get('value', '0') or '0', 16) & mask
            pre = max(0, min(depth - 2, int(float(q.get('pre', depth // 2)))))
            a.cmd(5, 0)                                       # stop the last one
            for k in reversed(range(nb)):
                a.cmd(2, mask >> (8 * k) & 0xFF)
            for k in reversed(range(nb)):
                a.cmd(2, value >> (8 * k) & 0xFF)
            a.cmd(3, pre)
            a.cmd(4, mode & 3)
            a.cmd(5, 1)
            return dict(a.status(), pre=pre)
        finally:
            a.close()


def trigger_now(q=None):
    with _lock:
        a, st = _open()
        try:
            a.cmd(4, 0)                                       # "at once" while armed: it fills up and stops
            return a.status()
        finally:
            a.close()


def stop(q=None):
    with _lock:
        a, st = _open()
        try:
            a.cmd(5, 0)
            return a.status()
        finally:
            a.close()


def read(q=None):
    """The samples of a finished capture, oldest first, as hex strings; trigger = the index of the trigger sample."""
    wait = min(30.0, float((q or {}).get('wait', 0)))
    t0 = time.time()
    while True:
        with _lock:
            a, st = _open()
            try:
                if st['done']:
                    w, depth = st['width'], st['depth']
                    pre = int((q or {}).get('pre', 0))
                    words = (w + 30) // 31
                    start = (st['trigger_at'] - pre) % depth
                    vals = [0] * depth
                    for k in range(words):
                        a.cmd(1, k)
                        for i in range(depth):
                            vals[i] |= (a.cmd(0, (start + i) % depth) & 0x7FFFFFFF) << (31 * k)
                    return dict(st, trigger=pre, samples=['%x' % v for v in vals])
            finally:
                a.close()
        if time.time() - t0 >= wait:
            return dict(st, samples=None)
        time.sleep(0.05)
