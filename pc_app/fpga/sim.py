"""Verilog simulation on the PC with Icarus Verilog (bundled in tools/icarus): the app's Simulate button.

A project is simulated with a testbench (a file named *_tb.v, tb_*.v or tb.v): a module without ports that
makes the inputs, instantiates the design and ends with $finish. The parts the real chip gives (the ARM side
ardzy_soc / ardzy_bus, Xilinx primitives) are replaced by the models in fpga/simlib/ardzy_sim.v; the rest of the
Ardzy library (fpga/hdl) is used as it is. The waves (VCD) are turned into a compact form for the app's viewer.

Icarus can not work in folders with spaces, so it runs from a copy in %LOCALAPPDATA%\\Ardzy\\icarus and each
simulation in its own work folder there (file names stay the same, so error lines point at your files).
"""
import ctypes, glob, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = getattr(sys, '_MEIPASS', os.path.dirname(HERE))
SRC_ICARUS = os.path.join(BASE, 'tools', 'icarus')
HDL = os.path.join(HERE, 'hdl')
MODELS = os.path.join(HERE, 'simlib', 'ardzy_sim.v')
TB_RE = re.compile(r'(^tb[_.]|_tb\.|^tb\.|^testbench)', re.I)
SRC_EXT = ('.v', '.sv', '.vh', '.svh')
DATA_EXT = ('.mem', '.hex', '.bin', '.txt', '.coe', '.dat')
MAX_CHANGES = 1500000


def _short(p):
    """Windows 8.3 short path (no spaces) when there is one."""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(p, buf, 1024):
            return buf.value
    except Exception:
        pass
    return p


def home():
    root = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'Ardzy')
    os.makedirs(root, exist_ok=True)
    if ' ' in root:
        root = _short(root)
    return root


def icarus():
    """The Icarus folder to run from (copied once from the app; again when the app has a newer one)."""
    if not os.path.isfile(os.path.join(SRC_ICARUS, 'bin', 'iverilog.exe')):
        raise RuntimeError('Icarus Verilog is missing in the app (tools/icarus)')
    if ' ' not in SRC_ICARUS:
        return SRC_ICARUS
    dst = os.path.join(home(), 'icarus')
    stamp = str(os.path.getsize(os.path.join(SRC_ICARUS, 'bin', 'vvp.exe'))) + ':' + \
        str(int(os.path.getmtime(os.path.join(SRC_ICARUS, 'bin', 'vvp.exe'))))
    mark = os.path.join(dst, 'ardzy_copy.txt')
    if not (os.path.exists(mark) and open(mark).read() == stamp):
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(SRC_ICARUS, dst)
        open(mark, 'w').write(stamp)
    return dst


def modules_in(text):
    return re.findall(r'^\s*module\s+(\w+)', text, re.M)


def testbenches(pdir):
    out = []
    for f in sorted(os.listdir(pdir)) + ['sim/' + x for x in (sorted(os.listdir(os.path.join(pdir, 'sim'))) if os.path.isdir(os.path.join(pdir, 'sim')) else [])]:
        if f.lower().endswith(('.v', '.sv')) and TB_RE.search(os.path.basename(f)):
            out.append(f)
    return out


def design_files(pdir):
    return [f for f in sorted(os.listdir(pdir)) if f.lower().endswith(('.v', '.sv')) and not TB_RE.search(f)]


def info(pdir):
    tbs = testbenches(pdir)
    return {'testbenches': tbs, 'design': design_files(pdir), 'top': find_top(pdir)}


def find_top(pdir):
    """The design's top module: 'top' if there is one, else the module no other module instantiates."""
    mods, text = [], ''
    for f in design_files(pdir):
        t = open(os.path.join(pdir, f), encoding='utf-8', errors='replace').read()
        mods += modules_in(t)
        text += t
    if 'top' in mods:
        return 'top'
    used = set(re.findall(r'^\s*(\w+)\s*(?:#\s*\(.*?\))?\s+\w+\s*\(', text, re.M | re.S))
    roots = [m for m in mods if m not in used]
    return roots[0] if roots else (mods[0] if mods else None)


def _ports(text, mod):
    """Ports of a module (ANSI style): [(direction, width text, name)]."""
    m = re.search(r'module\s+%s\b\s*(?:#\s*\((?:[^()]|\([^()]*\))*\)\s*)?\((.*?)\);' % re.escape(mod), text, re.S)
    if not m:
        return []
    body = re.sub(r'//[^\n]*', '', m.group(1))
    ports, last = [], ('input', '')
    for part in body.split(','):
        part = part.strip()
        d = re.match(r'(input|output|inout)\s+(?:wire|reg|logic)?\s*(signed\s+)?(\[[^\]]+\])?\s*(\w+)', part)
        if d:
            last = (d.group(1), d.group(3) or '')
            ports.append((d.group(1), d.group(3) or '', d.group(4)))
        elif re.match(r'^\w+$', part):
            ports.append((last[0], last[1], part))
    return ports


def new_testbench(pdir, run_ns=10000, wiggle=False):
    """A testbench for the top module. wiggle: the inputs change by themselves (for designs made with blocks)."""
    top = find_top(pdir)
    if not top:
        raise ValueError('no Verilog module in this project yet')
    text = ''.join(open(os.path.join(pdir, f), encoding='utf-8', errors='replace').read() for f in design_files(pdir))
    ports = _ports(text, top)
    soc = re.search(r'ardzy_soc\s*(?:#\s*\(.*?\))?\s*(\w+)\s*\(', text, re.S)
    bus = re.search(r'ardzy_bus\s+(\w+)\s*\(', text)
    name = top + '_tb'
    fn = name + '.v'
    if os.path.exists(os.path.join(pdir, fn)):
        raise ValueError(fn + ' already exists')
    decl, conn, stim = [], [], []
    clk_in = [p for p in ports if p[0] == 'input' and re.match(r'(clk|clock)', p[2], re.I)]
    for d, w, n in ports:
        if d == 'input':
            decl.append('    reg  %s%s = %d;' % (w + ' ' if w else '', n, 1 if wiggle else 0))
        else:
            decl.append('    wire %s%s;' % (w + ' ' if w else '', n))
        conn.append('.%s(%s)' % (n, n))
    if clk_in:
        stim.append('    always #5 %s = ~%s;                  // 100 MHz clock' % (clk_in[0][2], clk_in[0][2]))
    if wiggle:
        k = 0
        for d, w, n in ports:
            if d == 'input' and not (clk_in and n == clk_in[0][2]):
                stim.append('    always #%d %s = ~%s;      // changes by itself every %d us (like a button or a signal): change or remove' % (20000 + 6000 * k, n, n, 20 + 6 * k))
                k += 1
    lines = ['`timescale 1ns / 1ps', '// Testbench for %s: press Simulate (Code view, Simulation tab) and look at the waves.' % top,
             '// A testbench is not built into the FPGA; it only makes the inputs and checks the outputs.', '',
             'module %s;' % name] + decl + ([''] if decl else []) + \
            ['    %s dut (%s);' % (top, ', '.join(conn))] + ([''] + stim if stim else []) + ['', '    reg [31:0] value;', '',
             '    initial begin']
    if soc:
        lines += ['        // the ARM side (the simulation model of ardzy_soc): ctrl[n] = value, value = status[n]',
                  '        #200;                                     // after the reset (100 ns)',
                  '        dut.%s.write_ctrl(0, 32\'d1);' % soc.group(1),
                  '        #1000;',
                  '        dut.%s.read_status(0, value);' % soc.group(1),
                  '        $display("status[0] = %d", value);']
    elif bus:
        lines += ['        // the ARM side (the simulation model of ardzy_bus): address = slot * 16\'h1000 + 4 * register',
                  '        #200;',
                  '        dut.%s.write(16\'h1000, 32\'d1);' % bus.group(1),
                  '        dut.%s.read(16\'h1000, value);' % bus.group(1),
                  '        $display("slot 1 register 0 = %h", value);']
    else:
        lines += ['        // set the inputs here, wait, and check the outputs:',
                  '        #100;']
        for d, w, n in ports:
            if d == 'input' and not (clk_in and n == clk_in[0][2]) and not wiggle:
                lines.append('        %s = 1;' % n)
        lines += ['        #1000;']
    lines += ['        #%d;                                   // let the design run %s more (change it as you need)' % (run_ns, fmt_ns(run_ns)),
              '        $display("done at %0d ns", $time);', '        $finish;', '    end', 'endmodule', '']
    open(os.path.join(pdir, fn), 'w', encoding='utf-8', newline='\n').write('\n'.join(lines))
    return fn


def _library(work):
    """The Ardzy library for simulation: every block, minus the ones the models replace."""
    replaced = set(modules_in(open(MODELS, encoding='utf-8').read()))
    out = []
    for f in sorted(glob.glob(os.path.join(HDL, '*.v'))):
        t = open(f, encoding='utf-8', errors='replace').read()
        for m in replaced:
            t = re.sub(r'^\s*module\s+%s\b.*?^\s*endmodule\b' % m, '', t, flags=re.S | re.M)
        out.append('// ---- %s\n%s\n' % (os.path.basename(f), t))
    open(os.path.join(work, 'ardzy_lib.v'), 'w', encoding='utf-8').write('\n'.join(out))
    shutil.copy(MODELS, os.path.join(work, 'ardzy_sim.v'))


def run(pdir, tb, limit_ns=100000, log=print, timeout=120):
    ic = icarus()
    work = os.path.join(home(), 'sim', re.sub(r'\W', '_', os.path.basename(pdir)))
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    tb_path = os.path.join(pdir, tb)
    if not os.path.isfile(tb_path):
        raise ValueError('testbench %s not found' % tb)
    tb_text = open(tb_path, encoding='utf-8', errors='replace').read()
    tb_mods = modules_in(tb_text)
    if not tb_mods:
        raise ValueError('%s has no module' % tb)
    root = tb_mods[0]
    # the files, copied as they are (same names, so the error lines point at the project's files)
    srcs = []
    for f in design_files(pdir) + [tb]:
        shutil.copy(os.path.join(pdir, f), os.path.join(work, os.path.basename(f)))
        srcs.append(os.path.basename(f))
    for d in (pdir, os.path.join(pdir, 'sim')):
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.lower().endswith(DATA_EXT + ('.vh', '.svh')) and os.path.isfile(os.path.join(d, f)):
                    shutil.copy(os.path.join(d, f), work)
    _library(work)
    own_dump = '$dumpvars' in tb_text
    dumpfile = (re.search(r'\$dumpfile\s*\(\s*"([^"]+)"', tb_text) or [None, 'waves.vcd'])[1] if own_dump else 'waves.vcd'
    open(os.path.join(work, 'ardzy_ts.v'), 'w').write('`timescale 1ns / 1ps\n')
    open(os.path.join(work, 'ardzy_sim_ctl.v'), 'w').write(
        '`timescale 1ns / 1ps\nmodule ardzy_sim_ctl;\n  initial begin\n' +
        ('' if own_dump else '    $dumpfile("waves.vcd");\n    $dumpvars(0, %s);\n' % root) +
        '    #(%d);\n    $display("ARDZY_SIM: the time limit (%d ns) was reached: the testbench did not call $finish before");\n'
        '    $finish;\n  end\nendmodule\n' % (int(limit_ns), int(limit_ns)))
    env = dict(os.environ, PATH=os.path.join(ic, 'bin') + os.pathsep + os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'system32'))
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    t0 = time.time()
    cmd = [os.path.join(ic, 'bin', 'iverilog.exe'), '-B', os.path.join(ic, 'lib', 'ivl'), '-g2012', '-DARDZY_SIM', '-Wimplicit',
           '-o', 'sim.vvp', '-s', root, '-s', 'ardzy_sim_ctl', '-l', 'ardzy_lib.v',
           'ardzy_ts.v', 'ardzy_sim.v'] + srcs + ['ardzy_sim_ctl.v']
    r = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, errors='replace', creationflags=flags)
    msgs = (r.stdout + r.stderr).strip()
    for line in msgs.splitlines():
        log('  ' + line, 'err' if 'error' in line.lower() else 'warn' if 'warning' in line.lower() else 'out')
    if r.returncode:
        return {'ok': False, 'stage': 'compile'}
    log('  compiled in %.1f s; running (up to %s) ...' % (time.time() - t0, fmt_ns(limit_ns)))
    t1 = time.time()
    p = subprocess.Popen([os.path.join(ic, 'bin', 'vvp.exe'), '-M', os.path.join(ic, 'lib', 'ivl'), '-n', 'sim.vvp'], cwd=work, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace', creationflags=flags)
    n = 0
    killed = False
    try:
        for line in p.stdout:
            line = line.rstrip()
            if line.startswith('VCD info:'):
                continue
            n += 1
            if n <= 2000:
                log('  ' + line, 'warn' if line.startswith('ARDZY_SIM') else 'err' if re.search(r'\berror\b|fail', line, re.I) else 'out')
            elif n == 2001:
                log('  (more output: only the first 2000 lines are shown)', 'warn')
            if time.time() - t1 > timeout:
                p.kill(); killed = True
                log('  stopped after %d s (the simulation took too long: set a shorter time)' % timeout, 'warn')
                break
    finally:
        p.wait()
    vcd = os.path.join(work, dumpfile)
    return {'ok': not killed or os.path.exists(vcd), 'vcd': vcd if os.path.exists(vcd) else None, 'seconds': round(time.time() - t1, 1),
            'root': root}


def fmt_ns(ns):
    return '%g ns' % ns if ns < 1000 else '%g us' % (ns / 1000) if ns < 1e6 else '%g ms' % (ns / 1e6)


def parse_vcd(path, max_changes=MAX_CHANGES):
    """VCD -> {timescale_ns, end, signals:[{name, scope, short, width, id}], waves:{id: [t, v, t, v, ...]}}.
    Times stay in the file's unit (timescale_ns says how many ns one unit is); values are '0' '1' 'x' 'z' or a
    binary string for vectors, a number string for reals."""
    sigs, waves, scope, kinds, ts = [], {}, [], [], 1.0
    t, n, cut = 0, 0, None
    units = {'s': 1e9, 'ms': 1e6, 'us': 1e3, 'ns': 1.0, 'ps': 1e-3, 'fs': 1e-6}
    with open(path, encoding='utf-8', errors='replace') as f:
        header = True
        buf = ''
        for line in f:
            if header:
                buf += line
                if '$enddefinitions' in line:
                    header = False
                    toks = buf.split()
                    i = 0
                    while i < len(toks):
                        k = toks[i]
                        if k == '$timescale':
                            j = i + 1
                            spec = ''
                            while toks[j] != '$end':
                                spec += toks[j]; j += 1
                            m = re.match(r'(\d+)\s*(\w+)', spec)
                            if m:
                                ts = int(m.group(1)) * units.get(m.group(2), 1.0)
                            i = j
                        elif k == '$scope':
                            scope.append(toks[i + 2]); kinds.append(toks[i + 1]); i += 3
                        elif k == '$upscope':
                            scope.pop(); kinds.pop(); i += 1
                        elif k == '$var':
                            j = i + 1
                            parts = []
                            while toks[j] != '$end':
                                parts.append(toks[j]); j += 1
                            kind, width, ident, name = parts[0], int(parts[1]), parts[2], parts[3]
                            rng = parts[4] if len(parts) > 4 else ''
                            sigs.append({'name': '.'.join(scope + [name]) + rng, 'scope': '.'.join(scope), 'short': name + rng,
                                         'width': width, 'id': ident, 'kind': kind,
                                         # parameters and the variables inside tasks / functions / named blocks: hidden at first
                                         'minor': kind == 'parameter' or any(x != 'module' for x in kinds)})
                            waves.setdefault(ident, [])
                            i = j
                        i += 1
                continue
            line = line.strip()
            if not line or line.startswith('$'):
                continue
            c = line[0]
            if c == '#':
                t = int(line[1:])
                if n > max_changes:
                    cut = t
                    break
                continue
            if c in '01xzXZ':
                ident, v = line[1:], c.lower()
            elif c in 'bB':
                v, ident = line[1:].split()
                v = v.lower()
            elif c in 'rR':
                v, ident = line[1:].split()
            else:
                continue
            w = waves.get(ident)
            if w is None:
                continue
            if len(w) >= 2 and w[-1] == v:
                continue
            if len(w) >= 2 and w[-2] == t:
                w[-1] = v
            else:
                w.append(t); w.append(v)
            n += 1
    return {'timescale_ns': ts, 'end': cut if cut is not None else t, 'cut': cut is not None, 'changes': n,
            'signals': sigs, 'waves': waves}
