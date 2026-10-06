"""Ardzy FPGA instruments, version 2 of the pin-control design ("ARZ2", projects/ardzy_io):
pin functions, 8 PWM outputs, 4 measuring channels, a UART on any pins, a 4096-sample logic
analyzer over 56 signals, I2C on the two board buses (bit-banged through the AXI GPIO) and the
chip's Device DNA. Register map: projects/ardzy_io/ardzy_ctl.v.

Safety: nothing here touches the FPGA unless the ardzy_io design is loaded and answers with
its ID, and the version-2 registers are only used when the ID says "ARZ2" (an address outside
the loaded design would give a bus error). The 4 board-ID straps can never be outputs.
"""
import struct, threading, time
import hwapi
from hwapi import Mem, io_map, io_ready, IO_GPIO

CTL = 0x43C00000
ID_V1, ID_V2 = 0x41525A31, 0x41525A32
DEPTH = 4096
FUNCS = ['gpio'] + ['pwm%d' % i for i in range(8)] + ['uart_tx']
ID_PINS = range(41, 45)                                  # board_id[0..3]
_lock = hwapi._lock
_ctl = None
_uart = {'baud': None, 'tx': None, 'rx': None}
_la = {}


# ------------------------------------------------------------------ helpers
def ctl():
    """The ardzy_ctl registers, after checking the design is there."""
    global _ctl
    if not io_ready():
        raise ValueError('load the pin-control design first (I/O view, "Load pin-control design")')
    if _ctl is None:
        _ctl = Mem(CTL, 0x10000)
    return _ctl


def version():
    v = ctl().rd(0)
    return 2 if v == ID_V2 else 1 if v == ID_V1 else 0


def v2():
    c = ctl()
    if c.rd(0) != ID_V2:
        raise ValueError('this needs the new pin-control design (version 2): press "Load pin-control design" again')
    return c


def signals():
    """Names of the 56 sampled signals: 49 pins, 6 fan speed inputs, the fan PWM."""
    return [p['name'] for p in io_map()] + ['fan_tach[%d]' % i for i in range(6)] + ['fan_pwm']


def sig_index(name):
    s = signals()
    if str(name).isdigit() and int(name) < len(s):
        return int(name)
    if name not in s:
        raise ValueError('unknown pin or signal: %s' % name)
    return s.index(name)


def pin_index(name):
    i = sig_index(name)
    if i >= 49:
        raise ValueError('%s is an input only signal' % name)
    return i


def fclk_hz():
    return hwapi.clocks()['fclk'][0]['mhz'] * 1e6


def funcs(c):
    regs = [c.rd(0x40 + 4 * k) for k in range(7)]
    return [regs[i // 8] >> (4 * (i % 8)) & 0xF for i in range(49)]


DNA_FILE = '/var/lib/ardzy/dna'


def dna(c=None):
    """The chip's 57-bit Device DNA. It never changes, so a good value is kept on the card:
    designs built with the open toolchain can not read it yet (they give 0) and show the kept one."""
    c = c or v2()
    hi, lo = c.rd(0x38), c.rd(0x34)
    val = ((hi & 0x1FFFFFF) << 32) | lo if hi >> 31 else 0
    if val:
        s = '%015X' % val
        if hwapi.read(DNA_FILE) != s:
            try:
                open(DNA_FILE, 'w').write(s)
            except OSError:
                pass
        return s
    return hwapi.read(DNA_FILE) or None


# ------------------------------------------------------------------ pins
def io_read():
    """hwapi.io_read() plus each pin's function, the design version and the Device DNA."""
    r = hwapi.io_read()
    c = ctl()
    r['version'] = version()
    if r['version'] == 2:
        fn = funcs(c)
        for i, p in enumerate(r['pins']):
            p['func'] = FUNCS[fn[i]] if fn[i] < len(FUNCS) and i not in ID_PINS else 'gpio'
        r['dna'] = dna(c)
        f = fclk_hz()
        r['fan']['rpm'] = [round(t / (c.rd(0x28) / f) * 60 / 2) for t in r['fan']['tach_pulses']]
    return r


def set_func(name, func):
    c = v2()
    i = pin_index(name)
    if i in ID_PINS:
        raise ValueError('board ID pins are fixed straps: input only')
    if func not in FUNCS:
        raise ValueError('function: ' + ', '.join(FUNCS))
    off, sh = 0x40 + 4 * (i // 8), 4 * (i % 8)
    with _lock:
        c.wr(off, (c.rd(off) & ~(0xF << sh)) | (FUNCS.index(func) << sh))
    return '%s = %s' % (name, func)


def io_set(name, mode):
    """GPIO In/0/1. With version 2 the pin is switched back to GPIO first."""
    if version() == 2 and mode in ('in', '0', '1'):
        i = pin_index(name)
        if i not in ID_PINS and funcs(ctl())[i] != 0:
            set_func(name, 'gpio')
    return hwapi.io_set(name, mode)


def release_func(func):
    """Every pin using this function goes back to GPIO."""
    c = v2()
    fn = funcs(c)
    names = [p['name'] for p in io_map()]
    for i, f in enumerate(fn):
        if i < 49 and f == FUNCS.index(func):
            set_func(names[i], 'gpio')


# ------------------------------------------------------------------ PWM
def pwm_read():
    c = v2()
    f = fclk_hz()
    fn = funcs(c)
    names = [p['name'] for p in io_map()]
    out = []
    for ch in range(8):
        per, hi = c.rd(0x60 + 8 * ch), c.rd(0x64 + 8 * ch)
        out.append({'ch': ch, 'period': per, 'high': hi, 'hz': round(f / max(per, 1), 3),
                    'duty_pct': round(100 * min(hi, per) / max(per, 1), 2), 'pulse_us': round(hi / f * 1e6, 3),
                    'pins': [names[i] for i in range(49) if fn[i] == ch + 1]})
    return {'fclk_hz': f, 'channels': out}


def pwm_set(ch, hz=None, duty=None, pulse_us=None, pin=None, release=None):
    c = v2()
    ch = int(ch)
    if ch not in range(8):
        raise ValueError('PWM channel 0..7')
    f = fclk_hz()
    po, ho = 0x60 + 8 * ch, 0x64 + 8 * ch
    with _lock:
        per = c.rd(po)
        ratio = c.rd(ho) / max(per, 1)
        if hz not in (None, ''):
            hz = float(hz)
            if not 0.02 <= hz <= f / 2:
                raise ValueError('frequency 0.02 Hz to %d MHz' % (f / 2e6))
            per = max(2, min(0xFFFFFFFF, round(f / hz)))
            c.wr(po, per)
            c.wr(ho, round(per * min(ratio, 1.0)))
        if duty not in (None, ''):
            c.wr(ho, round(per * max(0.0, min(100.0, float(duty))) / 100))
        if pulse_us not in (None, ''):
            c.wr(ho, min(per, round(float(pulse_us) * f / 1e6)))
    if release:
        release_func('pwm%d' % ch)
    if pin:
        set_func(pin, 'pwm%d' % ch)
    return pwm_read()


# ------------------------------------------------------------------ measuring channels
def meas_read():
    c = v2()
    f = fclk_hz()
    gate = c.rd(0x28)
    secs = gate / f
    names = signals()
    live = c.rd(0x128) | c.rd(0x12C) << 32
    out = []
    for ch in range(4):
        b = 0xA0 + 16 * ch
        sel, cnt, high, per = c.rd(b), c.rd(b + 4), c.rd(b + 8), c.rd(b + 12)
        r = {'ch': ch, 'signal': names[sel] if sel < len(names) else str(sel), 'level': live >> sel & 1,
             'edges': cnt, 'duty_pct': round(100 * high / max(gate, 1), 2), 'hz': round(cnt / secs, 3)}
        if per and per != 0xFFFFFFFF:
            r['period_us'] = round(per / f * 1e6, 3)
            if cnt < 1000:                                  # slow signals: the period is more exact
                r['hz_period'] = round(f / per, 4)
        out.append(r)
    return {'gate_s': round(secs, 4), 'fclk_hz': f, 'channels': out}


def meas_set(ch=None, signal=None, gate_s=None):
    c = v2()
    with _lock:
        if ch not in (None, '') and signal not in (None, ''):
            ch = int(ch)
            if ch not in range(4):
                raise ValueError('measuring channel 0..3')
            c.wr(0xA0 + 16 * ch, sig_index(signal))
        if gate_s not in (None, ''):
            g = float(gate_s)
            if not 0.01 <= g <= 10:
                raise ValueError('gate time 0.01 to 10 s')
            c.wr(0x28, max(1000, round(g * fclk_hz())))
    return meas_read()


# ------------------------------------------------------------------ UART on any pins
def uart_state():
    c = v2()
    f = fclk_hz()
    ctrl = c.rd(0xE0)
    st = c.rd(0xEC)
    fn = funcs(c)
    names = [p['name'] for p in io_map()]
    div = ctrl & 0xFFFF
    return {'enabled': bool(ctrl >> 31), 'baud': round(f / max(div, 4)), 'divider': div,
            'rx': signals()[ctrl >> 16 & 0x3F], 'tx': [names[i] for i in range(49) if fn[i] == 9],
            'waiting': st & 0x7FF, 'overflow': bool(st >> 16 & 1), 'frame_error': bool(st >> 17 & 1),
            'tx_free': c.rd(0xE4) & 0x7F}


def uart_config(baud=115200, tx=None, rx=None, enable=True):
    c = v2()
    f = fclk_hz()
    baud = float(baud)
    div = round(f / baud)
    if not 4 <= div <= 0xFFFF:
        raise ValueError('baud rate %d to %d at this clock' % (f / 0xFFFF + 1, f / 4))
    rxi = sig_index(rx) if rx not in (None, '') else c.rd(0xE0) >> 16 & 0x3F
    if tx not in (None, ''):
        release_func('uart_tx')
        set_func(tx, 'uart_tx')
    with _lock:
        c.wr(0xE0, (1 << 31 if enable else 0) | rxi << 16 | div)
        c.wr(0xEC, 1)                                      # clear old flags
    return uart_state()


def uart_send(data):
    c = v2()
    if not c.rd(0xE0) >> 31:
        raise ValueError('the UART is off: set it up first')
    t0 = time.monotonic()
    sent = 0
    for b in data:
        while not c.rd(0xE4) & 0x7F:                       # queue full: wait for the wire
            if time.monotonic() - t0 > 5:
                raise ValueError('UART send timeout after %d bytes' % sent)
            time.sleep(0.0005)
        c.wr(0xE4, b)
        sent += 1
    return sent


def uart_recv(limit=4096):
    c = v2()
    data = bytearray()
    with _lock:
        n = min(c.rd(0xEC) & 0x7FF, limit)
        for _ in range(n):
            v = c.rd(0xE8)
            if not v >> 8 & 1:
                break
            data.append(v & 0xFF)
    st = uart_state()
    if st['overflow'] or st['frame_error']:
        c.wr(0xEC, 1)
    st['data_hex'] = data.hex()
    return st


# ------------------------------------------------------------------ logic analyzer
def la_start(rate_hz=1e6, pre_pct=10, trig='', edge=None):
    """trig: comma separated conditions 'name:rise', 'name:fall', 'name:1', 'name:0'.
    Empty = capture at once. The trigger is the moment the whole pattern starts to match
    (edge mode) as soon as one condition is rise/fall, else any time it matches."""
    c = v2()
    f = fclk_hz()
    rate = float(rate_hz)
    if not 1 <= rate <= f:
        raise ValueError('sample rate 1 Hz to %d MHz' % (f / 1e6))
    div = max(0, round(f / rate) - 1)
    pre = max(0, min(DEPTH - 1, int(DEPTH * float(pre_pct) / 100)))
    mask = val = 0
    is_edge = False
    conds = []
    for t in [x.strip() for x in str(trig).split(',') if x.strip()]:
        name, _, kind = t.rpartition(':')
        i = sig_index(name)
        if kind not in ('rise', 'fall', '1', '0'):
            raise ValueError('trigger kind: rise, fall, 1 or 0')
        mask |= 1 << i
        if kind in ('rise', '1'):
            val |= 1 << i
        is_edge |= kind in ('rise', 'fall')
        conds.append({'signal': name, 'kind': kind})
    if edge is not None and edge != '':
        is_edge = str(edge) in ('1', 'true')
    with _lock:
        c.wr(0x100, 2)                                     # stop a running capture
        c.wr(0x104, div)
        c.wr(0x108, pre)
        c.wr(0x10C, mask & 0xFFFFFFFF); c.wr(0x110, mask >> 32)
        c.wr(0x114, val & 0xFFFFFFFF); c.wr(0x118, val >> 32)
        c.wr(0x11C, 1 if is_edge else 0)
        c.wr(0x100, 1)
    _la.clear()
    _la.update({'rate_hz': f / (div + 1), 'pre': pre, 'trigger': conds, 'edge': is_edge, 'started': time.time()})
    return la_status()


def la_status():
    c = v2()
    s = c.rd(0x100)
    out = {'running': bool(s & 1), 'triggered': bool(s & 2), 'done': bool(s & 4),
           'write_index': c.rd(0x124), 'depth': DEPTH}
    out.update({k: v for k, v in _la.items() if k != 'started'})
    if _la.get('started'):
        out['elapsed_s'] = round(time.time() - _la['started'], 2)
    if not _la:
        out['rate_hz'] = fclk_hz() / (c.rd(0x104) + 1)
        out['pre'] = c.rd(0x108)
    if out['rate_hz']:
        out['window_s'] = DEPTH / out['rate_hz']
    return out


def la_ctrl(action):
    c = v2()
    if action == 'force':
        c.wr(0x100, 4)
    elif action == 'stop':
        c.wr(0x100, 2)
    else:
        raise ValueError('action: force, stop')
    return la_status()


def la_data():
    """The finished capture, oldest sample first, as a list of changes [index, low32, high32]."""
    c = v2()
    st = la_status()
    if not st['done']:
        raise ValueError('no finished capture yet' + (' (waiting for the trigger)' if st['running'] else ''))
    tidx, pre = c.rd(0x120), c.rd(0x108)
    with _lock:
        words = c.w[0x8000 // 4:0x8000 // 4 + 2 * DEPTH].tolist()
    start = (tidx - pre) % DEPTH
    changes, last = [], None
    for k in range(DEPTH):
        j = (start + k) % DEPTH
        lo, hi = words[2 * j], words[2 * j + 1]
        if (lo, hi) != last:
            changes.append([k, lo, hi])
            last = (lo, hi)
    return {'rate_hz': st['rate_hz'], 'n': DEPTH, 'trigger_at': pre, 'signals': signals(),
            'changes': changes, 'trigger': st.get('trigger', [])}


# ------------------------------------------------------------------ I2C (bit-banged, open drain)
I2C_BUS = {1: (13, 14), 2: (15, 16)}                       # AXI GPIO channel 2 bits (SCL, SDA)
I2C_NAMES = {1: ('i2c1_scl', 'i2c1_sda'), 2: ('i2c2_scl', 'i2c2_sda')}


class I2C:
    """Open-drain I2C through the AXI GPIO: a line is pulled low by making its pin an output
    with value 0, and released (the board's 1 kohm pull-up makes it 1) by making it an input.
    Speed is about 20 to 50 kHz (each step is one register write from Python)."""

    def __init__(self, bus):
        bus = int(bus)
        if bus not in I2C_BUS:
            raise ValueError('I2C bus 1 (J1..J8) or 2 (J9)')
        c = ctl()
        if c.rd(0) == ID_V2:
            for n in I2C_NAMES[bus]:
                if funcs(c)[pin_index(n)] != 0:
                    set_func(n, 'gpio')
        self.g = Mem(IO_GPIO, 0x10000)
        self.scl, self.sda = (1 << b for b in I2C_BUS[bus])
        self.g.wr(0x8, self.g.rd(0x8) & ~(self.scl | self.sda))   # output value 0 for both lines
        self.release(self.scl | self.sda)

    def low(self, m):
        self.g.wr(0xC, self.g.rd(0xC) & ~m)

    def release(self, m):
        self.g.wr(0xC, self.g.rd(0xC) | m)

    def get(self, m):
        return bool(self.g.rd(0x8) & m)

    def scl_high(self):
        self.release(self.scl)
        t0 = time.monotonic()
        while not self.get(self.scl):                       # a device may hold SCL (clock stretching)
            if time.monotonic() - t0 > 0.01:
                raise ValueError('SCL is held low')

    def recover(self):
        """Free a bus left in the middle of a byte: 9 clocks, then a stop."""
        self.release(self.sda)
        for _ in range(9):
            if self.get(self.sda):
                break
            self.low(self.scl)
            self.scl_high()
        self.stop()

    def start(self):
        self.release(self.sda)
        self.scl_high()
        if not self.get(self.sda):
            self.recover()
        self.low(self.sda)
        self.low(self.scl)

    def stop(self):
        self.low(self.sda)
        self.scl_high()
        self.release(self.sda)

    def write(self, b):
        for k in range(7, -1, -1):
            (self.release if b >> k & 1 else self.low)(self.sda)
            self.scl_high()
            self.low(self.scl)
        self.release(self.sda)
        self.scl_high()
        ack = not self.get(self.sda)
        self.low(self.scl)
        return ack

    def read(self, ack):
        self.release(self.sda)
        v = 0
        for _ in range(8):
            self.scl_high()
            v = v << 1 | self.get(self.sda)
            self.low(self.scl)
        if ack:
            self.low(self.sda)
        self.scl_high()
        self.low(self.scl)
        self.release(self.sda)
        return v


def i2c_lines(bus):
    with _lock:
        b = I2C(bus)
        return {'scl': int(b.get(b.scl)), 'sda': int(b.get(b.sda))}


def i2c_scan(bus):
    """Like i2cdetect: a read for 0x30-0x37 and 0x50-0x5F (EEPROMs), an empty write elsewhere."""
    found = []
    with _lock:
        b = I2C(bus)
        if not b.get(b.scl) or not b.get(b.sda):
            b.recover()
        if not b.get(b.scl) or not b.get(b.sda):
            raise ValueError('bus %s: a line is stuck low (SCL=%d SDA=%d)' % (bus, b.get(b.scl), b.get(b.sda)))
        for a in range(0x08, 0x78):
            rd = 0x30 <= a <= 0x37 or 0x50 <= a <= 0x5F
            b.start()
            if b.write(a << 1 | rd):
                found.append(a)
                if rd:
                    b.read(False)
            b.stop()
    return {'bus': int(bus), 'found': ['0x%02X' % a for a in found], 'count': len(found)}


def _addr(a):
    a = int(str(a), 0)
    if not 0x03 <= a <= 0x77:
        raise ValueError('I2C address 0x03 to 0x77')
    return a


def i2c_read(bus, addr, reg=None, n=1):
    a, n = _addr(addr), max(1, min(256, int(n)))
    with _lock:
        b = I2C(bus)
        b.start()
        if reg not in (None, ''):
            if not b.write(a << 1):
                b.stop()
                raise ValueError('no answer from 0x%02X' % a)
            for x in bytes.fromhex(str(reg)) if len(str(reg)) > 4 else [int(str(reg), 0)]:
                b.write(x)
            b.start()                                       # repeated start
        if not b.write(a << 1 | 1):
            b.stop()
            raise ValueError('no answer from 0x%02X' % a)
        data = bytes(b.read(k < n - 1) for k in range(n))
        b.stop()
    return {'addr': '0x%02X' % a, 'data_hex': data.hex(), 'data': list(data)}


def i2c_write(bus, addr, data_hex):
    a = _addr(addr)
    data = bytes.fromhex(data_hex.replace(' ', ''))
    if not data or len(data) > 256:
        raise ValueError('1 to 256 bytes')
    with _lock:
        b = I2C(bus)
        b.start()
        if not b.write(a << 1):
            b.stop()
            raise ValueError('no answer from 0x%02X' % a)
        acks = [b.write(x) for x in data]
        b.stop()
    return 'wrote %d bytes to 0x%02X%s' % (len(data), a, '' if all(acks) else ' (some bytes not acknowledged)')
