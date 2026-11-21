#!/usr/bin/env python3
"""Ardzy serial link: the whole app over a USB-UART cable (no network cable needed).

One file, two ends:
  * on the PC   the app imports it (class Link, role 'pc') and opens the COM port;
  * on the board  `python3 ardzy_link.py board` runs on the serial console (ttyPS0): the app logs in,
                copies this file to the board when it is missing or older, and starts it with `exec`.
                It takes over the console until the app says goodbye; then the login prompt is back.

Every board call of the app (the same HTTP API as over the network) travels as frames:

    0x7E | escaped( type 1 byte | id 2 bytes | payload | CRC-32 4 bytes ) | 0x7E

0x7E, 0x7D, XON and XOFF inside a frame are sent as 0x7D, byte ^ 0x20. A frame with a wrong CRC is dropped
(the call it belongs to times out and the app tells you). Frame types:

    Q  request header (JSON: m, path, port, len, t)      R  response header (JSON: status, len, ctype)
    D  body bytes of the request / response with this id  P / p  ping / pong
    S / s  change speed (JSON baud) / agreed              H  hello (JSON: the board side's version)
    X  goodbye: the board side ends and gives the console back

The board side answers /api/term/* itself (a shell on a pseudo terminal, class Terminals), so the terminal
works over the cable on every board; other paths go to the board's web service on 127.0.0.1.
Pure Python standard library on the board (pyserial is used only on the PC).
"""
import base64, collections, json, os, select, sys, threading, time, zlib

VERSION = 1
FLAG, ESC = 0x7E, 0x7D
ESCAPED = (0x7E, 0x7D, 0x11, 0x13)
CHUNK = 1024                       # body bytes per frame (small: a terminal key never waits long behind a file)
MAX_BODY = 160 * 1024 * 1024
SPEEDS = (921600, 460800, 230400, 115200)
BASE_BAUD = 115200


# ------------------------------------------------------------------ frames
def encode(typ, cid, payload=b''):
    body = bytes((ord(typ),)) + (cid & 0xFFFF).to_bytes(2, 'big') + payload
    body += zlib.crc32(body).to_bytes(4, 'big')
    out = bytearray((FLAG,))
    for b in body:
        if b in ESCAPED:
            out += bytes((ESC, b ^ 0x20))
        else:
            out.append(b)
    out.append(FLAG)
    return bytes(out)


class Decoder:
    """Bytes in, frames out: [(type, id, payload)]. Counts frames with a wrong CRC in .bad."""

    def __init__(self):
        self.buf, self.esc, self.bad, self.good = bytearray(), False, 0, 0

    def feed(self, data):
        frames = []
        for b in data:
            if b == FLAG:
                if len(self.buf) >= 7:
                    body, crc = bytes(self.buf[:-4]), bytes(self.buf[-4:])
                    if zlib.crc32(body).to_bytes(4, 'big') == crc:
                        frames.append((chr(body[0]), int.from_bytes(body[1:3], 'big'), body[3:]))
                        self.good += 1
                    else:
                        self.bad += 1
                elif self.buf:
                    self.bad += 1
                self.buf.clear()
                self.esc = False
            elif b == ESC:
                self.esc = True
            else:
                self.buf.append(b ^ 0x20 if self.esc else b)
                self.esc = False
                if len(self.buf) > CHUNK + 4096:          # noise without a flag: forget it
                    self.buf.clear()
        return frames

    def pending(self):
        return bytes(self.buf)


# ------------------------------------------------------------------ the link (both ends)
class Link:
    """io: an object with read(n) -> bytes (returns b'' after a short timeout), write(bytes),
    and optionally set_baud(baud). role: 'pc' or 'board'."""

    def __init__(self, io, role, on_frame=None):
        self.io, self.role = io, role
        self.dec = Decoder()
        self.hi = collections.deque()          # small frames first (headers, pings, terminal keys)
        self.lo = collections.deque()          # iterators of body frames (big transfers, round robin)
        self.cv = threading.Condition()
        self.waiting = {}                      # id -> dict(header, body, done event)
        self.incoming = {}                     # board: id -> request being received
        self.next_id = 1
        self.last_rx = time.monotonic()
        self.alive = True
        self.on_frame = on_frame
        self.events = {}                       # 'p', 's', 'H' -> threading.Event (+ payload)
        self.baud = BASE_BAUD
        self.rx_bytes = self.tx_bytes = 0
        threading.Thread(target=self._sender, daemon=True).start()
        threading.Thread(target=self._reader, daemon=True).start()

    # ---- sending
    def send(self, typ, cid=0, payload=b''):
        with self.cv:
            self.hi.append(encode(typ, cid, payload))
            self.cv.notify()

    def send_body(self, cid, data):
        def frames():
            for i in range(0, len(data), CHUNK):
                yield encode('D', cid, data[i:i + CHUNK])
        if data:
            with self.cv:
                self.lo.append(frames())
                self.cv.notify()

    def idle(self):
        with self.cv:
            return not self.hi and not self.lo

    def _sender(self):
        while self.alive:
            with self.cv:
                while self.alive and not self.hi and not self.lo:
                    self.cv.wait(0.5)
                if not self.alive:
                    return
                if self.hi:
                    frame = self.hi.popleft()
                else:
                    it = self.lo[0]
                    frame = next(it, None)
                    self.lo.rotate(-1)
                    if frame is None:
                        self.lo.remove(it)
                        continue
            try:
                self.io.write(frame)
                self.tx_bytes += len(frame)
            except Exception as e:
                self.alive = False
                self._fail_all('the serial port stopped working (%s)' % e)
                return

    # ---- receiving
    def _reader(self):
        while self.alive:
            try:
                data = self.io.read(4096)
            except Exception as e:
                self.alive = False
                self._fail_all('the serial port stopped working (%s)' % e)
                return
            if not data:
                continue
            self.rx_bytes += len(data)
            for typ, cid, payload in self.dec.feed(data):
                self.last_rx = time.monotonic()
                try:
                    self._frame(typ, cid, payload)
                except Exception as e:                  # a bad frame must never stop the link
                    sys.stderr.write('ardzy-link: %s\n' % e)

    def _frame(self, typ, cid, payload):
        if typ == 'P':
            return self.send('p', cid, payload)
        if typ in ('p', 's', 'H'):
            ev = self.events.get(typ)
            if ev:
                ev.payload = payload
                ev.set()
            return
        if self.on_frame and self.on_frame(self, typ, cid, payload):
            return
        if typ == 'R' and cid in self.waiting:          # pc: a response starts
            w = self.waiting[cid]
            w['head'] = json.loads(payload)
            w['body'] = bytearray()
            if w['head'].get('len', 0) == 0:
                w['done'].set()
        elif typ == 'D':
            w = self.waiting.get(cid) if self.role == 'pc' else self.incoming.get(cid)
            if w is not None and w.get('body') is not None:
                w['body'] += payload
                if len(w['body']) >= w['head'].get('len', 0):
                    w['done'].set()

    def _fail_all(self, why):
        for w in list(self.waiting.values()):
            w['error'] = why
            w['done'].set()

    def wait_for(self, typ, send=None, timeout=1.0):
        ev = threading.Event()
        ev.payload = b''
        self.events[typ] = ev
        if send:
            self.send(*send)
        ok = ev.wait(timeout)
        self.events.pop(typ, None)
        return ev.payload if ok else None

    def ping(self, timeout=1.0):
        return self.wait_for('p', ('P', 0, b'ping'), timeout) is not None

    def close(self):
        self.alive = False
        with self.cv:
            self.cv.notify_all()

    # ---- the PC end: an HTTP-like call
    def request(self, method, path, body=None, timeout=10, port=80):
        if not self.alive:
            raise ConnectionError('the serial link is closed')
        body = body or b''
        if len(body) > MAX_BODY:
            raise ValueError('too big for the serial link (%d MB): use the network cable' % (len(body) >> 20))
        with self.cv:
            cid = self.next_id
            self.next_id = self.next_id % 65000 + 1
        w = {'head': None, 'body': None, 'done': threading.Event()}
        self.waiting[cid] = w
        head = {'m': method, 'path': path, 'port': port, 'len': len(body), 't': timeout}
        self.send('Q', cid, json.dumps(head).encode())
        self.send_body(cid, body)
        # the time it takes to move the bytes at this speed counts too (10 bits per byte)
        allow = timeout + 3 + (len(body) * 10.5) / max(self.baud, 9600)
        try:
            while not w['done'].wait(0.25):
                allow -= 0.25
                if w['body'] is not None:                       # data is coming: wait for the rest
                    allow = max(allow, 2 + (w['head'].get('len', 0) - len(w['body'])) * 10.5 / max(self.baud, 9600))
                if allow <= 0:
                    raise TimeoutError('the board did not answer over the serial link (%s)' % path.split('?')[0])
            if w.get('error'):
                raise ConnectionError(w['error'])
            h = w['head']
            return h.get('status', 0), bytes(w['body'] or b''), h
        finally:
            self.waiting.pop(cid, None)


# ------------------------------------------------------------------ the terminal (board)
class Terminals:
    """Shells on pseudo terminals. Output is kept per session (the newest 256 KB) with an offset,
    so a reader that comes back later gets what it missed."""
    KEEP = 256 * 1024
    MAX = 6

    def __init__(self):
        self.s, self.lock, self.n = {}, threading.Lock(), 0

    def open(self, cols=100, rows=30, cmd=None):
        with self.lock:
            for k in [k for k, v in self.s.items() if not v['alive']]:
                self.s.pop(k)
            if len(self.s) >= self.MAX:
                raise ValueError('too many terminals open (%d): close one first' % self.MAX)
            self.n += 1
            tid = str(self.n)
        t = {'id': tid, 'buf': bytearray(), 'start': 0, 'alive': True, 'cv': threading.Condition(), 'used': time.time()}
        if os.name == 'posix':
            import pty
            pid, fd = pty.fork()
            if pid == 0:                                       # the child: a login shell
                # signals as a fresh program expects them: Python ignores SIGPIPE, and a process started in the
                # background ignores SIGINT; inherited, Ctrl+C would not stop a program, `yes | head` would misbehave
                import signal
                for name in ('SIGINT', 'SIGQUIT', 'SIGPIPE', 'SIGTSTP', 'SIGTTIN', 'SIGTTOU', 'SIGHUP', 'SIGXFSZ', 'SIGCHLD'):
                    if hasattr(signal, name):
                        try:
                            signal.signal(getattr(signal, name), signal.SIG_DFL)
                        except (OSError, ValueError):
                            pass
                env = dict(os.environ, TERM='xterm-256color', COLORTERM='truecolor', HOME=os.environ.get('HOME', '/root'))
                env.pop('ARDZY_LINK', None)
                try:
                    os.chdir(env['HOME'])
                except OSError:
                    pass
                argv = cmd or ['/bin/bash', '-l']
                os.execvpe(argv[0], argv, env)
            t['pid'], t['fd'] = pid, fd
            self._size(t, cols, rows)
        else:                                                  # (only for tests on a PC: no real terminal)
            import subprocess
            p = subprocess.Popen(cmd or ['cmd.exe'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            t['proc'] = p
        with self.lock:
            self.s[tid] = t
        threading.Thread(target=self._pump, args=(t,), daemon=True).start()
        return {'id': tid}

    def _size(self, t, cols, rows):
        if 'fd' in t:
            import fcntl, struct, termios
            fcntl.ioctl(t['fd'], termios.TIOCSWINSZ, struct.pack('HHHH', max(2, int(rows)), max(2, int(cols)), 0, 0))

    def _pump(self, t):
        while True:
            try:
                if 'fd' in t:
                    data = os.read(t['fd'], 8192)
                else:
                    data = t['proc'].stdout.read1(8192)
            except OSError:
                data = b''
            with t['cv']:
                if not data:
                    t['alive'] = False
                    t['cv'].notify_all()
                    break
                t['buf'] += data
                if len(t['buf']) > self.KEEP:
                    cut = len(t['buf']) - self.KEEP
                    del t['buf'][:cut]
                    t['start'] += cut
                t['cv'].notify_all()
        if 'pid' in t:
            try:
                os.waitpid(t['pid'], 0)
            except OSError:
                pass

    def get(self, tid):
        t = self.s.get(str(tid))
        if not t:
            raise ValueError('no terminal %s (it was closed)' % tid)
        t['used'] = time.time()
        return t

    def read(self, tid, since=0, wait=0):
        t = self.get(tid)
        since = int(since or 0)
        end = time.monotonic() + min(float(wait or 0), 25.0)
        with t['cv']:
            while t['alive'] and t['start'] + len(t['buf']) <= since and time.monotonic() < end:
                t['cv'].wait(min(0.5, max(0.01, end - time.monotonic())))
            first = max(since, t['start'])
            data = bytes(t['buf'][first - t['start']:])
            return {'data': base64.b64encode(data).decode(), 'next': t['start'] + len(t['buf']),
                    'lost': first > since, 'alive': t['alive']}

    def write(self, tid, data):
        t = self.get(tid)
        if not t['alive']:
            raise ValueError('the shell has ended')
        if 'fd' in t:
            view = memoryview(data)
            while view:
                n = os.write(t['fd'], view)
                view = view[n:]
        else:
            t['proc'].stdin.write(data)
            t['proc'].stdin.flush()
        return {'sent': len(data)}

    def resize(self, tid, cols, rows):
        self._size(self.get(tid), cols, rows)
        return {}

    def close(self, tid):
        t = self.s.pop(str(tid), None)
        if t:
            if 'pid' in t:
                import signal
                for sig in (signal.SIGHUP, signal.SIGKILL):
                    try:
                        os.kill(t['pid'], sig)
                    except OSError:
                        pass
                    time.sleep(0.05)
                try:
                    os.close(t['fd'])
                except OSError:
                    pass
            elif 'proc' in t:
                t['proc'].kill()
        return {}

    def list(self):
        return {'terminals': [{'id': k, 'alive': v['alive'], 'idle_s': int(time.time() - v['used'])} for k, v in self.s.items()]}

    def http(self, method, path, q, body):
        """The /api/term/* calls (the same in the board's web service and over the serial link)."""
        act = path.rsplit('/', 1)[-1]
        if act == 'open':
            return self.open(q.get('cols', 100), q.get('rows', 30))
        if act == 'read':
            return self.read(q.get('id'), q.get('since', 0), q.get('wait', 0))
        if act == 'write':
            return self.write(q.get('id'), body if body else q.get('text', '').encode())
        if act == 'resize':
            return self.resize(q.get('id'), q.get('cols', 100), q.get('rows', 30))
        if act == 'close':
            return self.close(q.get('id'))
        if act == 'list':
            return self.list()
        raise ValueError('unknown terminal call')


def parse_query(path):
    from urllib.parse import urlparse, parse_qs
    u = urlparse(path)
    return u.path, {k: v[0] for k, v in parse_qs(u.query).items()}


# ------------------------------------------------------------------ the board end
class SerialTTY:
    """The console (stdin/stdout = /dev/ttyPS0) in raw mode; its settings come back at the end."""
    RATES = {}

    def __init__(self, fd=0):
        import termios, tty
        self.fd = fd
        self.saved = termios.tcgetattr(fd)
        tty.setraw(fd)
        a = termios.tcgetattr(fd)
        a[2] |= termios.CLOCAL                      # no modem lines
        termios.tcsetattr(fd, termios.TCSANOW, a)
        for b in SPEEDS:
            SerialTTY.RATES[b] = getattr(termios, 'B%d' % b)

    def read(self, n):
        r, _, _ = select.select([self.fd], [], [], 0.2)
        return os.read(self.fd, n) if r else b''

    def write(self, data):
        view = memoryview(data)
        while view:
            n = os.write(self.fd, view)
            view = view[n:]

    def set_baud(self, baud):
        import termios
        termios.tcdrain(self.fd)
        a = termios.tcgetattr(self.fd)
        a[4] = a[5] = SerialTTY.RATES[baud]
        termios.tcsetattr(self.fd, termios.TCSANOW, a)

    def restore(self):
        import termios
        try:
            termios.tcdrain(self.fd)
            termios.tcsetattr(self.fd, termios.TCSANOW, self.saved)
        except Exception:
            pass


class SocketIO:
    """For tests: a TCP connection instead of the serial cable."""

    def __init__(self, sock):
        self.sock = sock
        sock.settimeout(None)                     # (sending a big answer may wait for the reader)

    def read(self, n):
        r, _, _ = select.select([self.sock], [], [], 0.2)
        if not r:
            return b''
        d = self.sock.recv(n)
        if not d:
            raise ConnectionError('closed')
        return d

    def write(self, data):
        self.sock.sendall(data)

    def set_baud(self, baud):
        pass


def board_main(io, http_host='127.0.0.1', idle_exit=None, port_map=None):
    """Serve the app over `io` until it says goodbye (or the console gets 3 Enter keys from a person)."""
    import urllib.request, urllib.error
    terms = Terminals()
    state = {'bye': False, 'switch_at': None, 'old_baud': BASE_BAUD}

    def serve(link, cid, head, body):
        path, q = parse_query(head.get('path', '/'))
        status, ctype, out = 200, 'application/json', b''
        try:
            if path.startswith('/api/term/'):
                out = json.dumps(dict(terms.http(head.get('m'), path, q, body), ok=True)).encode()
            elif path == '/api/link':
                out = json.dumps({'ok': True, 'version': VERSION, 'baud': link.baud, 'bad_frames': link.dec.bad,
                                  'good_frames': link.dec.good}).encode()
            else:
                port = int(head.get('port', 80))
                url = 'http://%s:%d%s' % (http_host, (port_map or {}).get(port, port), head.get('path', '/'))
                req = urllib.request.Request(url, data=body if head.get('m') in ('POST', 'PUT') else None,
                                             method=head.get('m', 'GET'))
                if body:
                    req.add_header('Content-Type', 'application/octet-stream')
                try:
                    with urllib.request.urlopen(req, timeout=float(head.get('t', 10)) + 2) as r:
                        status, ctype, out = r.status, r.headers.get('Content-Type', ''), r.read()
                except urllib.error.HTTPError as e:
                    status, ctype, out = e.code, e.headers.get('Content-Type', ''), e.read()
        except (ValueError, OSError) as e:
            status, out = (200, json.dumps({'ok': False, 'out': str(e)}).encode()) if path.startswith('/api/term/') \
                else (502, json.dumps({'ok': False, 'out': 'board web service: %s' % e}).encode())
        link.send('R', cid, json.dumps({'status': status, 'len': len(out), 'ctype': ctype}).encode())
        link.send_body(cid, out)

    def on_frame(link, typ, cid, payload):
        if typ == 'Q':
            head = json.loads(payload)
            if head.get('len', 0) > MAX_BODY:
                link.send('R', cid, json.dumps({'status': 413, 'len': 0}).encode())
                return True
            r = {'head': head, 'body': bytearray(), 'done': threading.Event()}
            link.incoming[cid] = r
            if not head.get('len'):
                r['done'].set()

            def run():
                if r['done'].wait(30 + head.get('len', 0) * 10.5 / max(link.baud, 9600)):
                    serve(link, cid, head, bytes(r['body']))
                link.incoming.pop(cid, None)
            threading.Thread(target=run, daemon=True).start()
            return True
        if typ == 'S':
            baud = int(json.loads(payload).get('baud', BASE_BAUD))
            if baud not in SPEEDS:
                link.send('s', cid, json.dumps({'ok': False}).encode())
                return True
            link.send('s', cid, json.dumps({'ok': True, 'baud': baud}).encode())
            state['old_baud'], state['new_baud'] = link.baud, baud
            state['switch_at'] = time.monotonic()
            return True
        if typ == 'X':
            state['bye'] = True
            return True
        return False

    link = Link(io, 'board', on_frame)
    link.send('H', 0, json.dumps({'version': VERSION, 'pid': os.getpid()}).encode())
    last_len, quiet_since = 0, time.monotonic()
    while link.alive and not state['bye']:
        time.sleep(0.05)
        now = time.monotonic()
        if state['switch_at'] is not None and now - state['switch_at'] > 0.05 and link.idle():
            time.sleep(0.05)
            io.set_baud(state['new_baud'])
            link.baud = state['new_baud']
            switched, state['switch_at'] = now, None
            link.last_rx = switched
            state['check_from'] = switched
        # after a speed change the app must be heard within 3 s; else back to the old speed
        if state.get('check_from') and now - state['check_from'] > 3:
            if link.last_rx <= state['check_from']:
                io.set_baud(state['old_baud'])
                link.baud = state['old_baud']
            state['check_from'] = None
        # the app is gone (no frame for 20 s): back to 115200, so it finds this side again
        if link.baud != BASE_BAUD and now - link.last_rx > 20:
            io.set_baud(BASE_BAUD)
            link.baud = BASE_BAUD
        if idle_exit and now - link.last_rx > idle_exit:
            break
        # a person typed Enter three times on a terminal program (not the app): give the console back
        pend = link.dec.pending()
        if len(pend) != last_len:
            last_len, quiet_since = len(pend), now
        elif pend.endswith(b'\r\r\r') and now - quiet_since > 1 and now - link.last_rx > 2:
            break
    time.sleep(0.2)                                  # let the last frames go out
    link.close()
    for k in list(terms.s):
        terms.close(k)


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == 'board':
        if '--tcp' in sys.argv:                      # tests: --tcp PORT (listen once) [--bind ADDR] [--http HOST]
            import socket
            port = int(sys.argv[sys.argv.index('--tcp') + 1])
            srv = socket.socket()
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.settimeout(120)                      # nobody came: give up
            srv.bind((sys.argv[sys.argv.index('--bind') + 1] if '--bind' in sys.argv else '127.0.0.1', port))
            srv.listen(1)
            conn, _ = srv.accept()
            board_main(SocketIO(conn), sys.argv[sys.argv.index('--http') + 1] if '--http' in sys.argv else '127.0.0.1')
            return
        # on the console: quiet kernel messages (they would break frames), raw mode; all back at the end
        level = None
        try:
            level = open('/proc/sys/kernel/printk').read().split()[0]
            open('/proc/sys/kernel/printk', 'w').write('1')
        except OSError:
            pass
        io = SerialTTY(0)
        try:
            board_main(io)
        finally:
            io.set_baud(BASE_BAUD)
            io.restore()
            if level:
                try:
                    open('/proc/sys/kernel/printk', 'w').write(level)
                except OSError:
                    pass
            sys.stdout.write('\r\nArdzy serial link ended: the console is yours again.\r\n')
            sys.stdout.flush()
        return
    print(__doc__)


if __name__ == '__main__':
    main()
