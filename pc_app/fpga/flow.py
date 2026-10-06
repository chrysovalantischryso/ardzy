"""Ardzy built-in FPGA build: Verilog -> .bit for the S9's XC7Z010, no Vivado needed.

    Yosys (synthesis)  ->  nextpnr-himbaechel (place and route)  ->  fasm2bit (bitstream)

A project is a folder with Verilog files (*.v, *.sv) and constraints (*.xdc). The Ardzy library
(fpga/hdl: PS7 link, AXI bridge, GPIO, register bus) is always available. The top module is
taken from fpga.json {"top": "..."}, else a module called "top", else the one no other module uses.
"""
import json, os, re, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import fasm2bit  # noqa: E402

PART = 'xc7z010clg400-1'


def tools_dir():
    for d in (os.path.join(HERE, '..', 'tools', 'fpga'), os.path.join(os.path.dirname(sys.executable), 'tools', 'fpga'),
              os.path.join(getattr(sys, '_MEIPASS', HERE), 'tools', 'fpga')):
        if os.path.isfile(os.path.join(d, 'bin', 'nextpnr-himbaechel.exe')):
            return os.path.normpath(d)
    return None


def available():
    return tools_dir() is not None


def library_files():
    d = os.path.join(HERE, 'hdl')
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(('.v', '.sv')))


def project_sources(proj):
    return sorted(os.path.join(proj, f) for f in os.listdir(proj)
                  if f.endswith(('.v', '.sv')) and not f.startswith(('tb_', 'test_')) and os.path.isfile(os.path.join(proj, f)))


_COMMENTS = re.compile(r'//[^\n]*|/\*.*?\*/', re.S)
_MODULE = re.compile(r'\bmodule\s+([A-Za-z_]\w*)')
_INST = re.compile(r'^\s*([A-Za-z_]\w*)\s*(?:#\s*\((?:[^()]|\([^()]*\))*\)\s*)?([A-Za-z_]\w*)\s*\(', re.M)
_KEYWORDS = {'module', 'input', 'output', 'inout', 'wire', 'reg', 'assign', 'always', 'if', 'else', 'case', 'for',
             'function', 'task', 'begin', 'end', 'generate', 'initial', 'localparam', 'parameter', 'integer', 'genvar'}


def find_top(files, wanted=None, own=None):
    """own: the project's files; only modules defined there can be the top (an unused library
    module such as ardzy_clock is not a candidate)."""
    modules, used, own_modules = [], set(), []
    for f in files:
        text = _COMMENTS.sub('', open(f, encoding='utf-8', errors='replace').read())
        found = _MODULE.findall(text)
        modules += found
        if own is None or f in own:
            own_modules += found
        for a, b in _INST.findall(text):
            if a not in _KEYWORDS:
                used.add(a)
    if wanted:
        if wanted not in modules:
            raise ValueError('top module "%s" not found (modules: %s)' % (wanted, ', '.join(modules)))
        return wanted
    if 'top' in own_modules:
        return 'top'
    cand = [m for m in own_modules if m not in used]
    if len(cand) == 1:
        return cand[0]
    raise ValueError('can not tell the top module (candidates: %s). Name it "top" or add fpga.json {"top": "name"}'
                     % ', '.join(cand or modules))


def design_ports(json_path, top):
    """Port bit names of the synthesized top module: leds[0], leds[1], ..., clk."""
    mod = json.load(open(json_path))['modules'][top]
    names = []
    for name, port in mod.get('ports', {}).items():
        bits = port.get('bits', [])
        if len(bits) == 1 and not port.get('upto') and 'offset' not in port:
            names.append(name)
        else:
            off = port.get('offset', 0)
            names += ['%s[%d]' % (name, off + i) for i in range(len(bits))]
    return names


# What was measured on the real XC7Z010 with this toolchain (projects/fpga_selftest, fpga_ramtest):
# works: LUT logic, carry chains, flip-flops, block RAM (RAMB18/RAMB36, all widths, SDP 72), LUT RAM,
# SRL shift registers, DSP48E1, MMCM, PLL, BUFG/BUFGCTRL clock switching, ODDR, IOBUF/OBUF, PS7.
NOT_VERIFIED = {
    'OSERDESE2': 'OSERDESE2 (serializer) does not work with the built-in toolchain yet: on the chip the pin '
                 'never toggles. Build this design with Vivado (Settings, FPGA build tool).',
    'ISERDESE2': 'ISERDESE2 (deserializer) has not been tested with the built-in toolchain.',
    'IDELAYE2': 'IDELAYE2 (input delay) has not been tested with the built-in toolchain.',
    'ODELAYE2': 'ODELAYE2 does not exist on the 3.3 V (HR) banks of this chip.',
    'XADC': 'XADC can not be used from the FPGA with the built-in toolchain; the ARM reads it '
            '(analogRead in sketches, the Board view).',
}


def check_cells(json_path, top):
    """Warnings for parts of the chip that the built-in toolchain cannot (yet) build correctly."""
    cells = json.load(open(json_path))['modules'][top].get('cells', {}).values()
    out = []
    for t in sorted({c['type'] for c in cells} & set(NOT_VERIFIED)):
        out.append(NOT_VERIFIED[t])
    for c in cells:
        if c['type'] == 'RAMB36E1':
            ext = {str(c['parameters'].get(k, 'NONE')).strip('"') for k in ('RAM_EXTENSION_A', 'RAM_EXTENSION_B')}
            if ext - {'NONE'}:
                out.append('Cascaded block RAM (RAM_EXTENSION) is not supported by the built-in toolchain.')
                break
    return out


def clean_xdc(src_files, out, ports=None):
    """nextpnr reads a simple XDC: no comments after commands, one port per get_ports,
    no wildcards (leds[*] is expanded with the design's real ports)."""
    import fnmatch
    lines, unknown = [], set()
    for f in src_files:
        for raw in open(f, encoding='utf-8', errors='replace'):
            line = raw.split(';#')[0].split('; #')[0].rstrip()
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            m = re.match(r'^(.*\[get_ports\s+)(\{[^}]*\}|\S+?)(\].*)$', line)
            if not m:
                lines.append(line)
                continue
            pats = m.group(2).strip('{}').split()
            for pat in pats:
                if ports is not None and any(c in pat for c in '*?'):
                    # in XDC the brackets are a bit index, not a character set
                    fpat = pat.replace('[', '\0').replace(']', '[]]').replace('\0', '[[]')
                    hits = [x for x in ports if fnmatch.fnmatchcase(x, fpat)]
                else:
                    hits = [pat]
                    if ports is not None and pat not in ports:
                        unknown.add(pat)
                        continue
                lines += ['%s{%s}%s' % (m.group(1), x, m.group(3)) for x in hits]
    open(out, 'w').write('\n'.join(lines) + '\n')
    return len(lines), sorted(unknown)


def _run(cmd, cwd, log, prefix, keep=None):
    flags = 0x08000000 if os.name == 'nt' else 0          # CREATE_NO_WINDOW
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         errors='replace', creationflags=flags)
    tail = []
    for line in p.stdout:
        line = line.rstrip()
        tail = (tail + [line])[-40:]
        if keep and keep(line):
            log(prefix + line)
    if p.wait():
        for l in tail[-15:]:
            log(prefix + l, 'err')
        raise RuntimeError('%s failed (exit code %d)' % (os.path.basename(cmd[0]), p.returncode))


def build(proj, log=print, freq_mhz=100, out_name=None):
    """Build the project's FPGA design. Returns the path of the .bit (inside the project)."""
    t0 = time.time()
    tdir = tools_dir()
    if not tdir:
        raise RuntimeError('the built-in FPGA toolchain is missing (tools/fpga)')
    name = out_name or os.path.basename(os.path.normpath(proj))
    cfg = {}
    if os.path.isfile(os.path.join(proj, 'fpga.json')):
        cfg = json.load(open(os.path.join(proj, 'fpga.json')))
    srcs = project_sources(proj)
    if not srcs:
        raise ValueError('no Verilog files (*.v) in the project')
    xdcs = sorted(os.path.join(proj, f) for f in os.listdir(proj) if f.endswith('.xdc'))
    if not xdcs:
        raise ValueError('no pin constraints (*.xdc) in the project: copy ardzy_pins.xdc and uncomment your pins')
    lib = library_files()
    top = find_top(srcs + lib, cfg.get('top'), own=srcs)
    work = os.path.join(tempfile.gettempdir(), 'ardzy_fpga', re.sub(r'[^\w.-]', '_', name))
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    files = []
    for f in srcs + lib:
        dst = os.path.join(work, os.path.basename(f))
        shutil.copy(f, dst)
        files.append(os.path.basename(f))
    log('FPGA build (built-in toolchain): top "%s", %d Verilog files + Ardzy library' % (top, len(srcs)), 'head')
    bindir = os.path.join(tdir, 'bin')
    freq = float(cfg.get('clock_mhz', freq_mhz))

    log('1/3  Synthesis (Yosys) ...')
    t = time.time()
    reads = '; '.join('read_verilog %s"%s"' % ('-sv ' if f.endswith('.sv') else '', f) for f in files)
    script = '%s; synth_xilinx -flatten -abc9 -arch xc7 -top %s; stat; write_json design.json' % (reads, top)
    _run([os.path.join(bindir, 'yosys.exe'), '-q', '-l', 'yosys.log', '-p', script], work, log, '     ',
         keep=lambda l: (l.startswith(('ERROR', 'Warning: Replacing', 'Warning: Wire', 'Warning: Driver-driver conflict',
                                       'Warning: multiple conflicting drivers'))
                         and 'Replacing memory' not in l and 'floating point parameter' not in l))
    stats = _yosys_stats(os.path.join(work, 'yosys.log'))
    log('     done in %.0f s: %s' % (time.time() - t, ', '.join('%s %s' % (v, k) for k, v in stats.items()) or 'ok'))

    for w in check_cells(os.path.join(work, 'design.json'), top):
        log('     WARNING: ' + w, 'warn')
    ports = design_ports(os.path.join(work, 'design.json'), top)
    n, unknown = clean_xdc(xdcs, os.path.join(work, 'pins.xdc'), ports)
    log('     %d pins in the design, %d constraint lines%s' % (
        len(ports), n, ('; constraints for ports not in the design (ignored): ' + ', '.join(unknown[:8])) if unknown else ''))
    log('2/3  Place and route (nextpnr) ...')
    # Placement is random: when a try misses the clock speed (setup) or has hold-time problems,
    # other seeds are tried and the best result is kept.
    best = None
    for seed in (1, 2, 3, 4, 5):
        t = time.time()
        fasm = 'design_%d.fasm' % seed
        _run([os.path.join(bindir, 'nextpnr-himbaechel.exe'), '--device', PART, '--json', 'design.json',
              '-o', 'xdc=pins.xdc', '-o', 'fasm=' + fasm, '--router', 'router2', '--freq', '%g' % freq,
              '--seed', str(seed), '--timing-allow-fail', '-l', 'nextpnr.log', '--quiet'], work, log, '     ',
             keep=lambda l: l.startswith('ERROR') and 'time violation' not in l)
        text = open(os.path.join(work, 'nextpnr.log'), errors='replace').read()
        # the log has a report after placement and one after routing: the later line of a clock wins
        clocks = {}
        for m in re.finditer(r"Max frequency for clock\s+'([^']+)': ([\d.]+) MHz \((PASS|FAIL) at ([\d.]+) MHz\)", text):
            clocks[m.group(1)] = (float(m.group(2)), m.group(3), float(m.group(4)))
        summary = ', '.join("clock '%s' %.1f MHz (%s at %g MHz)" % (k, f, r, need) for k, (f, r, need) in clocks.items()) \
            or 'no clock found'
        hold = len(re.findall(r'ERROR: Hold/min time violation', text))
        fmax = min([f / need for f, r, need in clocks.values()] or [0])     # the tightest margin
        ok = bool(clocks) and all(r == 'PASS' for f, r, need in clocks.values()) and not hold
        log('     try %d done in %.0f s: %s%s' % (seed, time.time() - t, summary,
                                                  ', %d hold-time problem(s)' % hold if hold else ''),
            None if ok else 'warn')
        shutil.copy(os.path.join(work, 'nextpnr.log'), os.path.join(work, 'nextpnr_%d.log' % seed))
        score = (ok, -hold, fmax)
        if best is None or score > best[0]:
            best = (score, fasm, seed)
        if ok:
            break
    (ok, _, _), fasm, seed = best
    shutil.copy(os.path.join(work, fasm), os.path.join(work, 'design.fasm'))
    if not ok:
        log('     No try met the clock speed without timing problems: the design may not work reliably. '
            'Use fewer logic levels (add a register stage) or a slower clock. Kept the best try (%d).' % seed, 'warn')

    log('3/3  Bitstream (fasm2bit) ...')
    bit = os.path.join(work, name + '.bit')
    fasm2bit.assemble(os.path.join(tdir, 'db', 'zynq7'), PART, os.path.join(work, 'design.fasm'), bit,
                      log=lambda s: log('     ' + s))
    dst = os.path.join(proj, name + '.bit')
    shutil.copy(bit, dst)
    log('FPGA build done in %.0f s: %s' % (time.time() - t0, dst), 'ok')
    return dst


def _yosys_stats(path):
    want = {'LUT': 0, 'FD': 0, 'RAMB': 0, 'DSP48E1': 0, 'IOBUF': 0}
    try:
        text = open(path, errors='replace').read()
    except OSError:
        return {}
    text = text[text.rfind('Printing statistics'):]
    for m in re.finditer(r'^\s+(\d+)\s+(\w+)\s*$', text, re.M):
        n, cell = int(m.group(1)), m.group(2)
        for k in want:
            if cell.startswith(k):
                want[k] += n
    names = {'LUT': 'LUTs', 'FD': 'flip-flops', 'RAMB': 'block RAMs', 'DSP48E1': 'DSPs', 'IOBUF': 'I/O buffers'}
    return {names[k]: v for k, v in want.items() if v}


if __name__ == '__main__':
    build(sys.argv[1], log=lambda s, c=None: print(s))
