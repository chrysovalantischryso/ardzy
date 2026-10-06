"""blocks.py - Python drivers for the Ardzy FPGA blocks (the FPGA projects), on the board.

Every project has the same layout on the ARM side: a 64 KB window at 0x43C0_0000, cut into 16 slots
of 4 KB. Slot 0 is always the Info block (project name, seconds, the 4 LEDs). The other slots hold
the project's blocks; project.json / the guide list which block is in which slot.

    from blocks import Bus, Info, LedStrip
    bus = Bus()
    print(Info(bus).project())          # e.g. 'LEDS'
    strip = LedStrip(bus, slot=1)
"""
import time

try:
    from ardzy import MMIO
except ImportError:                       # for tests on a PC
    MMIO = None

BASE = 0x43C00000


class Bus:
    """The register window of an Ardzy FPGA project."""

    def __init__(self, base=BASE):
        self.m = MMIO(base, 0x10000)

    def rd(self, slot, i):
        return self.m.read(slot * 0x1000 + 4 * i)

    def wr(self, slot, i, v):
        self.m.write(slot * 0x1000 + 4 * i, int(v) & 0xFFFFFFFF)

    def rd_signed(self, slot, i):
        v = self.rd(slot, i)
        return v - (1 << 32) if v & 0x80000000 else v


def _text(v):
    return v.to_bytes(4, 'big').decode('ascii', 'replace')


class Block:
    def __init__(self, bus, slot):
        self.bus, self.slot = bus, slot

    def r(self, i):
        return self.bus.rd(self.slot, i)

    def rs(self, i):
        return self.bus.rd_signed(self.slot, i)

    def w(self, i, v):
        self.bus.wr(self.slot, i, v)


class Info(Block):
    """Slot 0: which project is loaded, uptime, the 4 board LEDs."""

    def __init__(self, bus, slot=0):
        super().__init__(bus, slot)

    def ok(self):
        return self.r(0) == 0x4152445A

    def project(self):
        return _text(self.r(1))

    def version(self):
        return self.r(2)

    def seconds(self):
        return self.r(3)

    def leds(self, value=None):
        if value is not None:
            self.w(4, value & 0xF)
        return self.r(4)


def require(bus, project):
    """Stop with a clear message when another FPGA design is loaded."""
    info = Info(bus)
    if not info.ok() or info.project() != project:
        raise SystemExit('The FPGA does not hold the %s project (found %r). Upload this project first.'
                         % (project, info.project() if info.ok() else 'another design'))
    return info


# ---------------------------------------------------------------------------------------- LED strip
class LedStrip(Block):
    """WS2812 / WS2812B / SK6812 LED strip. Pixels are 0xRRGGBB."""
    ORDERS = {'GRB': 0, 'RGB': 1, 'BRG': 2, 'RBG': 3, 'BGR': 4, 'GBR': 5}

    def __init__(self, bus, slot=1, count=None):
        super().__init__(bus, slot)
        if count:
            self.count(count)

    def count(self, n=None):
        if n is not None:
            self.w(1, n)
        return self.r(1)

    def brightness(self, b=None):
        if b is not None:
            self.w(2, max(0, min(255, int(b))))
        return self.r(2)

    def order(self, name):
        self.w(3, self.ORDERS[name.upper()])

    def timing(self, t0h_ns=400, t1h_ns=800, bit_ns=1250, reset_us=300):
        """WS2812B defaults. SK6812: t0h 300, t1h 600, bit 1250, reset 80."""
        self.w(4, round(t0h_ns / 10))
        self.w(5, round(t1h_ns / 10))
        self.w(6, round(bit_ns / 10))
        self.w(7, round(reset_us * 100))

    def set(self, i, rgb):
        self.bus.wr(self.slot + 1, i, rgb)

    def fill(self, rgb, n=None):
        for i in range(n if n is not None else self.count()):
            self.set(i, rgb)

    def write(self, pixels):
        for i, p in enumerate(pixels):
            self.set(i, p)

    def busy(self):
        return bool(self.r(0) & 1)

    def frames(self):
        return self.r(0) >> 8

    def show(self, wait=True):
        while self.busy():
            pass
        self.w(0, 1)
        if wait:
            time.sleep(0.0005)
            while self.busy():
                pass

    def pin_stats(self):
        """What the pin really did during the last frame (read back at the pad)."""
        return {'pulses': self.r(8), 'short_ns': self.r(9) * 10, 'long_ns': self.r(10) * 10}


def rgb(r, g, b):
    return (int(r) & 255) << 16 | (int(g) & 255) << 8 | (int(b) & 255)


def wheel(pos):
    """Colour wheel 0..255 -> 0xRRGGBB (red -> green -> blue -> red)."""
    pos &= 255
    if pos < 85:
        return rgb(255 - pos * 3, pos * 3, 0)
    if pos < 170:
        pos -= 85
        return rgb(0, 255 - pos * 3, pos * 3)
    pos -= 170
    return rgb(pos * 3, 0, 255 - pos * 3)


# ---------------------------------------------------------------------------------------- pattern generator
class PatternGen(Block):
    """Plays a table of up to 1024 steps on 16 pins. Step k of the table = pin levels (bit n = pin n)."""

    def __init__(self, bus, slot=1):
        super().__init__(bus, slot)

    def load(self, steps):
        steps = list(steps)
        for i, v in enumerate(steps[:1024]):
            self.bus.wr(self.slot + 1, i, v)
        self.w(1, max(1, min(1024, len(steps))))

    def rate(self, steps_per_second):
        """Up to 100,000,000 steps per second (exactly 100 MHz / a whole number)."""
        self.w(2, max(0, round(100e6 / steps_per_second) - 1))

    def outputs(self, mask):
        self.w(3, mask & 0xFFFF)

    def idle(self, levels):
        self.w(4, levels & 0xFFFF)

    def start(self, loop=True):
        self.w(0, 1 | (2 if loop else 0))

    def stop(self):
        self.w(0, 0)

    def running(self):
        return bool(self.r(0) & 1)

    def status(self):
        return {'running': self.running(), 'step': self.r(5), 'loops': self.r(6), 'mismatches': self.r(7),
                'inputs': self.r(8)}


# ---------------------------------------------------------------------------------------- encoders
class Encoders(Block):
    """Quadrature encoder counters. 4 counts per encoder line (every edge of A and B)."""

    def __init__(self, bus, slot=1):
        super().__init__(bus, slot)

    def count(self, ch, value=None):
        if value is not None:
            self.w(8 * ch, value)
        return self.rs(8 * ch)

    def speed(self, ch):
        """Counts per second (from the last gate time)."""
        return self.rs(8 * ch + 1) * 100e6 / self.r(64)

    def errors(self, ch):
        return self.r(8 * ch + 2)

    def config(self, ch, reverse=False, filter_ns=200):
        self.w(8 * ch + 3, (1 if reverse else 0) | (max(0, min(255, round(filter_ns / 10))) << 8))

    def gate(self, seconds):
        self.w(64, round(seconds * 100e6))

    def test(self, internal=False, drive_pins=False):
        """internal: the generator feeds every counter (no pins). drive_pins: it drives channel 0's
        pins A and B (nothing may be connected to them)."""
        self.w(65, (1 if internal else 0) | (2 if drive_pins else 0))

    def generate(self, steps=0, counts_per_second=100000, backwards=False):
        """Make quadrature steps (steps = 0: run on until generate() is called again)."""
        self.w(66, max(4, round(100e6 / counts_per_second)))
        self.w(67, (steps & 0x7FFFFFFF) | (0x80000000 if backwards else 0))

    def generator_left(self):
        return self.r(67)

    def generator_done(self):
        return self.r(68)


# ---------------------------------------------------------------------------------------- steppers
class Stepper(Block):
    """One step/dir axis with acceleration (axis 0 or 1 of the stepper block)."""
    K = 2 ** 40 / 1e6                         # steps per second -> the block's speed unit

    def __init__(self, bus, slot=1, axis=0):
        super().__init__(bus, slot)
        self.o = 16 * axis

    def setup(self, max_speed=2000, accel=4000, start_speed=100, pulse_us=2.0, dir_setup_us=5.0):
        """Speeds in steps per second, acceleration in steps per second per second."""
        v = round(max_speed * self.K)
        self.w(self.o + 2, v & 0xFFFFFFFF)
        self.w(self.o + 3, v >> 32)
        self.w(self.o + 4, max(1, round(accel * 2 ** 40 / 1e12)))
        self.w(self.o + 5, round(start_speed * self.K))
        self.w(self.o + 8, round(pulse_us * 100))
        self.w(self.o + 11, round(dir_setup_us * 100))

    def move_to(self, position):
        self.w(self.o, position)

    def move(self, steps):
        self.w(self.o, self.target() + steps)

    def target(self):
        return self.rs(self.o)

    def position(self, value=None):
        if value is not None:
            self.w(self.o + 1, value)
        return self.rs(self.o + 1)

    def moving(self):
        return bool(self.r(self.o + 6) & 9)

    def speed(self):
        return (self.r(self.o + 7) << 8) / self.K

    def stop(self, now=False):
        self.w(self.o + 9, 2 if now else 1)

    def wait(self, timeout=60):
        t = time.time()
        while self.moving() and time.time() - t < timeout:
            time.sleep(0.005)
        return not self.moving()

    def pin_steps(self, clear=False):
        v = self.r(self.o + 10)
        if clear:
            self.w(self.o + 10, 0)
        return v


# ---------------------------------------------------------------------------------------- SPI
class SPI(Block):
    def __init__(self, bus, slot=1):
        super().__init__(bus, slot)

    def setup(self, hz=1000000, mode=0, bits=8, lsb_first=False, loopback=False, auto_cs=True):
        self.w(1, max(0, round(100e6 / (2 * hz)) - 1))
        self.w(2, bits)
        self.w(0, (mode & 3) | (4 if lsb_first else 0) | (8 if loopback else 0) | (16 if auto_cs else 0))

    def hz(self):
        return 100e6 / (2 * (self.r(1) + 1))

    def cs(self, level):
        self.w(6, 1 if level else 0)

    def transfer(self, words):
        """Send words; returns the words received at the same time (SPI is full duplex)."""
        out = []
        words = list(words)
        for k in range(0, len(words), 64):
            chunk = words[k:k + 64]
            for v in chunk:
                self.w(3, v)
            t = time.time()
            while len(out) < k + len(chunk) and time.time() - t < 2:
                if (self.r(5) >> 8) & 0x7F:
                    out.append(self.r(4))
        return out

    def busy(self):
        return bool(self.r(5) & (1 << 16))


# ---------------------------------------------------------------------------------------- I2C
class I2C(Block):
    START, STOP, WRITE, READ, READ_LAST = 1, 2, 3, 4, 5

    def __init__(self, bus, slot=1, hz=100000):
        super().__init__(bus, slot)
        self.speed(hz)

    def speed(self, hz):
        self.w(3, max(4, round(100e6 / (4 * hz)) - 1))

    def _cmd(self, c, d=0):
        self.w(0, (c << 8) | (d & 0xFF))

    def _results(self, n, timeout=0.5):
        out, t = [], time.time()
        while len(out) < n and time.time() - t < timeout:
            v = self.r(1)
            if v & 0x80000000:
                out.append(v)
        return out

    def write(self, addr, data=b''):
        """Write bytes to a device. True when every byte was acknowledged."""
        self._cmd(self.START)
        self._cmd(self.WRITE, addr << 1)
        for b in data:
            self._cmd(self.WRITE, b)
        self._cmd(self.STOP)
        res = self._results(1 + len(data))
        return len(res) == 1 + len(data) and all(v & 0x100 for v in res)

    def read(self, addr, n, reg=None):
        """Read n bytes (after writing a register number first, if given). None when no ACK."""
        k = 1
        self._cmd(self.START)
        if reg is not None:
            self._cmd(self.WRITE, addr << 1)
            self._cmd(self.WRITE, reg)
            self._cmd(self.START)
            k += 2
        self._cmd(self.WRITE, (addr << 1) | 1)
        for i in range(n):
            self._cmd(self.READ_LAST if i == n - 1 else self.READ)
        self._cmd(self.STOP)
        res = self._results(k + n)
        if len(res) != k + n or not all(v & 0x100 for v in res[:k]):
            return None
        return bytes(v & 0xFF for v in res[k:])

    def scan(self):
        return [a for a in range(0x08, 0x78) if self.write(a)]

    def lines(self):
        s = self.r(2)
        return {'scl': (s >> 17) & 1, 'sda': (s >> 18) & 1, 'timeout': (s >> 19) & 1}


# ---------------------------------------------------------------------------------------- signal generator
class SignalGen(Block):
    WAVES = {'sine': 0, 'triangle': 1, 'saw': 2, 'square': 3}
    K = 2 ** 32 / 100e6

    def __init__(self, bus, slot=1):
        super().__init__(bus, slot)

    def frequency(self, hz=None):
        if hz is not None:
            self.w(1, round(hz * self.K))
        return self.r(12) / self.K

    def wave(self, name):
        self.w(2, self.WAVES[name])

    def amplitude(self, a):
        """0..1"""
        self.w(3, max(0, min(65535, round(a * 65535))))

    def offset(self, o):
        """-1..1"""
        self.w(4, max(-32768, min(32767, round(o * 32767))) & 0xFFFF)

    def duty(self, d):
        """0..1 (square wave)"""
        self.w(5, max(0, min(65535, round(d * 65535))))

    def on(self, enable=True):
        self.w(0, (self.r(0) & ~1) | (1 if enable else 0))

    def sweep(self, start_hz, stop_hz, seconds, repeat=True, steps_per_second=1000):
        n = max(1, round(seconds * steps_per_second))
        self.w(1, round(start_hz * self.K))
        self.w(6, round(stop_hz * self.K))
        self.w(7, round((stop_hz - start_hz) * self.K / n) & 0xFFFFFFFF)
        self.w(8, round(100e6 / steps_per_second))
        self.w(0, 1 | 2 | (4 if repeat else 0))

    def sweep_off(self):
        self.w(0, self.r(0) & 1)

    def measured_hz(self):
        return self.r(11)

    def phase(self, turns):
        self.w(9, round(turns * 2 ** 32) & 0xFFFFFFFF)

    def sample(self):
        return self.rs(10)


# ---------------------------------------------------------------------------------------- VGA
_FONT = None


def font8():
    """8 x 8 font for the characters 32..126 (font8x8.py next to this file, 8 bytes per character)."""
    global _FONT
    if _FONT is None:
        try:
            from font8x8 import FONT
            _FONT = FONT
        except ImportError:
            _FONT = bytes(8 * 95)
    return _FONT


class VGA(Block):
    """320 x 240 pixels, 16 colours (palette entries 0..15), shown 2 x 2 on a 640 x 480 VGA screen."""
    W, H = 320, 240
    BLACK, BLUE, GREEN, CYAN, RED, MAGENTA, BROWN, GREY, DARKGREY, LBLUE, LGREEN, LCYAN, LRED, PINK, YELLOW, WHITE = range(16)

    def __init__(self, bus, slot=1):
        super().__init__(bus, slot)
        self.buf = [0] * 9600

    def on(self, picture=True, test_pattern=False):
        self.w(0, (1 if picture else 0) | (2 if test_pattern else 0))

    def palette(self, n, r, g, b):
        """r, g, b 0..3"""
        self.w(16 + n, (r & 3) << 4 | (g & 3) << 2 | (b & 3))

    def clear(self, c=0):
        word = 0
        for k in range(8):
            word |= (c & 15) << (4 * k)
        self.buf = [word] * 9600

    def pixel(self, x, y, c):
        if 0 <= x < 320 and 0 <= y < 240:
            i = y * 40 + (x >> 3)
            s = 4 * (x & 7)
            self.buf[i] = (self.buf[i] & ~(15 << s)) | ((c & 15) << s)

    def rect(self, x, y, w, h, c):
        for yy in range(max(0, y), min(240, y + h)):
            for xx in range(max(0, x), min(320, x + w)):
                self.pixel(xx, yy, c)

    def line(self, x0, y0, x1, y1, c):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.pixel(x0, y0, c)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def text(self, x, y, s, c, scale=1):
        f = font8()
        for ch in s:
            o = (ord(ch) - 32) * 8
            if 0 <= o < len(f):
                for row in range(8):
                    bits = f[o + row]
                    for col in range(8):
                        if bits & (0x80 >> col):
                            if scale == 1:
                                self.pixel(x + col, y + row, c)
                            else:
                                self.rect(x + col * scale, y + row * scale, scale, scale, c)
            x += 8 * scale

    def show(self, rows=None):
        """Send the picture (or only rows y0..y1-1) to the frame buffer."""
        y0, y1 = rows if rows else (0, 240)
        for i in range(y0 * 40, y1 * 40):
            self.bus.wr(self.slot + 1 + (i >> 10), i & 1023, self.buf[i])

    def probe(self, sx, sy):
        """What the monitor gets at screen position (sx 0..639, sy 0..479): (frame-buffer value, 6-bit colour).
        Waits one frame (the picture side captures it while drawing)."""
        self.w(5, (sy & 1023) << 16 | (sx & 1023))
        time.sleep(0.04)
        v = self.r(6)
        return v >> 6, v & 63

    def sync_check(self):
        return {'frames': self.r(1), 'line_us': self.r(2) / 100, 'frame_ms': self.r(3) / 1e5,
                'clock_locked': bool(self.r(0) & 4)}


# ---------------------------------------------------------------------------------------- audio
class Audio(Block):
    FS = 100e6 / 2048          # 48828.125 samples per second

    def __init__(self, bus, slot=1):
        super().__init__(bus, slot)

    def setup(self, out=True, tone=False, rx=False, rx_source='din', pdm_test=False):
        src = {'din': 0, 'loop': 1, 'pin': 2, 'pdm': 3}[rx_source]
        self.w(0, (1 if out else 0) | (2 if tone else 0) | (src << 2) | (16 if rx else 0) | (32 if pdm_test else 0))

    def tone(self, hz):
        self.w(5, round(hz / self.FS * 2 ** 32))

    def volume(self, v):
        """0..1"""
        self.w(6, max(0, min(256, round(v * 256))))

    def play(self, samples):
        """samples: (left, right) pairs, -32768..32767, at 48828 samples per second. Writes in bursts
        into the 2048-sample buffer (the level is read once per burst, not per sample)."""
        it = iter(samples)
        free = 0
        while True:
            if free <= 0:
                free = 2048 - self.r(2)
                if free < 256:
                    time.sleep(0.004)
                    continue
            try:
                l, r = next(it)
            except StopIteration:
                return
            self.w(1, (r & 0xFFFF) << 16 | (l & 0xFFFF))
            free -= 1

    def preload(self, samples):
        """Fill the buffer while sound is off (at most 2048 samples); start() then plays them from the start."""
        self.setup(out=False)
        for l, r in list(samples)[:2048]:
            self.w(1, (r & 0xFFFF) << 16 | (l & 0xFFFF))

    def record(self, n, timeout=5):
        out, t = [], time.time()
        while len(out) < n and time.time() - t < timeout:
            k = self.r(4)
            for _ in range(min(k, n - len(out))):
                v = self.r(3)
                l, r = v & 0xFFFF, v >> 16
                out.append((l - 65536 if l & 0x8000 else l, r - 65536 if r & 0x8000 else r))
            if not k:
                time.sleep(0.001)
        return out

    def drain(self):
        while self.r(4):
            self.r(3)

    def lrclk_hz(self):
        p = self.r(9)
        return 100e6 / p if p else 0


# ---------------------------------------------------------------------------------------- sensors
class Sensors(Block):
    def __init__(self, bus, slot=1):
        super().__init__(bus, slot)

    def setup(self, distance=True, echo_sim=False, touch=True, ir_test=False):
        self.w(0, (1 if distance else 0) | (2 if echo_sim else 0) | (4 if touch else 0) | (8 if ir_test else 0))

    def distance_mm(self):
        return self.r(3) if self.r(2) else None

    def echo_us(self):
        return self.r(2)

    def simulate_echo(self, us):
        self.w(6, us)

    def rangings(self):
        return {'done': self.r(4), 'timeouts': self.r(5)}

    def ir(self):
        c = self.r(7)
        a, na, cmd, ncmd = c & 255, (c >> 8) & 255, (c >> 16) & 255, c >> 24
        return {'count': self.r(8), 'repeats': self.r(9), 'errors': self.r(10), 'address': a, 'command': cmd,
                'valid': (a ^ na) == 255 and (cmd ^ ncmd) == 255, 'raw': c}

    def ir_send_test(self, address, command):
        self.w(11, address | (~address & 255) << 8 | command << 16 | (~command & 255) << 24)

    def touch(self):
        t = self.r(14)
        return {'raw': self.r(12), 'base': self.r(13), 'touched': bool(t & 1), 'touches': t >> 8}

    def touch_threshold(self, clocks):
        self.w(15, clocks)


# ---------------------------------------------------------------------------------------- stream lab
class StreamLab(Block):
    """The AXI-Stream lab of project 11 (chains A: CRC-32, B: speed meter, C: arbiter)."""

    def __init__(self, bus, slot=1):
        super().__init__(bus, slot)

    def reset(self):
        self.w(0, 1)

    def sources(self, b=False, c=False):
        self.w(0, (2 if b else 0) | (4 if c else 0))

    def crc_frame(self, data):
        """Send bytes (a multiple of 4) through chain A; returns the CRC-32 the FPGA computed."""
        words = [int.from_bytes(data[i:i + 4], 'little') for i in range(0, len(data), 4)]
        n = self.r(4)
        for i, w in enumerate(words):
            self.w(2 if i == len(words) - 1 else 1, w)
        t = time.time()
        while self.r(4) == n and time.time() - t < 1:
            pass
        return self.r(3)

    def meter(self):
        return {'per_sec': self.r(6), 'words': self.r(7), 'errors': self.r(8)}

    def slow(self, n):
        self.w(9, n)

    def frame_len(self, n):
        self.w(10, n)

    def take(self, n):
        """Take up to n words from chain C: list of (word, last, source)."""
        out = []
        while len(out) < n and self.r(12):
            w = self.r(11)
            info = self.r(13)
            out.append((w, bool(info & 1), (info >> 1) & 1))
        return out


# ---------------------------------------------------------------------------------------- RISC-V
class RiscV(Block):
    """The RISC-V computer: its 16 KB RAM is in slots slot+1 .. slot+4."""

    def __init__(self, bus, slot=1):
        super().__init__(bus, slot)

    def stop(self):
        self.w(0, 0)

    def load(self, words):
        self.stop()
        for i, v in enumerate(words):
            self.bus.wr(self.slot + 1 + (i >> 10), i & 1023, v)

    def start(self):
        self.w(0, 0)
        self.w(0, 1)

    def peek(self, addr):
        return self.bus.rd(self.slot + 1 + (addr >> 12), (addr & 0xFFF) >> 2)

    def poke(self, addr, value):
        self.bus.wr(self.slot + 1 + (addr >> 12), (addr & 0xFFF) >> 2, value)

    def status(self):
        s = self.r(1)
        return {'running': bool(s & 1), 'halted': bool(s & 2), 'illegal': bool(s & 4), 'pc': self.r(2),
                'retired': self.r(7)}

    def console(self):
        out = []
        while True:
            v = self.r(3)
            if not v & 0x80000000:
                break
            out.append(chr(v & 0xFF))
        return ''.join(out)

    def mail(self, value=None):
        if value is not None:
            self.w(5, value)
        return self.r(6)

    def wait(self, timeout=10):
        """Collect the console until the program stops (or timeout seconds)."""
        t, text = time.time(), ''
        while time.time() - t < timeout:
            text += self.console()
            if self.status()['halted']:
                break
            time.sleep(0.01)
        return text + self.console()


# ---------------------------------------------------------------------------------------- radio
class Radio(Block):
    """The radio transmitter (ardzy_radio): FM stereo with RDS, AM, a carrier, and a symbol player.
    Uses 6 slots: `slot` registers, slot + 1 RDS blocks, slot + 2 .. slot + 5 the MPX capture."""
    CLK = 500e6                       # carrier samples per second
    FS_AUDIO = 100e6 / 2048           # 48828.125 audio samples per second
    FS_MPX = 100e6 / 256              # 390625 MPX samples per second
    MODES = {'off': 0, 'carrier': 1, 'fm': 2, 'am': 3, 'symbols': 4, 'usb': 5, 'lsb': 6, 'dsb': 7}
    BITS = {'tx': 0, 'stereo': 1, 'rds': 2, 'pilot': 3, 'mute': 6, 'tones': 7, 'narrow': 8}

    def __init__(self, bus, slot=1):
        super().__init__(bus, slot)
        m = bus.m
        self._mv = m._w                                       # fast path for the audio and symbol FIFOs
        self._a_audio = (m._off + slot * 0x1000 + 4 * 9) >> 2

    def ok(self):
        return self.r(29) == 0x464D5458

    def locked(self):
        return bool(self.r(28) & 1)

    @classmethod
    def inc(cls, hz):
        return round(hz / cls.CLK * 2 ** 32) & 0xFFFFFFFF

    def frequency(self, hz=None):
        if hz is not None:
            self.w(2, self.inc(hz))
        return self.r(2) * self.CLK / 2 ** 32

    def mode(self, name=None):
        if name is not None:
            self.w(1, self.MODES[name])
        return {v: k for k, v in self.MODES.items()}.get(self.r(1), '?')

    def setup(self, preemph=None, **flags):
        """Switch parts on or off: tx, stereo, rds, pilot, mute, tones, narrow (the 300 .. 2700 Hz voice
        filter, mono: for NFM and AM) (True / False); preemph 0, 50 or 75 (us)."""
        c = self.r(0)
        for k, v in flags.items():
            if v is not None:
                c = (c | (1 << self.BITS[k])) if v else (c & ~(1 << self.BITS[k]))
        if preemph is not None:
            c = (c & ~0x30) | ({0: 0, 50: 1, 75: 2}[int(preemph)] << 4)
        self.w(0, c)
        return c

    def flags(self):
        c = self.r(0)
        d = {k: bool(c >> b & 1) for k, b in self.BITS.items()}
        d['preemph'] = [0, 50, 75, 0][(c >> 4) & 3]
        return d

    def deviation(self, hz=75000):
        """FM deviation at full MPX (75 kHz broadcast, 5 kHz or 2.5 kHz for narrow FM)."""
        self.w(3, round(hz / self.CLK * 2 ** 32 * 65536 / 32767))

    def levels(self, audio=0.87, pilot=0.09, rds=0.04):
        """Shares of the MPX signal (the total should stay at or below 1)."""
        self.w(4, round(audio * 32768) & 0x7FFF)
        self.w(5, round(pilot * 32768) & 0x7FFF)
        self.w(6, round(rds * 32768) & 0x7FFF)

    def volume(self, v=1.0):
        self.w(7, max(0, min(1023, round(v * 256))))

    def tones(self, left_hz=1000, right_hz=400):
        self.w(11, round(left_hz / self.FS_AUDIO * 2 ** 32) & 0xFFFFFFFF)
        self.w(12, round(right_hz / self.FS_AUDIO * 2 ** 32) & 0xFFFFFFFF)

    def am_depth(self, d=0.9):
        self.w(13, round(max(0.0, min(0.999, d)) * 32768))

    def power(self, level=1.0, key=None):
        """Carrier strength 0..1 for carrier and FM (the fundamental of the pin's square wave);
        key: for the carrier mode, True = carrier on."""
        import math
        width = round(1024 * math.asin(max(0.0, min(1.0, level))) / math.pi)
        k = (self.r(14) >> 16) & 1 if key is None else int(bool(key))
        self.w(14, width | k << 16)

    def key(self, on):
        v = self.r(14)
        self.w(14, (v & 0x3FF) | (int(bool(on)) << 16))

    # ---- audio
    def input_rate(self, hz):
        """The sample rate of the audio you push (resampled in the FPGA to 48828 Hz)."""
        self.w(8, round(hz / self.FS_AUDIO * 65536))

    AUDIO_FIFO = 8192                 # stereo samples the FPGA's sound buffer holds

    def audio_free(self):
        return self.AUDIO_FIFO - self.r(10)

    def push(self, words):
        """Put stereo samples (right << 16 | left, as unsigned 32-bit words) into the FIFO (8192 places).
        Only push as many as audio_free() says."""
        mv, a = self._mv, self._a_audio
        for v in words:
            mv[a] = v

    def audio_flush(self):
        """Drop the audio still waiting in the FIFO (for an instant stop or a new song)."""
        self.w(10, 0)

    def underruns(self):
        return self.r(26)

    # ---- RDS
    def rds_load(self, blocks, bank):
        """Write a list of 26-bit RDS blocks (a multiple of 4: whole groups) into a bank and ask for it.
        Write only the bank that is not on air (see rds_bank())."""
        n = len(blocks)
        assert 4 <= n <= 256 and n % 4 == 0
        for i, b in enumerate(blocks):
            self.bus.wr(self.slot + 1, bank * 256 + i, b)
        self.w(15, n | (bank & 1) << 16)

    def rds_bank(self):
        """(bank on air, bank asked for): they differ until the current list has been sent to its end."""
        v = self.r(15)
        return (v >> 17) & 1, (v >> 16) & 1

    def rds_log(self):
        """The RDS data bits sent since the last call (up to 2048), first sent first."""
        bits = []
        for _ in range(self.r(21)):
            v = self.r(20)
            bits += [(v >> (31 - i)) & 1 for i in range(32)]
        return bits

    def rds_log_clear(self):
        self.w(21, 1)

    # ---- symbols (CW, FSK, PSK, beacons)
    def symbols_free(self):
        return 512 - self.r(18)

    def symbol(self, offset_hz=0.0, us=1000, width=512, phase=0):
        """Queue one symbol: carrier offset in Hz (up to +-970 kHz), time in microseconds (up to 1 s),
        width 0 (silent) .. 512 (full), phase in 1/256 of a turn. Mode 'symbols' sends them."""
        off = round(offset_hz / self.CLK * 2 ** 32)
        self.w(16, (off & 0xFFFFFF) | (int(phase) & 0xFF) << 24)
        self.w(17, (int(width) & 0x3FF) | (max(1, min(0xFFFFF, int(us))) << 10))

    def send(self, symbols, stop=None):
        """Queue (offset_hz, us, width, phase) tuples, waiting while the queue is full.
        stop: an optional function; when it returns True the sending ends early."""
        free = 0
        for s in symbols:
            while free <= 0:
                if stop and stop():
                    return False
                free = self.symbols_free()
                if free <= 0:
                    time.sleep(0.01)
            self.symbol(*s)
            free -= 1
        return True

    def symbols_flush(self):
        """Drop the queued symbols and stop the one on air."""
        self.w(18, 0)

    def symbol_gaps(self):
        return self.r(27)

    # ---- measurements
    def capture(self):
        """4096 MPX samples (390625 per second), -32767..32767."""
        self.w(19, 1)
        t = time.time()
        while self.r(19) & 1 and time.time() - t < 1:
            time.sleep(0.002)
        out = []
        for i in range(4096):
            v = self.bus.rd(self.slot + 2 + (i >> 10), i & 1023)
            out.append(v - (1 << 32) if v & 0x80000000 else v)
        return out

    def capture_iq(self):
        """2048 complex samples I + jQ (390625 per second) of the SSB / DSB signal, -1 .. 1."""
        self.w(19, 3)
        t = time.time()
        while self.r(19) & 1 and time.time() - t < 1:
            time.sleep(0.002)
        v = []
        for i in range(4096):
            x = self.bus.rd(self.slot + 2 + (i >> 10), i & 1023)
            v.append((x - (1 << 32) if x & 0x80000000 else x) / 32767)
        return [complex(v[2 * i], v[2 * i + 1]) for i in range(2048)]

    def peaks(self):
        """Largest audio (left, right) and MPX sizes since the last call, 0..1."""
        return {'left': self.r(22) / 32767, 'right': self.r(23) / 32767, 'mpx': self.r(24) / 32767}

    def rf_hz(self):
        """Carrier rising edges counted at the pin per second (updated every 0.1 s)."""
        return self.r(25)

    def rf_duty(self):
        """The part of the time the pin was high in the last 0.1 s (0.5 = half: the strongest carrier)."""
        return self.r(30) / 25e6


def tone_level(samples, hz, fs, complex_value=False):
    """The amplitude of one frequency in a block of samples (Goertzel with a Hann window)."""
    import cmath, math
    n = len(samples)
    w = 2 * math.pi * hz / fs
    acc = 0j
    for i, x in enumerate(samples):
        acc += x * (0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1))) * cmath.exp(-1j * w * i)
    acc = acc * 2 / (n * 0.5)
    return acc if complex_value else abs(acc)


# ---------------------------------------------------------------------------------------- SHA-256 miner
class ShaMiner(Block):
    """Project 13: SHA-256 in the FPGA. compress() / sha256() hash anything; mine() searches a nonce."""

    def __init__(self, bus, slot=1):
        super().__init__(bus, slot)

    def compress(self, state, block_words):
        """One compression in the FPGA (65 clocks): 8 + 16 words -> 8 words."""
        for i, v in enumerate(state):
            self.w(24 + i, v)
        for i, v in enumerate(block_words):
            self.w(32 + i, v)
        self.w(0, 1)
        while self.r(1) & 1:
            pass
        return [self.r(48 + i) for i in range(8)]

    def sha256(self, data):
        """The whole SHA-256 of bytes, with every block compressed by the FPGA (= hashlib.sha256(data).digest())."""
        import struct
        from sha256_model import IV
        msg = data + b'\x80' + b'\x00' * ((55 - len(data)) % 64) + struct.pack('>Q', 8 * len(data))
        h = IV
        for i in range(0, len(msg), 64):
            h = self.compress(h, struct.unpack('>16I', msg[i:i + 64]))
        return struct.pack('>8I', *h)

    def mine(self, header, start=0, count=0, zero_bits=24, wait=True, timeout=None):
        """Search nonces start .. start + count - 1 (count 0: all 2^32) for a double SHA-256 of the 80-byte
        header with zero_bits leading zero bits. Returns a dict (found, nonce, hash, hashes, seconds, rate)."""
        from sha256_model import header_job
        mid, tail = header_job(header)
        for i, v in enumerate(mid):
            self.w(8 + i, v)
        for i, v in enumerate(tail):
            self.w(16 + i, v)
        self.w(2, start)
        self.w(3, count)
        self.w(4, zero_bits)
        self.w(0, 2)
        t0 = time.time()
        while wait and self.r(1) & 2:
            if timeout and time.time() - t0 > timeout:
                self.stop()
                break
            time.sleep(0.01)
        return self.result()

    def stop(self):
        self.w(0, 4)

    def result(self):
        import struct
        st, cycles = self.r(1), self.r(7)
        h = struct.pack('>8I', *[self.r(56 + i) for i in range(8)])
        return {'mining': bool(st & 2), 'found': bool(st & 4), 'nonce': self.r(5), 'hash': h[::-1].hex() if st & 4 else None,
                'hashes': self.r(6), 'seconds': cycles / 100e6, 'rate': self.r(6) / (cycles / 100e6) if cycles else 0.0}


# ---------------------------------------------------------------------------------------- FIR filter lab
def fir_design(kind='lowpass', f1=0.1, f2=0.2, taps=63, window='hamming'):
    """Windowed-sinc FIR design (pure Python). Frequencies are fractions of the sample rate (0 .. 0.5).
    kind: lowpass (f1 = cut-off), highpass (f1), bandpass (f1 .. f2), bandstop (f1 .. f2). Returns floats."""
    import math
    m = taps - 1

    def sinc_lp(fc, n):
        x = n - m / 2
        return 2 * fc if x == 0 else math.sin(2 * math.pi * fc * x) / (math.pi * x)

    def win(n):
        if window == 'hamming':
            return 0.54 - 0.46 * math.cos(2 * math.pi * n / m) if m else 1.0
        if window == 'blackman':
            return 0.42 - 0.5 * math.cos(2 * math.pi * n / m) + 0.08 * math.cos(4 * math.pi * n / m) if m else 1.0
        return 1.0
    h = []
    for n in range(taps):
        if kind == 'lowpass':
            v = sinc_lp(f1, n)
        elif kind == 'highpass':
            v = (1.0 if n == m / 2 else 0.0) - sinc_lp(f1, n)
        elif kind == 'bandpass':
            v = sinc_lp(f2, n) - sinc_lp(f1, n)
        else:
            v = (1.0 if n == m / 2 else 0.0) - (sinc_lp(f2, n) - sinc_lp(f1, n))
        h.append(v * win(n))
    return h


def fir_gain(h, f):
    """|H(f)| of float or integer coefficients at f (fraction of the sample rate)."""
    import cmath, math
    return abs(sum(c * cmath.exp(-2j * math.pi * f * k) for k, c in enumerate(h)))


class FirLab(Block):
    """Project 14: the FIR filter, its generator and meters."""
    SHIFT = 17

    def __init__(self, bus, slot=1):
        super().__init__(bus, slot)
        self.coef = []

    def reset(self):
        self.w(0, 1)
        time.sleep(0.001)

    def set_filter(self, h, shift=SHIFT):
        """Float coefficients -> 18-bit integers scaled by 2^shift (as large as fits)."""
        q = [max(-131072, min(131071, int(round(c * (1 << shift))))) for c in h]
        self.set_coef(q, shift)
        return q

    def set_coef(self, q, shift):
        if not 1 <= len(q) <= 64:
            raise ValueError('1 .. 64 taps')
        self.coef = list(q)
        self.w(2, len(q))
        self.w(3, shift)
        for k, c in enumerate(q):
            self.w(64 + k, c & 0x3FFFF)
        self.shift = shift

    def status(self):
        s = self.r(1)
        return {'in_level': s & 0xFF, 'out_level': (s >> 8) & 0x3FF, 'busy': bool(s >> 24 & 1),
                'samples': self.r(13), 'clipped': self.r(14), 'lost': self.r(16)}

    def filter(self, samples):
        """Samples (ints -32768 .. 32767) through the FPGA's filter; returns the results (the ARM path)."""
        self.w(0, 0)
        out = []
        for i in range(0, len(samples), 32):
            for x in samples[i:i + 32]:
                self.w(4, int(x) & 0xFFFF)
            t = time.time()
            while (self.r(1) & 0xFF or self.r(1) >> 24 & 1) and time.time() - t < 1:
                pass
            out += self.take()
        return out

    def take(self, n=None):
        out = []
        while n is None or len(out) < n:
            level = (self.r(1) >> 8) & 0x3FF
            if not level:
                break
            for _ in range(level if n is None else min(level, n - len(out))):
                v = self.r(5) >> 16
                out.append(v - 65536 if v & 0x8000 else v)
        return out

    def generator(self, freq_hz, rate=100, amp=16384, noise=0):
        """The built-in source: a sine of freq_hz plus noise at 100 MHz / rate samples per second."""
        fs = 100e6 / rate
        self.w(7, int(round(freq_hz / fs * 2 ** 32)) & 0xFFFFFFFF)
        self.w(8, rate)
        self.w(9, amp)
        self.w(10, noise)
        self.w(0, 2)
        return fs

    def peaks(self, seconds=0.01):
        """Largest |input| and |output| during the next `seconds`."""
        self.r(11), self.r(12)
        time.sleep(seconds)
        return self.r(11), self.r(12)

    def response(self, freqs_hz, rate=100, amp=16384, seconds=0.02):
        """Measured gain (output peak / input peak) at each frequency, with the generator."""
        out = []
        for f in freqs_hz:
            self.generator(f, rate, amp, 0)
            time.sleep(0.002)
            pin, pout = self.peaks(max(seconds, 3.0 / max(f, 1)))
            out.append(pout / pin if pin else 0.0)
        return out

    def capture(self, n=256):
        """The generator's next n (input, output) pairs."""
        while (self.r(1) >> 8) & 0x3FF:
            self.r(5)
        self.w(15, n)
        t = time.time()
        while self.r(15) and time.time() - t < 2:
            pass
        pairs = []
        while (self.r(1) >> 8) & 0x3FF:
            v = self.r(5)
            y, x = v >> 16, v & 0xFFFF
            pairs.append((x - 65536 if x & 0x8000 else x, y - 65536 if y & 0x8000 else y))
        return pairs


# ---------------------------------------------------------------------------------------- Game of Life
LIFE_PATTERNS = {
    # name: rows of text, '#' = alive. Classic shapes of Conway's Game of Life.
    'glider': ['.#.', '..#', '###'],
    'blinker': ['###'],
    'toad': ['.###', '###.'],
    'beacon': ['##..', '##..', '..##', '..##'],
    'block': ['##', '##'],
    'beehive': ['.##.', '#..#', '.##.'],
    'lwss': ['.#..#', '#....', '#...#', '####.'],          # lightweight spaceship
    'r_pentomino': ['.##', '##.', '.#.'],                   # 5 cells, 1103 generations of chaos
    'acorn': ['.#.....', '...#...', '##..###'],             # 7 cells, 5206 generations
    'pulsar': ['..###...###..', '.............', '#....#.#....#', '#....#.#....#', '#....#.#....#',
               '..###...###..', '.............', '..###...###..', '#....#.#....#', '#....#.#....#',
               '#....#.#....#', '.............', '..###...###..'],
    'gosper_gun': ['........................#...........', '......................#.#...........',
                   '............##......##............##', '...........#...#....##............##',
                   '##........#.....#...##..............', '##........#...#.##....#.#...........',
                   '..........#.....#.......#...........', '...........#...#....................',
                   '............##......................'],
}


def life_step(grid):
    """One generation in Python (64 ints, bit c of row r = cell), for comparing with the FPGA."""
    new = []
    for r in range(64):
        a, h, b = grid[(r - 1) % 64], grid[r], grid[(r + 1) % 64]
        row = 0
        for c in range(64):
            n = 0
            for v in (a, h, b):
                n += (v >> ((c - 1) % 64)) & 1
                n += (v >> ((c + 1) % 64)) & 1
            n += (a >> c) & 1
            n += (b >> c) & 1
            if n == 3 or (n == 2 and (h >> c) & 1):
                row |= 1 << c
        new.append(row)
    return new


class Life(Block):
    """Project 15: the 64 x 64 Game of Life engine."""

    def __init__(self, bus, slot=1):
        super().__init__(bus, slot)

    def _idle(self):
        t = time.time()
        while self.r(1) & 1 and time.time() - t < 1:
            pass

    def clear(self):
        self.w(0, 1)
        self._idle()

    def randomize(self, sparse=False):
        self.w(0, 4 | (8 if sparse else 0))
        self._idle()

    def stop(self):
        self.w(0, 0)
        self.w(2, 0)
        self._idle()

    def run(self, per_second=None):
        """Generations without end: as fast as it goes, or about per_second of them."""
        self.w(5, 0 if not per_second else max(0, int(100e6 / per_second) - 70))
        self.w(0, 2)

    def steps(self, n, wait=True):
        self.w(2, n)
        t = time.time()
        while wait and (self.r(2) or self.r(1) & 1) and time.time() - t < 10:
            pass

    def generation(self):
        return self.r(3)

    def population(self):
        return self.r(4)

    def per_second(self):
        return self.r(6)

    def read(self):
        """The grid: 64 ints (bit c of row r = the cell in column c)."""
        return [self.r(64 + 2 * r) | (self.r(65 + 2 * r) << 32) for r in range(64)]

    def write(self, grid):
        for r, v in enumerate(grid):
            self.w(64 + 2 * r, v & 0xFFFFFFFF)
            self.w(65 + 2 * r, (v >> 32) & 0xFFFFFFFF)

    def place(self, name_or_rows, row=0, col=0):
        """Put a pattern (a name from LIFE_PATTERNS or rows of '#' and '.') with its top-left at (row, col)."""
        rows = LIFE_PATTERNS.get(name_or_rows, name_or_rows) if isinstance(name_or_rows, str) else name_or_rows
        g = self.read()
        for dr, line in enumerate(rows):
            for dc, ch in enumerate(line):
                if ch in '#O*1':
                    g[(row + dr) % 64] |= 1 << ((col + dc) % 64)
        self.write(g)

    @staticmethod
    def text(grid, rows=64):
        """The grid as text, two rows per line: full, upper or lower half blocks (fits a terminal)."""
        out = []
        for r in range(0, rows, 2):
            a, b = grid[r], grid[r + 1] if r + 1 < 64 else 0
            out.append(''.join(' ▀▄█'[((a >> c) & 1) | (((b >> c) & 1) << 1)] for c in range(64)))
        return '\n'.join(out)
