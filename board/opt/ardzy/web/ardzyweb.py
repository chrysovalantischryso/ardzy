#!/usr/bin/env python3
"""Ardzy board service: web page + HTTP API (used by the Ardzy PC app) + network discovery.
Pure Python standard library. HTTP on port 80 (http://ardzy.local), discovery on UDP 41414:
the PC sends "ARDZY_DISCOVER" (broadcast), every Ardzy board answers with its info as JSON."""
import http.server, json, os, re, subprocess, socketserver, sys, zipfile, io, shutil, socket, threading, struct, time
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, '/usr/lib/python3/dist-packages')
VERSION = '0.2'
STARTED = '%d-%d' % (os.getpid(), time.monotonic())   # changes when this service restarts (the app waits for it)
PROJ = '/opt/ardzy/projects'
STATE = '/var/lib/ardzy'
HERE = os.path.dirname(os.path.abspath(__file__))
NAME_RE = re.compile(r'^[A-Za-z0-9_.-]+$')
PART_RE = re.compile(r'^[A-Za-z0-9_.+-]+$')     # parts of a path inside an uploaded zip (TinyGPS++.h)
DISCOVERY_PORT = 41414
HTTP_PORT = 80


def ardzy(*args):
    r = subprocess.run(['/usr/local/bin/ardzy'] + list(args), capture_output=True, text=True)
    return {'ok': r.returncode == 0, 'out': (r.stdout + r.stderr).strip()}


def read(p):
    try:
        return open(p).read().strip()
    except OSError:
        return ''


def status():
    projects = []
    if os.path.isdir(PROJ):
        for n in sorted(os.listdir(PROJ)):
            d = os.path.join(PROJ, n)
            if os.path.isdir(d):
                files = sorted(f for f in os.listdir(d) if not f.startswith('.'))
                projects.append({'name': n, 'files': files})
    temp = ''
    for p in ('/sys/bus/iio/devices/iio:device0/in_temp0_raw',):
        raw = read(p)
        if raw:
            off = read(p.replace('_raw', '_offset')) or '0'
            sc = read(p.replace('_raw', '_scale')) or '1'
            t = (int(raw) + int(off)) * float(sc) / 1000
            temp = '%.1f C' % t if -40 < t < 150 else ''
    up = float(read('/proc/uptime').split()[0] or 0)
    mem = {l.split(':')[0]: int(l.split()[1]) for l in open('/proc/meminfo') if ':' in l}
    return {
        'current': read(STATE + '/current'), 'default': read(STATE + '/default'),
        'running': subprocess.run(['systemctl', 'is-active', '--quiet', 'ardzy-app']).returncode == 0,
        'safemode': os.path.exists(STATE + '/safemode'),
        'fpga': read('/sys/class/fpga_manager/fpga0/state'),
        'uptime': '%dh %02dm' % (up // 3600, up % 3600 // 60),
        'mem': '%d / %d MB' % ((mem['MemTotal'] - mem['MemAvailable']) // 1024, mem['MemTotal'] // 1024),
        'temp': temp, 'load': read('/proc/loadavg').split(' ')[0],
        'projects': projects,
    }


def ipv6_linklocal():
    out = []
    for line in read('/proc/net/if_inet6').splitlines():
        hexaddr, _idx, _plen, scope, _flags, ifname = line.split()
        if scope == '20' and ifname != 'lo':                     # 0x20 = link-local
            out.append(socket.inet_ntop(socket.AF_INET6, bytes.fromhex(hexaddr)) + '%' + ifname)
    return out


def info():
    """Who am I: used by discovery and by the PC app's board panel."""
    ips = subprocess.run(['hostname', '-I'], capture_output=True, text=True).stdout.split()
    return {
        'ardzy': VERSION, 'started': STARTED, 'hostname': socket.gethostname(), 'port': HTTP_PORT,
        'model': read('/proc/device-tree/model').rstrip('\0'),
        'kernel': os.uname().release, 'os': next((l.split('=', 1)[1].strip().strip('"') for l in
                                                  open('/etc/os-release') if l.startswith('PRETTY_NAME=')), ''),
        'ips': [i for i in ips if ':' not in i], 'ipv6': ipv6_linklocal(),
        'mac': read('/sys/class/net/end0/address') or
        read('/sys/class/net/eth0/address'),
        'chip': 'XC7Z010', 'fpga': read('/sys/class/fpga_manager/fpga0/state'),
        'current': read(STATE + '/current'),
        'image': dict(l.split('=', 1) for l in read('/etc/ardzy-release').splitlines() if '=' in l),
    }


def app_log(cursor=None):
    """Program output. With a cursor only the new lines since the last call are returned."""
    cmd = ['journalctl', '-u', 'ardzy-app', '-o', 'cat', '--no-pager', '--show-cursor']
    cmd += ['--after-cursor=' + cursor] if cursor else ['-n', '300']
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    lines, new_cursor = [], cursor
    for l in out.splitlines():
        if l.startswith('-- cursor: '):
            new_cursor = l[len('-- cursor: '):]
        else:
            lines.append(l)
    return lines, new_cursor


def discovery_responder(family):
    """Answers "ARDZY_DISCOVER". IPv4: broadcasts. IPv6: multicast to ff02::1 (all nodes),
    which works on any direct cable even when the PC and the board have no IPv4 in common."""
    s = socket.socket(family, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if family == socket.AF_INET6:
        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        s.bind(('::', DISCOVERY_PORT))
        for idx, _name in socket.if_nameindex():        # be sure ff02::1 reaches this socket
            try:
                s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP,
                             socket.inet_pton(socket.AF_INET6, 'ff02::1') + struct.pack('@I', idx))
            except OSError:
                pass
    else:
        s.bind(('', DISCOVERY_PORT))
    while True:
        try:
            data, addr = s.recvfrom(256)
            if data.strip() == b'ARDZY_DISCOVER':
                s.sendto(json.dumps(info()).encode(), addr)
        except Exception as e:
            print('discovery:', e, flush=True)


import hwapi, iotools, sysinfo, datalog

HW_GET = {   # GET /api/...  -> function(query) ; all read-only
    '/api/hw': lambda q: hwapi.hw(),
    '/api/sensors': lambda q: hwapi.sensors(),
    '/api/clocks': lambda q: hwapi.clocks(),
    '/api/mio': lambda q: hwapi.mio(),
    '/api/net': lambda q: hwapi.net(),
    '/api/cpufreq': lambda q: hwapi.cpufreq(),
    '/api/nand': lambda q: hwapi.nand_info(),
    '/api/nand/scan': lambda q: hwapi.nand_scan(),
    '/api/io': lambda q: iotools.io_read(),
    '/api/io/fclk0': lambda q: {'fclk0_mhz': hwapi.measure_fclk0()},
    '/api/io/pwm': lambda q: iotools.pwm_read(),
    '/api/io/meas': lambda q: iotools.meas_read(),
    '/api/io/uart': lambda q: iotools.uart_state(),
    '/api/io/signals': lambda q: {'signals': iotools.signals()},
    '/api/la': lambda q: iotools.la_status(),
    '/api/la/data': lambda q: iotools.la_data(),
    '/api/sys/procs': lambda q: sysinfo.procs(),
    '/api/sys/services': lambda q: sysinfo.services(),
    '/api/sys/journal': lambda q: sysinfo.journal(q.get('unit'), q.get('n', 200), q.get('prio'), q.get('grep')),
    '/api/sys/dmesg': lambda q: sysinfo.dmesg(),
    '/api/sys/info': lambda q: sysinfo.info(),
    '/api/regs': lambda q: {'blocks': sysinfo.regs_list()},
    '/api/regs/block': lambda q: sysinfo.regs(q.get('b', '')),
    '/api/logger': lambda q: {'status': datalog.status(), 'logs': datalog.logs()},
    '/api/logger/csv': lambda q: {'csv': datalog.to_csv(q.get('name', ''))},
}
HW_POST = {  # POST /api/...?args  -> changes something
    '/api/mio/set': lambda q: hwapi.mio_set(q.get('pin', ''), q.get('mode', '')),
    '/api/clocks/fclk': lambda q: {'fclk_mhz': hwapi.set_fclk(q.get('n', ''), q.get('mhz', ''))},
    '/api/cpufreq/set': lambda q: hwapi.set_cpufreq(q.get('governor'), q.get('khz')),
    '/api/net/speed': lambda q: hwapi.set_net_speed(q.get('mode', '')),
    '/api/io/set': lambda q: iotools.io_set(q.get('name', ''), q.get('mode', '')),
    '/api/io/func': lambda q: iotools.set_func(q.get('name', ''), q.get('func', '')),
    '/api/io/pwm/set': lambda q: iotools.pwm_set(q.get('ch', ''), q.get('hz'), q.get('duty'), q.get('pulse_us'),
                                                 q.get('pin'), q.get('release') == '1'),
    '/api/io/meas/set': lambda q: iotools.meas_set(q.get('ch'), q.get('signal'), q.get('gate_s')),
    '/api/io/uart/config': lambda q: iotools.uart_config(q.get('baud', 115200), q.get('tx'), q.get('rx'),
                                                         q.get('enable', '1') == '1'),
    '/api/io/uart/send': lambda q: {'sent': iotools.uart_send(bytes.fromhex(q['hex']) if 'hex' in q
                                                              else q.get('text', '').encode())},
    '/api/io/uart/read': lambda q: iotools.uart_recv(),
    '/api/la/start': lambda q: iotools.la_start(q.get('rate', 1e6), q.get('pre', 10), q.get('trig', ''), q.get('edge')),
    '/api/la/ctrl': lambda q: iotools.la_ctrl(q.get('action', '')),
    '/api/i2c/lines': lambda q: iotools.i2c_lines(q.get('bus', 1)),
    '/api/i2c/scan': lambda q: iotools.i2c_scan(q.get('bus', 1)),
    '/api/i2c/read': lambda q: iotools.i2c_read(q.get('bus', 1), q.get('addr', ''), q.get('reg'), q.get('n', 1)),
    '/api/i2c/write': lambda q: iotools.i2c_write(q.get('bus', 1), q.get('addr', ''), q.get('hex', '')),
    '/api/sys/service': lambda q: sysinfo.service_action(q.get('name', ''), q.get('action', '')),
    '/api/sys/time': lambda q: sysinfo.set_time(q.get('epoch', '')),
    '/api/bench': lambda q: sysinfo.bench(q.get('test', '')),
    '/api/io/fan': lambda q: hwapi.io_fan(on=(q['on'] == '1') if 'on' in q else None,
                                          duty=q.get('duty'), hz=q.get('hz')),
    '/api/system': lambda q: hwapi.system(q.get('action', '')),
    '/api/logger/start': lambda q: datalog.start(q.get('name'), q.get('interval'), q.get('ch'), q.get('hours')),
    '/api/logger/stop': lambda q: datalog.stop(),
    '/api/logger/delete': lambda q: datalog.delete(q.get('name', '')),
}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype='application/json'):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def q(self):
        u = urlparse(self.path)
        return u.path, {k: v[0] for k, v in parse_qs(u.query).items()}

    def name_ok(self, n):
        if not n or not NAME_RE.match(n):
            self.send(400, {'ok': False, 'out': 'bad name (letters, digits, _ . - only)'})
            return False
        return True

    def do_GET(self):
        path, q = self.q()
        if path == '/':
            return self.send(200, open(os.path.join(HERE, 'index.html'), 'rb').read(), 'text/html; charset=utf-8')
        if path == '/api/status':
            return self.send(200, status())
        if path == '/api/info':
            return self.send(200, info())
        if path == '/api/log':
            lines, cur = app_log(q.get('cursor'))
            return self.send(200, {'log': '\n'.join(lines) + ('\n' if lines else ''), 'lines': lines, 'cursor': cur})
        if path == '/api/file':
            if not (self.name_ok(q.get('p')) and NAME_RE.match(q.get('f', ''))):
                return
            p = os.path.join(PROJ, q['p'], q['f'])
            if not os.path.isfile(p) or os.path.getsize(p) > 512 * 1024:
                return self.send(404, {'ok': False, 'out': 'not found or too big'})
            return self.send(200, open(p, 'rb').read(), 'text/plain; charset=utf-8')
        if path == '/api/peek':
            return self.send(200, ardzy('peek', q.get('a', '0'), q.get('n', '1')))
        if path == '/api/nand/backup':
            return self.nand_backup(q.get('raw') == '1')
        if path == '/api/config':
            r = subprocess.run(['/usr/local/sbin/ardzy-config', 'show'], capture_output=True, text=True)
            try:
                return self.send(200, dict(json.loads(r.stdout), ok=True))
            except ValueError:
                return self.send(200, {'ok': False, 'out': (r.stdout + r.stderr).strip()})
        if path == '/api/update/status':
            st = {'ok': True, 'release': dict(l.split('=', 1) for l in read('/etc/ardzy-release').splitlines() if '=' in l),
                  'kernel': os.uname().release, 'last': read(STATE + '/update_status')}
            try:
                import ardzy_env
                env = ardzy_env.read()[0]
                st['trial'] = env.get('ardzy_try') == '1'
            except Exception as e:
                st['env_error'] = str(e)
            st['old_kernel_kept'] = os.path.exists('/boot/zImage.old')
            return self.send(200, st)
        if path == '/api/bench/download':
            return self.bench_download(q.get('mb', '20'))
        if path.startswith('/api/hw') or path in HW_GET:
            return self.hw_call(HW_GET.get(path), q)
        self.send(404, {'ok': False, 'out': 'not found'})

    def hw_call(self, fn, q):
        """Hardware API: functions from hwapi.py; a ValueError becomes a friendly message."""
        if fn is None:
            return self.send(404, {'ok': False, 'out': 'not found'})
        try:
            r = fn(q)
            self.send(200, dict(r, ok=True) if isinstance(r, dict) else {'ok': True, 'out': r})
        except (ValueError, OSError) as e:
            self.send(200, {'ok': False, 'out': str(e)})

    def nand_backup(self, raw):
        """Stream the NAND (read-only) to the PC: raw = exact copy incl. spare (OOB) bytes and bad blocks."""
        try:
            cmd, size = hwapi.nand_backup_cmd(raw)
        except (ValueError, OSError) as e:
            return self.send(200, {'ok': False, 'out': str(e)})
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(size))
        self.send_header('Content-Disposition', 'attachment; filename="s9_nand_%s.bin"' % ('raw' if raw else 'data'))
        self.end_headers()
        sent = 0
        try:
            while sent < size:
                chunk = p.stdout.read(min(1 << 20, size - sent))
                if not chunk:
                    break
                self.wfile.write(chunk)
                sent += len(chunk)
            if sent < size:                       # keep the promised length (should not happen)
                self.wfile.write(b'\xff' * (size - sent))
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            p.kill()

    def bench_download(self, mb):
        """Network speed test: mb megabytes of zeros, the PC measures the time."""
        size = max(1, min(200, int(mb))) * 2**20
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(size))
        self.end_headers()
        block = bytes(1 << 16)
        try:
            for _ in range(size // len(block)):
                self.wfile.write(block)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        path, q = self.q()
        n = q.get('p', '')
        if path == '/api/load':
            return self.name_ok(n) and self.send(200, ardzy('load', n, *(['--default'] if q.get('default') else [])))
        if path == '/api/build':
            return self.name_ok(n) and self.send(200, ardzy('build', n))
        if path == '/api/stop':
            return self.send(200, ardzy('stop'))
        if path == '/api/restart':
            return self.send(200, ardzy('restart'))
        if path == '/api/unload':
            return self.send(200, ardzy('unload'))
        if path == '/api/default':
            return self.send(200, ardzy('default', n or 'none'))
        if path == '/api/delete':
            return self.name_ok(n) and self.send(200, ardzy('delete', n))
        if path == '/api/poke':
            return self.send(200, ardzy('poke', q.get('a', '0'), q.get('v', '0')))
        if path == '/api/config':
            # settings come in the body (JSON), so a password never appears in a URL or a log
            size = int(self.headers.get('Content-Length', 0) or 0)
            try:
                vals = json.loads(self.rfile.read(size) or b'{}') if size else {}
            except ValueError:
                return self.send(400, {'ok': False, 'out': 'bad JSON'})
            args = ['%s=%s' % (k, v) for k, v in vals.items() if re.fullmatch(r'[a-z_]+', str(k))]
            if not args:
                return self.send(200, {'ok': False, 'out': 'nothing to change'})
            r = subprocess.run(['/usr/local/sbin/ardzy-config', 'set'] + args, capture_output=True, text=True)
            return self.send(200, {'ok': r.returncode == 0, 'out': (r.stdout + r.stderr).strip()})
        if path == '/api/serial/send':
            # text for Serial.read() of a running sketch (and stdin-style input of other programs)
            text = q.get('text', '') + ('\n' if q.get('nl', '1') == '1' else '')
            try:
                fd = os.open(SERIAL_IN, os.O_WRONLY | os.O_NONBLOCK)
                os.write(fd, text.encode())
                os.close(fd)
                return self.send(200, {'ok': True, 'out': 'sent %d bytes' % len(text)})
            except OSError:
                return self.send(200, {'ok': False, 'out': 'the program is not reading input'})
        if path == '/api/clear':
            # empty a project folder before a fresh upload (old files must not stay behind)
            if not self.name_ok(n):
                return
            d = os.path.join(PROJ, n)
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d, exist_ok=True)
            return self.send(200, {'ok': True, 'out': 'cleared ' + n})
        if path in HW_POST:
            return self.hw_call(HW_POST[path], q)
        self.send(404, {'ok': False, 'out': 'not found'})

    def do_PUT(self):
        """PUT /api/upload?p=<project>&f=<file>  body = file bytes (.zip is unpacked)."""
        path, q = self.q()
        if path == '/api/system/update':                # an Ardzy update bundle (tar.gz)
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= 400 * 1024 * 1024:
                return self.send(413, {'ok': False, 'out': 'bundle missing or too big'})
            dst = '/var/tmp/ardzy-update.tar.gz'
            with open(dst, 'wb') as f:
                got = 0
                while got < size:
                    chunk = self.rfile.read(min(1 << 20, size - got))
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
            if got != size:
                return self.send(200, {'ok': False, 'out': 'upload incomplete'})
            # the installer runs as its own system task: restarting this web service (it restarts
            # itself after an update) can never stop an update halfway
            cmd = ['systemd-run', '--quiet', '--wait', '--pipe', '--collect', '--unit',
                   'ardzy-update-%d' % time.time(), '/usr/local/sbin/ardzy-update', dst, '--no-web-restart']
            r = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
            try:
                os.remove(dst)
            except OSError:
                pass
            out = (r.stdout + r.stderr).strip()
            restart = 'RESTART_WEB=1' in out
            self.send(200, {'ok': r.returncode == 0, 'out': out.replace('RESTART_WEB=1', '').strip(),
                            'reboot': 'REBOOT_NEEDED=1' in out, 'restart_web': restart, 'started': STARTED})
            if restart:   # only after the answer has gone out; the app waits until "started" changes
                subprocess.Popen(['systemd-run', '--quiet', '--on-active=1', 'systemctl', 'restart', 'ardzy-web'],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        if path == '/api/bench/upload':                 # network speed test: read and drop
            size, got = int(self.headers.get('Content-Length', 0)), 0
            while got < size:
                chunk = self.rfile.read(min(1 << 16, size - got))
                if not chunk:
                    break
                got += len(chunk)
            return self.send(200, {'ok': True, 'bytes': got})
        if path != '/api/upload':
            return self.send(404, {'ok': False})
        n, f = q.get('p', ''), os.path.basename(q.get('f', ''))
        if not self.name_ok(n) or not NAME_RE.match(f):
            return
        size = int(self.headers.get('Content-Length', 0))
        if size > 64 * 1024 * 1024:
            return self.send(413, {'ok': False, 'out': 'file too big'})
        data = self.rfile.read(size)
        d = os.path.join(PROJ, n)
        os.makedirs(d, exist_ok=True)
        if f.lower().endswith('.zip'):
            # folders are kept (a sketch's libraries/...); every part of a path must be a plain name
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for m in z.infolist():
                    parts = [x for x in m.filename.replace('\\', '/').split('/') if x]
                    if m.is_dir() or not parts or len(parts) > 12 or not all(PART_RE.match(x) and x not in ('.', '..')
                                                                              for x in parts):
                        continue
                    dst_path = os.path.join(d, *parts)
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    with z.open(m) as src, open(dst_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
        else:
            with open(os.path.join(d, f), 'wb') as out:
                out.write(data)
        self.send(200, {'ok': True, 'out': 'saved ' + f})


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Dual stack: one IPv6 socket that also accepts IPv4 (IPV6_V6ONLY off)."""
    daemon_threads = True
    allow_reuse_address = True
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


class Server4(Server):
    address_family = socket.AF_INET

    def server_bind(self):
        http.server.HTTPServer.server_bind(self)


SERIAL_IN = '/run/ardzy/serial_in'


def make_serial_pipe():
    """A named pipe for Serial.read(): opened by the sketch, written by /api/serial/send."""
    os.makedirs(os.path.dirname(SERIAL_IN), exist_ok=True)
    if not os.path.exists(SERIAL_IN):
        try:
            os.mkfifo(SERIAL_IN, 0o600)
        except OSError as e:
            print('serial pipe:', e, flush=True)


if __name__ == '__main__':
    os.makedirs(PROJ, exist_ok=True)
    make_serial_pipe()
    for fam in (socket.AF_INET, socket.AF_INET6):
        threading.Thread(target=discovery_responder, args=(fam,), daemon=True).start()
    for port in (80, 8080):
        HTTP_PORT = port
        try:
            try:
                srv = Server(('::', port), Handler)
            except OSError:                      # no IPv6 in the kernel: IPv4 only
                srv = Server4(('', port), Handler)
            print('Ardzy web page on port', port, flush=True)
            srv.serve_forever()
        except OSError as e:
            print('port', port, 'failed:', e, flush=True)
