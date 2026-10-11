"""The schematic of a design (like Vivado's RTL schematic): Yosys reads the Verilog, keeps the hierarchy (no flatten)
and turns always blocks into registers, multiplexers and operators; the app (ui/schematic.js) draws each module.

netlist(proj) -> {top, modules: {name: {ports, cells, src, own}}}: every module the top uses. Your modules come with
their insides; library modules (fpga/hdl) and FPGA primitives only as boxes with their ports.
"""
import json, os, re, shutil, tempfile

from . import flow

MAX_CELLS = 600          # more than this in one module: only the instances of other modules are kept


def _src(attrs):
    """'top.v:12.5-14.9' (or several joined by |) -> 'top.v:12'."""
    s = (attrs or {}).get('src', '')
    m = re.match(r'([^|:]+?):(\d+)', s)
    return '%s:%s' % (os.path.basename(m.group(1)), m.group(2)) if m else ''


def netlist(proj, log=None):
    cfg = {}
    if os.path.isfile(os.path.join(proj, 'fpga.json')):
        cfg = json.load(open(os.path.join(proj, 'fpga.json')))
    srcs = flow.project_sources(proj)
    if not srcs:
        raise ValueError('no Verilog files (*.v) in the project')
    lib = flow.library_files()
    top = flow.find_top(srcs + lib, cfg.get('top'), own=srcs)
    tdir = flow.tools_dir()
    if not tdir:
        raise RuntimeError('the built-in FPGA toolchain is missing (tools/fpga)')
    name = os.path.basename(os.path.normpath(proj))
    work = os.path.join(tempfile.gettempdir(), 'ardzy_schematic', re.sub(r'[^\w.-]', '_', name))
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    files = []
    for f in srcs + lib:
        shutil.copy(f, os.path.join(work, os.path.basename(f)))
        files.append(os.path.basename(f))
    own_files = {os.path.basename(f) for f in srcs}
    reads = '; '.join('read_verilog %s"%s"' % ('-sv ' if f.endswith('.sv') else '', f) for f in files)
    out = []
    try:
        flow._run([os.path.join(tdir, 'bin', 'yosys.exe'), '-q', '-p',
                   '%s; hierarchy -top %s; proc; opt_clean; write_json schematic.json' % (reads, top)],
                  work, (lambda s, k=None: out.append(s)), '', keep=lambda l: l.startswith('ERROR'))
    except RuntimeError:
        raise ValueError('Yosys could not read the design: ' + ' '.join(l.strip() for l in out[-4:]))
    data = json.load(open(os.path.join(work, 'schematic.json')))['modules']
    mods = {}
    for mname, m in data.items():
        if m.get('attributes', {}).get('blackbox'):
            continue
        src = _src(m.get('attributes'))
        own = src.split(':')[0] in own_files
        clean = mname.split('\\')[-1] if mname.startswith('$paramod') else mname
        ports = [{'name': p, 'dir': v['direction'], 'bits': v['bits']} for p, v in m.get('ports', {}).items()]
        entry = {'name': clean, 'ports': ports, 'src': src, 'own': own, 'cells': [], 'nets': {}}
        if own:
            cells = m.get('cells', {})
            big = len(cells) > MAX_CELLS
            for cname, c in cells.items():
                t = c['type']
                if big and t.startswith('$'):
                    continue
                conns = {p: {'dir': c.get('port_directions', {}).get(p, 'input'), 'bits': b}
                         for p, b in c.get('connections', {}).items()}
                entry['cells'].append({'name': cname if not cname.startswith('$') else '', 'type': t,
                                       'width': _width(c), 'src': _src(c.get('attributes')), 'conns': conns})
            entry['cut'] = big
            # a name for every bit: the shortest name the Verilog gave it
            for nn, n in m.get('netnames', {}).items():
                if n.get('hide_name'):
                    continue
                for i, b in enumerate(n['bits']):
                    if isinstance(b, int):
                        cur = entry['nets'].get(b)
                        label = nn if len(n['bits']) == 1 else '%s[%d]' % (nn, i + n.get('offset', 0))
                        if cur is None or len(label) < len(cur):
                            entry['nets'][b] = label
        mods[mname] = entry
    return {'top': top, 'modules': mods}


def _width(c):
    p = c.get('parameters', {})
    for k in ('Y_WIDTH', 'WIDTH', 'A_WIDTH'):
        if k in p:
            try:
                return int(p[k], 2)
            except (TypeError, ValueError):
                return 0
    return 0
