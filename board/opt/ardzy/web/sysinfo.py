"""Ardzy system information for the app's System view: processes, services, logs, kernel,
network details, device tree, U-Boot environment, a read-only register explorer for the
Zynq's own blocks, speed tests and the board clock.

Register explorer safety: only registers that can be read without side effects are listed
(no FIFOs, no clear-on-read counters, no interrupt acknowledge), and a block whose clock is
switched off is not read at all (that would stop the bus).
"""
import glob, json, os, re, subprocess, time
import hwapi
from hwapi import Mem, read, sh, f

SERVICES_OK = {   # service: actions allowed from the app
    'ardzy-app.service': ('start', 'stop', 'restart'),
    'ardzy-web.service': ('restart',),
    'ardzy-autoload.service': ('restart',),
    'ssh.service': ('restart',),
    'avahi-daemon.service': ('restart',),
    'systemd-timesyncd.service': ('start', 'stop', 'restart'),
}


# ------------------------------------------------------------------ processes and services
def procs():
    out = sh('ps', '-eo', 'pid,user,pcpu,pmem,rss,etimes,stat,comm,args', '--sort=-pcpu', '--no-headers')
    rows = []
    for line in out.splitlines()[:80]:
        p = line.split(None, 8)
        if len(p) < 8:
            continue
        rows.append({'pid': int(p[0]), 'user': p[1], 'cpu': float(p[2]), 'mem': float(p[3]),
                     'rss_kb': int(p[4]), 'age_s': int(p[5]), 'stat': p[6], 'name': p[7],
                     'cmd': (p[8] if len(p) > 8 else p[7])[:160]})
    return {'count': len(out.splitlines()), 'procs': rows}


def services():
    out = sh('systemctl', 'list-units', '--type=service', '--all', '--no-legend', '--plain', '--no-pager')
    rows = []
    for line in out.splitlines():
        p = line.split(None, 4)
        if len(p) < 4:
            continue
        rows.append({'unit': p[0], 'load': p[1], 'active': p[2], 'sub': p[3], 'desc': p[4] if len(p) > 4 else '',
                     'actions': list(SERVICES_OK.get(p[0], ()))})
    rows.sort(key=lambda r: (not r['unit'].startswith('ardzy'), r['active'] != 'active', r['unit']))
    failed = [r['unit'] for r in rows if r['active'] == 'failed']
    return {'services': rows, 'failed': failed}


def service_action(name, action):
    if name not in SERVICES_OK or action not in SERVICES_OK[name]:
        raise ValueError('%s %s is not offered from the app' % (action, name))
    if name == 'ardzy-web.service':
        subprocess.Popen(['systemd-run', '--on-active=1', 'systemctl', 'restart', name])
        return 'board service restarts in 1 s'
    r = subprocess.run(['systemctl', action, name], capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise ValueError((r.stderr or r.stdout).strip() or 'failed')
    return '%s %s: done' % (name, action)


def journal(unit=None, n=200, prio=None, grep=None):
    cmd = ['journalctl', '--no-pager', '-o', 'short-iso', '-n', str(max(10, min(2000, int(n or 200))))]
    if unit:
        if not re.match(r'^[A-Za-z0-9@_.-]+$', unit):
            raise ValueError('bad unit name')
        cmd += ['-u', unit]
    if prio not in (None, ''):
        if str(prio) not in '01234567' or len(str(prio)) != 1:
            raise ValueError('priority 0..7')
        cmd += ['-p', str(prio)]
    if grep:
        cmd += ['-g', grep[:80]]
    return {'text': sh(*cmd, timeout=20)}


def dmesg():
    return {'text': sh('dmesg', '--level=emerg,alert,crit,err,warn,notice,info', timeout=10) or sh('dmesg')}


# ------------------------------------------------------------------ system details
def uboot_env():
    """/boot/uboot.env: 4-byte CRC, then name=value strings ending with two zero bytes."""
    try:
        raw = open('/boot/uboot.env', 'rb').read()
    except OSError:
        return {}
    env = {}
    for item in raw[4:].split(b'\0'):
        if not item:
            break
        k, _, v = item.decode('latin-1').partition('=')
        env[k] = v
    return env


def dt_nodes():
    """Device tree: every node under /amba (and the top level) with its status."""
    base = '/proc/device-tree'
    out = []
    for d in sorted(glob.glob(base + '/*/') + glob.glob(base + '/axi/*/') + glob.glob(base + '/amba/*/')):
        comp = read(d + 'compatible').replace('\0', ' ').strip()
        if not comp:
            continue
        st = read(d + 'status').rstrip('\0') or 'okay'
        out.append({'node': d[len(base):].strip('/'), 'compatible': comp, 'status': st})
    return out


def interrupts():
    lines = read('/proc/interrupts').splitlines()
    rows = []
    for l in lines[1:]:
        p = l.split()
        if len(p) < 3:
            continue
        cpus = [int(x) for x in p[1:3] if x.isdigit()]
        rows.append({'irq': p[0].rstrip(':'), 'cpu0': cpus[0] if cpus else 0, 'cpu1': cpus[1] if len(cpus) > 1 else 0,
                     'name': ' '.join(p[3:]) if len(cpus) == 2 else ' '.join(p[1 + len(cpus):])})
    return rows


def listening():
    out = sh('ss', '-Hltnu')
    rows = []
    for l in out.splitlines():
        p = l.split()
        if len(p) >= 5:
            rows.append({'proto': p[0], 'local': p[4]})
    return rows


def info():
    try:
        addrs = json.loads(sh('ip', '-j', 'addr') or '[]')
        routes = json.loads(sh('ip', '-j', 'route') or '[]')
    except ValueError:
        addrs, routes = [], []
    td = dict(l.split('=', 1) for l in sh('timedatectl', 'show').splitlines() if '=' in l)
    mounts = []
    for l in read('/proc/mounts').splitlines():
        p = l.split()
        if p[0].startswith('/dev/') or p[1] in ('/', '/boot', '/tmp'):
            try:
                st = os.statvfs(p[1])
                mounts.append({'dev': p[0], 'at': p[1], 'type': p[2], 'opts': p[3].split(',')[0],
                               'size_mb': st.f_blocks * st.f_frsize // 2**20, 'free_mb': st.f_bavail * st.f_frsize // 2**20})
            except OSError:
                pass
    overlays = [os.path.basename(d) for d in glob.glob('/sys/kernel/config/device-tree/overlays/*')]
    mods = [l.split()[0] for l in read('/proc/modules').splitlines()]
    return {
        'cmdline': read('/proc/cmdline'), 'kernel': os.uname().release, 'kernel_build': os.uname().version,
        'python': sh('python3', '--version').strip(), 'gcc': (sh('gcc', '--version').splitlines() or [''])[0],
        'packages': len(sh('dpkg-query', '-f', '.\n', '-W').splitlines()),
        'time': {'now': time.time(), 'local': time.strftime('%Y-%m-%d %H:%M:%S %Z'), 'timezone': td.get('Timezone', ''),
                 'ntp_synced': td.get('NTPSynchronized') == 'yes', 'ntp': td.get('NTP') == 'yes'},
        'users': sh('who').strip().splitlines(),
        'addrs': [{'ifname': a.get('ifname'), 'state': a.get('operstate'), 'mtu': a.get('mtu'),
                   'mac': a.get('address'), 'addr': ['%s/%s' % (x.get('local'), x.get('prefixlen')) for x in a.get('addr_info', [])]}
                  for a in addrs],
        'routes': ['%s via %s dev %s' % (r.get('dst'), r.get('gateway', '-'), r.get('dev')) for r in routes],
        'dns': re.findall(r'^nameserver\s+(\S+)', read('/run/systemd/resolve/resolv.conf'), re.M),
        'listening': listening(), 'mounts': mounts, 'overlays': overlays, 'modules': mods,
        'interrupts': interrupts(), 'dt_model': read('/proc/device-tree/model').rstrip('\0'),
        'dt_compatible': read('/proc/device-tree/compatible').replace('\0', ' ').strip(),
        'dt_nodes': dt_nodes(), 'uboot_env': uboot_env(),
    }


def set_time(epoch):
    """Set the board clock from the PC (the board has no battery clock)."""
    t = float(epoch)
    if not 1.7e9 < t < 4.1e9:
        raise ValueError('bad time')
    diff = t - time.time()
    if abs(diff) < 2:
        return {'changed': False, 'diff_s': round(diff, 2)}
    r = subprocess.run(['date', '-u', '-s', '@%.3f' % t], capture_output=True, text=True)
    if r.returncode:
        raise ValueError(r.stderr.strip())
    return {'changed': True, 'diff_s': round(diff, 2)}


# ------------------------------------------------------------------ speed tests
def bench(test):
    if test == 'cpu':
        t0 = time.perf_counter()
        n, x = 0, 0
        while time.perf_counter() - t0 < 1.0:
            for i in range(2000):
                x = (x * 31 + i) & 0xFFFFFFFF
            n += 2000
        py = n / (time.perf_counter() - t0)
        t0 = time.perf_counter()
        r = subprocess.run('dd if=/dev/zero bs=1M count=32 status=none | sha256sum', shell=True, capture_output=True)
        sha = 32 / (time.perf_counter() - t0)
        return {'test': 'cpu', 'python_loops_per_s': round(py), 'sha256_mb_s': round(sha, 1),
                'note': 'one core; Python loop and SHA-256 hashing of 32 MB'}
    if test == 'mem':
        a = bytearray(32 * 2**20)
        t0 = time.perf_counter()
        for _ in range(4):
            b = bytes(a)
        cp = 4 * 32 / (time.perf_counter() - t0)
        del a, b
        r = subprocess.run(['dd', 'if=/dev/zero', 'of=/dev/null', 'bs=1M', 'count=1024'], capture_output=True, text=True)
        m = re.search(r'([\d.,]+) ([GM])B/s', r.stderr)
        fill = float(m.group(1).replace(',', '.')) * (1000 if m.group(2) == 'G' else 1) if m else None
        return {'test': 'mem', 'copy_mb_s': round(cp), 'fill_mb_s': fill,
                'note': 'copy: 32 MB blocks copied 4 times; fill: kernel writes 1 GB of zeros'}
    if test == 'sd':
        out = {'test': 'sd'}
        r = subprocess.run(['dd', 'if=/dev/mmcblk0', 'of=/dev/null', 'bs=1M', 'count=64', 'iflag=direct', 'skip=64'],
                           capture_output=True, text=True, timeout=120)
        m = re.search(r'([\d.,]+) ([GMk])B/s', r.stderr)
        out['read_mb_s'] = float(m.group(1).replace(',', '.')) * {'G': 1000, 'M': 1, 'k': 0.001}[m.group(2)] if m else None
        tmp = '/var/tmp/ardzy_speedtest.bin'
        try:
            r = subprocess.run(['dd', 'if=/dev/zero', 'of=' + tmp, 'bs=1M', 'count=32', 'oflag=direct', 'conv=fsync'],
                               capture_output=True, text=True, timeout=180)
            m = re.search(r'([\d.,]+) ([GMk])B/s', r.stderr)
            out['write_mb_s'] = float(m.group(1).replace(',', '.')) * {'G': 1000, 'M': 1, 'k': 0.001}[m.group(2)] if m else None
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        out['note'] = 'read: 64 MB straight from the card; write: a 32 MB file (deleted after)'
        return out
    raise ValueError('test: cpu, mem, sd')


# ------------------------------------------------------------------ register explorer
APER = 0x12C   # SLCR APER_CLK_CTRL: AMBA peripheral clocks


def _onoff(v, bit, on='on', off='off'):
    return on if v >> bit & 1 else off


def d_pll(v):
    return 'x%d, %s%s' % (f(v, 18, 12), 'bypassed, ' if v >> 4 & 1 else '', 'powered down' if v >> 1 & 1 else 'running')


def d_clk(v):
    src = {0: 'IO PLL', 1: 'IO PLL', 2: 'ARM PLL', 3: 'DDR PLL'}[f(v, 5, 4)]
    return '%s / %d / %d, %s' % (src, f(v, 13, 8), f(v, 25, 20) or 1, _onoff(v, 0, 'clock on', 'clock off'))


def d_aper(v):
    names = [(2, 'USB0'), (3, 'USB1'), (6, 'GEM0'), (7, 'GEM1'), (10, 'SDIO0'), (11, 'SDIO1'), (14, 'SPI0'),
             (15, 'SPI1'), (16, 'CAN0'), (17, 'CAN1'), (18, 'I2C0'), (19, 'I2C1'), (20, 'UART0'), (21, 'UART1'),
             (22, 'GPIO'), (23, 'QSPI'), (24, 'SMC'), (0, 'DMA')]
    return 'on: ' + ', '.join(n for b, n in names if v >> b & 1)


def d_bootmode(v):
    return {0: 'JTAG', 1: 'NOR', 2: 'NAND', 4: 'QSPI', 5: 'SD card'}.get(v & 7, '?') + (', PLL bypass' if v >> 4 & 1 else '')


def d_reboot(v):
    return ', '.join(n for b, n in hwapi.RESET_BITS if v >> b & 1) or '-'


def d_ddrc_ctrl(v):
    return '%s, %s bus, power-down %s, auto refresh %s' % (
        'running' if v & 1 else 'in reset', {0: '32-bit', 1: '16-bit'}.get(f(v, 3, 2), '?'),
        _onoff(v, 1), 'off' if v >> 18 & 1 else 'on')


def d_mode(v):
    return {0: 'starting', 1: 'normal', 2: 'power-down', 3: 'self refresh'}.get(v & 7, 'deep power-down')


def d_mr(v):
    mr0 = v & 0xFFFF
    return 'MR0 0x%04x (CAS latency %d), MR1 0x%04x' % (mr0, f(mr0, 6, 4) + 4, v >> 16)


def d_emr(v):
    return 'MR2 0x%04x (CAS write latency %d), MR3 0x%04x' % (v & 0xFFFF, f(v, 5, 3) + 5, v >> 16)


def d_scu_cfg(v):
    return '%d CPUs, SMP on CPU %s' % ((v & 3) + 1, ','.join(str(i) for i in range(2) if v >> (4 + i) & 1))


def d_l2id(v):
    return 'maker 0x%02x (ARM), part %s, release %d' % (v >> 24, 'PL310' if f(v, 9, 6) == 3 else f(v, 9, 6), v & 0x3F)


def d_l2aux(v):
    way_kb = {1: 16, 2: 32, 3: 64, 4: 128, 5: 256, 6: 512}.get(f(v, 19, 17), 0)
    ways = 16 if v >> 16 & 1 else 8
    return '%d ways x %d KB = %d KB, %s' % (ways, way_kb, ways * way_kb,
                                           'parity on' if v >> 21 & 1 else 'parity off')


def d_netcfg(v):
    return '%s, %s duplex' % ('1000 Mbit' if v >> 10 & 1 else '100 Mbit' if v & 1 else '10 Mbit', 'full' if v >> 1 & 1 else 'half')


def d_netctrl(v):
    return 'receive %s, send %s, MDIO %s' % (_onoff(v, 2), _onoff(v, 3), _onoff(v, 4))


def d_sd_state(v):
    return 'card %s, write protect %s, DAT lines %s, CMD %d' % (
        'inserted' if v >> 16 & 1 else 'missing', 'off' if v >> 19 & 1 else 'on', format(f(v, 23, 20), '04b'), v >> 24 & 1)


def d_sd_hc(v):
    return '%s bus, %s speed, power %s' % ('4-bit' if v >> 1 & 1 else '1-bit', 'high' if v >> 2 & 1 else 'normal',
                                          _onoff(v, 8))


def d_sd_cap(v):
    return 'base clock %d MHz, %s%s%s' % (f(v, 13, 8), 'high speed, ' if v >> 21 & 1 else '',
                                          '3.3 V' if v >> 24 & 1 else '', ', 1.8 V' if v >> 26 & 1 else '')


def d_uart_mode(v):
    bits = {3: 6, 2: 7}.get(f(v, 2, 1), 8)
    par = 'N' if f(v, 5, 3) >= 4 else {0: 'E', 1: 'O', 2: '0', 3: '1'}[f(v, 5, 3)]
    stop = {0: '1', 1: '1.5', 2: '2'}.get(f(v, 7, 6), '?')
    return '%d%s%s' % (bits, par, stop)


def d_swdt_mode(v):
    return 'watchdog %s, reset %s, interrupt %s' % (_onoff(v, 0), _onoff(v, 1), _onoff(v, 2))


def d_swdt_ctrl(v):
    pre = {0: 8, 1: 64, 2: 512, 3: 4096}[v & 3]
    return 'prescaler /%d, restart value %d' % (pre, f(v, 13, 2))


def d_ocm(v):
    return '64 KB blocks at the top of memory: %s' % format(v & 0xF, '04b')


def d_mio(v):
    return '%s, %s%s' % (hwapi.IO_TYPE.get(f(v, 11, 9), '?'), 'pull-up, ' if v >> 12 & 1 else '',
                         'GPIO' if not (v >> 1) & 0x7F else 'peripheral')


def d_devcfg_int(v):
    return 'PL configured (DONE) %s' % ('yes' if v >> 2 & 1 else 'no')


def d_devcfg_mctrl(v):
    return 'silicon %s' % hwapi.PS_VERSION.get(v >> 28, '?')


BLOCKS = [
    ('slcr', 'System control (SLCR): clocks and PLLs', 0xF8000000, None, [
        (0x100, 'ARM_PLL_CTRL', 'CPU PLL', d_pll), (0x104, 'DDR_PLL_CTRL', 'memory PLL', d_pll),
        (0x108, 'IO_PLL_CTRL', 'peripheral PLL', d_pll), (0x10C, 'PLL_STATUS', 'bits 0-2 locked (ARM, DDR, IO)', None),
        (0x110, 'ARM_PLL_CFG', 'PLL loop settings', None), (0x114, 'DDR_PLL_CFG', '', None), (0x118, 'IO_PLL_CFG', '', None),
        (0x120, 'ARM_CLK_CTRL', 'CPU clock source/divider', lambda v: 'divider %d, source %d, CPU clocks %s' % (f(v, 13, 8), f(v, 5, 4), format(f(v, 28, 24), '05b'))),
        (0x124, 'DDR_CLK_CTRL', 'DDR 3x / 2x dividers', lambda v: 'DDR_3x / %d, DDR_2x / %d' % (f(v, 25, 20), f(v, 31, 26))),
        (0x128, 'DCI_CLK_CTRL', 'DDR impedance calibration clock', None),
        (0x12C, 'APER_CLK_CTRL', 'peripheral clocks on/off', d_aper),
        (0x140, 'GEM0_CLK_CTRL', 'Ethernet', d_clk), (0x148, 'SMC_CLK_CTRL', 'NAND controller', d_clk),
        (0x150, 'SDIO_CLK_CTRL', 'SD card', d_clk), (0x154, 'UART_CLK_CTRL', 'UART', d_clk),
        (0x164, 'DBG_CLK_CTRL', 'debug', None), (0x168, 'PCAP_CLK_CTRL', 'FPGA loading port', d_clk),
        (0x170, 'FPGA0_CLK_CTRL', 'FCLK0', d_clk), (0x180, 'FPGA1_CLK_CTRL', 'FCLK1', d_clk),
        (0x190, 'FPGA2_CLK_CTRL', 'FCLK2', d_clk), (0x1A0, 'FPGA3_CLK_CTRL', 'FCLK3', d_clk),
        (0x1C4, 'CLK_621_TRUE', '1 = 6:2:1 CPU clock ratio', None)]),
    ('reset', 'System control (SLCR): reset, boot, memory, I/O', 0xF8000000, None, [
        (0x000, 'SCL', 'secure lock', None), (0x00C, 'SLCR_LOCKSTA', '1 = locked (Ardzy keeps it unlocked)', None),
        (0x240, 'FPGA_RST_CTRL', 'FPGA resets (1 = held)', None), (0x244, 'A9_CPU_RST_CTRL', 'CPU resets', None),
        (0x24C, 'RS_AWDT_CTRL', 'CPU watchdog reset control', None), (0x258, 'REBOOT_STATUS', 'why the last reset happened', d_reboot),
        (0x25C, 'BOOT_MODE', 'boot straps', d_bootmode), (0x300, 'APU_CTRL', 'CPU control', None),
        (0x304, 'WDT_CLK_SEL', 'system watchdog clock', None), (0x530, 'PSS_IDCODE', 'chip ID code', lambda v: 'device 0x%02x (7z010 = 0x02), revision %d' % (f(v, 16, 12), v >> 28)),
        (0x600, 'DDR_URGENT', '', None), (0x618, 'DDR_CMD_STA', 'DDR command queue', None),
        (0x620, 'DDR_DFI_STATUS', '', None), (0x804, 'MIO_LOOPBACK', '', None),
        (0x830, 'SD0_WP_CD_SEL', 'SD write-protect / card-detect pins', lambda v: 'WP = MIO%d, CD = MIO%d' % (v & 0x3F, f(v, 21, 16))),
        (0x900, 'LVL_SHFTR_EN', 'PS-PL level shifters', lambda v: 'all on' if (v & 0xF) == 0xF else 'partly off (FPGA signals blocked)'),
        (0x910, 'OCM_CFG', 'on-chip RAM mapping', d_ocm),
        (0xB00, 'GPIOB_CTRL', 'MIO buffer control', None), (0xB6C, 'DDRIOB_DDR_CTRL', 'DDR I/O control', None),
        (0xB70, 'DDRIOB_DCI_CTRL', 'DDR impedance calibration', None), (0xB74, 'DDRIOB_DCI_STATUS', 'bit 0 = calibration done', None)]
        + [(0x700 + 4 * n, 'MIO_PIN_%02d' % n, hwapi.MIO_FUNC.get(n, ('', ''))[0], d_mio) for n in range(54)]),
    ('ddrc', 'DDR memory controller', 0xF8006000, None, [
        (0x000, 'ddrc_ctrl', 'main control', d_ddrc_ctrl), (0x004, 'Two_rank_cfg', 'refresh interval (x32 clocks)', lambda v: 't_rfc_nom = %d x 32 clocks' % (v & 0xFFF)),
        (0x008, 'HPR_reg', 'high priority read queue', None), (0x00C, 'LPR_reg', 'low priority read queue', None),
        (0x010, 'WR_reg', 'write queue', None), (0x014, 'DRAM_param_reg0', 't_rc, t_rfc_min', lambda v: 't_rc %d, t_rfc_min %d clocks' % (v & 0x3F, f(v, 13, 6))),
        (0x018, 'DRAM_param_reg1', 'timing', None), (0x01C, 'DRAM_param_reg2', 'timing', None),
        (0x020, 'DRAM_param_reg3', 'timing', None), (0x024, 'DRAM_param_reg4', 'timing', None),
        (0x028, 'DRAM_init_param', 'start-up', None), (0x02C, 'DRAM_EMR_reg', 'mode registers 2/3', d_emr),
        (0x030, 'DRAM_EMR_MR_reg', 'mode registers 0/1', d_mr), (0x034, 'DRAM_burst8_rdwr', 'burst length', None),
        (0x038, 'DRAM_disable_DQ', '', None), (0x03C, 'DRAM_addr_map_bank', 'bank address bits', None),
        (0x040, 'DRAM_addr_map_col', 'column address bits', None), (0x044, 'DRAM_addr_map_row', 'row address bits', None),
        (0x048, 'DRAM_ODT_reg', 'on-die termination', None), (0x054, 'mode_sts_reg', 'operating mode', d_mode),
        (0x058, 'DLL_calib', '', None), (0x060, 'ctrl_reg1', '', None), (0x064, 'ctrl_reg2', '', None),
        (0x068, 'ctrl_reg3', '', None), (0x06C, 'ctrl_reg4', '', None), (0x0A0, 'CHE_REFRESH_TIMER01', '', None),
        (0x0A4, 'CHE_T_ZQ', 'ZQ calibration', None), (0x0B8, 'dfi_timing', '', None),
        (0x0C4, 'CHE_ECC_CONTROL', 'ECC (not used on this board)', None), (0x114, 'phy_rcvr_enable', '', None),
        (0x118, 'PHY_Config0', 'data lane 0', None), (0x11C, 'PHY_Config1', 'data lane 1', None),
        (0x120, 'PHY_Config2', 'data lane 2', None), (0x124, 'PHY_Config3', 'data lane 3', None),
        (0x200, 'page_mask', '', None)]),
    ('devcfg', 'FPGA loading (devcfg) and XADC interface', 0xF8007000, None, [
        (0x000, 'CTRL', 'configuration control', None), (0x004, 'LOCK', '', None), (0x008, 'CFG', '', None),
        (0x00C, 'INT_STS', 'events', d_devcfg_int), (0x010, 'INT_MASK', '', None), (0x014, 'STATUS', '', None),
        (0x02C, 'MULTIBOOT_ADDR', '', None), (0x080, 'MCTRL', 'misc control, silicon version', d_devcfg_mctrl),
        (0x100, 'XADCIF_CFG', 'XADC interface', None), (0x104, 'XADCIF_INT_STS', 'XADC alarms', None),
        (0x10C, 'XADCIF_MSTS', 'XADC status', None), (0x118, 'XADCIF_MCTL', '', None)]),
    ('mpcore', 'CPU complex: SCU, interrupt controller, timers', 0xF8F00000, None, [
        (0x000, 'SCU_CONTROL', 'snoop control', lambda v: 'SCU ' + _onoff(v, 0)), (0x004, 'SCU_CONFIG', 'CPUs', d_scu_cfg),
        (0x008, 'SCU_CPU_POWER', 'CPU power states', None), (0x040, 'FILTER_START', 'address filtering', None),
        (0x044, 'FILTER_END', '', None), (0x050, 'SCU_SAC', '', None),
        (0x100, 'ICCICR', 'GIC CPU interface', None), (0x104, 'ICCPMR', 'priority mask', None),
        (0x114, 'ICCRPR', 'running priority', None), (0x118, 'ICCHPIR', 'highest pending interrupt', lambda v: 'interrupt %d' % (v & 0x3FF)),
        (0x1FC, 'ICCIDR', 'GIC id', None),
        (0x200, 'GTIMER_LO', 'global timer (CPU clock / 2)', None), (0x204, 'GTIMER_HI', '', None),
        (0x208, 'GTIMER_CTRL', '', lambda v: 'timer ' + _onoff(v, 0)),
        (0x600, 'PTIMER_LOAD', 'private timer', None), (0x604, 'PTIMER_COUNT', '', None), (0x608, 'PTIMER_CTRL', '', None),
        (0x620, 'PWDT_LOAD', 'private watchdog', None), (0x624, 'PWDT_COUNT', '', None), (0x628, 'PWDT_CTRL', '', None),
        (0x1000, 'ICDDCR', 'GIC distributor', lambda v: 'distributor ' + _onoff(v, 0)),
        (0x1004, 'ICDICTR', 'GIC type', lambda v: '%d interrupt lines, %d CPUs' % (32 * ((v & 0x1F) + 1), f(v, 7, 5) + 1)),
        (0x1008, 'ICDIIDR', 'GIC implementer', None)]),
    ('l2c', 'L2 cache controller (PL310)', 0xF8F02000, None, [
        (0x000, 'CACHE_ID', '', d_l2id), (0x004, 'CACHE_TYPE', '', None),
        (0x100, 'CONTROL', '', lambda v: 'L2 cache ' + _onoff(v, 0)), (0x104, 'AUX_CONTROL', 'size and options', d_l2aux),
        (0x108, 'TAG_RAM_CTRL', 'latencies', None), (0x10C, 'DATA_RAM_CTRL', 'latencies', None),
        (0x200, 'EV_COUNTER_CTRL', '', None), (0x20C, 'EV_COUNTER1', '', None), (0x210, 'EV_COUNTER0', '', None),
        (0x214, 'INT_MASK', '', None), (0x21C, 'INT_RAW', '', None),
        (0xF40, 'DEBUG_CTRL', '', None), (0xF60, 'PREFETCH_CTRL', '', None), (0xF80, 'POWER_CTRL', '', None)]),
    ('gem0', 'Ethernet controller (GEM0)', 0xE000B000, 6, [
        (0x000, 'net_ctrl', '', d_netctrl), (0x004, 'net_cfg', 'speed / duplex', d_netcfg),
        (0x008, 'net_status', '', None), (0x010, 'dma_cfg', '', None), (0x014, 'tx_status', '', None),
        (0x018, 'rx_qbar', 'receive list address', None), (0x01C, 'tx_qbar', 'send list address', None),
        (0x020, 'rx_status', '', None), (0x030, 'intr_mask', '', None), (0x034, 'phy_maint', 'last MDIO access', None),
        (0x088, 'spec_addr1_bot', 'MAC address (low)', None), (0x08C, 'spec_addr1_top', 'MAC address (high)', None),
        (0x0FC, 'module_id', '', None)]),
    ('sdio0', 'SD card controller (SDIO0)', 0xE0100000, 10, [
        (0x004, 'BLOCK_SIZE_COUNT', '', None), (0x008, 'ARGUMENT', 'last command argument', None),
        (0x00C, 'TRANSFER_CMD', 'last command', lambda v: 'CMD%d' % f(v, 29, 24)),
        (0x010, 'RESPONSE0', '', None), (0x024, 'PRESENT_STATE', 'card and line state', d_sd_state),
        (0x028, 'HOST_CTRL', 'bus width, power', d_sd_hc),
        (0x02C, 'CLOCK_CTRL', 'card clock', lambda v: 'card clock %s, divider %d' % (_onoff(v, 2), f(v, 15, 8) * 2 or 1)),
        (0x030, 'INT_STATUS', '', None), (0x034, 'INT_STATUS_EN', '', None),
        (0x040, 'CAPABILITIES', '', d_sd_cap), (0x0FC, 'VERSION', '', lambda v: 'SD host spec %s' % {0: '1.0', 1: '2.0', 2: '3.0'}.get(v >> 16 & 0xFF, '?'))]),
    ('uart1', 'Console UART (UART1)', 0xE0001000, 21, [
        (0x000, 'Control', '', lambda v: 'receive %s, send %s' % ('off' if v >> 3 & 1 else 'on', 'off' if v >> 5 & 1 else 'on')),
        (0x004, 'Mode', 'format', d_uart_mode), (0x010, 'Intrpt_mask', '', None),
        (0x018, 'Baud_rate_gen', 'CD', None), (0x01C, 'Rcvr_timeout', '', None), (0x020, 'Rcvr_FIFO_trigger', '', None),
        (0x024, 'Modem_ctrl', '', None), (0x02C, 'Channel_sts', 'FIFO state', None),
        (0x034, 'Baud_rate_divider', 'BDIV', None), (0x044, 'Tx_FIFO_trigger', '', None)]),
    ('gpio', 'ARM GPIO (MIO and EMIO pins)', 0xE000A000, 22, [
        (0x060, 'DATA_0_RO', 'MIO 0-31 levels', None), (0x064, 'DATA_1_RO', 'MIO 32-53 levels', None),
        (0x040, 'DATA_0', 'MIO 0-31 output values', None), (0x044, 'DATA_1', 'MIO 32-53 output values', None),
        (0x204, 'DIRM_0', 'MIO 0-31 direction (1 = out)', None), (0x208, 'OEN_0', 'output enable', None),
        (0x244, 'DIRM_1', 'MIO 32-53 direction', None), (0x248, 'OEN_1', 'output enable', None),
        (0x20C, 'INT_MASK_0', '', None), (0x24C, 'INT_MASK_1', '', None)]),
    ('smc', 'NAND controller (SMC PL353)', 0xE000E000, 24, [
        (0x000, 'memc_status', '', None), (0x004, 'memc_if_config', '', None),
        (0x180, 'nand_cycles1_0', 'NAND timing', None), (0x184, 'opmode1_0', 'NAND bus width', lambda v: '%s bus' % ('16-bit' if v & 3 == 1 else '8-bit')),
        (0x400, 'ecc_status_1', '', None), (0x404, 'ecc_memcfg_1', 'ECC setup', None)]),
    ('timers', 'Triple timer TTC0 and system watchdog', 0xF8001000, None, [
        (0x000, 'TTC0 Clock_Control_1', '', None), (0x00C, 'TTC0 Counter_Control_1', '', None),
        (0x018, 'TTC0 Counter_Value_1', 'running count', None), (0x024, 'TTC0 Interval_1', '', None),
        (0x004, 'TTC0 Clock_Control_2', '', None), (0x010, 'TTC0 Counter_Control_2', '', None),
        (0x01C, 'TTC0 Counter_Value_2', '', None), (0x028, 'TTC0 Interval_2', '', None),
        (0x4000, 'SWDT MODE', 'system watchdog', d_swdt_mode), (0x4004, 'SWDT CONTROL', '', d_swdt_ctrl),
        (0x400C, 'SWDT STATUS', 'bit 0 = ran out', None),
        (0xB000, 'OCM_PARITY_CTRL', 'on-chip RAM', None), (0xB00C, 'OCM_CONTROL', '', None)]),
]


def regs_list():
    return [{'key': k, 'title': t, 'base': '0x%08X' % b, 'count': len(r)} for k, t, b, _, r in BLOCKS]


def regs(block):
    blk = next((b for b in BLOCKS if b[0] == block), None)
    if not blk:
        raise ValueError('unknown block')
    key, title, base, clk, rows = blk
    if clk is not None and not hwapi.slcr().rd(APER) >> clk & 1:
        return {'key': key, 'title': title, 'base': '0x%08X' % base, 'off': True, 'regs': [],
                'note': 'the clock of this block is off, so it is not read'}
    span = max(o for o, *_ in rows) + 4
    m = Mem(base, (span + 0xFFF) & ~0xFFF)
    out = []
    for off, name, desc, dec in rows:
        v = m.rd(off)
        try:
            d = dec(v) if dec else ''
        except Exception:
            d = ''
        out.append({'addr': '0x%08X' % (base + off), 'name': name, 'value': '0x%08X' % v, 'desc': desc, 'decoded': d})
    return {'key': key, 'title': title, 'base': '0x%08X' % base, 'off': False, 'regs': out}
