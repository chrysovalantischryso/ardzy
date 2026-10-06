"""Ardzy hardware API: everything the board can tell about itself, and the controls the app uses.

Read side : chip, CPU, memory, storage, NAND, network, boot, clocks, sensors, all 54 MIO pins.
Control   : free ARM GPIO pins, FPGA clocks FCLK0-3, CPU speed, Ethernet speed, reboot/power off,
            FPGA pins + fans through the "ardzy_io" design, read-only NAND backup.
Safety    : pins used by NAND / Ethernet / SD / UART can not be changed; FPGA registers are only
            touched while the ardzy_io design is loaded (an empty FPGA address would freeze the bus);
            board-ID straps are never driven; the NAND is mounted read-only by the kernel.
"""
import glob, json, mmap, os, re, struct, subprocess, threading, time

STATE = '/var/lib/ardzy'
HERE = os.path.dirname(os.path.abspath(__file__))
SLCR, GPIO_BASE, IO_GPIO, IO_FAN = 0xF8000000, 0xE000A000, 0x41200000, 0x43C00000
_lock = threading.Lock()


def read(p, default=''):
    try:
        with open(p) as f:
            return f.read().strip()
    except OSError:
        return default


def sh(*cmd, timeout=10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ''


class Mem:
    """Read/write 32-bit words of a physical address window (via /dev/mem)."""

    def __init__(self, base, size=0x1000):
        fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
        self.m = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=base)
        os.close(fd)
        # one 32-bit bus access per call. Never struct.pack_into for registers: it first clears
        # the 4 bytes with byte writes, so the register sees 4 extra zero writes.
        self.w = memoryview(self.m).cast('I')

    def rd(self, off):
        return self.w[off >> 2]

    def wr(self, off, v):
        self.w[off >> 2] = v & 0xFFFFFFFF


_slcr = None


def slcr():
    global _slcr
    if _slcr is None:
        _slcr = Mem(SLCR)
    return _slcr


def f(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)


# ------------------------------------------------------------------ static board description
MIO_FUNC = {}
for n in range(0, 15):
    MIO_FUNC[n] = ('NAND', 'nand')
for n, name in enumerate(['TX_CLK', 'TXD0', 'TXD1', 'TXD2', 'TXD3', 'TX_CTL', 'RX_CLK', 'RXD0', 'RXD1',
                          'RXD2', 'RXD3', 'RX_CTL']):
    MIO_FUNC[16 + n] = ('Ethernet ' + name, 'eth')
for n in range(1, 10):
    MIO_FUNC[27 + n] = ('EN%d (J%d pin 18)' % (n, n), 'en')
MIO_FUNC.update({15: ('LED D2 (green, active low)', 'led'), 37: ('Status LED red', 'led'),
                 38: ('Status LED green', 'led'), 39: ('Buzzer', 'buzzer'),
                 40: ('SD CLK', 'sd'), 41: ('SD CMD', 'sd'), 42: ('SD DAT0', 'sd'), 43: ('SD DAT1', 'sd'),
                 44: ('SD DAT2', 'sd'), 45: ('SD DAT3', 'sd'), 46: ('SD card detect', 'sd'),
                 47: ('Button S1 "Reset"', 'button'), 48: ('UART1 TX', 'uart'), 49: ('UART1 RX', 'uart'),
                 50: ('SD write protect', 'sd'), 51: ('Button S2 "IP"', 'button'),
                 52: ('Ethernet MDC', 'eth'), 53: ('Ethernet MDIO', 'eth')})
MIO_OUT_OK = {15, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39}   # free outputs (28/29 = I2C1, rest in use)
MIO_IN_OK = {30, 31, 32, 33, 34, 35, 36, 47, 51}
IO_TYPE = {1: 'LVCMOS18', 2: 'LVCMOS25', 3: 'LVCMOS33', 4: 'HSTL'}
PS_VERSION = {0: '1.0', 1: '2.0', 2: '3.0', 3: '3.1'}
RESET_BITS = [(22, 'power-on'), (21, 'external reset (SRST)'), (20, 'debug'), (19, 'software (Linux reboot)'),
              (18, 'CPU1 watchdog'), (17, 'CPU0 watchdog'), (16, 'system watchdog')]


# ------------------------------------------------------------------ information
def xadc():
    d = '/sys/bus/iio/devices/iio:device0/'
    out = {}
    for lab in sorted(glob.glob(d + 'in_voltage*_label')):
        base = lab[:-len('label')]
        try:
            out[read(lab)] = round(int(read(base + 'raw')) * float(read(base + 'scale')) / 1000, 3)
        except ValueError:
            pass
    out.pop('vrefp', None), out.pop('vrefn', None)
    try:
        t = (int(read(d + 'in_temp0_raw')) + int(read(d + 'in_temp0_offset'))) * float(read(d + 'in_temp0_scale')) / 1000
        out['temp_c'] = round(t, 1)
    except ValueError:
        pass
    return out


_cpu_last = None


def cpu_usage():
    global _cpu_last
    v = [int(x) for x in read('/proc/stat').splitlines()[0].split()[1:]]
    idle, total = v[3] + v[4], sum(v)
    pct = None
    if _cpu_last:
        dt, di = total - _cpu_last[0], idle - _cpu_last[1]
        pct = round(100 * (1 - di / dt), 1) if dt else 0.0
    _cpu_last = (total, idle)
    return pct


def meminfo():
    m = {l.split(':')[0]: int(l.split()[1]) for l in read('/proc/meminfo').splitlines() if ':' in l}
    return {'total_mb': m['MemTotal'] // 1024, 'available_mb': m['MemAvailable'] // 1024,
            'free_mb': m['MemFree'] // 1024, 'cached_mb': (m.get('Cached', 0) + m.get('Buffers', 0)) // 1024,
            'used_mb': (m['MemTotal'] - m['MemAvailable']) // 1024, 'swap_mb': m.get('SwapTotal', 0) // 1024}


def sensors():
    s = xadc()
    s.update({'cpu_pct': cpu_usage(), 'load': read('/proc/loadavg').split()[:3], 'mem': meminfo(),
              'uptime_s': int(float(read('/proc/uptime', '0').split()[0])), 'time': time.time()})
    return s


def clocks():
    r = slcr().rd
    ps_clk = 33.333333
    pll = {}
    for name, off in (('ARM', 0x100), ('DDR', 0x104), ('IO', 0x108)):
        pll[name] = ps_clk * f(r(off), 18, 12)
    src2 = lambda s: {0: 'IO', 1: 'IO', 2: 'ARM', 3: 'DDR'}[s]
    arm = r(0x120)
    cpu = pll[{0: 'ARM', 1: 'ARM', 2: 'DDR', 3: 'IO'}[f(arm, 5, 4)]] / max(1, f(arm, 13, 8))
    ddr = r(0x124)
    out = {'ps_clk_mhz': round(ps_clk, 3), 'pll_mhz': {k: round(v, 1) for k, v in pll.items()},
           'cpu_mhz': round(cpu, 1), 'ratio_621': bool(r(0x1C4) & 1),
           'ddr_mhz': round(pll['DDR'] / max(1, f(ddr, 25, 20)), 1)}
    per = {}
    for name, off, two in (('GEM0', 0x140, True), ('SDIO', 0x150, False), ('UART', 0x154, False),
                           ('SMC', 0x148, False), ('PCAP', 0x168, False)):
        v = r(off)
        d0, d1 = f(v, 13, 8), (f(v, 25, 20) if two else 1)
        s = f(v, 6, 4) if two else f(v, 5, 4)
        p = pll[src2(s & 3)] if (not two or s < 4) else 0
        per[name] = {'mhz': round(p / d0 / d1, 2) if d0 and d1 else 0, 'on': bool(v & 1)}
    out['peripherals'] = per
    out['fclk'] = []
    for i, off in enumerate((0x170, 0x180, 0x190, 0x1A0)):
        v = r(off)
        d0, d1 = f(v, 13, 8), f(v, 25, 20)
        out['fclk'].append({'n': i, 'mhz': round(pll[src2(f(v, 5, 4))] / d0 / d1, 3) if d0 and d1 else 0,
                            'src': src2(f(v, 5, 4)), 'div0': d0, 'div1': d1})
    return out


def set_fclk(n, mhz):
    """Set FCLKn (0..3) as close as possible to mhz, from the IO PLL (1000 MHz). Returns the real value."""
    n, mhz = int(n), float(mhz)
    if n not in range(4) or not 0.5 <= mhz <= 250:
        raise ValueError('FCLK 0..3, 0.5 to 250 MHz')
    io = clocks()['pll_mhz']['IO']
    best = min(((abs(io / (a * b) - mhz), a, b) for a in range(1, 64) for b in range(1, 64)), key=lambda t: t[0])
    _, d0, d1 = best
    with _lock:
        s = slcr()
        s.wr(0x008, 0xDF0D)                                    # unlock (Linux keeps it unlocked anyway)
        s.wr(0x170 + 0x10 * n, (d1 << 20) | (d0 << 8))         # source IO PLL
    return round(io / d0 / d1, 3)


def boot_info():
    r = slcr().rd
    bm, rs = r(0x25C), r(0x258)
    reasons = [name for bit, name in RESET_BITS if rs >> bit & 1]
    devcfg = Mem(0xF8007000)
    return {'boot_mode': {0: 'JTAG', 1: 'NOR', 2: 'NAND', 4: 'QSPI', 5: 'SD card'}.get(bm & 7, '?'),
            'boot_mode_raw': '0x%x' % bm, 'last_reset': reasons or ['unknown'], 'reboot_status': '0x%08x' % rs,
            'ps_version': PS_VERSION.get(f(devcfg.rd(0x80), 31, 28), '?'), 'idcode': '0x%08x' % r(0x530)}


def storage():
    out = {}
    for mnt in ('/', '/boot'):
        st = os.statvfs(mnt)
        out[mnt] = {'size_mb': st.f_blocks * st.f_frsize // 2**20, 'free_mb': st.f_bavail * st.f_frsize // 2**20}
    dev = '/sys/block/mmcblk0/'
    out['card'] = {'size_mb': int(read(dev + 'size', '0')) * 512 // 2**20, 'name': read(dev + 'device/name'),
                   'manfid': read(dev + 'device/manfid'), 'date': read(dev + 'device/date'),
                   'type': read(dev + 'device/type'), 'speed': (re.findall(r'timing spec:\s*(.*)', read(
                       '/sys/kernel/debug/mmc0/ios')) or [''])[0]}
    return out


def net():
    d = '/sys/class/net/end0/'
    out = {'ifname': 'end0', 'mac': read(d + 'address'), 'speed': read(d + 'speed'), 'duplex': read(d + 'duplex'),
           'carrier': read(d + 'carrier') == '1', 'rx_bytes': int(read(d + 'statistics/rx_bytes', '0')),
           'tx_bytes': int(read(d + 'statistics/tx_bytes', '0')),
           'ipv4': sh('hostname', '-I').split(), 'hostname': os.uname().nodename}
    e = sh('ethtool', 'end0')
    if e:
        grab = lambda k: ' '.join(re.findall(r'%s:\s*(.*(?:\n\s{20,}.*)*)' % re.escape(k), e)[:1]).split()
        out['supported'] = [m for m in grab('Supported link modes') if 'base' in m]
        out['advertised'] = [m for m in grab('Advertised link modes') if 'base' in m]
        out['partner'] = [m for m in grab('Link partner advertised link modes') if 'base' in m]
        out['autoneg'] = (re.findall(r'Auto-negotiation:\s*(\w+)', e) or [''])[0]
    return out


def set_net_speed(mode):
    if not sh('which', 'ethtool').strip():
        raise ValueError('ethtool is not installed on this image')
    adv = {'auto': '0x03f', '100': '0x00f', '1000': '0x030'}.get(mode)   # 10/100 half+full, 1000 half+full
    if not adv:
        raise ValueError('mode: auto, 100 or 1000')
    sh('ethtool', '-s', 'end0', 'autoneg', 'on', 'advertise', adv)
    return 'link renegotiating (%s); the connection drops for a few seconds' % mode


def cpufreq():
    d = '/sys/devices/system/cpu/cpu0/cpufreq/'
    if not os.path.isdir(d):
        return {'available': False}
    return {'available': True, 'cur_khz': int(read(d + 'scaling_cur_freq', '0')),
            'freqs_khz': [int(x) for x in read(d + 'scaling_available_frequencies').split()],
            'governor': read(d + 'scaling_governor'), 'governors': read(d + 'scaling_available_governors').split()}


def set_cpufreq(governor=None, khz=None):
    d = '/sys/devices/system/cpu/cpu0/cpufreq/'
    if not os.path.isdir(d):
        raise ValueError('CPU speed control is not available: the kernel driver crashed in testing, so it is off')
    if governor:
        if governor not in read(d + 'scaling_available_governors').split():
            raise ValueError('unknown governor')
        open(d + 'scaling_governor', 'w').write(governor)
    if khz:
        if read(d + 'scaling_governor') != 'userspace':
            open(d + 'scaling_governor', 'w').write('userspace')
        open(d + 'scaling_setspeed', 'w').write(str(int(khz)))
    return cpufreq()


def hw():
    rel = dict(l.split('=', 1) for l in read('/etc/ardzy-release').splitlines() if '=' in l)
    cpuinfo = read('/proc/cpuinfo')
    return {
        'board': 'Antminer S9 control board (XC7010 V1.01)', 'chip': 'XC7Z010-1CLG400', 'image': rel,
        'kernel': os.uname().release, 'os': next((l.split('=', 1)[1].strip().strip('"') for l in
                                                  read('/etc/os-release').splitlines() if l.startswith('PRETTY_NAME=')), ''),
        'cpu': {'cores': cpuinfo.count('processor\t:'), 'model': 'ARM Cortex-A9 (ARMv7, NEON, VFPv3)',
                'bogomips': (re.findall(r'BogoMIPS\s*:\s*([\d.]+)', cpuinfo) or ['?'])[0], 'freq': cpufreq()},
        'memory': dict(meminfo(), physical_mb=512, type='DDR3, 32 bit (2 x 16-bit chips)'),
        'boot': boot_info(), 'clocks': clocks(), 'storage': storage(), 'net': net(), 'nand': nand_info(),
        'watchdog': {'device': '/dev/watchdog0',
                     'timeout_s': read('/sys/class/watchdog/watchdog0/timeout') or
                     sh('systemctl', 'show', '-p', 'RuntimeWatchdogUSec', '--value').strip(),
                     'state': read('/sys/class/watchdog/watchdog0/state') or 'active (systemd)',
                     'identity': read('/sys/class/watchdog/watchdog0/identity')},
        'fpga': {'state': read('/sys/class/fpga_manager/fpga0/state'), 'project': read(STATE + '/current'),
                 'io_design': io_ready()},
        'sensors': sensors(),
    }


# ------------------------------------------------------------------ MIO pins
def mio():
    s = slcr()
    clk_on = bool(s.rd(0x12C) >> 22 & 1)
    g = Mem(GPIO_BASE) if clk_on else None
    pins = []
    for n in range(54):
        v = s.rd(0x700 + 4 * n)
        sel = (v >> 1) & 0x7F
        bank = 0 if n < 32 else 1
        bit = n if n < 32 else n - 32
        p = {'pin': n, 'func': MIO_FUNC.get(n, ('', ''))[0], 'group': MIO_FUNC.get(n, ('', ''))[1],
             'mux': 'GPIO' if sel == 0 else 'peripheral', 'io': IO_TYPE.get(f(v, 11, 9), '?'),
             'pullup': bool(v >> 12 & 1), 'tristate': bool(v & 1), 'raw': '0x%04x' % v,
             'bank': '500 (3.3 V)' if n < 16 else '501 (2.5 V)',
             'can_out': n in MIO_OUT_OK, 'can_in': n in MIO_IN_OK}
        if g and sel == 0:
            dirm = g.rd(0x204 + 0x40 * bank) >> bit & 1
            p['dir'] = 'out' if dirm else 'in'
            p['level'] = g.rd(0x60 + 4 * bank) >> bit & 1
        pins.append(p)
    return {'gpio_clock_on': clk_on, 'pins': pins}


def mio_set(pin, mode):
    """mode: 'in', '0' or '1'. Only free pins (EN3-EN9, status LEDs, D2, buzzer, buttons as inputs)."""
    pin = int(pin)
    if mode in ('0', '1') and pin not in MIO_OUT_OK:
        raise ValueError('MIO%d can not be an output (in use or not free)' % pin)
    if mode == 'in' and pin not in MIO_IN_OK and pin not in MIO_OUT_OK:
        raise ValueError('MIO%d is not a free pin' % pin)
    if mode not in ('in', '0', '1'):
        raise ValueError('mode: in, 0, 1')
    bank25 = pin >= 16
    with _lock:
        s = slcr()
        s.wr(0x008, 0xDF0D)
        s.wr(0x700 + 4 * pin, ((2 if bank25 else 3) << 9) | (1 << 12 if mode == 'in' else 0) | (1 if mode == 'in' else 0))
        base = '/sys/class/gpio/gpio%d' % pin
        if not os.path.isdir(base):
            open('/sys/class/gpio/export', 'w').write(str(pin))
            for _ in range(50):
                if os.path.exists(base + '/direction'):
                    break
                time.sleep(0.02)
        open(base + '/direction', 'w').write({'in': 'in', '0': 'low', '1': 'high'}[mode])
    return 'MIO%d = %s' % (pin, {'in': 'input', '0': 'output 0', '1': 'output 1'}[mode])


# ------------------------------------------------------------------ NAND (read-only)
def nand_info():
    d = None
    for m in glob.glob('/sys/class/mtd/mtd*'):
        if re.match(r'.*/mtd\d+$', m) and read(m + '/type') == 'nand':
            d = m
            break
    chip = {'part': 'Micron MT29F2G08AACWP', 'size_mb': 256, 'bus': '8 bit', 'type': 'SLC',
            'page': 2048, 'oob': 64, 'block_kb': 128}
    if not d:
        return {'enabled': False, 'chip': chip,
                'note': 'NAND driver not enabled in this image (needs the newer kernel/device tree)'}
    dm = sh('dmesg')
    ident = re.findall(r'nand: (device found.*|.*Micron.*|.*Manufacturer ID.*)', dm)
    info = {'enabled': True, 'chip': chip, 'mtd': os.path.basename(d), 'name': read(d + '/name'),
            'size_mb': int(read(d + '/size', '0')) // 2**20, 'erase_kb': int(read(d + '/erasesize', '0')) // 1024,
            'page': int(read(d + '/writesize', '0')), 'oob': int(read(d + '/oobsize', '0')),
            'bad_blocks': int(read(d + '/bad_blocks', '0')), 'ecc_failures': int(read(d + '/ecc_failures', '0')),
            'corrected_bits': int(read(d + '/corrected_bits', '0')),
            'read_only': not int(read(d + '/flags', '0x0'), 16) & 0x400,      # MTD_WRITEABLE = 0x400
            'flags': read(d + '/flags'), 'kernel': ident[:3]}
    return info


SIGNATURES = [(b'XNLX', 0x24, 'Zynq boot image (BOOT.bin)'), (b'\x27\x05\x19\x56', 0, 'U-Boot uImage'),
              (b'UBI#', 0, 'UBI volume (file system)'), (b'\xd0\x0d\xfe\xed', 0, 'device tree (dtb)'),
              (b'hsqs', 0, 'squashfs'), (b'\x1f\x8b\x08', 0, 'gzip data'), (b'\x85\x19', 0, 'JFFS2')]


def nand_scan():
    """First bytes of every 128 KB block: finds boot images, kernels, file systems. Read-only."""
    info = nand_info()
    if not info.get('enabled'):
        return info
    dev = '/dev/%sro' % info['mtd'] if os.path.exists('/dev/%sro' % info['mtd']) else '/dev/' + info['mtd']
    found, empty, bad = [], 0, 0
    blk = info['erase_kb'] * 1024
    with open(dev, 'rb', buffering=0) as fd:
        for off in range(0, info['size_mb'] * 2**20, blk):
            try:
                os.lseek(fd.fileno(), off, 0)
                head = os.read(fd.fileno(), 64)
            except OSError:
                bad += 1
                continue
            if head == b'\xff' * len(head):
                empty += 1
                continue
            for sig, pos, what in SIGNATURES:
                if head[pos:pos + len(sig)] == sig:
                    found.append({'offset': '0x%08x' % off, 'what': what})
                    break
    info.update({'found': found, 'empty_blocks': empty, 'unreadable_blocks': bad,
                 'used_mb': round((info['size_mb'] * 2**20 / blk - empty) * blk / 2**20, 1)})
    return info


def nand_backup_cmd(raw):
    info = nand_info()
    if not info.get('enabled'):
        raise ValueError(info['note'])
    dev = '/dev/' + info['mtd']
    if raw:
        if not sh('which', 'nanddump').strip():
            raise ValueError('nanddump (mtd-utils) is not installed on this image')
        pages = info['size_mb'] * 2**20 // info['page']
        return ['nanddump', '--noecc', '--oob', '--bb=dumpbad', '-q', dev], pages * (info['page'] + info['oob'])
    # data only (ECC corrected); unreadable blocks are filled with zeros instead of stopping the copy
    return ['dd', 'if=' + (dev + 'ro' if os.path.exists(dev + 'ro') else dev), 'bs=128k', 'conv=noerror,sync',
            'status=none'], info['size_mb'] * 2**20


# ------------------------------------------------------------------ FPGA pins + fans (ardzy_io design)
def io_map():
    return json.load(open(os.path.join(HERE, 'io_map.json')))


def io_ready():
    """The pin-control design is in the FPGA (loaded by the ardzy_io project or for a sketch)."""
    design = read(STATE + '/fpga_design') or (read(STATE + '/current') == 'ardzy_io' and 'ardzy_io')
    return design == 'ardzy_io' and read('/sys/class/fpga_manager/fpga0/state') == 'operating'


def _need_io():
    if not io_ready():
        raise ValueError('load the pin-control design first (project ardzy_io)')
    return Mem(IO_GPIO, 0x10000), Mem(IO_FAN)


def io_read():
    gp, fan = _need_io()
    regs = {'gpio1': (gp.rd(0x0), gp.rd(0x4)), 'gpio2': (gp.rd(0x8), gp.rd(0xC))}
    pins = []
    for p in io_map():
        data, tri = regs[p['port']]
        pins.append(dict(p, level=data >> p['bit'] & 1, mode='in' if tri >> p['bit'] & 1 else 'out'))
    gate = fan.rd(0x28) or 1
    period, high = fan.rd(0x08), fan.rd(0x0C)
    tach = [fan.rd(0x10 + 4 * i) for i in range(6)]
    secs = gate / (clocks()['fclk'][0]['mhz'] * 1e6 or 100e6)
    return {'pins': pins, 'fan': {'on': bool(fan.rd(0x04) & 1), 'duty_pct': round(100 * high / max(period, 1), 1),
                                  'pwm_hz': round(clocks()['fclk'][0]['mhz'] * 1e6 / max(period, 1)),
                                  'tach_pulses': tach, 'rpm': [round(t / secs * 60 / 2) for t in tach]},
            'id': '0x%08x' % fan.rd(0x00), 'cycles': fan.rd(0x30)}


def io_set(name, mode):
    if name.startswith('board_id') and mode != 'in':
        raise ValueError('board ID pins are fixed straps: input only')
    if mode not in ('in', '0', '1'):
        raise ValueError('mode: in, 0, 1')
    gp, _ = _need_io()
    p = next((x for x in io_map() if x['name'] == name), None)
    if not p:
        raise ValueError('unknown pin ' + name)
    doff, toff = (0x0, 0x4) if p['port'] == 'gpio1' else (0x8, 0xC)
    m = 1 << p['bit']
    with _lock:
        if mode == 'in':
            gp.wr(toff, gp.rd(toff) | m)
        else:
            gp.wr(doff, (gp.rd(doff) & ~m) | (m if mode == '1' else 0))
            gp.wr(toff, gp.rd(toff) & ~m)
    return '%s = %s' % (name, mode)


def io_fan(on=None, duty=None, hz=None):
    _, fan = _need_io()
    with _lock:
        if hz:
            fan.wr(0x08, max(2, int(clocks()['fclk'][0]['mhz'] * 1e6 / float(hz))))
        if duty is not None:
            fan.wr(0x0C, int(fan.rd(0x08) * max(0.0, min(100.0, float(duty))) / 100))
        if on is not None:
            fan.wr(0x04, (fan.rd(0x04) & ~1) | (1 if on else 0))
    return io_read()['fan']


def measure_fclk0(seconds=0.5):
    """Real FCLK0 frequency, counted by the ardzy_io design against Linux time."""
    _, fan = _need_io()
    c0, t0 = fan.rd(0x30), time.monotonic()
    time.sleep(seconds)
    c1, t1 = fan.rd(0x30), time.monotonic()
    return round(((c1 - c0) & 0xFFFFFFFF) / (t1 - t0) / 1e6, 3)


def system(action):
    if action == 'reboot':
        subprocess.Popen(['systemd-run', '--on-active=2', 'systemctl', 'reboot'])
        return 'rebooting in 2 s'
    if action == 'poweroff':
        subprocess.Popen(['systemd-run', '--on-active=2', 'systemctl', 'poweroff'])
        return 'switching off in 2 s (to start again: power off and on)'
    if action == 'restart-web':
        subprocess.Popen(['systemd-run', '--on-active=1', 'systemctl', 'restart', 'ardzy-web'])
        return 'board service restarts in 1 s'
    raise ValueError('action: reboot, poweroff, restart-web')
