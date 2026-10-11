"""Ardzy built-in FPGA build: Verilog -> .bit for the XC7Z010 of an Ardzy board, no Vivado needed.

    Yosys (synthesis)  ->  nextpnr-himbaechel (place and route)  ->  fasm2bit (bitstream)

A project is a folder with Verilog files (*.v, *.sv) and constraints (*.xdc). The Ardzy library
(fpga/hdl: PS7 link, AXI bridge, GPIO, register bus) is always available. The top module is
taken from fpga.json {"top": "..."}, else a module called "top", else the one no other module uses.

The board (fpga.json {"board": "ebaz4205"}, else the one asked for, else the S9) gives the chip and what every
design must keep: on the EBAZ4205 the Ethernet PHY hangs on FPGA pins, so the build adds the Ethernet
connection (and the two LEDs, when the design does not use their pins) to every design by itself.
"""
import json, os, re, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import fasm2bit  # noqa: E402
sys.path.insert(0, os.path.dirname(HERE))
import boards  # noqa: E402

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


_TESTBENCH = re.compile(r'(^tb[_.]|_tb\.|^testbench|^test_)', re.I)     # (the names Simulate takes as testbenches)


def project_sources(proj):
    return sorted(os.path.join(proj, f) for f in os.listdir(proj)
                  if f.endswith(('.v', '.sv')) and not _TESTBENCH.search(f) and os.path.isfile(os.path.join(proj, f)))


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
    lines, overridden = merge_port_properties(lines)
    open(out, 'w').write('\n'.join(lines) + '\n')
    return len(lines), sorted(unknown), overridden


_PROP_LINE = re.compile(r'^\s*set_property\s+(?:-dict\s+\{([^}]*)\}|(\S+)\s+(\S+))\s+\[get_ports\s+\{([^}]+)\}\]\s*$')


def merge_port_properties(lines):
    """One line per port with all its properties; a property set twice (in two files, or a pin and then all
    pins with leds[*]) keeps the later value, like Vivado does. nextpnr itself stops at a second value."""
    props, order, other, overridden = {}, [], [], []
    for line in lines:
        m = _PROP_LINE.match(line)
        if not m:
            other.append(line)
            continue
        port = m.group(4).strip()
        if m.group(1) is not None:
            words = m.group(1).split()
            pairs = list(zip(words[0::2], words[1::2]))
        else:
            pairs = [(m.group(2), m.group(3))]
        if port not in props:
            props[port] = {}
            order.append(port)
        for k, v in pairs:
            k = k.upper()
            if k in props[port] and props[port][k] != v:
                overridden.append('%s %s %s -> %s' % (port, k, props[port][k], v))
            props[port][k] = v
    merged = ['set_property -dict {%s} [get_ports {%s}]' % (' '.join('%s %s' % kv for kv in props[p].items()), p) for p in order]
    return other + merged, overridden


# ---------------------------------------------------------------- boards with the Ethernet on FPGA pins
XDC_PORT = re.compile(r'get_ports\s+(?:\{\s*([^}]+?)\s*\}|([^\s\]]+))\s*\]')   # {leds[0]} or leds
ETH_PORTS = [   # (port, direction, width, the library's wire)
    ('eth_txd', 'output', 4, 'ardzy_eth_txd'), ('eth_txen', 'output', 1, 'ardzy_eth_txen'),
    ('eth_txclk', 'input', 1, 'ardzy_eth_txclk'), ('eth_rxclk', 'input', 1, 'ardzy_eth_rxclk'),
    ('eth_rxd', 'input', 4, 'ardzy_eth_rxd'), ('eth_rxdv', 'input', 1, 'ardzy_eth_rxdv'),
    ('eth_mdc', 'output', 1, 'ardzy_eth_mdc'), ('eth_mdio', 'inout', 1, 'ardzy_eth_mdio'),
    ('eth_phyclk', 'output', 1, 'ardzy_eth_phyclk')]


def xdc_pins(xdcs):
    """{package pin: port} of the constraints (to see which board pins a design uses)."""
    out = {}
    for f in xdcs:
        for line in open(f, encoding='utf-8', errors='replace'):
            line = line.split('#')[0]
            m = re.search(r'PACKAGE_PIN\s+(\w+)', line)
            p = XDC_PORT.search(line)
            if m and p:
                out[m.group(1).upper()] = (p.group(1) or p.group(2)).strip()
    return out


def _wrapper(pre_json, top, ps7=True, ila=None):
    """A top module around the design: + the library's PS7 when the design has no ARM side (for the Ethernet or the
    analyzer), + the signal analyzer (ila = (width, log2 depth)). Their wires are connected after flatten."""
    mod = json.load(open(pre_json))['modules'][top]
    decl, conn = [], []
    for name, port in mod.get('ports', {}).items():
        n, off = len(port['bits']), port.get('offset', 0)
        rng = '' if n == 1 and 'offset' not in port and not port.get('upto') else \
            ('[%d:%d] ' % (off, off + n - 1) if port.get('upto') else '[%d:%d] ' % (off + n - 1, off))
        decl.append('    %s wire %s%s' % (port['direction'], rng, name))
        conn.append('.%s(%s)' % (name, name))
    # (the ARM side's outputs stay open: only its Ethernet, LED, clock and analyzer wires are used)
    text = 'module ardzy_board_top (\n%s\n);\n    %s u_design (%s);\n' % (',\n'.join(decl), top, ', '.join(conn))
    if ps7:
        text += ('    ardzy_ps7 u_ardzy_ps7 (.clk(), .rstn(), .awaddr(), .awlen(), .awsize(), .awburst(), .awid(), .awvalid(),\n'
                 '        .awready(1\'b0), .wdata(), .wstrb(), .wlast(), .wvalid(), .wready(1\'b0), .bid(12\'d0), .bresp(2\'d0),\n'
                 '        .bvalid(1\'b0), .bready(), .araddr(), .arlen(), .arsize(), .arburst(), .arid(), .arvalid(),\n'
                 '        .arready(1\'b0), .rid(12\'d0), .rdata(32\'d0), .rresp(2\'d0), .rlast(1\'b0), .rvalid(1\'b0), .rready());\n')
    if ila:
        text += '    ardzy_ila #(.W(%d), .AW(%d)) u_ila (.sclk(), .probe(), .fclk(), .ctl(), .dout());\n' % ila
    return text + 'endmodule\n'


ILA_MAX_WIDTH = 217          # 7 words of 31 bits (bit 31 is the answer's tag; word 7 is the status)
ILA_MAX_BITS = 16 * 36864    # at most 16 block RAMs for the samples


def debug_config(proj, cfg, srcs):
    """The analyzer's settings: fpga.json "debug" (a list of names, or {"signals": [...], "clock": name, "depth": n}),
    and whether any source marks signals with (* mark_debug *). None when nothing asks for it."""
    d = cfg.get('debug') or {}
    if isinstance(d, list):
        d = {'signals': d}
    marked = any(re.search(r'\bmark_debug\b', open(f, encoding='utf-8', errors='replace').read()) for f in srcs)
    if not d.get('signals') and not marked:
        return None
    return {'signals': [str(x) for x in d.get('signals', [])], 'clock': d.get('clock'), 'depth': int(d.get('depth', 1024))}


def debug_signals(flat_json, top, dbg):
    """The signals to watch, from the flattened design: [(name, width)] (the marked ones, then the listed ones)."""
    nets = json.load(open(flat_json))['modules'][top]['netnames']
    out, seen = [], set()
    for name, n in nets.items():
        a = n.get('attributes', {}).get('mark_debug')
        if a is not None and str(a).strip('0') not in ('', 'false') and '$' not in name:
            out.append((name, len(n['bits'])))
            seen.add(name)
    missing = []
    for name in dbg['signals']:
        name = name.lstrip('\\')
        if name in seen:
            continue
        if name in nets:
            out.append((name, len(nets[name]['bits'])))
            seen.add(name)
        else:
            missing.append(name)
    if missing:
        close = [n for n in nets if '$' not in n and any(m.split('.')[-1] == n.split('.')[-1] for m in missing)]
        raise ValueError('fpga.json "debug": no signal called %s in the design%s' % (
            ', '.join(missing), ' (did you mean %s?)' % ', '.join(sorted(close)[:6]) if close else ''))
    bad = [n for n, w in out if re.search(r'[\s\[\]{}]', n)]
    if bad:
        raise ValueError('the analyzer can not watch %s (a memory or a name with brackets): watch a plain reg or wire'
                         % ', '.join(bad))
    return out, nets


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


def build(proj, log=print, freq_mhz=100, out_name=None, board=None):
    """Build the project's FPGA design for a board. Returns the path of the .bit (inside the project)."""
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
    xdcs = sorted((os.path.join(proj, f) for f in os.listdir(proj) if f.endswith('.xdc')),
                  key=lambda p: (os.path.basename(p) == 'io_plan.xdc', p))      # (the I/O plan last: it wins)
    if not xdcs:
        raise ValueError('no pin constraints (*.xdc) in the project: copy ardzy_pins.xdc and uncomment your pins')
    lib = library_files()
    top = find_top(srcs + lib, cfg.get('top'), own=srcs)
    prof = boards.load(cfg.get('board') or board)
    part = prof.get('part', PART)
    eth = (prof.get('ethernet') or {}).get('pins') or {}
    work = os.path.join(tempfile.gettempdir(), 'ardzy_fpga', re.sub(r'[^\w.-]', '_', name))
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    files = []
    for f in srcs + lib:
        dst = os.path.join(work, os.path.basename(f))
        shutil.copy(f, dst)
        files.append(os.path.basename(f))
    log('FPGA build (built-in toolchain) for the %s: top "%s", %d Verilog files + Ardzy library'
        % (prof['name'], top, len(srcs)), 'head')
    bindir = os.path.join(tdir, 'bin')
    freq = float(cfg.get('clock_mhz', freq_mhz))
    yosys = os.path.join(bindir, 'yosys.exe')

    log('1/3  Synthesis (Yosys) ...')
    t = time.time()
    dbg = debug_config(proj, cfg, srcs)
    defines = ('-D ARDZY_EMIO_ENET0 ' if eth else '') + ('-D ARDZY_ILA ' if dbg else '')
    reads = '; '.join('read_verilog %s%s"%s"' % (defines, '-sv ' if f.endswith('.sv') else '', f) for f in files)
    synth_top, extra, board_xdc, cmds, debug_info = top, '', [], [], None
    if eth or dbg:
        # 1. where the design's ARM side (PS7) is: the Ethernet and the analyzer hang on it
        _run([yosys, '-q', '-p', '%s; hierarchy -top %s; proc; flatten; tee -q -o ps7.txt select -list w:*ardzy_fclk%s'
              % (reads, top, '; write_json flat.json' if dbg else '')], work, log, '     ', keep=lambda l: l.startswith('ERROR'))
        found = [l.strip().split('/', 1)[1] for l in open(os.path.join(work, 'ps7.txt')) if '/' in l]
        if len(found) > 1:
            raise ValueError('the design has %d ARM sides (PS7): a design can only have one' % len(found))
        ila = None
        if dbg:
            sigs, nets = debug_signals(os.path.join(work, 'flat.json'), top, dbg)
            if not sigs:
                raise ValueError('the analyzer has no signals: mark them with (* mark_debug *) or list them in fpga.json "debug"')
            width = sum(w for _, w in sigs)
            if width > ILA_MAX_WIDTH:
                raise ValueError('the analyzer can watch %d bits at most, the marked signals have %d (%s)' % (
                    ILA_MAX_WIDTH, width, ', '.join('%s %d' % x for x in sigs)))
            depth = max(64, min(4096, dbg['depth']))
            aw = depth.bit_length() - 1
            while width * (1 << aw) > ILA_MAX_BITS and aw > 6:
                aw -= 1
            ila = (width, aw)
            clock = dbg['clock'] or ('clk' if 'clk' in nets else None)
            if clock and clock not in nets:
                raise ValueError('fpga.json "debug": no clock called %s in the design' % clock)
        if found and not dbg:
            prefix = found[0][:-len('ardzy_fclk')]
        else:                            # a top around the design: the analyzer, and the ARM side when it has none
            _run([yosys, '-q', '-p', '%s; hierarchy -top %s; proc; write_json pre.json' % (reads, top)], work, log, '     ',
                 keep=lambda l: l.startswith('ERROR'))
            open(os.path.join(work, 'ardzy_board_top.v'), 'w').write(
                _wrapper(os.path.join(work, 'pre.json'), top, ps7=not found, ila=ila))
            reads += '; read_verilog %s"ardzy_board_top.v"' % defines
            synth_top = 'ardzy_board_top'
            prefix = 'u_design.' + found[0][:-len('ardzy_fclk')] if found else 'u_ardzy_ps7.'
        if dbg:
            lsb, layout = 0, []
            for sname, w in sigs:
                layout.append({'name': sname, 'width': w, 'lsb': lsb})
                lsb += w
            sclk = '\\u_design.' + clock if clock else '\\' + prefix + 'ardzy_fclk'
            cmds += ['connect -set \\u_ila.probe[%d:%d] \\u_design.%s' % (x['lsb'] + x['width'] - 1, x['lsb'], x['name'])
                     for x in layout]
            cmds += ['connect -set \\u_ila.sclk %s' % sclk,
                     'connect -set \\u_ila.fclk \\%sardzy_fclk' % prefix,
                     'connect -set \\u_ila.ctl \\%sardzy_ila_ctl' % prefix,
                     'connect -set \\%sardzy_ila_dout \\u_ila.dout' % prefix]
            debug_info = {'signals': layout, 'width': ila[0], 'depth': 1 << ila[1],
                          'clock': clock or 'FCLK0 (the ARM clock)', 'clock_mhz': freq if clock else None}
            log('     signal analyzer: %d signals, %d bits x %d samples, clock %s: %s' % (
                len(sigs), ila[0], 1 << ila[1], debug_info['clock'], ', '.join(n for n, _ in sigs[:8]) + (' ...' if len(sigs) > 8 else '')))
    if eth:
        used = xdc_pins(xdcs)
        clash = sorted('%s (%s)' % (pin, used[pin]) for pin in set(eth.values()) if pin in used)
        if clash:
            raise ValueError('on the %s these pins belong to the Ethernet: %s. Use other pins.' % (prof['name'], ', '.join(clash)))
        for port, direction, width, wire in ETH_PORTS:
            cmds.append('add -%s %s %d' % (direction, port, width))
            lhs, rhs = (port, '\\' + prefix + wire) if direction != 'input' else ('\\' + prefix + wire, port)
            cmds.append('connect -set %s %s' % (lhs, rhs))
        xdc = ['set_property -dict {PACKAGE_PIN %s IOSTANDARD LVCMOS33} [get_ports {%s}]' % (pin, port)
               for port, pin in sorted(eth.items())]
        for lname, led in sorted((prof.get('leds') or {}).items()):
            if led.get('pl') and led['pin'] not in used:      # the board's LED, unless the design drives it itself
                cmds += ['add -output led_%s 1' % lname, 'connect -set led_%s \\%sardzy_led_%s' % (lname, prefix, lname)]
                xdc.append('set_property -dict {PACKAGE_PIN %s IOSTANDARD LVCMOS33} [get_ports {led_%s}]' % (led['pin'], lname))
        board_xdc = [os.path.join(work, 'board_pins.xdc')]
        open(board_xdc[0], 'w').write('\n'.join(xdc) + '\n')
        log('     the %s: the Ethernet (and the free LEDs) are connected to this design, so the network stays up'
            % prof['name'])
    if cmds:
        extra = 'hierarchy -top %s; proc; flatten; %s; ' % (synth_top, '; '.join(cmds))
    script = '%s; %ssynth_xilinx -flatten -abc9 -arch xc7 -top %s; stat; write_json design.json' % (reads, extra, synth_top)
    _run([yosys, '-q', '-l', 'yosys.log', '-p', script], work, log, '     ',
         keep=lambda l: (l.startswith(('ERROR', 'Warning: Replacing', 'Warning: Wire', 'Warning: Driver-driver conflict',
                                       'Warning: multiple conflicting drivers'))
                         and 'Replacing memory' not in l and 'floating point parameter' not in l))
    stats = _yosys_stats(os.path.join(work, 'yosys.log'))
    log('     done in %.0f s: %s' % (time.time() - t, ', '.join('%s %s' % (v, k) for k, v in stats.items()) or 'ok'))

    for w in check_cells(os.path.join(work, 'design.json'), synth_top):
        log('     WARNING: ' + w, 'warn')
    ports = design_ports(os.path.join(work, 'design.json'), synth_top)
    n, unknown, overridden = clean_xdc(xdcs + board_xdc, os.path.join(work, 'pins.xdc'), ports)
    log('     %d pins in the design, %d constraint lines%s' % (
        len(ports), n, ('; constraints for ports not in the design (ignored): ' + ', '.join(unknown[:8])) if unknown else ''))
    if overridden:
        log('     set twice, the later one is used: %s' % ', '.join(overridden[:6]) + (' ...' if len(overridden) > 6 else ''), 'warn')
    log('2/3  Place and route (nextpnr) ...')
    # Placement is random: when a try misses the clock speed (setup) or has hold-time problems,
    # other seeds are tried and the best result is kept.
    best = None
    for seed in (1, 2, 3, 4, 5):
        t = time.time()
        fasm = 'design_%d.fasm' % seed
        _run([os.path.join(bindir, 'nextpnr-himbaechel.exe'), '--device', part, '--json', 'design.json',
              '-o', 'xdc=pins.xdc', '-o', 'fasm=' + fasm, '--router', 'router2', '--freq', '%g' % freq,
              '--seed', str(seed), '--timing-allow-fail', '-l', 'nextpnr.log', '--quiet'], work, log, '     ',
             keep=lambda l: l.startswith('ERROR') and 'time violation' not in l)
        text = open(os.path.join(work, 'nextpnr.log'), errors='replace').read()
        # the log has a report after placement and one after routing: the later line of a clock wins
        clocks = {}
        for m in re.finditer(r"Max frequency for clock\s+'([^']+)': ([\d.]+) MHz \((PASS|FAIL) at ([\d.]+) MHz\)", text):
            clocks[m.group(1)] = (float(m.group(2)), m.group(3), float(m.group(4)))
        summary = ', '.join("clock '%s' %.1f MHz (%s at %g MHz)" % (k, f, r, need) for k, (f, r, need) in clocks.items()) \
            or 'no clock in the design (only logic between pins: nothing to time)'
        hold = len(re.findall(r'ERROR: Hold/min time violation', text))
        fmax = min([f / need for f, r, need in clocks.values()] or [1])     # the tightest margin
        ok = all(r == 'PASS' for f, r, need in clocks.values()) and not hold
        log('     try %d done in %.0f s: %s%s' % (seed, time.time() - t, summary,
                                                  ', %d hold-time problem(s)' % hold if hold else ''),
            None if ok else 'warn')
        shutil.copy(os.path.join(work, 'nextpnr.log'), os.path.join(work, 'nextpnr_%d.log' % seed))
        score = (ok, -hold, fmax)
        if best is None or score > best[0]:
            best = (score, fasm, seed, dict(clocks), hold, critical_paths(text))
        if ok:
            break
    (ok, _, _), fasm, seed, best_clocks, best_hold, best_paths = best
    shutil.copy(os.path.join(work, fasm), os.path.join(work, 'design.fasm'))
    if not ok:
        log('     No try met the clock speed without timing problems: the design may not work reliably. '
            'Use fewer logic levels (add a register stage) or a slower clock. Kept the best try (%d).' % seed, 'warn')

    log('3/3  Bitstream (fasm2bit) ...')
    bit = os.path.join(work, name + '.bit')
    fasm2bit.assemble(os.path.join(tdir, 'db', 'zynq7'), part, os.path.join(work, 'design.fasm'), bit,
                      log=lambda s: log('     ' + s))
    dst = os.path.join(proj, name + '.bit')
    shutil.copy(bit, dst)
    cells = cell_counts(os.path.join(work, 'yosys.log'))
    def own(n):                      # names inside the top the build put around the design: as the design calls them
        return re.sub(r'(^|(?<=[\s(]))u_design\.', '', n) if synth_top == 'ardzy_board_top' else n
    for p in best_paths:
        p['clock'], p['start'], p['end'] = own(p['clock']), own(p['start']), own(p['end'])
        for st in p['steps']:
            st['net'] = own(st['net'])
    report = {'board': prof['id'], 'board_name': prof['name'], 'part': part, 'top': top, 'seconds': round(time.time() - t0),
              'date': time.strftime('%Y-%m-%d %H:%M'), 'used': cells, 'max': CHIP_MAX, 'pins': len(ports),
              'clocks': {own(k): {'fmax': f, 'need': need, 'pass': r == 'PASS'} for k, (f, r, need) in best_clocks.items()},
              'hold_problems': best_hold, 'timing_ok': ok, 'paths': best_paths, 'debug': debug_info, 'seed': seed, 'ethernet_added': bool(eth)}
    write_build_info(proj, dst, prof['id'], report)
    log('     used: %s' % ', '.join('%s %d of %d (%.0f %%)' % (k, v, CHIP_MAX[k], 100.0 * v / CHIP_MAX[k])
                                    for k, v in cells.items() if k in CHIP_MAX))
    log('FPGA build done in %.0f s: %s (Report: the build report)' % (time.time() - t0, dst), 'ok')
    return dst


# what the XC7Z010 has (Xilinx DS190): LUTs, flip-flops, 36 Kb block RAMs, DSP slices, user I/O pins (CLG400)
CHIP_MAX = {'LUT': 17600, 'FF': 35200, 'BRAM': 60, 'DSP': 80, 'PINS': 100}


def cell_counts(yosys_log):
    """The design's cells from Yosys' statistics: LUTs, flip-flops, block RAM (36 Kb units), DSPs, clocks."""
    try:
        text = open(yosys_log, errors='replace').read()
    except OSError:
        return {}
    text = text[text.rfind('Printing statistics'):]
    raw = {}
    for m in re.finditer(r'^\s+(\d+)\s+(\w+)\s*$', text, re.M):
        raw[m.group(2)] = raw.get(m.group(2), 0) + int(m.group(1))
    pick = lambda pre: sum(v for k, v in raw.items() if k.startswith(pre))
    out = {'LUT': pick('LUT'), 'FF': pick('FD'), 'BRAM': raw.get('RAMB36E1', 0) + (raw.get('RAMB18E1', 0) + 1) // 2,
           'DSP': raw.get('DSP48E1', 0), 'LUT_RAM': pick('RAM32') + pick('RAM64') + pick('RAM128') + pick('RAM256'),
           'SRL': pick('SRL'), 'CARRY': raw.get('CARRY4', 0), 'BUFG': pick('BUFG'),
           'MMCM_PLL': pick('MMCME2') + pick('PLLE2')}
    return out


BUILD_INFO = '.ardzy_build.json'       # which board each bitstream of the project was built for


_CRIT_HEAD = re.compile(r"^Info: Critical path report for (?:clock '([^']+)'|cross-domain path '([^']+)' -> '([^']+)')")
_CRIT_STEP = re.compile(r'^Info:\s+(clk-to-q|routing|logic|setup|hold|source|sink)\s+([\d.-]+)\s+([\d.-]+)\s+(Source|Net)\s+(\S+)')
_CRIT_DEF = re.compile(r'^Info:\s+(\S+?):(\d+)\.\d+-\d+\.\d+\s*$')


def _cell_name(n):
    """A readable name for a nextpnr cell or net: yosys makes names like $abc$123$lut... for logic it made."""
    if n.startswith('$'):
        m = re.search(r'flatten\\([\w.]+)\.\$', n)
        return (m.group(1) + ' (logic)') if m else '(logic)'
    return n


def critical_paths(log_text, keep=12):
    """The slowest path of each clock (and between clocks) from the last report in a nextpnr log: where it starts
    and ends, its delay, how many logic levels, and the nets of your own source files it goes through."""
    paths, cur = {}, None
    for line in log_text.splitlines():
        h = _CRIT_HEAD.match(line)
        if h:
            key = h.group(1) or '%s -> %s' % (h.group(2), h.group(3))
            cur = {'clock': key, 'cross': h.group(1) is None, 'start': '', 'end': '', 'delay': 0.0,
                   'levels': 0, 'logic_ns': 0.0, 'route_ns': 0.0, 'steps': []}
            paths[key] = cur
            continue
        if cur is None:
            continue
        m = _CRIT_STEP.match(line)
        if m:
            kind, curr, total, what, name = m.group(1), float(m.group(2)), float(m.group(3)), m.group(4), m.group(5)
            cur['delay'] = total
            if kind == 'logic':
                cur['levels'] += 1
            if kind == 'routing':
                cur['route_ns'] += curr
            else:
                cur['logic_ns'] += curr
            if kind == 'routing' and what == 'Net':
                cur['steps'].append({'net': _cell_name(name), 'ns': curr, 'src': ''})
            continue
        m = _CRIT_DEF.match(line)
        if m and cur['steps'] and not cur['steps'][-1]['src']:
            f = m.group(1).replace('\\', '/')
            if '/share/yosys/' not in f:            # the tool's own cell library is not your code
                cur['steps'][-1]['src'] = '%s:%s' % (os.path.basename(f), m.group(2))
            continue
        if line.startswith('Info: ') and re.match(r'^Info: [\d.]+ ns logic, [\d.]+ ns routing', line):
            cur = None
    out = []
    for p in paths.values():
        for k in ('delay', 'logic_ns', 'route_ns'):
            p[k] = round(p[k], 2)
        nets = [x['net'] for x in p['steps'] if x['net'] != '(logic)']
        p['start'], p['end'] = (nets[0], nets[-1]) if nets else ('', '')     # the first and the last signal
        p['steps'] = [x for x in p['steps'] if x['src'] or not x['net'].startswith('(')][:keep]
        out.append(p)
    return out


def write_build_info(proj, bit, board_id, report=None):
    import hashlib
    p = os.path.join(proj, BUILD_INFO)
    try:
        info = json.load(open(p))
    except (OSError, ValueError):
        info = {}
    info[os.path.basename(bit)] = {'board': board_id, 'sha256': hashlib.sha256(open(bit, 'rb').read()).hexdigest(),
                                   'date': time.strftime('%Y-%m-%d %H:%M')}
    if report:
        info[os.path.basename(bit)]['report'] = report
    json.dump(info, open(p, 'w'), indent=1)


def bit_board(proj, bit):
    """The board a bitstream was built for: from the project's build record, else the project's fpga.json,
    else the S9 (every design made before Ardzy knew other boards, Vivado builds, the ready projects)."""
    import hashlib
    try:
        rec = json.load(open(os.path.join(proj, BUILD_INFO))).get(os.path.basename(bit))
        if rec and rec.get('sha256') == hashlib.sha256(open(bit, 'rb').read()).hexdigest():
            return rec['board']
    except (OSError, ValueError):
        pass
    try:
        return json.load(open(os.path.join(proj, 'fpga.json'))).get('board') or 's9'
    except (OSError, ValueError):
        return 's9'


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


def build_report(proj):
    """The report of the project's newest build (None if it was not built here)."""
    try:
        info = json.load(open(os.path.join(proj, BUILD_INFO)))
    except (OSError, ValueError):
        return None
    reps = [dict(v['report'], bit=k) for k, v in info.items() if isinstance(v, dict) and v.get('report')]
    return max(reps, key=lambda r: r.get('date', '')) if reps else None


def project_board(proj):
    """The board named in the project's fpga.json ({"board": "ebaz4205"}), or None."""
    try:
        return json.load(open(os.path.join(proj, 'fpga.json'))).get('board')
    except (OSError, ValueError):
        return None
