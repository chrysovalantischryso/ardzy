"""The PC side of the signal analyzer (fpga/hdl/ardzy_ila.v; board side /opt/ardzy/web/ila.py).

The build records which signals the analyzer watches (report "debug": signals with their bit positions, the depth,
the clock). Here: a trigger from "signal, condition, value" -> the analyzer's mode / mask / value, and a capture
from the board -> the Simulation viewer's waves (same shape as sim.parse_vcd) + a .vcd file (GTKWave reads it too).
"""
import os, time

MODES = {'now': 0, 'eq': 1, 'becomes': 2, 'changes': 3}


def parse_value(text, width):
    """'12', '0x1f', 'b1010', '1010b' or 'h1f' -> an int that fits the signal, else ValueError."""
    t = str(text).strip().lower().replace('_', '')
    if not t:
        raise ValueError('give the value to wait for')
    try:
        if t.startswith(('0x', 'h')):
            v = int(t.split('x', 1)[-1] if t.startswith('0x') else t[1:], 16)
        elif t.startswith(('0b', 'b')):
            v = int(t[2:] if t.startswith('0b') else t[1:], 2)
        elif t.endswith('h'):
            v = int(t[:-1], 16)
        elif t.endswith('b') and set(t[:-1]) <= {'0', '1'}:
            v = int(t[:-1], 2)
        else:
            v = int(t, 10)
    except ValueError:
        raise ValueError('"%s" is not a number (write 12, 0x1f or b1010)' % text)
    if v < 0 or v >= 1 << width:
        raise ValueError('%s does not fit in %d bit%s' % (text, width, 's' if width > 1 else ''))
    return v


def trigger(debug, signal, cond, value):
    """-> {mode, mask (hex), value (hex)} for the board."""
    mode = MODES.get(cond)
    if mode is None:
        raise ValueError('unknown trigger condition: %s' % cond)
    if mode == 0:
        return {'mode': 0, 'mask': '0', 'value': '0'}
    sig = next((s for s in debug['signals'] if s['name'] == signal), None)
    if sig is None:
        raise ValueError('the analyzer does not watch %s' % signal)
    mask = ((1 << sig['width']) - 1) << sig['lsb']
    v = 0 if mode == 3 else parse_value(value, sig['width']) << sig['lsb']
    return {'mode': mode, 'mask': '%x' % mask, 'value': '%x' % v}


def to_waves(debug, samples, trigger_index, project=''):
    """The samples (hex strings, oldest first) -> {timescale_ns, end, signals, waves, ...} like sim.parse_vcd."""
    mhz = debug.get('clock_mhz') or 100.0
    vals = [int(x, 16) for x in samples]
    sigs, waves = [], {}
    for i, s in enumerate(debug['signals']):
        ident = 'a%d' % i
        scope, _, short = s['name'].rpartition('.')
        rng = '[%d:0]' % (s['width'] - 1) if s['width'] > 1 else ''
        sigs.append({'name': 'analyzer.' + s['name'] + rng, 'scope': 'analyzer' + ('.' + scope if scope else ''),
                     'short': short + rng, 'width': s['width'], 'id': ident, 'kind': 'wire', 'minor': False})
        w, last, m = [], None, (1 << s['width']) - 1
        for t, v in enumerate(vals):
            x = v >> s['lsb'] & m
            if x != last:
                w += [t, format(x, '0%db' % s['width']) if s['width'] > 1 else str(x)]
                last = x
        waves[ident] = w
    return {'ok': True, 'timescale_ns': 1000.0 / mhz, 'end': max(1, len(vals) - 1), 'cut': False,
            'changes': sum(len(w) // 2 for w in waves.values()), 'signals': sigs, 'waves': waves,
            'tb': 'signal analyzer on the board', 'when': time.strftime('%H:%M:%S'), 'trigger': trigger_index,
            'clock': debug.get('clock'), 'clock_mhz': mhz}


def write_vcd(path, waves):
    """The capture as a VCD file (one time unit = one sample)."""
    ts_ps = int(round(waves['timescale_ns'] * 1000))
    lines = ['$date %s $end' % time.strftime('%Y-%m-%d %H:%M:%S'), '$version Ardzy signal analyzer $end',
             '$timescale %d ps $end' % ts_ps, '$scope module analyzer $end']
    for s in waves['signals']:
        lines.append('$var wire %d %s %s $end' % (s['width'], s['id'], s['name'][len('analyzer.'):].replace(' ', '_')))
    lines += ['$upscope $end', '$enddefinitions $end']
    events = {}
    for s in waves['signals']:
        w = waves['waves'][s['id']]
        for i in range(0, len(w), 2):
            events.setdefault(w[i], []).append(('b%s %s' % (w[i + 1], s['id'])) if s['width'] > 1 else w[i + 1] + s['id'])
    for t in sorted(events):
        lines.append('#%d' % t)
        lines += events[t]
    lines.append('#%d' % (waves['end'] + 1))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
