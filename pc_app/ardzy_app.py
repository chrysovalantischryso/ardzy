#!/usr/bin/env python3
"""Ardzy - PC app for the Ardzy board (Antminer S9 Zynq used like an Arduino).

Architecture
  * this file = local engine: a small HTTP server on 127.0.0.1 (random port, secret token)
  * ui/       = the interface (HTML/JS), shown in a native window (pywebview / WebView2)
  * board link = HTTP API of the board (ardzyweb.py on the board), found by UDP discovery
  * serial    = USB-UART console (pyserial), for boot messages and a login shell

Run:  python ardzy_app.py          (or the packaged Ardzy.exe)
      python ardzy_app.py --browser  (open in the normal web browser instead of a window)
"""
import json, os, sys, socket, struct, threading, time, subprocess, shutil, secrets, re, glob, tempfile
import http.server, socketserver, urllib.request, urllib.error, urllib.parse, py_compile, webbrowser

APP_VERSION = '0.2a'                    # the app; the board's system (SD image) is 0.2
APP_STAGE = 'BETA'                      # shown next to the version everywhere
DISCOVERY_PORT = 41414
CHIP_IDCODE = 0x03722093        # XC7Z010
FROZEN = getattr(sys, 'frozen', False)
APP_DIR = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
UI_DIR = os.path.join(getattr(sys, '_MEIPASS', APP_DIR), 'ui')
TEMPLATES_DIR = os.path.join(getattr(sys, '_MEIPASS', APP_DIR), 'templates')
SETTINGS_FILE = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'Ardzy', 'settings.json')
NAME_RE = re.compile(r'^[A-Za-z0-9_.-]+$')
PROGRAM_FILES = ('main.py', 'run.sh', 'Makefile', 'devices.dtsi', 'overlay.dts')
UPLOAD_EXT = ('.py', '.c', '.h', '.txt', '.json', '.csv', '.s', '.wav')
EDIT_EXT = ('.py', '.c', '.h', '.v', '.sv', '.vhd', '.xdc', '.tcl', '.sh', '.txt', '.json', '.md',
            '.dtsi', '.dts', '.csv', 'Makefile', '.ino', '.cpp', '.hpp', '.s')
CACHE_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'Ardzy', 'cache')
ARDUINO_EXAMPLES = next((d for d in (os.path.join(getattr(sys, '_MEIPASS', APP_DIR), 'arduino', 'examples'),
                                     os.path.normpath(os.path.join(APP_DIR, '..', 'arduino', 'examples')),
                                     os.path.normpath(os.path.join(APP_DIR, '..', '..', 'arduino', 'examples')))
                         if os.path.isdir(d)), '')
GALLERY_DIR = next((d for d in (os.path.join(getattr(sys, '_MEIPASS', APP_DIR), 'fpga_projects'),
                                os.path.normpath(os.path.join(APP_DIR, '..', 'fpga_projects')),
                                os.path.normpath(os.path.join(APP_DIR, '..', '..', '..', 'fpga_projects')))
                    if os.path.isdir(d)), '')
sys.path.insert(0, getattr(sys, '_MEIPASS', APP_DIR))
import arduino_support                     # noqa: E402  (sketches, Library Manager, examples)
import sdflash                             # noqa: E402  (SD card writer)
from fpga import flow as fpga_flow          # noqa: E402  (built-in FPGA toolchain, no Vivado)
from fpga import sim as fpga_sim            # noqa: E402  (Verilog simulation with Icarus)


class child_safe:
    """Use around starting other programs (Vivado, Explorer). The packaged app (PyInstaller)
    sets a private DLL folder that child processes inherit: Vivado would then load Ardzy's
    copy of the C runtime (and lock Ardzy's files). Reset it while the child starts."""

    def __enter__(self):
        if FROZEN and os.name == 'nt':
            import ctypes
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        return self

    def __exit__(self, *a):
        if FROZEN and os.name == 'nt':
            import ctypes
            ctypes.windll.kernel32.SetDllDirectoryW(getattr(sys, '_MEIPASS', None))


def child_env():
    """Environment for child processes, without the app's private folders in PATH."""
    env = dict(os.environ)
    mei = getattr(sys, '_MEIPASS', None)
    if mei:
        env['PATH'] = os.pathsep.join(p for p in env.get('PATH', '').split(os.pathsep)
                                      if p and not p.lower().startswith(mei.lower()))
    return env


def pick_file(kind='All files (*.*)'):
    """A Windows file dialog (pywebview's, or tkinter when running in a browser)."""
    try:
        import webview
        if webview.windows:
            r = webview.windows[0].create_file_dialog(webview.OPEN_DIALOG, file_types=(kind, 'All files (*.*)'))
            return r[0] if r else None
    except Exception:
        pass
    try:
        import tkinter, tkinter.filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        ext = re.findall(r'\(([^)]*)\)', kind)
        path = tkinter.filedialog.askopenfilename(filetypes=[(kind, ext[0] if ext else '*.*'), ('All files', '*.*')])
        root.destroy()
        return path or None
    except Exception:
        return None


def startfile(path):
    with child_safe():
        os.startfile(path)


def default_workspace():
    # 2_Ardzy/projects when running from 2_Ardzy/pc_app (or its dist folder), else Documents/Ardzy
    # (only the projects folder of an Ardzy checkout: next to pc_app and fpga_projects. A "projects" folder found
    # anywhere else above the app, for example D:\projects, belongs to something else.)
    for up in ('..', os.path.join('..', '..'), os.path.join('..', '..', '..')):
        root = os.path.normpath(os.path.join(APP_DIR, up))
        p = os.path.join(root, 'projects')
        if os.path.isdir(p) and os.path.isdir(os.path.join(root, 'pc_app')) and os.path.isdir(os.path.join(root, 'fpga_projects')):
            return p
    return os.path.join(os.path.expanduser('~'), 'Documents', 'Ardzy')


DEFAULTS = {
    'workspace': default_workspace(),
    'vivado': r'C:\Xilinx\Vivado\2021.1\bin\vivado.bat',
    'last_board': '',          # {"host": ..., "port": ...} (IPv4, name, or IPv6 with zone)
    'manual_hosts': ['ardzy.local'],
    'fpga_tool': 'builtin',    # 'builtin' (Yosys + nextpnr, in the app) or 'vivado'
}


class Settings(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        try:
            self.update(json.load(open(SETTINGS_FILE)))
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        json.dump(self, open(SETTINGS_FILE, 'w'), indent=2)


settings = Settings()


# ------------------------------------------------------------------ events / jobs
class Events:
    """Console lines + job states for the UI (it polls /api/events?since=N)."""

    def __init__(self):
        self.items, self.lock, self.busy = [], threading.Lock(), None

    def add(self, kind, text='', **extra):
        with self.lock:
            self.items.append(dict(id=len(self.items) + 1, t=time.strftime('%H:%M:%S'), kind=kind, text=text, **extra))
            if len(self.items) > 5000:
                self.items = self.items[-3000:]

    def since(self, n):
        with self.lock:
            return [e for e in self.items if e['id'] > n]


events = Events()


def log(text, kind='out'):
    events.add(kind, text)


def run_job(name, fn, *args):
    if events.busy:
        return {'ok': False, 'out': 'busy: %s is still running' % events.busy}

    def wrap():
        events.busy = name
        events.add('job', name, state='start')
        ok = False
        try:
            ok = bool(fn(*args))
        except Exception as e:
            log('ERROR: %s' % e, 'err')
        finally:
            events.busy = None
            events.add('job', name, state='ok' if ok else 'fail')
    threading.Thread(target=wrap, daemon=True).start()
    return {'ok': True, 'out': name + ' started'}


# ------------------------------------------------------------------ board link (HTTP)
def http_base(host, port):
    """URL base for an IPv4 address, a name, or an IPv6 address with zone (fe80::1%13)."""
    if ':' in host:                                   # IPv6: brackets, and '%' must be %25 in a URL
        return 'http://[%s]:%d' % (host.replace('%', '%25'), port)
    return 'http://%s:%d' % (host, port)


def fetch_info(host, port, timeout=3):
    with urllib.request.urlopen(http_base(host, port) + '/api/info', timeout=timeout) as r:
        d = json.loads(r.read())
    if 'ardzy' not in d:
        raise ConnectionError('%s answers, but it is not an Ardzy board' % host)
    return d


class Board:
    def __init__(self):
        self.host, self.port, self.info = '', 80, {}

    @property
    def base(self):
        return http_base(self.host, self.port)

    def call(self, method, path, data=None, timeout=10, raw=False):
        if not self.host:
            raise ConnectionError('no board connected')
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header('Content-Type', 'application/octet-stream')
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
        return body if raw else json.loads(body or b'{}')

    def connect(self, host, port=80):
        """Connect by name or address. A name (ardzy.local) can give several addresses
        (IPv4, IPv6 link-local): the first one that answers is kept, so every later
        request skips the (slow) name lookup."""
        port = int(port)
        try:
            addrs = []
            for fam, _, _, _, sa in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP):
                a = sa[0] + ('%%%d' % sa[3] if fam == socket.AF_INET6 and sa[3] and '%' not in sa[0] else '')
                if a not in addrs:
                    addrs.append(a)
        except socket.gaierror:
            raise ConnectionError('name "%s" not found: is the board on and connected?' % host)
        errors = []
        for a in sorted(addrs, key=lambda x: ':' in x):          # IPv4 first, then IPv6
            try:
                info = fetch_info(a, port, timeout=2)
            except Exception as e:
                errors.append('%s: %s' % (a, getattr(e, 'reason', e)))
                continue
            self.host, self.port, self.info = a, port, info      # all at once (no half state)
            settings['last_board'] = {'host': a, 'port': port}
            settings.save()
            return self.info
        raise ConnectionError('no answer from %s (%s)' % (host, '; '.join(errors)))


board = Board()


def local_ipv4():
    ips = set()
    try:
        for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(a[4][0])
    except OSError:
        pass
    try:   # the interface used for the default route
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(i for i in ips if not i.startswith('127.'))


def discover(wait=1.5):
    """Find Ardzy boards:
      * IPv4 UDP broadcast on every network card (router networks, 169.254.x.x cables)
      * IPv6 multicast ff02::1 on every network card: works on any direct cable, even when
        the PC and the board have no IPv4 network in common (e.g. a fixed PC address)
      * the remembered board and names like ardzy.local (works through routers)
    A board that answers on several paths is listed once (IPv4 preferred)."""
    found = {}
    socks = []
    v6 = None
    try:
        v6 = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        v6.bind(('::', 0))
        for idx, _name in socket.if_nameindex():
            try:
                v6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, idx)
                v6.sendto(b'ARDZY_DISCOVER', ('ff02::1', DISCOVERY_PORT, 0, idx))
            except OSError:
                pass
    except OSError:
        v6 = None
    targets = ['255.255.255.255']
    for ip in local_ipv4():
        a = ip.split('.')
        targets.append('169.254.255.255' if ip.startswith('169.254.') else '%s.%s.%s.255' % (a[0], a[1], a[2]))
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((ip, 0))
            socks.append(s)
        except OSError:
            pass
    if not socks:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        socks.append(s)
    for s in socks:
        for t in set(targets):
            try:
                s.sendto(b'ARDZY_DISCOVER', (t, DISCOVERY_PORT))
            except OSError:
                pass
    # unicast to remembered / manual hosts too (works through routers, and for ardzy.local)
    hosts = set(settings.get('manual_hosts', []))
    lb = last_board()
    if lb and ':' not in lb[0]:
        hosts.add(lb[0])
    # name lookups in parallel: on Windows a name that does not exist (board off) takes ~3 s each
    ips = {ip for ip in resolve_all(hosts).values() if ip}
    for ip in ips:
        try:
            socks[0].sendto(b'ARDZY_DISCOVER', (ip, DISCOVERY_PORT))
        except OSError:
            pass

    def add(d, host):
        d['host'] = host
        key = d.get('mac') or host
        old = found.get(key)
        if old is None or (':' in old['host'] and ':' not in host):     # prefer IPv4
            found[key] = d
    end = time.time() + wait
    while time.time() < end:
        for s in socks + ([v6] if v6 else []):
            s.settimeout(0.05)
            try:
                data, addr = s.recvfrom(4096)
                d = json.loads(data)
                host = addr[0]
                if s is v6 and len(addr) > 3 and addr[3] and '%' not in host:
                    host = '%s%%%d' % (host, addr[3])                  # link-local needs the zone
                add(d, host)
            except (socket.timeout, OSError, ValueError):
                pass
    for s in socks + ([v6] if v6 else []):
        s.close()
    # fallback: boards that answer HTTP but not UDP (e.g. a router or firewall that drops UDP)
    def probe(ip_port):
        try:
            d = fetch_info(ip_port[0], ip_port[1], timeout=1.5)
            d['port'] = ip_port[1]
            return d
        except Exception:
            return None
    seen = {d['host'] for d in found.values()}
    todo = [(ip, port) for ip in ips - seen for port in (80, 8080)]
    if todo:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as ex:
            for (ip, _), d in zip(todo, ex.map(probe, todo)):
                if d:
                    add(d, ip)
    return sorted(found.values(), key=lambda d: d.get('hostname', ''))


def last_board():
    """(host, port) of the last connected board, or None (old settings stored 'host:port')."""
    lb = settings.get('last_board')
    if isinstance(lb, dict) and lb.get('host'):
        return lb['host'], int(lb.get('port', 80))
    if isinstance(lb, str) and lb:
        h, _, p = lb.rpartition(':') if lb.count(':') == 1 else (lb, '', '80')
        return h, int(p or 80)
    return None


def resolve_all(names):
    """{name: ipv4 or None}, looked up in parallel."""
    from concurrent.futures import ThreadPoolExecutor

    def one(n):
        try:
            return socket.gethostbyname(n)
        except OSError:
            return None
    names = list(names)
    if not names:
        return {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(zip(names, ex.map(one, names)))


# ------------------------------------------------------------------ projects (on the PC)
STARTER_DIR = os.path.join(getattr(sys, '_MEIPASS', APP_DIR), 'starter')   # example projects inside the app


def ws():
    w = settings['workspace']
    empty = not os.path.isdir(w) or not os.listdir(w)
    os.makedirs(w, exist_ok=True)
    if empty and not settings.get('starter_done') and os.path.isdir(STARTER_DIR):
        # first start with an empty projects folder: put the example projects in it (once)
        for n in sorted(os.listdir(STARTER_DIR)):
            if not os.path.exists(os.path.join(w, n)):
                shutil.copytree(os.path.join(STARTER_DIR, n), os.path.join(w, n),
                                ignore=shutil.ignore_patterns('__pycache__'))
        settings['starter_done'] = True
        settings.save()
    return w


def proj_path(name):
    if not NAME_RE.match(name or ''):
        raise ValueError('bad project name (letters, digits, _ . -)')
    return os.path.join(ws(), name)


def find_bit(d):
    """Newest .bit in the folder, or inside a Vivado project in it (*.runs/impl_*/)."""
    c = glob.glob(os.path.join(d, '*.bit'))
    if not c:
        c = [p for p in glob.glob(os.path.join(d, '**', '*.bit'), recursive=True)
             if re.search(r'[\\/]impl_\d+[\\/]', p)]
    return max(c, key=os.path.getmtime) if c else None


def project_kind(d, files):
    if any(f.endswith('.ino') for f in files):
        return 'arduino'
    if any(f.endswith(('.v', '.sv')) for f in files) or 'build.tcl' in files:
        return 'fpga'
    if 'main.py' in files:
        return 'python'
    if any(f.endswith('.c') for f in files):
        return 'c'
    return 'other'


def list_projects():
    out = []
    root = ws()
    for n in sorted(os.listdir(root)):
        d = os.path.join(root, n)
        if not os.path.isdir(d) or n.startswith(('_', '.')) or not NAME_RE.match(n) or n == 'libraries':
            continue
        files = sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)) and not f.startswith('.'))
        bit = find_bit(d)
        out.append({'name': n, 'files': files, 'bit': os.path.relpath(bit, d) if bit else '',
                    'bit_age_min': int((time.time() - os.path.getmtime(bit)) / 60) if bit else None,
                    'kind': project_kind(d, files),
                    'buildable': os.path.exists(os.path.join(d, 'build.tcl')) or any(
                        f.endswith(('.v', '.sv')) for f in files)})
    return out


def parse_bit(path):
    data = open(path, 'rb').read()
    info = {}
    if data[:2] == b'\x00\x09':
        pos = 13
        names = {'a': 'design', 'b': 'part', 'c': 'date', 'd': 'time'}
        while pos < len(data):
            k = chr(data[pos]); pos += 1
            if k in names:
                (n,) = struct.unpack_from('>H', data, pos); pos += 2
                info[names[k]] = data[pos:pos + n].rstrip(b'\0').decode(errors='replace'); pos += n
            elif k == 'e':
                raw = data[pos + 4:]
                break
            else:
                return info, None
    else:
        raw = data
        if b'\x66\x55\x99\xaa' in raw[:256]:
            import array
            a = array.array('I', raw[:len(raw) // 4 * 4]); a.byteswap(); raw = a.tobytes()
    i = raw.find(b'\x30\x01\x80\x01')
    idc = struct.unpack_from('>I', raw, i + 4)[0] if i >= 0 else None
    return info, idc


arduino = arduino_support.Arduino(lambda: ws(), CACHE_DIR, ARDUINO_EXAMPLES, log)


def log_compiler(text):
    """Compiler messages with colours: errors red, warnings yellow; build paths shortened."""
    for line in text.splitlines():
        line = re.sub(r'/opt/ardzy/projects/[^/]+/(libraries/)?', '', line)
        line = re.sub(r'/usr/lib/ardzy/arduino/', 'ardzy/', line)
        low = line.lower()
        kind = 'err' if (' error' in low or 'error:' in low or 'failed' in low) else \
            'warn' if 'warning' in low else 'ok' if line.startswith(('built', 'compiled OK')) else 'out'
        log('  ' + line, kind)


def send_sketch(name):
    """Pack the sketch with the libraries it uses and put it on the board."""
    d = proj_path(name)
    data, chosen, missing, n = arduino.pack(d)
    if chosen:
        log('  libraries: ' + ', '.join('%s %s' % (l.name, l.version) for l in chosen))
    q = urllib.parse.quote
    board.call('POST', '/api/clear?p=' + q(name))
    board.call('PUT', '/api/upload?p=%s&f=project.zip' % q(name), data=data, timeout=120)
    log('  sent %d files (%.1f KB)' % (n, len(data) / 1024))


def verify_sketch(name):
    if not board.host:
        log('Check of an Arduino sketch compiles it on the board: connect a board first (Scan).', 'err')
        return False
    log('Compiling %s on the board ...' % name, 'head')
    send_sketch(name)
    t = time.time()
    r = board.call('POST', '/api/build?p=' + urllib.parse.quote(name), timeout=900)
    log_compiler(r.get('out', ''))
    log('Check %s (%.0f s)' % ('passed' if r.get('ok') else 'FAILED', time.time() - t), 'ok' if r.get('ok') else 'err')
    return r.get('ok')


def upload_sketch(name, run=True, default=False):
    if not board.host:
        log('No board connected: click Scan, then choose your board.', 'err')
        return False
    log('Uploading sketch %s to %s ...' % (name, board.host), 'head')
    send_sketch(name)
    if not run:
        return verify_sketch(name)
    t = time.time()
    r = board.call('POST', '/api/load?p=%s%s' % (urllib.parse.quote(name), '&default=1' if default else ''),
                   timeout=900)
    log_compiler(r.get('out', ''))
    log(('Running (%.0f s). Output is in the Monitor; type there to send text to Serial.' % (time.time() - t))
        if r.get('ok') else 'Upload FAILED (see above).', 'ok' if r.get('ok') else 'err')
    return r.get('ok')


def release_dirs():
    """Where Ardzy images and update bundles can be: next to the app, the build folder, Downloads."""
    out = [os.path.join(APP_DIR, 'images'), os.path.normpath(os.path.join(APP_DIR, '..', 'out', 'release')),
           os.path.normpath(os.path.join(APP_DIR, '..', '..', '..', 'out', 'release')),
           os.path.join(os.path.expanduser('~'), 'Downloads')]
    return [d for d in out if os.path.isdir(d)]


def find_bundles():
    res = []
    for d in release_dirs():
        for f in os.listdir(d):
            if f.lower().endswith('-update.tar.gz') and 'ardzy' in f.lower():
                pth = os.path.join(d, f)
                res.append({'path': pth, 'name': f, 'size': os.path.getsize(pth)})
    return sorted(res, key=lambda x: x['name'], reverse=True)


LEGACY_UPDATE_PROJECT = 'ardzy_system_update'
LEGACY_UPDATE_MAIN = r'''# Installs an Ardzy update bundle on a board that runs Ardzy 0.1 (sent by the Ardzy app).
import os, shutil, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
shutil.copy(os.path.join(here, 'ardzy_env.py'), '/usr/lib/python3/dist-packages/ardzy_env.py')
r = subprocess.run([sys.executable, os.path.join(here, 'ardzy-update'), os.path.join(here, 'update.tar.gz')],
                   capture_output=True, text=True)
out = (r.stdout + r.stderr).strip() + '\nARDZY_UPDATE_RESULT=%d\n' % r.returncode
print(out, flush=True)
try:
    os.remove(os.path.join(here, 'update.tar.gz'))
except OSError:
    pass
with open(os.path.join(here, 'result.txt.new'), 'w') as f:
    f.write(out)
os.replace(os.path.join(here, 'result.txt.new'), os.path.join(here, 'result.txt'))
'''


def wait_web_restart(old, timeout=120):
    """After an update the board's web service restarts. Requests sent before it is back would
    be cut off, so wait until it reports a new start ("started" differs from the old one)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(2)
        try:
            new = board.call('GET', '/api/info', timeout=5).get('started')
        except Exception:
            continue
        if new and new != old:
            log('  the board\'s web service restarted with the new files', 'ok')
            return True
    log('  the board\'s web service did not restart in %d s (restart the board if something looks old)' % timeout,
        'warn')
    return False


def legacy_update(data):
    """Ardzy 0.1 boards have no update service. They can run a project's main.py as root, so
    the bundle goes as a one-off project with the bundle's own installer (ardzy-update +
    ardzy_env.py, taken from the bundle), and the result is read back from result.txt."""
    import io as _io, tarfile
    tools = {}
    with tarfile.open(fileobj=_io.BytesIO(data)) as t:
        for m in t.getmembers():
            n = m.name.lstrip('./')
            if n in ('rootfs/usr/local/sbin/ardzy-update', 'rootfs/usr/lib/python3/dist-packages/ardzy_env.py'):
                tools[os.path.basename(n)] = t.extractfile(m).read().replace(b'\r\n', b'\n')
    if len(tools) != 2:
        return {'ok': False, 'out': 'this bundle cannot update an Ardzy 0.1 board (installer missing): '
                                    'write the new SD card image instead (SD card button)'}
    log('  this board runs Ardzy 0.1: sending the installer with the bundle', 'warn')
    q = urllib.parse.quote
    name = LEGACY_UPDATE_PROJECT
    board.call('POST', '/api/clear?p=' + q(name))
    files = [('update.tar.gz', data), ('ardzy-update', tools['ardzy-update']),
             ('ardzy_env.py', tools['ardzy_env.py']), ('main.py', LEGACY_UPDATE_MAIN.encode())]
    for fname, body in files:
        board.call('PUT', '/api/upload?p=%s&f=%s' % (q(name), q(fname)), data=body, timeout=300)
    board.call('POST', '/api/load?p=' + q(name), timeout=120)
    log('  installing on the board (about 1 to 3 minutes) ...')
    t0 = time.time()
    while time.time() - t0 < 1500:
        time.sleep(5)
        try:
            out = board.call('GET', '/api/file?p=%s&f=result.txt' % q(name), timeout=10, raw=True).decode('utf-8', 'replace')
        except Exception:
            continue                            # not done yet, or the web service is restarting
        ok = 'ARDZY_UPDATE_RESULT=0' in out
        if ok:
            wait_web_restart(None)              # the 0.1 web service is replaced by the 0.2 one
        try:
            board.call('POST', '/api/delete?p=' + q(name), timeout=30)
        except Exception:
            pass
        return {'ok': ok, 'out': out.replace('ARDZY_UPDATE_RESULT=0', '').strip(), 'reboot': 'REBOOT_NEEDED=1' in out}
    return {'ok': False, 'out': 'no answer from the installer after 25 minutes'}


def system_update(path):
    """Send an Ardzy update bundle to the board and install it there."""
    if not board.host:
        log('No board connected.', 'err')
        return False
    data = open(path, 'rb').read()
    log('System update %s (%.1f MB) to %s ...' % (os.path.basename(path), len(data) / 2**20, board.host), 'head')
    try:
        board.call('GET', '/api/update/status', timeout=15)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        r = legacy_update(data)                 # Ardzy 0.1: no update service on the board yet
    else:
        r = board.call('PUT', '/api/system/update', data=data, timeout=1800)
        if r.get('restart_web'):
            wait_web_restart(r.get('started'))
    for line in r.get('out', '').splitlines():
        if not line.startswith('REBOOT_NEEDED'):
            log('  ' + line, 'ok' if r.get('ok') else 'err')
    RESULTS['update'] = {'ok': r.get('ok'), 'reboot': r.get('reboot'), 'time': time.time()}
    if r.get('ok'):
        log('Update installed.' + (' The board must restart to finish (Restart button).' if r.get('reboot') else ''), 'ok')
    return r.get('ok')


SIM_LAST = {}          # project -> the waves of its last simulation (for the viewer)


def simulate(name, tb, ns):
    d = proj_path(name)
    if not tb:
        tbs = fpga_sim.testbenches(d)
        if not tbs:
            log('No testbench in %s: press "New testbench" first.' % name, 'err')
            return False
        tb = tbs[0]
    log('Simulating %s with %s (Icarus Verilog, up to %s) ...' % (name, tb, fpga_sim.fmt_ns(ns)), 'head')
    t = time.time()
    r = fpga_sim.run(d, tb, ns, log=log)
    if not r.get('vcd'):
        if r.get('stage') == 'compile':
            log('Simulation not started: fix the errors above (they are also in Problems).', 'err')
        else:
            log('The simulation wrote no waves.', 'err')
        return False
    w = fpga_sim.parse_vcd(r['vcd'])
    w.update(tb=tb, ns=ns, when=time.strftime('%H:%M:%S'), root=r['root'])
    SIM_LAST[name] = w
    end_ns = w['end'] * w['timescale_ns']
    log('Simulation done in %.1f s: %d signals, %s of time, %d changes%s. The waves are in the Simulation tab.' % (
        time.time() - t, len(w['signals']), fpga_sim.fmt_ns(round(end_ns, 3)), w['changes'],
        ' (cut: too many changes, only the start is drawn)' if w['cut'] else ''), 'ok')
    return True


def verify(name):
    """Local checks before an upload (like Arduino 'Verify')."""
    d = proj_path(name)
    if arduino.is_sketch(d):
        return verify_sketch(name)
    ok = True
    log('Checking project %s ...' % name, 'head')
    bit = find_bit(d)
    if bit:
        info, idc = parse_bit(bit)
        fits = idc is not None and (idc & 0x0fffffff) == CHIP_IDCODE
        log('  FPGA design: %s  (%s, %s %s)' % (os.path.relpath(bit, d), info.get('part', '?'),
                                               info.get('date', ''), info.get('time', '')))
        if fits:
            log('  chip check: OK, made for XC7Z010 (IDCODE 0x%08x)' % idc, 'ok')
        else:
            log('  chip check: WRONG CHIP (IDCODE %s). In Vivado use part xc7z010clg400-1'
                % ('0x%08x' % idc if idc else 'unknown'), 'err')
            ok = False
        for src in glob.glob(os.path.join(d, '*.v')) + glob.glob(os.path.join(d, '*.tcl')):
            if os.path.getmtime(src) > os.path.getmtime(bit) + 2:
                log('  note: %s changed after the bitstream was built: build again (Build FPGA)'
                    % os.path.basename(src), 'warn')
    elif glob.glob(os.path.join(d, '*.v')) or glob.glob(os.path.join(d, '*.sv')):
        # Verilog but no bitstream: the program would talk to FPGA registers that are not there (an access to an
        # empty FPGA address can hang the board's bus until it is reset), so stop here
        uses_fpga = False
        for src in glob.glob(os.path.join(d, '*.py')) + glob.glob(os.path.join(d, '*.c')):
            if re.search(r'0x4[0-3][0-9a-fA-F_]{6}\b|MMIO\(|/dev/mem', open(src, encoding='utf-8', errors='replace').read()):
                uses_fpga = True
        if uses_fpga:
            log('  the FPGA design is not built yet (Verilog here, but no .bit), and the program uses FPGA'
                ' registers: press Build FPGA first', 'err')
            ok = False
        else:
            log('  note: the Verilog here is not built yet (no .bit): press Build FPGA to use it', 'warn')
    else:
        log('  no FPGA design (.bit): only the program will run, the FPGA stays as it is', 'warn')
    for py in glob.glob(os.path.join(d, '*.py')):
        try:
            py_compile.compile(py, cfile=os.path.join(tempfile.gettempdir(), 'ardzy_check.pyc'), doraise=True)
            log('  %s: Python syntax OK' % os.path.basename(py), 'ok')
        except py_compile.PyCompileError as e:
            log('  %s: %s' % (os.path.basename(py), str(e.msg).strip()), 'err')
            ok = False
    if glob.glob(os.path.join(d, '*.c')):
        log('  C files are compiled on the board during the upload (errors appear in the Monitor)')
    if not bit and not any(os.path.exists(os.path.join(d, f)) for f in PROGRAM_FILES) \
            and not glob.glob(os.path.join(d, '*.c')):
        log('  nothing to run: add a .bit and/or main.py / *.c / run.sh', 'err')
        ok = False
    log('Check %s' % ('passed' if ok else 'FAILED'), 'ok' if ok else 'err')
    return ok


def upload_files(d):
    files = []
    bit = find_bit(d)
    if bit:
        files.append(bit)
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        if os.path.isfile(p) and p != bit and (f in PROGRAM_FILES or f.endswith(UPLOAD_EXT)):
            files.append(p)
    return files


def upload(name, run=True, default=False):
    if arduino.is_sketch(proj_path(name)):
        return upload_sketch(name, run, default)
    if not verify(name):
        log('Upload stopped: fix the problems above first.', 'err')
        return False
    d = proj_path(name)
    if not board.host:
        log('No board connected: click Scan, then choose your board.', 'err')
        return False
    log('Uploading %s to %s ...' % (name, board.host), 'head')
    q = urllib.parse.quote
    board.call('POST', '/api/clear?p=' + q(name))
    for p in upload_files(d):
        fname = os.path.basename(p)
        data = open(p, 'rb').read()
        t = time.time()
        board.call('PUT', '/api/upload?p=%s&f=%s' % (q(name), q(fname)), data=data, timeout=120)
        log('  sent %-28s %8.1f KB  (%.1f s)' % (fname, len(data) / 1024, time.time() - t))
    if not run:
        log('Upload done (not started).', 'ok')
        return True
    log('Loading into the FPGA and starting the program ...')
    r = board.call('POST', '/api/load?p=%s%s' % (q(name), '&default=1' if default else ''), timeout=120)
    for line in r.get('out', '').splitlines():
        log('  ' + line, 'ok' if r.get('ok') else 'err')
    log('Done. Program output is in the Monitor tab.' if r.get('ok') else 'Load FAILED (see above).',
        'ok' if r.get('ok') else 'err')
    return r.get('ok')


def nand_backup(raw):
    """Copy the board's NAND flash (original Bitmain firmware) to a file on this PC."""
    import hashlib
    if not board.host:
        log('No board connected.', 'err')
        return False
    info = board.call('GET', '/api/nand')
    if not info.get('enabled'):
        log('NAND backup not possible yet: %s' % info.get('note', info.get('out')), 'err')
        return False
    folder = os.path.normpath(os.path.join(ws(), '..', 'backups'))
    os.makedirs(folder, exist_ok=True)
    name = 's9_nand_%s_%s.bin' % ('raw' if raw else 'data', time.strftime('%Y%m%d_%H%M%S'))
    path = os.path.join(folder, name)
    log('NAND backup (%s) to %s ...' % ('exact raw copy with spare bytes' if raw else 'data only', path), 'head')
    req = urllib.request.Request(board.base + '/api/nand/backup?raw=%d' % (1 if raw else 0))
    h, done, t0, last = hashlib.sha256(), 0, time.time(), 0
    with urllib.request.urlopen(req, timeout=60) as r, open(path, 'wb') as out:
        total = int(r.headers.get('Content-Length', 0))
        if r.headers.get('Content-Type', '').startswith('application/json'):
            log('board says: %s' % json.loads(r.read()).get('out'), 'err')
            return False
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if time.time() - last > 2:
                last = time.time()
                log('  %5.1f %%  %d / %d MB  (%.1f MB/s)' % (100 * done / max(total, 1), done >> 20, total >> 20,
                                                         done / 2**20 / max(time.time() - t0, 0.1)))
    if done != total:
        log('Backup INCOMPLETE: %d of %d bytes' % (done, total), 'err')
        return False
    open(path + '.sha256', 'w').write('%s  %s\n' % (h.hexdigest(), name))
    log('Backup done: %s (%d MB, %d s), SHA-256 %s...' % (name, done >> 20, time.time() - t0, h.hexdigest()[:16]), 'ok')
    return True


def net_speed(mb=32):
    """Network speed test: mb MB from the board, then mb MB to the board."""
    if not board.host:
        log('No board connected.', 'err')
        return False
    log('Network speed test (%d MB each way) ...' % mb, 'head')
    t0 = time.time()
    with urllib.request.urlopen(board.base + '/api/bench/download?mb=%d' % mb, timeout=120) as r:
        n = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            n += len(chunk)
    down = n * 8 / 1e6 / max(time.time() - t0, 1e-3)
    data = bytes(mb << 20)
    t0 = time.time()
    board.call('PUT', '/api/bench/upload', data=data, timeout=120)
    up = len(data) * 8 / 1e6 / max(time.time() - t0, 1e-3)
    log('  board to PC: %.0f Mbit/s   PC to board: %.0f Mbit/s' % (down, up), 'ok')
    RESULTS['net'] = {'down_mbit': round(down), 'up_mbit': round(up), 'mb': mb, 'time': time.time()}
    return True


RESULTS = {}


def sync_time():
    """The board has no battery clock: give it this PC's time (UTC)."""
    try:
        r = board.call('POST', '/api/sys/time?epoch=%.3f' % time.time(), timeout=5)
        if r.get('ok') and r.get('changed'):
            log('Board clock set from this PC (it was %+.0f s off).' % -r['diff_s'], 'ok')
    except (OSError, ValueError):
        pass


def clock_keeper():
    """Keep the board's clock right: after a board restart (or an automatic connect) it starts
    from its last saved time. The board only changes its clock when it is 2 s or more off."""
    time.sleep(10)
    while True:
        if board.host:
            sync_time()
        time.sleep(60)


def load_io_design():
    """Load the built-in pin-control design (project ardzy_io). The board keeps a copy; it is sent
    again when this PC has a different (newer) build than the one last sent to this board."""
    import hashlib
    if not board.host:
        log('No board connected.', 'err')
        return False
    st = board.call('GET', '/api/status')
    local = find_bit(proj_path('ardzy_io')) if os.path.isdir(proj_path('ardzy_io')) else None
    key = board.info.get('mac') or board.host
    sent = settings.get('io_bit_sent', {})
    if local:
        sha = hashlib.sha256(open(local, 'rb').read()).hexdigest()
        if sent.get(key) != sha:
            ok = upload('ardzy_io')
            if ok:
                sent[key] = sha
                settings['io_bit_sent'] = sent
                settings.save()
            return ok
    if any(p['name'] == 'ardzy_io' and any(f.endswith('.bit') for f in p['files']) for p in st.get('projects', [])):
        r = board.call('POST', '/api/load?p=ardzy_io', timeout=120)
        for line in r.get('out', '').splitlines():
            log('  ' + line, 'ok' if r.get('ok') else 'err')
        return r.get('ok')
    if not os.path.isdir(proj_path('ardzy_io')):
        log('The pin-control design (ardzy_io) is neither on the board nor in the projects folder.', 'err')
        return False
    return upload('ardzy_io')


def build_fpga(name):
    """Build the FPGA design: the built-in toolchain (Yosys + nextpnr + fasm2bit, no Vivado)
    for Verilog projects, or Vivado (build.tcl) when chosen in Settings."""
    d = proj_path(name)
    has_hdl = bool(glob.glob(os.path.join(d, '*.v')) + glob.glob(os.path.join(d, '*.sv')))
    if settings.get('fpga_tool', 'builtin') == 'builtin' and has_hdl:
        if not fpga_flow.available():
            log('The built-in FPGA toolchain is missing (tools/fpga). Reinstall Ardzy, or choose Vivado in Settings.',
                'err')
            return False
        try:
            fpga_flow.build(d, log=lambda t, c=None: log(t, c or 'out'), out_name=name)
            return True
        except Exception as e:
            log('FPGA build FAILED: %s' % e, 'err')
            return False
    return build_vivado(name)


def build_vivado(name):
    """Run the project's build.tcl in Vivado (batch). Vivado does not like spaces in paths,
    so the project is copied to a temp folder, built there, and the .bit copied back."""
    d = proj_path(name)
    if not os.path.exists(os.path.join(d, 'build.tcl')):
        log('This project has no build.tcl. Open your design in Vivado and click Generate Bitstream;'
            ' Ardzy finds the newest .bit inside the project folder by itself.', 'warn')
        return False
    viv = settings['vivado']
    if not os.path.exists(viv):
        log('Vivado not found at %s (set it in Settings).' % viv, 'err')
        return False
    work = os.path.join(tempfile.gettempdir(), 'ardzy_vivado')
    shutil.rmtree(os.path.join(work, name), ignore_errors=True)
    shutil.copytree(d, os.path.join(work, name), ignore=shutil.ignore_patterns('_build', '*.bit', '.Xil'))
    for f in glob.glob(os.path.join(ws(), '*.xdc')):        # shared constraints (e.g. leds.xdc)
        shutil.copy(f, work)
    log('Building the FPGA design of %s with Vivado (takes a few minutes) ...' % name, 'head')
    t = time.time()
    with child_safe():
        p = subprocess.Popen(['cmd', '/c', viv, '-mode', 'batch', '-nojournal', '-nolog', '-source', 'build.tcl'],
                             cwd=os.path.join(work, name), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, errors='replace', env=child_env(),
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    keep = re.compile(r'^(ERROR|CRITICAL WARNING|BUILD_|INFO: \[(Synth 8-7080|Common 17-206|Vivado 12-1352)|'
                      r'(Starting|Finished|Phase \d+ ) |Bitstream|\[.*Runs 36-.*\]|.*Errors encountered)')
    for line in p.stdout:
        line = line.rstrip()
        if keep.match(line):
            log('  ' + line, 'err' if line.startswith(('ERROR', 'CRITICAL')) else 'out')
    p.wait()
    bits = glob.glob(os.path.join(work, name, '*.bit'))
    if p.returncode == 0 and bits:
        for b in bits:
            shutil.copy(b, d)
        log('FPGA design built in %d s: %s' % (time.time() - t, ', '.join(os.path.basename(b) for b in bits)), 'ok')
        return True
    log('Vivado build FAILED (exit %s). Open the project in Vivado to see the full report.' % p.returncode, 'err')
    return False


def new_project(name, template):
    d = proj_path(name)
    if os.path.exists(d):
        raise ValueError('project %s already exists' % name)
    src = os.path.join(TEMPLATES_DIR, template)
    if not os.path.isdir(src):
        raise ValueError('unknown template ' + template)
    shutil.copytree(src, d)
    for root, _, files in os.walk(d):          # template placeholders
        for f in files:
            p = os.path.join(root, f)
            if '__NAME__' in f:
                p2 = os.path.join(root, f.replace('__NAME__', name))
                os.rename(p, p2)
                p, f = p2, os.path.basename(p2)
            if f.endswith(('.tcl', '.py', '.v', '.c', '.md', '.txt', '.ino', '.cpp', '.h', '.xdc')):
                t = open(p, encoding='utf-8').read()
                if '__NAME__' in t:              # (only then: a prebuilt .bit must stay newer than its sources)
                    open(p, 'w', encoding='utf-8').write(t.replace('__NAME__', name))
    return d



# ---------------------------------------------------------------- FPGA project gallery (fpga_projects)
GALLERY_SKIP = ('guide.md', 'guide.html', 'pins.xdc', 'top.v', 'selftest.py', 'project.json')


def gallery_list():
    out = []
    if not GALLERY_DIR:
        return out
    for n in sorted(os.listdir(GALLERY_DIR)):
        d = os.path.join(GALLERY_DIR, n)
        pj = os.path.join(d, 'project.json')
        if not re.match(r'^\d\d_', n) or not os.path.isfile(pj):
            continue
        p = json.load(open(pj, encoding='utf-8'))
        panel = None
        if os.path.isfile(os.path.join(d, 'panel.json')):
            try:
                panel = json.load(open(os.path.join(d, 'panel.json'), encoding='utf-8'))
            except ValueError:
                panel = None
        out.append({'name': n, 'id': p.get('id'), 'title': p.get('title'), 'category': p.get('category'),
                    'level': p.get('level'), 'summary': p.get('summary'), 'slots': p.get('slots', {}),
                    'wiring': p.get('wiring', []), 'parts': p.get('parts', []), 'panel': panel,
                    'bit': os.path.isfile(os.path.join(d, n + '.bit')),
                    'guide': os.path.isfile(os.path.join(d, 'guide.html')),
                    'test': os.path.isfile(os.path.join(d, 'selftest.py'))})
    return out


def gallery_path(name):
    if not GALLERY_DIR or not re.match(r'^\d\d_[A-Za-z0-9_]+$', name or ''):
        raise ValueError('unknown project ' + str(name))
    d = os.path.join(GALLERY_DIR, name)
    if not os.path.isdir(d):
        raise ValueError('unknown project ' + name)
    return d


def gallery_upload(name, test=False, boot=False):
    """Upload a ready project (its prebuilt .bit and programs) and start it. test: run the self-test
    instead of the demo. Files the project made on the board (settings, songs) stay."""
    d = gallery_path(name)
    if not board.host:
        log('No board connected: click Scan, then choose your board.', 'err')
        return False
    q = urllib.parse.quote
    files = [f for f in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, f)) and f not in GALLERY_SKIP
             and not f.startswith('make_') and (f == name + '.bit' or f.endswith(('.py', '.json', '.s', '.txt', '.csv')))]
    log('%s %s on %s ...' % ('Self-test of' if test else 'Uploading', name, board.host), 'head')
    for f in files:
        src = 'selftest.py' if (test and f == 'main.py') else f
        data = open(os.path.join(d, src), 'rb').read()
        board.call('PUT', '/api/upload?p=%s&f=%s' % (q(name), q(f)), data=data, timeout=120)
        log('  sent %-24s %8.1f KB%s' % (f, len(data) / 1024, '  (the self-test)' if src != f else ''))
    log('Loading into the FPGA and starting %s ...' % ('the self-test' if test else 'the program'))
    cursor = board.call('GET', '/api/log').get('cursor') if test else None
    r = board.call('POST', '/api/load?p=%s%s' % (q(name), '&default=1' if boot and not test else ''), timeout=120)
    if test and r.get('ok') and os.path.isfile(os.path.join(d, 'main.py')):
        def restore():                    # the real program back on the board once the test has finished
            cur, t0 = cursor, time.time()
            while time.time() - t0 < 300:
                time.sleep(2)
                try:
                    x = board.call('GET', '/api/log?cursor=' + q(cur or ''))
                except Exception:
                    continue
                cur = x.get('cursor', cur)
                if 'RESULT:' in x.get('log', '') or 'Traceback' in x.get('log', ''):
                    break
            try:
                board.call('PUT', '/api/upload?p=%s&f=main.py' % q(name),
                           data=open(os.path.join(d, 'main.py'), 'rb').read(), timeout=60)
            except Exception:
                pass
        threading.Thread(target=restore, daemon=True).start()
    for line in r.get('out', '').splitlines():
        log('  ' + line, 'ok' if r.get('ok') else 'err')
    log(('Running: the results appear in the Monitor tab (the last line says how many checks passed).' if test else
         'Running. Program output is in the Monitor tab.') if r.get('ok') else 'Load FAILED (see above).',
        'ok' if r.get('ok') else 'err')
    return r.get('ok')


def gallery_copy(name, new_name):
    d = gallery_path(name)
    dst = proj_path(new_name)
    if os.path.exists(dst):
        raise ValueError(new_name + ' already exists in your projects')
    shutil.copytree(d, dst, ignore=shutil.ignore_patterns('guide.html', '__pycache__'))
    bit = os.path.join(dst, name + '.bit')
    if os.path.isfile(bit) and new_name != name:
        os.replace(bit, os.path.join(dst, new_name + '.bit'))
    log('Copied %s to your projects as %s: edit it, Build FPGA, Upload.' % (name, new_name), 'ok')
    return True


# ---------------------------------------------------------------- the FM radio (project 12_fm_radio)
RADIO_PROJECT = '12_fm_radio'


def board_file(project, name):
    try:
        return board.call('GET', '/api/file?p=%s&f=%s' % (urllib.parse.quote(project), urllib.parse.quote(name)),
                          raw=True, timeout=5)
    except urllib.error.HTTPError:
        return None


AI_PORT = 8080                  # project 16_digit_ai: its demo (main.py) serves the drawing page and /guess here


def ai_call(path, data=None, timeout=5):
    """Talk to the AI demo on the board (through the engine: works over IPv6 link-local too)."""
    if not board.host:
        return {'ok': False, 'running': False, 'out': 'no board connected'}
    req = urllib.request.Request(http_base(board.host, AI_PORT) + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read() or b'{}')
        out.setdefault('ok', True)
        return out
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {'ok': False, 'running': False, 'out': 'the AI demo does not answer (%s)' % getattr(e, 'reason', e),
                'current': board.info.get('current') if board.info else None}


HANDWRITING = os.path.join(os.path.dirname(SETTINGS_FILE), 'handwriting.json')   # your drawings, for "Learn my handwriting"


def ai_samples():
    try:
        return json.load(open(HANDWRITING))
    except (OSError, ValueError):
        return []


def ai_sample_add(pixels, label):
    s = ai_samples()
    px = bytes(int(v) & 255 for v in pixels)
    if len(px) != 784 or not 0 <= int(label) <= 9:
        return {'ok': False, 'out': 'a drawing is 784 pixels and a digit 0 .. 9'}
    s.append({'pixels': __import__('base64').b64encode(px).decode(), 'label': int(label)})
    os.makedirs(os.path.dirname(HANDWRITING), exist_ok=True)
    json.dump(s, open(HANDWRITING, 'w'))
    return ai_sample_counts()


def ai_sample_counts():
    s = ai_samples()
    counts = [0] * 10
    for x in s:
        counts[x['label']] += 1
    return {'ok': True, 'counts': counts, 'total': len(s)}


def ai_teach():
    """Fine-tune project 19's big reader on your drawings (here on the PC), send it to the board, switch to it."""
    import base64
    s = ai_samples()
    if len(s) < 10:
        log('Draw and mark at least 10 digits first (you have %d).' % len(s), 'err')
        return False
    d = gallery_path('19_ai_studio')
    if d not in sys.path:
        sys.path.insert(0, d)
    import numpy as np
    import teach
    out = os.path.join(os.path.dirname(SETTINGS_FILE), 'reader_mine.py')
    log('Teaching the reader your handwriting (%d drawings) ...' % len(s), 'head')
    samples = [(np.frombuffer(base64.b64decode(x['pixels']), np.uint8), x['label']) for x in s]
    teach.teach(samples, out, log=lambda m: log('  ' + m))
    if not board.host:
        log('Saved %s; connect the board to use it.' % out, 'warn')
        return True
    board.call('PUT', '/api/upload?p=19_ai_studio&f=reader_mine.py', data=open(out, 'rb').read(), timeout=120)
    r = ai_call('/reload_reader', {}, timeout=60)
    log('The board now reads with your reader.' if r.get('ok') else
        'Sent to the board; it is used the next time AI Studio starts (%s).' % r.get('out', ''), 'ok' if r.get('ok') else 'warn')
    return True


def radio_state(project):
    st = board_file(project, 'status.json')
    cfg = board_file(project, 'radio.json')
    status = json.loads(st) if st else None
    running = bool(status) and abs(time.time() - status.get('time', 0)) < 6
    return {'ok': True, 'status': status, 'config': json.loads(cfg) if cfg else None, 'running': running,
            'current': board.info.get('current') if board.info else None}


def radio_config(project, cfg):
    data = json.dumps(cfg, indent=1).encode()
    board.call('PUT', '/api/upload?p=%s&f=radio.json' % urllib.parse.quote(project), data=data, timeout=20)
    return {'ok': True}


def radio_capture(project, cid):
    """Ask the radio service for an MPX capture (a small file in the board's RAM: the settings stay untouched)."""
    data = json.dumps({'id': int(cid)}).encode()
    board.call('PUT', '/api/upload?p=%s&f=capture.json' % urllib.parse.quote(project), data=data, timeout=10)
    return {'ok': True}


def radio_add_wav(project):
    import wave
    path = pick_file('WAV audio (*.wav)')
    if not path:
        return {'ok': False, 'out': 'no file chosen'}
    try:
        with wave.open(path, 'rb') as w:
            rate, ch, bits = w.getframerate(), w.getnchannels(), 8 * w.getsampwidth()
            secs = w.getnframes() / rate
    except (wave.Error, EOFError, OSError, ZeroDivisionError) as e:
        raise ValueError('%s is not a PCM WAV file (%s). Convert it to WAV, 16 bit, with Audacity or VLC.'
                         % (os.path.basename(path), e))
    size = os.path.getsize(path)
    if size > 63 * 1024 * 1024:
        raise ValueError('%s is %.0f MB: the board takes files up to 63 MB. Save it as mono or 32 kHz.'
                         % (os.path.basename(path), size / 2 ** 20))
    name = re.sub(r'[^A-Za-z0-9_.-]+', '_', os.path.splitext(os.path.basename(path))[0]).strip('_')[:60] or 'song'
    name += '.wav'

    def send():
        log('Sending %s (%d Hz, %d bit, %s, %.0f s, %.1f MB) to the radio ...' % (
            name, rate, bits, 'stereo' if ch > 1 else 'mono', secs, size / 2 ** 20), 'head')
        t = time.time()
        board.call('PUT', '/api/upload?p=%s&f=%s' % (urllib.parse.quote(project), urllib.parse.quote(name)),
                   data=open(path, 'rb').read(), timeout=600)
        log('  %s sent in %.1f s. It joins the playlist of the radio.' % (name, time.time() - t), 'ok')
        return True
    run_job('Send song', send)
    return {'ok': True, 'name': name}


def radio_image(project, rgb_b64):
    """A picture for SSTV: 320 x 256 RGB bytes (the page makes them from any image file)."""
    import base64
    data = base64.b64decode(rgb_b64)
    if len(data) != 320 * 256 * 3:
        raise ValueError('the picture must be 320 x 256 RGB')
    board.call('PUT', '/api/upload?p=%s&f=sstv_image.rgb' % urllib.parse.quote(project), data=data, timeout=60)
    return {'ok': True}


# ---------------------------------------------------------------- network sound from this PC (AES67)
NET = {'heard': None, 'active': None}


def aes67_devices():
    import aes67_pc
    try:
        return {'ok': True, 'devices': aes67_pc.devices()}
    except ImportError:
        return {'ok': False, 'out': 'the sound library (pyaudiowpatch) is missing in this build'}


def aes67_stop():
    if NET['active']:
        try:
            NET['active'].close()
        except Exception:
            pass
        NET['active'] = None
    return {'ok': True}


def aes67_send(dev_id):
    import aes67_pc
    if not board.host:
        raise ConnectionError('no board connected')
    dev = next((d for d in aes67_pc.devices() if d['id'] == int(dev_id)), None)
    if not dev:
        raise ValueError('that sound device is gone')
    aes67_stop()
    NET['active'] = aes67_pc.Sender(dev, board.host)
    log('Network sound: sending "%s" (%s) to the radio, L24/%d, 1 ms packets, straight to %s' % (
        dev['name'], 'everything it plays' if dev['kind'] == 'loopback' else 'input', dev['rate'], board.host), 'ok')
    return {'ok': True, 'config': NET['active'].config()}


def aes67_relay(stream):
    import aes67_pc
    if not board.host:
        raise ConnectionError('no board connected')
    aes67_stop()
    st = {'name': stream.get('name', ''), 'address': stream['address'], 'port': int(stream['port']),
          'encoding': stream.get('encoding', 'L24'), 'rate': int(stream.get('rate', 48000)), 'channels': int(stream.get('channels', 2))}
    NET['active'] = aes67_pc.Relay(st, board.host)
    log('Network sound: passing %s:%d on to the radio' % (st['address'], st['port']), 'ok')
    return {'ok': True, 'config': NET['active'].config()}


def aes67_state():
    import aes67_pc
    if NET['heard'] is None:
        try:
            NET['heard'] = aes67_pc.Heard()
        except OSError as e:
            NET['heard'] = False
            log('Network sound: cannot listen for AES67 announcements on this PC (%s)' % e, 'warn')
    return {'ok': True, 'active': NET['active'].state() if NET['active'] else None,
            'heard': NET['heard'].list() if NET['heard'] else []}


def radio_mpx(project):
    m = board_file(project, 'mpx_live.json')          # the live spectrum's own captures (capture.json)
    if not m or b'"id"' not in m:
        m = board_file(project, 'mpx.json')           # (an older radio service)
    return {'ok': True, 'mpx': json.loads(m) if m else None}


# ------------------------------------------------------------------ serial console (USB-UART)
class Serial:
    def __init__(self):
        self.port, self.ser, self.lines = None, None, []

    @staticmethod
    def ports():
        try:
            from serial.tools import list_ports
            return [{'port': p.device, 'desc': p.description} for p in list_ports.comports()]
        except ImportError:
            return []

    def open(self, port, baud=115200):
        import serial
        self.close()
        self.ser = serial.Serial(port, baud, timeout=0.1)
        self.port = port
        events.add('serial', 'opened %s at %d baud' % (port, baud), state='open')
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        buf = b''
        ser = self.ser
        while ser is self.ser and ser and ser.is_open:
            try:
                data = ser.read(1024)
            except Exception as e:
                events.add('serial', 'port error: %s' % e, state='closed')
                self.ser = None
                return
            if data:
                buf += data
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    events.add('serial', re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', line.decode(errors='replace')).rstrip('\r'))
                if len(buf) > 0 and not data.endswith(b'\n') and len(buf) < 200 and buf.endswith((b': ', b'# ', b'$ ', b'> ')):
                    events.add('serial', buf.decode(errors='replace'))     # prompts without newline
                    buf = b''

    def write(self, text):
        if not self.ser:
            raise ConnectionError('serial port not open')
        self.ser.write(text.encode() + b'\r')

    def close(self):
        if self.ser:
            s, self.ser = self.ser, None
            try:
                s.close()
            except Exception:
                pass
            events.add('serial', 'closed %s' % self.port, state='closed')


serial_con = Serial()


# ------------------------------------------------------------------ local HTTP server (UI <-> engine)
TOKEN = secrets.token_hex(16)


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

    def static(self, path):
        p = os.path.normpath(os.path.join(UI_DIR, path.lstrip('/') or 'index.html'))
        if not p.startswith(os.path.normpath(UI_DIR)) or not os.path.isfile(p):
            return self.send(404, {'ok': False})
        ctype = {'.html': 'text/html; charset=utf-8', '.js': 'application/javascript', '.css': 'text/css',
                 '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon',
                 '.json': 'application/json'}.get(os.path.splitext(p)[1],
                                                                                          'application/octet-stream')
        data = open(p, 'rb').read()
        if p.endswith('index.html'):
            data = data.replace(b'__ARDZY_TOKEN__', TOKEN.encode())
        self.send(200, data, ctype)

    def body(self):
        n = int(self.headers.get('Content-Length', 0) or 0)
        return json.loads(self.rfile.read(n) or b'{}') if n else {}

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if not u.path.startswith('/api/'):
            return self.static(u.path)
        self.handle_api('GET', u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        self.handle_api('POST', u.path, self.body())

    def handle_api(self, method, path, a):
        if self.headers.get('X-Ardzy-Token') != TOKEN:      # only our own window may use the engine
            return self.send(403, {'ok': False, 'out': 'forbidden'})
        try:
            self.send(200, self.api(method, path, a))
        except urllib.error.URLError as e:
            self.send(200, {'ok': False, 'out': 'board not reachable (%s)' % getattr(e, 'reason', e), 'offline': True})
        except (socket.timeout, ConnectionError, OSError, ValueError) as e:
            self.send(200, {'ok': False, 'out': str(e), 'offline': isinstance(e, (socket.timeout, ConnectionError))})

    def api(self, method, path, a):
        q = urllib.parse.quote
        if path == '/api/app':
            return {'version': APP_VERSION, 'stage': APP_STAGE, 'settings': settings, 'busy': events.busy,
                    'board': {'host': board.host, 'port': board.port, 'info': board.info},
                    'templates': sorted(os.listdir(TEMPLATES_DIR)) if os.path.isdir(TEMPLATES_DIR) else []}
        if path == '/api/events':
            return {'events': events.since(int(a.get('since', 0))), 'busy': events.busy}
        if path == '/api/scan':
            boards = discover()
            log('Scan: %d board(s) found%s' % (len(boards), ''.join(
                '\n  %s  %s  (%s)' % (b.get('hostname'), b.get('host'), b.get('os', '')) for b in boards)), 'head')
            return {'ok': True, 'boards': boards}
        if path == '/api/connect':
            info = board.connect(a['host'], a.get('port', 80))
            threading.Thread(target=sync_time, daemon=True).start()
            log('Connected to %s (%s), %s, kernel %s' % (info.get('hostname'), board.host, info.get('os'),
                                                        info.get('kernel')), 'ok')
            return {'ok': True, 'info': info, 'host': board.host}
        if path == '/api/disconnect':
            board.host, board.info = '', {}
            return {'ok': True}
        if path == '/api/board/status':
            return {'ok': True, 'status': board.call('GET', '/api/status', timeout=4)}
        if path == '/api/board/log':
            return dict(ok=True, **board.call('GET', '/api/log' + ('?cursor=' + q(a['cursor']) if a.get('cursor') else ''), timeout=6))
        if path == '/api/board/action':
            act = a['action']
            if act not in ('load', 'stop', 'restart', 'unload', 'default', 'delete'):
                raise ValueError('bad action')
            r = board.call('POST', '/api/%s?p=%s' % (act, q(a.get('project', ''))), timeout=120)
            log('%s: %s' % (act, r.get('out', '')), 'ok' if r.get('ok') else 'err')
            return r
        if path == '/api/board/peek':
            return board.call('GET', '/api/peek?a=%s&n=%s' % (q(a['addr']), q(str(a.get('n', 4)))))
        if path == '/api/board/poke':
            return board.call('POST', '/api/poke?a=%s&v=%s' % (q(a['addr']), q(a['value'])))
        if path == '/api/board/proxy':
            # pass a hardware-API call through to the board (only its /api/ paths)
            bp, meth = a.get('path', ''), a.get('method', 'GET').upper()
            if not re.match(r'^/api/[a-z0-9/_-]+(\?[A-Za-z0-9_=&.%\[\]:,-]*)?$', bp) or meth not in ('GET', 'POST'):
                raise ValueError('bad board path')
            r = board.call(meth, bp, data=b'' if meth == 'POST' else None, timeout=60)
            if meth == 'POST' and isinstance(r, dict) and r.get('out'):
                log('%s: %s' % (bp.split('?')[0].replace('/api/', ''), r['out']), 'ok' if r.get('ok') else 'err')
            return r
        if path == '/api/nand/backup':
            return run_job('NAND backup', nand_backup, bool(a.get('raw')))
        if path == '/api/io/load':
            return run_job('Load pin control', load_io_design)
        if path == '/api/bench/net':
            return run_job('Network speed test', net_speed, int(a.get('mb', 32)))
        if path == '/api/gallery':
            return {'ok': True, 'projects': gallery_list(), 'dir': GALLERY_DIR}
        if path == '/api/learn/file':                 # a lesson project's file, shown in the Learn view (read only)
            t = os.path.basename(a.get('template', ''))
            f = os.path.basename(a.get('name', ''))
            p = os.path.join(TEMPLATES_DIR, t, f)
            if not t.startswith('learn_') or not os.path.isfile(p):
                return {'ok': False, 'out': 'no such lesson file'}
            return {'ok': True, 'text': open(p, encoding='utf-8').read()}
        if path == '/api/gallery/guide':
            d = gallery_path(a['name'])
            return {'ok': True, 'html': open(os.path.join(d, 'guide.html'), encoding='utf-8').read()}
        if path == '/api/gallery/upload':
            return run_job('Upload', gallery_upload, a['name'], bool(a.get('test')), bool(a.get('boot')))
        if path == '/api/gallery/copy':
            return {'ok': gallery_copy(a['name'], a.get('as') or a['name'])}
        if path == '/api/gallery/open':
            startfile(gallery_path(a['name']))
            return {'ok': True}
        if path == '/api/ai/state':
            r = ai_call('/state')
            r['current'] = board.info.get('current') if board.info else None
            return r
        if path == '/api/ai/guess':
            return ai_call('/guess', {'px': a.get('px', '')})
        if path == '/api/ai/example':
            return ai_call('/example')
        if path == '/api/ai/sample':
            return ai_sample_add(a.get('pixels', []), a.get('label', -1))
        if path == '/api/ai/samples':
            return ai_sample_counts()
        if path == '/api/ai/samples_clear':
            if os.path.exists(HANDWRITING):
                os.remove(HANDWRITING)
            return ai_sample_counts()
        if path == '/api/ai/teach':
            return run_job('Teach', ai_teach)
        if path in ('/api/ai/write', '/api/ai/next', '/api/ai/draw', '/api/ai/morph', '/api/ai/style'):
            return ai_call(path[7:], a, timeout=30)     # projects 17 (write, next) and 18 (draw, morph, style)
        if path == '/api/radio/state':
            return radio_state(a.get('p') or RADIO_PROJECT)
        if path == '/api/radio/config':
            return radio_config(a.get('p') or RADIO_PROJECT, a['config'])
        if path == '/api/radio/capture':
            return radio_capture(a.get('p') or RADIO_PROJECT, a['id'])
        if path == '/api/radio/wav':
            return radio_add_wav(a.get('p') or RADIO_PROJECT)
        if path == '/api/radio/image':
            return radio_image(a.get('p') or RADIO_PROJECT, a['rgb'])
        if path == '/api/aes67/devices':
            return aes67_devices()
        if path == '/api/aes67/send':
            return aes67_send(a['id'])
        if path == '/api/aes67/relay':
            return aes67_relay(a['stream'])
        if path == '/api/aes67/stop':
            return aes67_stop()
        if path == '/api/aes67/state':
            return aes67_state()
        if path == '/api/radio/mpx':
            return radio_mpx(a.get('p') or RADIO_PROJECT)
        if path == '/api/results':
            return {'ok': True, 'results': RESULTS}
        if path == '/api/projects':
            return {'ok': True, 'projects': list_projects(), 'workspace': ws()}
        if path == '/api/file':
            p = os.path.join(proj_path(a['project']), os.path.basename(a['name']))
            if method == 'GET':
                if os.path.getsize(p) > 2 * 1024 * 1024:
                    raise ValueError('file too big to edit')
                return {'ok': True, 'text': open(p, encoding='utf-8', errors='replace').read()}
            open(p, 'w', encoding='utf-8', newline='\n').write(a['text'])
            return {'ok': True, 'out': 'saved'}
        if path == '/api/file/new':
            name = os.path.basename(a['name'])
            p = os.path.join(proj_path(a['project']), name)
            if os.path.exists(p):
                raise ValueError(name + ' already exists')
            open(p, 'w').close()
            return {'ok': True}
        if path == '/api/project/new':
            new_project(a['name'], a['template'])
            log('New project %s (template: %s)' % (a['name'], a['template']), 'ok')
            return {'ok': True}
        if path == '/api/sim/info':
            return dict(ok=True, **fpga_sim.info(proj_path(a['project'])))
        if path == '/api/sim/newtb':
            fn = fpga_sim.new_testbench(proj_path(a['project']), int(a.get('run_ns') or 10000), bool(a.get('wiggle')))
            log('New testbench %s in %s: open it, set the inputs, press Simulate.' % (fn, a['project']), 'ok')
            return {'ok': True, 'name': fn}
        if path == '/api/sim/run':
            return run_job('Simulate', simulate, a['project'], a.get('tb') or '', int(float(a.get('ns') or 100000)))
        if path == '/api/sim/waves':
            w = SIM_LAST.get(a['project'])
            return dict(ok=True, **w) if w else {'ok': False, 'out': 'no simulation of this project yet'}
        if path == '/api/verify':
            return run_job('Check', verify, a['project'])
        if path == '/api/upload':
            return run_job('Upload', upload, a['project'], a.get('run', True), a.get('default', False))
        if path == '/api/build':
            return run_job('Build FPGA', build_fpga, a['project'])
        if path == '/api/savelog':                 # the monitor (or another panel) saved as a text file
            d = os.path.join(ws(), '_logs')           # ('_': not listed as a project)
            os.makedirs(d, exist_ok=True)
            name = re.sub(r'[^A-Za-z0-9_-]+', '_', str(a.get('name') or 'log'))[:40] or 'log'
            ext = 'csv' if a.get('ext') == 'csv' else 'txt'
            f = os.path.join(d, '%s-%s.%s' % (name, time.strftime('%Y%m%d-%H%M%S'), ext))
            with open(f, 'w', encoding='utf-8', newline='\r\n') as fh:
                fh.write(str(a.get('text') or ''))
            return {'ok': True, 'path': f}
        if path == '/api/open':
            what = a.get('what')
            if what == 'folder':
                startfile(proj_path(a['project']) if a.get('project') else ws())
            elif what == 'web' and board.host:
                # browsers cannot open IPv6 link-local addresses (zone id): use the name then
                url = ('http://%s.local' % board.info.get('hostname', 'ardzy')) if ':' in board.host else board.base
                with child_safe():
                    webbrowser.open(url)
            elif what == 'vivado':
                xpr = glob.glob(os.path.join(proj_path(a['project']), '**', '*.xpr'), recursive=True)
                startfile(xpr[0] if xpr else proj_path(a['project']))
            elif what == 'docs':
                docs = os.path.normpath(os.path.join(ws(), '..', '..', '..', 'Documents'))
                startfile(docs if os.path.isdir(docs) else ws())
            return {'ok': True}
        if path == '/api/libs/search':
            return dict(ok=True, **arduino.search(a.get('q', ''), int(a.get('limit', 80))))
        if path == '/api/libs/installed':
            return {'ok': True, 'libraries': [l.info() for l in arduino.installed()],
                    'builtin': sorted(arduino_support.BUILTIN), 'folder': arduino.libdir}
        if path == '/api/libs/install':
            return run_job('Install library', arduino.install, a['name'])
        if path == '/api/libs/remove':
            arduino.remove(a['name'])
            return {'ok': True}
        if path == '/api/libs/zip':
            zp = pick_file('ZIP library (*.zip)')
            if not zp:
                return {'ok': False, 'out': 'no file chosen'}
            return run_job('Install library', arduino.install_zip, zp)
        if path == '/api/examples':
            return {'ok': True, 'examples': arduino.examples()}
        if path == '/api/examples/new':
            src = os.path.normpath(a['path'])
            allowed = [os.path.normpath(ARDUINO_EXAMPLES), os.path.normpath(arduino.libdir)]
            if not any(src.startswith(x) for x in allowed if x):
                raise ValueError('not an example folder')
            arduino.new_from_example(src, proj_path(a['name']))
            log('New project %s from example %s' % (a['name'], os.path.basename(src)), 'ok')
            return {'ok': True}
        if path == '/api/board/serial_in':
            return board.call('POST', '/api/serial/send?text=%s&nl=%s' % (q(a.get('text', '')), '1' if a.get('nl', True) else '0'))
        if path == '/api/sd/disks':
            return {'ok': True, 'disks': sdflash.list_disks()}
        if path == '/api/sd/images':
            return {'ok': True, 'images': sdflash.find_images(release_dirs())}
        if path == '/api/sd/pick':
            f = pick_file('Ardzy SD image (*.img.xz;*.img)')
            return {'ok': bool(f), 'path': f or '', 'size': os.path.getsize(f) if f else 0}
        if path == '/api/sd/flash':
            disk = next((d for d in sdflash.list_disks() if d['number'] == int(a['disk'])), None)
            if not disk or not disk['ok']:
                raise ValueError('that disk can not be written: ' + (disk['why'] if disk else 'not found'))
            if disk['size'] != int(a['size']) or disk['name'] != a['name']:
                raise ValueError('the card changed since the list was made: choose it again')
            img = a['image']
            if not os.path.isfile(img) or not img.lower().endswith(('.img', '.img.xz')):
                raise ValueError('choose an Ardzy image file (.img.xz)')
            tag = time.strftime('%Y%m%d_%H%M%S')
            job = {'disk': disk['number'], 'name': disk['name'], 'size': disk['size'], 'serial': disk['serial'],
                   'image': os.path.abspath(img), 'verify': bool(a.get('verify', True)), 'settings': a.get('settings') or {},
                   'progress': os.path.join(tempfile.gettempdir(), 'ardzy_flash_%s.json' % tag)}
            jp = os.path.join(tempfile.gettempdir(), 'ardzy_flash_%s_job.json' % tag)
            json.dump(job, open(jp, 'w'))
            log('Writing %s to %s (%d GB, disk %d) ...' % (os.path.basename(img), disk['name'], disk['size'] >> 30, disk['number']), 'head')
            with child_safe():
                sdflash.start(jp)
            return {'ok': True, 'progress': job['progress']}
        if path == '/api/sd/progress':
            pp = os.path.abspath(a['progress'])
            if not (os.path.basename(pp).startswith('ardzy_flash_') and os.path.dirname(pp) == os.path.abspath(tempfile.gettempdir())):
                raise ValueError('bad progress file')
            if not os.path.exists(pp):
                return {'ok': True, 'phase': 'starting', 'text': 'waiting for Windows (administrator permission) ...'}
            st = json.load(open(pp))
            if st.get('phase') in ('done', 'error') and not st.get('_logged'):
                log('SD card: ' + st.get('text', ''), 'ok' if st.get('ok') else 'err')
                st['_logged'] = True
                json.dump(st, open(pp, 'w'))
            return dict(st, ok=True, success=st.get('ok'))
        if path == '/api/board/config':
            if method == 'GET':
                return board.call('GET', '/api/config', timeout=10)
            body = json.dumps({k: v for k, v in a.items() if k in ('hostname', 'password', 'network', 'address', 'gateway',
                                                                     'dns', 'timezone', 'ssh', 'at_boot')}).encode()
            r = board.call('POST', '/api/config', data=body, timeout=30)
            log('Board settings: ' + (r.get('out') or 'saved').replace('ardzy-config: ', ''), 'ok' if r.get('ok') else 'err')
            return r
        if path == '/api/board/update':
            pth = a.get('path') or pick_file('Ardzy update (*.tar.gz)')
            if not pth:
                return {'ok': False, 'out': 'no file chosen'}
            return run_job('System update', system_update, pth)
        if path == '/api/board/update/status':
            try:
                st = board.call('GET', '/api/update/status', timeout=10)
            except urllib.error.HTTPError:
                st = {'ok': True, 'release': board.info.get('image', {}), 'kernel': board.info.get('kernel', ''),
                      'last': 'this board runs Ardzy 0.1: install the 0.2 update to get settings and safe updates'}
            except (urllib.error.URLError, OSError) as e:
                st = {'ok': False, 'out': 'board not reachable (%s)' % e}
            return dict(st, bundles=find_bundles())
        if path == '/api/fpga/toolchain':
            return {'ok': True, 'builtin': fpga_flow.available(), 'tool': settings.get('fpga_tool', 'builtin'),
                    'dir': fpga_flow.tools_dir()}
        if path == '/api/settings':
            if a.get('fpga_tool') in ('builtin', 'vivado'):
                settings['fpga_tool'] = a['fpga_tool']
            for k in ('workspace', 'vivado'):
                if a.get(k):
                    settings[k] = a[k]
            if 'manual_hosts' in a:
                settings['manual_hosts'] = [h.strip() for h in a['manual_hosts'] if h.strip()]
            settings.save()
            return {'ok': True, 'settings': settings}
        if path == '/api/serial/ports':
            return {'ok': True, 'ports': Serial.ports(), 'open': serial_con.port if serial_con.ser else None}
        if path == '/api/serial/open':
            serial_con.open(a['port'], int(a.get('baud', 115200)))
            return {'ok': True}
        if path == '/api/serial/close':
            serial_con.close()
            return {'ok': True}
        if path == '/api/serial/send':
            serial_con.write(a.get('text', ''))
            return {'ok': True}
        raise ValueError('unknown api ' + path)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def auto_connect():
    """At start: reconnect to the last board, else connect if exactly one board is found."""
    last = last_board()
    if last:
        try:
            board.connect(*last)
            log('Reconnected to %s (%s)' % (board.info.get('hostname'), board.host), 'ok')
            return
        except Exception:
            pass
    boards = discover()
    if len(boards) == 1:
        b = boards[0]
        try:
            board.connect(b['host'], b.get('port', 80))
            log('Board found and connected: %s (%s)' % (b.get('hostname'), b['host']), 'ok')
        except Exception as e:
            log('Board found but not reachable: %s' % e, 'err')
    elif boards:
        log('%d boards found: choose one in the board list.' % len(boards), 'head')
    else:
        log('No board found yet. Check the cable and power, then click Scan.', 'warn')


# Ports Chromium (and so the WebView2 window) refuses to load ("ERR_UNSAFE_PORT"): a random free port can be one
# of them (6697 happened), and the window would stay blank. From Chromium's net/base/port_util.cc.
UNSAFE_PORTS = {1, 7, 9, 11, 13, 15, 17, 19, 20, 21, 22, 23, 25, 37, 42, 43, 53, 69, 77, 79, 87, 95, 101, 102, 103, 104,
                109, 110, 111, 113, 115, 117, 119, 123, 135, 137, 139, 143, 161, 179, 389, 427, 465, 512, 513, 514, 515,
                526, 530, 531, 532, 540, 548, 554, 556, 563, 587, 601, 636, 989, 990, 993, 995, 1719, 1720, 1723, 2049,
                3659, 4045, 4190, 5060, 5061, 6000, 6566, 6665, 6666, 6667, 6668, 6669, 6679, 6697, 10080}


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--flash':        # the SD card writer (run as administrator)
        sdflash.flash(json.load(open(sys.argv[2])))
        return
    srv = Server(('127.0.0.1', 0), Handler)
    while srv.server_address[1] in UNSAFE_PORTS:       # the window (Chromium / WebView2) refuses these ports
        srv.server_close()
        srv = Server(('127.0.0.1', 0), Handler)
    url = 'http://127.0.0.1:%d/' % srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log('Ardzy %s %s  -  workspace: %s' % (APP_VERSION, APP_STAGE, ws()), 'head')
    threading.Thread(target=auto_connect, daemon=True).start()
    threading.Thread(target=clock_keeper, daemon=True).start()
    if '--browser' in sys.argv or '--serve' in sys.argv:
        print('Ardzy running at', url, flush=True)
        if '--browser' in sys.argv:
            webbrowser.open(url)
        while True:
            time.sleep(3600)
    unblock_downloaded_files()
    try:
        import webview
        webview.create_window('Ardzy %s %s' % (APP_VERSION, APP_STAGE), url, width=1360, height=860, min_size=(900, 600))
        webview.start()
        return
    except Exception as e:                      # no window possible: the same app in the web browser
        log('app window not available (%s): opening Ardzy in the web browser' % e, 'warn')
    webbrowser.open(url)
    while True:
        time.sleep(3600)


def unblock_downloaded_files():
    """Files unzipped from a downloaded zip carry Windows' "from the internet" mark (Zone.Identifier), and .NET
    refuses to load a marked DLL, so the app window (pythonnet) could not start. Remove the mark from our own files."""
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        return
    for d, _, files in os.walk(os.path.dirname(sys.executable)):     # the Ardzy folder (with _internal)
        for f in files:
            if f.lower().endswith(('.dll', '.exe', '.pyd')):
                try:
                    os.remove(os.path.join(d, f) + ':Zone.Identifier')
                except OSError:
                    pass


if __name__ == '__main__':
    main()
