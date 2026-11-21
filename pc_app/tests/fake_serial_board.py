"""A pretend Ardzy board on a TCP port, for testing the serial link without a board or Linux.

    python fake_serial_board.py [console port 9501] [http port 9580]

* the console (TCP, used by the app as  socket://127.0.0.1:9501): a login prompt (root / root), a shell prompt,
  and the few shell commands the app sends (stty, the check sum loop, the base64 copy, exec). "exec python3
  .../ardzy_link.py board" runs the REAL board end of the link (ardzy_link.board_main) on that connection.
* a small stand-in for the board's web service (/api/info, /api/status, /api/log, echo, port 8080 -> same).
Prints what happens. Every new connection is a new console (like the board after the link ended)."""
import base64, hashlib, http.server, json, os, re, socket, socketserver, sys, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import ardzy_link  # noqa: E402

CON_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9501
HTTP_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 9580
FS = tempfile.mkdtemp(prefix='fakeboard_')          # stands for /var/lib/ardzy and /tmp
PASSWORD = os.environ.get('FAKE_PASSWORD', 'root')
STATS = {'logins': 0, 'copies': 0, 'links': 0}


def real(path):
    return os.path.join(FS, os.path.basename(path)) if path else ''


class Web(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.split('?')[0]
        if p == '/api/info':
            return self.reply({'ardzy': '0.3', 'started': 'fake-1', 'hostname': 'ardzy', 'port': 80, 'model': 'Fake Antminer S9 (test)',
                               'kernel': '6.18.0-xilinx-s9', 'os': 'Debian GNU/Linux 13 (trixie)', 'ips': [], 'ipv6': [],
                               'mac': '00:00:00:00:00:00', 'chip': 'XC7Z010', 'fpga': 'operating', 'board': 's9',
                               'board_name': 'Antminer S9', 'current': 'blink', 'image': {'ARDZY': '0.3'}})
        if p == '/api/status':
            return self.reply({'current': 'blink', 'default': '', 'running': True, 'safemode': False, 'fpga': 'operating',
                               'uptime': '0h 05m', 'mem': '80 / 488 MB', 'temp': '47.0 C', 'load': '0.10',
                               'projects': [{'name': 'blink', 'files': ['blink.bit', 'main.py']}]})
        if p == '/api/log':
            return self.reply({'log': 'hello from the fake board\n', 'lines': ['hello from the fake board'], 'cursor': 'c1'})
        if p == '/api/big':
            n = int(self.path.split('n=')[1]) if 'n=' in self.path else 100000
            data = bytes(i & 0xFF for i in range(n))
            self.send_response(200)
            self.send_header('Content-Length', str(n))
            self.end_headers()
            return self.wfile.write(data)
        if p == '/api/missing':
            return self.reply({'ok': False}, 404)
        return self.reply({'ok': True, 'path': self.path})

    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0) or 0)
        body = self.rfile.read(n) if n else b''
        return self.reply({'ok': True, 'got': len(body), 'sha': hashlib.sha256(body).hexdigest(), 'path': self.path})

    do_PUT = do_POST


class Srv(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def console(conn):
    """One login session on the console (like agetty + bash, only what the app uses)."""
    def out(s):
        conn.sendall(s.encode() if isinstance(s, str) else s)

    buf, state, echo, env, doc = b'', 'login', True, {}, None
    user = None
    conn.settimeout(None)
    while True:
        d = conn.recv(4096)
        if not d:
            return
        for ch in d:
            c = bytes((ch,))
            if c == b'\x03':
                buf = b''
                if state == 'shell':
                    out('^C\r\n' + prompt())
                continue
            if c != b'\r':
                buf += c
                if echo and state == 'shell' and doc is None:
                    out(c)
                continue
            line, buf = buf.decode(errors='replace'), b''
            if state == 'login':
                if not line.strip():
                    out('\r\n\r\nDebian GNU/Linux 13 ardzy ttyPS0\r\n\r\nardzy login: ')
                else:
                    user, state = line.strip(), 'password'
                    out('\r\nPassword: ')
            elif state == 'password':
                if user == 'root' and line == PASSWORD:
                    STATS['logins'] += 1
                    state = 'shell'
                    out('\r\nLinux ardzy 6.18.0-xilinx-s9 armv7l\r\n\r\nArdzy 0.3 BETA\r\nLast login: today\r\n' + prompt())
                else:
                    time.sleep(0.5)
                    state = 'login'
                    out('\r\n\r\nLogin incorrect\r\nardzy login: ')
            elif doc is not None:                       # inside the base64 here-document
                if line == 'AZEOF':
                    open(real(doc), 'wb').write(base64.b64decode(''.join(env.get('_doc', []))))
                    env.pop('_doc', None)
                    STATS['copies'] += 1
                    doc = None
                    out(prompt())
                else:
                    env.setdefault('_doc', []).append(line)
                    out('> ')
            else:
                if echo:
                    out('\r\n')
                res = shell(line, env)
                if res == 'EXEC':
                    STATS['links'] += 1
                    print('fake board: exec ardzy_link board  (logins %(logins)d, copies %(copies)d, links %(links)d)' % STATS, flush=True)
                    ardzy_link.board_main(ardzy_link.SocketIO(conn), port_map={80: HTTP_PORT, 8080: HTTP_PORT})
                    out('\r\nArdzy serial link ended: the console is yours again.\r\n')
                    print('fake board: link ended, back to the login', flush=True)
                    state, echo, env = 'login', True, {}
                    out('\r\nardzy login: ')
                    conn.settimeout(None)
                    continue
                if isinstance(res, tuple) and res[0] == 'HEREDOC':
                    doc = res[1]
                    out('> ')
                    continue
                if env.pop('_noecho', False):
                    echo = False
                out(res + prompt())


def prompt():
    return 'root@ardzy:~# '


def shell(line, env):
    """The commands the app sends, done for real against the folder FS."""
    outp = []
    if line.startswith('exec python3 '):
        return 'EXEC'
    m = re.match(r"base64 -d > \$D/(\S+) <<'AZEOF'$", line)
    if m:
        return ('HEREDOC', m.group(1))
    known = False
    env['_noecho'] = 'stty -echo' in line
    if line.startswith('P=; for f in'):
        known = True
        sha = re.search(r'= "(\w+)" \]', line).group(1)
        env['P'] = ''
        for f in re.search(r'for f in (.*?); do', line).group(1).split():
            p = real(f)
            if os.path.exists(p) and hashlib.sha256(open(p, 'rb').read()).hexdigest()[:16] == sha:
                env['P'] = f
                break
        outp.append('AZ_P=' + env['P'])
    if line.startswith('D=/var/lib/ardzy'):
        known, env['D'] = True, '/var/lib/ardzy'
    if line.startswith('mv -f $D/'):
        known = True
        os.replace(real('ardzy_link.py.part'), real('ardzy_link.py'))
        env['P'] = env['D'] + '/ardzy_link.py'
        outp.append('AZ_S=%s AZ_P=%s' % (hashlib.sha256(open(real(env['P']), 'rb').read()).hexdigest()[:16], env['P']))
    m = re.search(r'echo AZ_\$\(\((\d+)\+0\)\)_END', line)
    if not (known or env['_noecho']) and line.strip():
        outp.append('-bash: %s: (the fake board does not know this)' % line.split()[0])
    if m:
        outp.append('AZ_%s_END' % m.group(1))
    return ''.join(x + '\r\n' for x in outp)


def main():
    web = Srv(('127.0.0.1', HTTP_PORT), Web)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('127.0.0.1', CON_PORT))
    s.listen(4)
    print('fake board: console socket://127.0.0.1:%d, web service on %d, files in %s' % (CON_PORT, HTTP_PORT, FS), flush=True)
    while True:
        conn, _ = s.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        threading.Thread(target=lambda c=conn: (console(c), c.close()), daemon=True).start()


if __name__ == '__main__':
    main()
