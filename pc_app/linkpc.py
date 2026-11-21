"""Ardzy - the PC end of the serial link (ardzy_link.py has the frames and the board end).

open_link(port, ...) does what a person would do on the console, then hands the cable to the link:
  1. is a link already running there (an earlier app session)? -> use it
  2. log in (root / your password), quiet the echo
  3. is ardzy_link.py on the board, the same version? if not, copy it over (base64, ~3 s at 115200)
  4. exec python3 ardzy_link.py board  -> its "hello" frame
  5. agree on a higher speed (921600 ...) and check it with pings; back to 115200 if the adapter can not
"""
import base64, hashlib, json, os, re, sys, time

import ardzy_link as L

# (in the packaged app, ardzy_link.py is a data file in the app's folder: build_exe.bat --add-data)
HERE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
ANSI = re.compile(rb'\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Z0-9]')


class NoAnswer(ConnectionError):
    pass


class PySerialIO:
    def __init__(self, ser):
        self.ser = ser

    def read(self, n):
        sock = getattr(self.ser, '_socket', None)          # socket:// (tests): its in_waiting is only 0 or 1
        if sock is not None:
            import select
            r, _, _ = select.select([sock], [], [], 0.2)
            if not r:
                return b''
            d = sock.recv(n)
            if not d:
                raise ConnectionError('closed')
            return d
        first = self.ser.read(1)                           # waits up to the timeout (0.2 s) for the first byte
        if not first:
            return b''
        more = self.ser.in_waiting
        return first + (self.ser.read(min(n - 1, more)) if more else b'')

    def write(self, data):
        self.ser.write(data)

    def set_baud(self, baud):
        self.ser.baudrate = baud

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass


def link_source():
    """The bytes of ardzy_link.py that go to the board (and their short sha256)."""
    data = open(os.path.join(HERE, 'ardzy_link.py'), 'rb').read().replace(b'\r\n', b'\n')
    return data, hashlib.sha256(data).hexdigest()[:16]


class Console:
    """Talking to the login console like a person (text, prompts)."""

    def __init__(self, io, log):
        self.io, self.log, self.text = io, log, b''

    def write(self, s):
        self.io.write(s.encode() if isinstance(s, str) else s)

    def read_for(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            d = self.io.read(4096)
            if d:
                self.text = (self.text + d)[-8192:]

    def expect(self, pattern, timeout):
        """Wait until the text since the last call matches; returns the match (or None)."""
        self.text = self.clean = b''
        rx = re.compile(pattern.encode() if isinstance(pattern, str) else pattern)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            d = self.io.read(4096)
            if d:
                self.text = (self.text + d)[-16384:]
                self.clean = ANSI.sub(b'', self.text).replace(b'\r', b'')
                m = rx.search(self.clean)
                if m:
                    return m
        return None

    def run(self, cmd, n, timeout=8):
        """Run a shell command; the marker AZ_<n> (made by the shell, so the echo of the command never
        matches) says it is done. Returns the output before the marker."""
        self.write('%s; echo AZ_$((%d+0))_END\r' % (cmd, n))
        m = self.expect(r'AZ_%d_END' % n, timeout)
        if not m:
            raise TimeoutError('the board did not finish: %s' % cmd[:60])
        return self.clean[:m.start()].decode(errors='replace')


def ping_raw(io, timeout=0.6):
    """Is a link already there? (a ping frame; nothing else is sent)"""
    io.write(L.encode('P', 0, b'probe'))
    dec, end = L.Decoder(), time.monotonic() + timeout
    while time.monotonic() < end:
        for typ, _cid, _p in dec.feed(io.read(4096)):
            if typ == 'p':
                return True
    return False


def wait_hello(io, timeout):
    dec, end, seen = L.Decoder(), time.monotonic() + timeout, b''
    while time.monotonic() < end:
        d = io.read(4096)
        seen = (seen + d)[-2000:]
        for typ, _cid, payload in dec.feed(d):
            if typ == 'H':
                return json.loads(payload)
    tail = ANSI.sub(b'', seen).decode(errors='replace').strip()[-300:]
    raise ConnectionError('the link did not start on the board' + (': ' + tail if tail else ''))


def open_link(port, baud=921600, user='root', password='root', log=print, ser=None):
    """Returns (Link, io, hello). `ser` (tests): an open pyserial-like object instead of opening `port`."""
    if ser is None:
        import serial
        ser = serial.serial_for_url(port, L.BASE_BAUD, timeout=0.2, write_timeout=10)
    io = PySerialIO(ser)
    try:
        hello, current = None, L.BASE_BAUD
        # 1. a link from an earlier session (it is back at 115200 when it heard nothing for 20 s)
        if ping_raw(io):
            log('  the serial link is already running on the board')
            hello = {'version': None, 'reused': True}
        else:
            try:
                hello = start_on_console(io, user, password, log)
            except NoAnswer:
                # a silent console: maybe a link at a higher speed (the app ended less than 20 s ago)
                for b in [x for x in L.SPEEDS if x != L.BASE_BAUD]:
                    io.set_baud(b)
                    if ping_raw(io):
                        log('  the serial link is already running on the board (%d baud)' % b)
                        hello, current = {'version': None, 'reused': True}, b
                        break
                if hello is None:
                    io.set_baud(L.BASE_BAUD)
                    raise
        link = L.Link(io, 'pc')
        link.baud = current
        if not link.ping(1.5):
            raise ConnectionError('the link started but does not answer pings')
        if baud and baud != current:
            speed_up(link, io, baud, log)
        return link, io, hello
    except Exception:
        io.close()
        raise


def start_on_console(io, user, password, log):
    con = Console(io, log)
    con.write(b'\x03')                          # stop whatever runs there (a program, half a command)
    time.sleep(0.2)
    con.write(b'\r')
    m = con.expect(r'(login: ?$|[Pp]assword: ?$|[#$] ?$)', 3)
    if not m:
        con.write(b'\r')
        m = con.expect(r'(login: ?$|[Pp]assword: ?$|[#$] ?$)', 4)
    if not m:
        heard = ANSI.sub(b'', con.text).decode(errors='replace').strip()
        if heard:
            raise ConnectionError('the board answers, but not with a login or a shell (%r): is it still starting? '
                                  'Try again in a few seconds.' % heard[-80:])
        raise NoAnswer('no answer on this port. Check: board on, TX of the adapter to RX of the board, '
                              'RX to TX, GND to GND, 3.3 V levels, and the right COM port.')
    what = m.group(1).decode()
    if 'assword' in what:                         # a half login from before: start again
        con.write(b'\r')
        m = con.expect(r'(login: ?$)', 5)
        what = 'login:' if m else what
    if 'login' in what:
        log('  logging in as %s ...' % user)
        con.write(user + '\r')
        if not con.expect(r'[Pp]assword: ?$', 6):
            raise ConnectionError('no password question after the user name')
        con.write(password + '\r')
        m = con.expect(r'([#$] ?$|[Ii]ncorrect|[Ff]ailure)', 15)
        if not m or m.group(1)[:1] not in (b'#', b'$'):
            raise PermissionError('login failed: wrong user name or password (Settings, Serial link)')
    con.run('stty -echo', 1)
    data, sha = link_source()
    out = con.run('P=; for f in /opt/ardzy/web/ardzy_link.py /var/lib/ardzy/ardzy_link.py /tmp/ardzy_link.py; do '
                  '[ "$(sha256sum $f 2>/dev/null | cut -c1-16)" = "%s" ] && P=$f && break; done; echo "AZ_P=$P"' % sha, 2)
    path = (re.search(r'AZ_P=(\S*)', out) or [None, ''])[1]
    if not path:
        log('  copying the link program to the board (%d KB) ...' % (len(data) // 1024 + 1))
        t = time.time()
        con.run('D=/var/lib/ardzy; mkdir -p $D 2>/dev/null; [ -w $D ] || D=/tmp', 3)
        lines = base64.encodebytes(data).decode().split('\n')
        con.write("base64 -d > $D/ardzy_link.py.part <<'AZEOF'\r")
        for i in range(0, len(lines), 24):       # a few lines, then wait for the shell (its tty buffer is 4 KB)
            part = '\r'.join(x for x in lines[i:i + 24] if x) + '\r'
            con.write(part)
            con.expect(r'> ?$', 3)
        con.write('AZEOF\r')
        out = con.run('mv -f $D/ardzy_link.py.part $D/ardzy_link.py && P=$D/ardzy_link.py; '
                      'echo "AZ_S=$(sha256sum $P | cut -c1-16) AZ_P=$P"', 4, timeout=10)
        got = (re.search(r'AZ_S=(\w+)', out) or [None, ''])[1]
        path = (re.search(r'AZ_P=(\S*)', out) or [None, ''])[1]
        if got != sha or not path:
            raise ConnectionError('copying the link program failed (check sum %s, expected %s)' % (got or '?', sha))
        log('  copied in %.1f s' % (time.time() - t))
    log('  starting the link on the board ...')
    con.write('exec python3 %s board\r' % path)
    return wait_hello(io, 12)


def speed_up(link, io, baud, log):
    ans = link.wait_for('s', ('S', 0, json.dumps({'baud': baud}).encode()), 2)
    if not ans or not json.loads(ans).get('ok'):
        log('  the board stays at %d baud' % link.baud, 'warn')
        return
    time.sleep(0.25)                          # the board switches as soon as its answer has gone out
    io.set_baud(baud)
    link.baud = baud
    for _ in range(4):
        if link.ping(0.5):
            log('  speed: %d baud (about %d KB/s)' % (baud, baud // 10240))
            return
    io.set_baud(L.BASE_BAUD)                  # the adapter or the wires can not: the board goes back after 3 s
    link.baud = L.BASE_BAUD
    time.sleep(3.3)
    if link.ping(1.5):
        log('  %d baud did not work with this adapter: staying at %d baud (about 11 KB/s)' % (baud, L.BASE_BAUD), 'warn')
        return
    raise ConnectionError('the link was lost while changing the speed')
