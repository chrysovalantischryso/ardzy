"""I/O planning (like Vivado's I/O Planning view): the top module's ports, the board's pins, and which pin each
port is on. The app shows them as a table; Save writes the choices into io_plan.xdc and turns the older
lines for the same ports (in the project's other .xdc files) into comments, so there is one place per pin.
"""
import json, os, re, time

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN_FILE = 'io_plan.xdc'
XDC_PORT = re.compile(r'get_ports\s+(?:\{\s*([^}]+?)\s*\}|([^\s\]]+))\s*\]')   # {leds[0]} or leds
PIN_RE = re.compile(r'^[A-Z]{1,2}\d{1,2}$')
STANDARDS = ('LVCMOS33', 'LVCMOS25', 'LVCMOS18', 'LVTTL')


def _expand(ports):
    """[(dir, '[3:0]', 'leds')] -> [{'port': 'leds[0]', 'dir': 'output', 'group': 'leds'}, ...]"""
    out = []
    for d, w, n in ports:
        m = re.match(r'\[\s*(\d+)\s*:\s*(\d+)\s*\]', w or '')
        if m:
            hi, lo = int(m.group(1)), int(m.group(2))
            for i in (range(lo, hi + 1) if lo <= hi else range(lo, hi - 1, -1)):
                out.append({'port': '%s[%d]' % (n, i), 'dir': d, 'group': n})
        else:
            out.append({'port': n, 'dir': d, 'group': n})
    return out


def top_ports(proj):
    import flow, sim
    srcs = flow.project_sources(proj)
    if not srcs:
        raise ValueError('no Verilog (.v) files in this project')
    cfg = {}
    if os.path.isfile(os.path.join(proj, 'fpga.json')):
        cfg = json.load(open(os.path.join(proj, 'fpga.json')))
    top = flow.find_top(srcs + flow.library_files(), cfg.get('top'), own=srcs)
    text = ''.join(open(f, encoding='utf-8', errors='replace').read() for f in srcs)
    ports = sim._ports(text, top)
    if not ports:
        raise ValueError('the ports of the top module %s could not be read (write them in the module line: '
                         'module %s (input wire clk, output wire [3:0] leds);)' % (top, top))
    return top, _expand(ports)


def assignments(proj):
    """{port: {'pin', 'iostd', 'file'}} from the project's .xdc files (lines that are not comments)."""
    out = {}
    for f in sorted(os.listdir(proj)):
        if not f.endswith('.xdc'):
            continue
        for line in open(os.path.join(proj, f), encoding='utf-8', errors='replace'):
            line = line.split('#')[0]
            pin = re.search(r'PACKAGE_PIN\s+(\w+)', line)
            port = XDC_PORT.search(line)
            std = re.search(r'IOSTANDARD\s+(\w+)', line)
            if pin and port:
                out[port.group(1) or port.group(2)] = {'pin': pin.group(1).upper(), 'iostd': std.group(1) if std else 'LVCMOS33', 'file': f}
    return out


def board_pins(profile, ui_dir):
    """The pins a design may use on this board: [{'pin', 'name', 'group', 'note', 'reserved'}]."""
    pins = []
    if profile['id'] == 's9':
        d = json.load(open(os.path.join(ui_dir, 'pins.json'), encoding='utf-8'))
        for c in d['connectors']:
            pins.append({'pin': c['pin'], 'name': c['port'], 'group': c['conn'],
                         'note': 'pin %s, Bitmain %s' % (c['cpin'], c['bitmain'])})
        for c in d['pl_other']:
            pins.append({'pin': c['pin'], 'name': c['port'], 'group': c['what'], 'note': c['notes']})
    else:
        for h, ps in (profile.get('headers') or {}).items():
            if isinstance(ps, dict):
                for n, pin in ps.items():
                    pins.append({'pin': pin, 'name': '%s_%s' % (h.lower(), n), 'group': h, 'note': '%s pin %s' % (h, n)})
        for n, l in (profile.get('leds') or {}).items():
            if l.get('pin'):
                pins.append({'pin': l['pin'], 'name': 'led_%s_n' % n, 'group': 'LED',
                             'note': 'LED %s, on when 0' % n if l.get('active_low') else 'LED %s' % n})
        for n, f in (profile.get('fans') or {}).items():
            pins.append({'pin': f['pwm'], 'name': '%s_pwm' % n.lower(), 'group': 'Fan', 'note': n + ' PWM out'})
            pins.append({'pin': f['tach'], 'name': '%s_tach' % n.lower(), 'group': 'Fan', 'note': n + ' speed in'})
        if (profile.get('clock_pin') or {}).get('pin'):
            pins.append({'pin': profile['clock_pin']['pin'], 'name': 'clk50', 'group': 'Clock', 'note': profile['clock_pin'].get('note', '')})
    reserved = set(((profile.get('ethernet') or {}).get('pins') or {}).values())
    for p in pins:
        p['reserved'] = p['pin'] in reserved
    return pins


def plan(proj, profile, ui_dir):
    top, ports = top_ports(proj)
    cur = assignments(proj)
    for p in ports:
        a = cur.get(p['port'])
        p.update(pin=a['pin'] if a else '', iostd=a['iostd'] if a else 'LVCMOS33', file=a['file'] if a else '')
    return {'top': top, 'ports': ports, 'pins': board_pins(profile, ui_dir), 'board': profile['id'],
            'board_name': profile['name'], 'standards': list(STANDARDS)}


def save(proj, profile, ui_dir, assign):
    """assign: {port: {'pin': 'T11', 'iostd': 'LVCMOS33'}} ('' pin = no pin). Returns (lines written, notes)."""
    top, ports = top_ports(proj)
    known = {p['port'] for p in ports}
    allowed = {p['pin']: p for p in board_pins(profile, ui_dir)}
    used, lines, problems = {}, [], []
    for port in [p['port'] for p in ports]:
        a = assign.get(port) or {}
        pin = (a.get('pin') or '').upper()
        if not pin:
            continue
        if not PIN_RE.match(pin):
            problems.append('%s: "%s" is not a pin name' % (port, pin))
            continue
        if pin in used:
            problems.append('pin %s is chosen twice (%s and %s)' % (pin, used[pin], port))
            continue
        if pin in allowed and allowed[pin]['reserved']:
            problems.append('%s: pin %s belongs to the Ethernet on the %s' % (port, pin, profile['name']))
            continue
        std = a.get('iostd') if a.get('iostd') in STANDARDS else 'LVCMOS33'
        used[pin] = port
        lines.append('set_property -dict {PACKAGE_PIN %s IOSTANDARD %s} [get_ports {%s}]%s' % (
            pin, std, port, ('   ;# ' + allowed[pin]['name']) if pin in allowed and allowed[pin]['name'] != port else ''))
    unknown = [p for p in assign if p not in known]
    if problems:
        raise ValueError('; '.join(problems))
    # the same ports in the other .xdc files: commented out (one place per pin)
    moved = []
    for f in sorted(os.listdir(proj)):
        if not f.endswith('.xdc') or f == PLAN_FILE:
            continue
        p = os.path.join(proj, f)
        text = open(p, encoding='utf-8', errors='replace').read()
        out, changed = [], False
        for line in text.splitlines():
            body = line.split('#')[0]
            m = XDC_PORT.search(body)
            if m and 'PACKAGE_PIN' in body and (m.group(1) or m.group(2)) in known:
                out.append('#[io plan] ' + line)
                changed = True
                moved.append('%s (%s)' % (m.group(1) or m.group(2), f))
            else:
                out.append(line)
        if changed:
            open(p, 'w', encoding='utf-8', newline='\n').write('\n'.join(out) + '\n')
    head = ['# Pins of %s on the %s: made by the Ardzy app (I/O planning, %s). Edit them there or here.'
            % (top, profile['name'], time.strftime('%Y-%m-%d %H:%M'))]
    open(os.path.join(proj, PLAN_FILE), 'w', encoding='utf-8', newline='\n').write('\n'.join(head + lines) + '\n')
    placed = set(used.values())
    free = [p['port'] for p in ports if p['port'] not in placed]
    return len(lines), moved, free, unknown
