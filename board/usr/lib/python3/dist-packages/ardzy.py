"""ardzy - talk to your FPGA design from Python on the Antminer S9.

    from ardzy import MMIO
    leds = MMIO(0x41200000)        # base address from Vivado's Address Editor
    leds.write(0, 0b1010)          # write register at offset 0
    print(leds.read(0))            # read it back

    from ardzy import UIO
    irq = UIO('my_ip')             # device with compatible = "generic-uio" in devices.dtsi
    irq.wait()                     # block until the FPGA raises the interrupt

    from ardzy import led, beep, button
    led('red'); beep(0.1)          # board status LED and buzzer (ARM side)
    if button('ip'): print('IP button pressed')
"""
import mmap, os, struct, glob

PAGE = mmap.PAGESIZE


class MMIO:
    """32-bit register access to an AXI address range (via /dev/mem)."""

    def __init__(self, base, size=0x10000):
        self.base = base
        page_base = base & ~(PAGE - 1)
        self._off = base - page_base
        self._size = size + self._off
        fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
        try:
            self._m = mmap.mmap(fd, self._size, mmap.MAP_SHARED,
                                mmap.PROT_READ | mmap.PROT_WRITE, offset=page_base)
        finally:
            os.close(fd)
        # one 32-bit bus access per read/write (struct.pack_into would first write 4 zero bytes)
        self._w = memoryview(self._m).cast('I')

    def read(self, offset=0):
        return self._w[(self._off + offset) >> 2]

    def write(self, offset, value):
        self._w[(self._off + offset) >> 2] = value & 0xFFFFFFFF

    def __getitem__(self, offset):
        return self.read(offset)

    def __setitem__(self, offset, value):
        self.write(offset, value)

    def close(self):
        self._w.release()
        self._m.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def peek(addr):
    with MMIO(addr & ~3, 4) as m:
        return m.read(0)


def poke(addr, value):
    with MMIO(addr & ~3, 4) as m:
        m.write(0, value)


class UIO:
    """Interrupts + registers of a device declared as compatible = "generic-uio"."""

    def __init__(self, name):
        for d in glob.glob('/sys/class/uio/uio*'):
            if open(d + '/name').read().strip() == name:
                self.dev = '/dev/' + os.path.basename(d)
                self.size = int(open(d + '/maps/map0/size').read(), 16)
                break
        else:
            raise FileNotFoundError('no UIO device named %r (is it in devices.dtsi?)' % name)
        self._fd = os.open(self.dev, os.O_RDWR | os.O_SYNC)
        self._m = mmap.mmap(self._fd, self.size, mmap.MAP_SHARED,
                            mmap.PROT_READ | mmap.PROT_WRITE, offset=0)
        self._w = memoryview(self._m).cast('I')

    def read(self, offset=0):
        return self._w[offset >> 2]

    def write(self, offset, value):
        self._w[offset >> 2] = value & 0xFFFFFFFF

    def wait(self):
        """Enable the interrupt and wait for it. Returns the total interrupt count."""
        os.write(self._fd, struct.pack('<I', 1))
        return struct.unpack('<I', os.read(self._fd, 4))[0]


# ---- board extras on the ARM side (set up at boot by ardzy-board-init) ----------------
#   led('green' | 'red' | 'ps', on)   bicolor status LED (red/green) and the small PS LED
#   beep(seconds)                       buzzer
#   button('ip' | 'reset') -> True while pressed
# Other boards (EBAZ4205: LEDs red / green, buttons s2 / s3 = ip / reset, no buzzer) from /run/ardzy/board-io.txt.
_LEDS = {'green': (38, True), 'red': (37, True), 'ps': (15, False)}   # (MIO/GPIO, active high): the S9
_BUTTONS = {'ip': (51, False), 'reset': (47, False)}                  # (GPIO, high = pressed)
_BUZZER = 39


def _board_io():
    """The GPIOs of the board this runs on, from /run/ardzy/board-io.txt (written at boot by ardzy-board-init).
    Without the file (an older card) the S9's numbers above stay."""
    global _BUZZER
    try:
        lines = open('/run/ardzy/board-io.txt').read().splitlines()
    except OSError:
        return
    leds, buttons, buzzer = {}, {}, None
    for line in lines:
        f = line.split('#')[0].split()
        if len(f) != 3:
            continue
        name, g, on = f[0], int(f[1]), f[2] == '1'
        if name.startswith('led_'):
            leds[name[4:]] = (g, on)
        elif name.startswith('button_'):
            buttons[name[7:]] = (g, on)
        elif name == 'buzzer':
            buzzer = g
    if leds or buttons:
        _LEDS.clear()
        _LEDS.update(leds)
        _BUTTONS.clear()
        _BUTTONS.update(buttons)
        _BUZZER = buzzer


_board_io()


def _gpio_set(n, value):
    with open('/sys/class/gpio/gpio%d/value' % n, 'w') as f:
        f.write('1' if value else '0')


def _gpio_get(n):
    with open('/sys/class/gpio/gpio%d/value' % n) as f:
        return f.read().strip() == '1'


def led(name, on=True):
    """Switch a board LED: led('green'), led('red', False), led('ps')."""
    n, active_high = _LEDS[name]
    _gpio_set(n, bool(on) == active_high)


def beep(seconds=0.1):
    """Sound the buzzer for a moment (a board without a buzzer just waits)."""
    import time
    if _BUZZER is None:
        time.sleep(seconds)
        return
    _gpio_set(_BUZZER, 1)
    try:
        time.sleep(seconds)
    finally:
        _gpio_set(_BUZZER, 0)


def button(name='ip'):
    """True while the button is pressed: button('ip') (S2) or button('reset') (S1); on the EBAZ4205 also 's2', 's3'."""
    n, pressed_high = _BUTTONS[name]
    return _gpio_get(n) == pressed_high


def fpga_state():
    try:
        return open('/sys/class/fpga_manager/fpga0/state').read().strip()
    except OSError:
        return 'unknown'


def watch(**values):
    """Show values live in the app (Watch tab, Plotter) and in the board's data logger:
    watch(speed=12.5, state="running")  prints  speed:12.5 state="running"  on one line."""
    parts = []
    for k, v in values.items():
        if isinstance(v, bool):
            v = int(v)
        if isinstance(v, (int, float)):
            parts.append('%s:%s' % (k, round(v, 6) if isinstance(v, float) else v))
        else:
            parts.append('%s="%s"' % (k, str(v).replace('"', "'")))
    print(' '.join(parts), flush=True)
