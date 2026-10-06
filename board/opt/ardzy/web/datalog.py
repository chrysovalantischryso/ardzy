"""Ardzy data logger: records the board's sensors, the pins and the values your program prints, to the SD card,
for hours, without the PC. Runs as its own service (ardzy-logger, started by the board's web service) so it keeps
going when the app is closed or the web service restarts.

    datalog.py run <config.json>     the logger itself (the web service starts it with systemd-run)

Each log is /var/lib/ardzy/logs/<name>.jsonl: one JSON object per sample {"t": unix time, "temp_c": 54.1, ...}.
The web service turns it into CSV (one column per value) for the app.
Values from the program: every "name:number" or name="text" in a line of its output (the same lines the app's
Plotter and Watch understand; Ardzy.watch() / ardzy.watch() print them).
"""
import json, os, re, shutil, subprocess, sys, threading, time

LOG_DIR = '/var/lib/ardzy/logs'
STATUS = '/run/ardzy-logger.json'
UNIT = 'ardzy-logger'
MIN_FREE_MB = 300                 # stops before the card gets full
NUM = re.compile(r'(?:^|[\s,;])([A-Za-z_][\w.\[\]-]*)[:=](-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(?![\w.])')
TXT = re.compile(r'([A-Za-z_][\w.-]*)="([^"]*)"')
SYSTEM_LINE = re.compile(r'^(===|Started |Stopped |Stopping |ardzy-app)')


def safe_name(n):
    n = re.sub(r'[^A-Za-z0-9_.-]', '_', n or '')[:60].strip('._')
    return n or time.strftime('log_%Y%m%d_%H%M%S')


def logs():
    os.makedirs(LOG_DIR, exist_ok=True)
    out = []
    for f in sorted(os.listdir(LOG_DIR)):
        if not f.endswith('.jsonl'):
            continue
        p = os.path.join(LOG_DIR, f)
        st = os.stat(p)
        first = last = None
        n = 0
        with open(p, 'rb') as fh:
            for line in fh:
                n += 1
                if first is None:
                    first = line
                last = line
        t0 = json.loads(first)['t'] if first else None
        t1 = json.loads(last)['t'] if last else None
        out.append({'name': f[:-6], 'size_kb': round(st.st_size / 1024, 1), 'rows': n, 'start': t0, 'end': t1,
                    'modified': st.st_mtime})
    return out


def status():
    try:
        s = json.load(open(STATUS))
    except (OSError, ValueError):
        s = {}
    active = subprocess.run(['systemctl', 'is-active', UNIT], capture_output=True, text=True).stdout.strip() == 'active'
    s['running'] = active
    du = shutil.disk_usage('/var/lib')
    s['free_mb'] = du.free // 1048576
    return s


def to_csv(name):
    p = os.path.join(LOG_DIR, safe_name(name) + '.jsonl')
    rows, cols = [], []
    with open(p, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            rows.append(r)
            for k in r:
                if k != 't' and k not in cols:
                    cols.append(k)
    esc = lambda v: '"' + str(v).replace('"', '""') + '"' if isinstance(v, str) and re.search(r'[",\n]', v) else str(v)
    lines = ['time,seconds,' + ','.join(cols)]
    t0 = rows[0]['t'] if rows else 0
    for r in rows:
        lines.append(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(r['t'])) + ',%.1f,' % (r['t'] - t0) +
                     ','.join(esc(r[k]) if k in r else '' for k in cols))
    return '\n'.join(lines) + '\n'


def start(name, interval, channels, hours):
    if status().get('running'):
        raise ValueError('the logger is already recording: stop it first')
    interval = max(0.2, min(3600.0, float(interval or 1)))
    channels = [c for c in (channels or 'sensors').split(',') if c in ('sensors', 'pins', 'program')] or ['sensors']
    name = safe_name(name)
    os.makedirs(LOG_DIR, exist_ok=True)
    cfg = {'name': name, 'interval': interval, 'channels': channels, 'hours': float(hours or 0),
           'file': os.path.join(LOG_DIR, name + '.jsonl')}
    path = '/run/ardzy-logger-config.json'
    json.dump(cfg, open(path, 'w'))
    subprocess.run(['systemctl', 'reset-failed', UNIT], capture_output=True)
    r = subprocess.run(['systemd-run', '--unit=' + UNIT, '--collect', '--description=Ardzy data logger',
                        sys.executable, os.path.abspath(__file__), 'run', path], capture_output=True, text=True)
    if r.returncode:
        raise ValueError('could not start the logger: ' + (r.stderr or r.stdout).strip())
    return cfg


def stop():
    subprocess.run(['systemctl', 'stop', UNIT], capture_output=True)
    return status()


def delete(name):
    if status().get('running') and status().get('name') == safe_name(name):
        raise ValueError('stop the logger first')
    p = os.path.join(LOG_DIR, safe_name(name) + '.jsonl')
    if os.path.exists(p):
        os.remove(p)
    return {'deleted': safe_name(name)}


# ------------------------------------------------------------------ the logger process
class Program:
    """Follows the program's output and keeps the newest value of each name."""

    def __init__(self):
        self.values, self.lock = {}, threading.Lock()
        threading.Thread(target=self.follow, daemon=True).start()

    def follow(self):
        p = subprocess.Popen(['journalctl', '-u', 'ardzy-app', '-f', '-n', '0', '-o', 'cat'], stdout=subprocess.PIPE,
                             text=True, errors='replace')
        for line in p.stdout:
            if SYSTEM_LINE.match(line):
                continue
            found = {m.group(1): float(m.group(2)) for m in NUM.finditer(line)}
            found.update({m.group(1): m.group(2) for m in TXT.finditer(line)})
            if found:
                with self.lock:
                    self.values.update(found)

    def take(self):
        with self.lock:
            return {'prog.' + k: v for k, v in self.values.items()}


def run(cfg_path):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import hwapi
    cfg = json.load(open(cfg_path))
    prog = Program() if 'program' in cfg['channels'] else None
    t_start, n = time.time(), 0
    end = t_start + cfg['hours'] * 3600 if cfg['hours'] else None
    why = 'stopped'
    with open(cfg['file'], 'a', buffering=1) as out:
        nxt = time.time()
        while True:
            row = {'t': round(time.time(), 2)}
            if 'sensors' in cfg['channels']:
                s = hwapi.sensors()
                for k in ('temp_c', 'vccint', 'vccaux', 'vccbram', 'vccpint', 'vccpaux', 'vccoddr'):
                    if k in s:
                        row[k] = s[k]
                if s.get('cpu_pct') is not None:
                    row['cpu_pct'] = s['cpu_pct']
                row['mem_used_mb'] = s['mem']['used_mb']
            if 'pins' in cfg['channels'] and hwapi.io_ready():
                try:
                    io = hwapi.io_read()
                    for p in io['pins']:
                        m = re.match(r'(j\d|leds)\[(\d)\]$', p['name'])
                        if m:                                  # j3[1] -> J3_11, leds[2] -> LED2 (the Arduino names)
                            nm = 'LED' + m.group(2) if m.group(1) == 'leds' else \
                                'J%s_%d' % (m.group(1)[1], (5, 11, 12, 15)[int(m.group(2))])
                            row[nm] = 1 - p['level'] if nm.startswith('LED') else p['level']   # LEDs: 1 = lit
                    for i, rpm in enumerate(io['fan']['rpm']):
                        row['fan%d_rpm' % (i + 1)] = rpm
                except Exception:
                    pass
            if prog:
                row.update(prog.take())
            out.write(json.dumps(row) + '\n')
            n += 1
            json.dump(dict(cfg, started=t_start, samples=n, last=row['t'],
                           size_kb=round(os.path.getsize(cfg['file']) / 1024, 1)), open(STATUS, 'w'))
            if end and time.time() >= end:
                why = 'time is up'
                break
            if shutil.disk_usage(os.path.dirname(cfg['file'])).free // 1048576 < MIN_FREE_MB:
                why = 'the SD card is almost full'
                break
            nxt += cfg['interval']
            time.sleep(max(0.0, nxt - time.time()))
    json.dump(dict(cfg, started=t_start, samples=n, ended=time.time(), why=why), open(STATUS, 'w'))


if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == 'run':
    run(sys.argv[2])
