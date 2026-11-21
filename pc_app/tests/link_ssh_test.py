"""The whole serial-link start on a REAL board, with an SSH terminal instead of the USB-UART cable:
linkpc.open_link talks to a real bash on a real terminal (plink -t), copies ardzy_link.py with base64 through
the shell, execs it, puts the terminal in raw mode, and then the app's calls travel as frames.
Not covered here (needs a cable): the getty login and the change of the UART speed.
Leaves the board as it was (the copied file is removed at the end).

    python tests/link_ssh_test.py <board address> [ssh host key]"""
import base64, json, os, queue, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import ardzy_link as L  # noqa: E402
import linkpc  # noqa: E402

HOST = sys.argv[1]
KEY = sys.argv[2] if len(sys.argv) > 2 else ''
ok = fail = 0


def check(name, cond, extra=''):
    global ok, fail
    ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
    print('  %s %s' % ('ok   ' if cond else 'FAIL ', name), '' if cond else extra)


class PlinkSerial:
    """Looks like a pyserial port to linkpc (read with timeout, write, in_waiting, baudrate)."""

    def __init__(self):
        self.p = subprocess.Popen(['plink', '-batch', '-t', '-pw', 'root'] + (['-hostkey', KEY] if KEY else []) +
                                  ['root@' + HOST], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self.q, self.buf, self.baudrate = queue.Queue(), b'', 115200
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        while True:
            d = self.p.stdout.read1(4096) if hasattr(self.p.stdout, 'read1') else os.read(self.p.stdout.fileno(), 4096)
            if not d:
                self.q.put(None)
                return
            self.q.put(d)

    def _fill(self, timeout):
        try:
            d = self.q.get(timeout=timeout)
        except queue.Empty:
            return
        if d is None:
            raise ConnectionError('ssh closed')
        self.buf += d
        while not self.q.empty():
            d = self.q.get_nowait()
            if d is None:
                break
            self.buf += d

    @property
    def in_waiting(self):
        self._fill(0)
        return len(self.buf)

    def read(self, n=1):
        if not self.buf:
            self._fill(0.2)
        d, self.buf = self.buf[:n], self.buf[n:]
        return d

    def write(self, data):
        self.p.stdin.write(data)
        self.p.stdin.flush()

    def close(self):
        self.p.kill()


def ssh(cmd):
    return subprocess.run(['plink', '-batch', '-pw', 'root'] + (['-hostkey', KEY] if KEY else []) + ['root@' + HOST, cmd],
                          capture_output=True, text=True, timeout=30)


def main():
    before = ssh('cat /proc/sys/kernel/printk; ls /var/lib/ardzy/ardzy_link.py 2>&1 | tail -1').stdout.split('\n')
    logs = []
    ser = PlinkSerial()
    seen, end = b'', time.time() + 15                     # the SSH session first (like a board that is up)
    while b'# ' not in seen[-40:] and time.time() < end:
        seen += ser.read(4096)
    t = time.time()
    try:
        link, io, hello = linkpc.open_link('ssh', 921600, log=lambda m, k='': logs.append(m), ser=ser)
    except Exception as e:
        print('\n'.join(logs))
        check('open_link through a real shell', False, e)
        return finish()
    print('    ' + '\n    '.join(logs))
    check('copied with base64 through the real shell, started, said hello', hello.get('version') == L.VERSION and
          any('copied' in m for m in logs), hello)
    print('    (%.1f s)' % (time.time() - t))
    info = json.loads(link.request('GET', '/api/info')[1])
    check('frames through a raw terminal: /api/info of the real board', info.get('hostname') == 'ardzy', info)
    r = json.loads(link.request('GET', '/api/link')[1])
    check('no damaged frame so far (raw mode works)', r.get('bad_frames') == 0, r)
    st, body, h = link.request('POST', '/api/term/open?cols=80&rows=24')
    tid = json.loads(body)['id']
    link.request('POST', '/api/term/write?id=%s' % tid, b'printf "%s" | wc -c\r' % (b'x' * 3000))
    seen, since, end = b'', 0, time.time() + 8
    while b'3000' not in seen and time.time() < end:
        r = json.loads(link.request('GET', '/api/term/read?id=%s&since=%d&wait=2' % (tid, since))[1])
        seen += base64.b64decode(r['data'])
        since = r['next']
    check('terminal through the link (a 3000-character line typed)', b'3000' in seen, seen[-120:])
    st, body, h = link.request('GET', '/api/file?p=..&f=x')
    check('the board refuses ".." (the safety fix is not on this board yet: 404 or 400 both fine)', st in (400, 404), st)
    r = json.loads(link.request('GET', '/api/link')[1])
    check('still no damaged frame (%d good)' % r.get('good_frames', 0), r.get('bad_frames') == 0, r)
    link.send('X')
    time.sleep(0.3)
    link.close()                                     # (its reader stops within 0.2 s)
    # the link was exec'd in place of the shell: when it ends, the session ends (on the real console getty then
    # shows the login again; over SSH the connection closes)
    end = time.time() + 6
    while io.ser.p.poll() is None and time.time() < end:
        time.sleep(0.2)
    check('after goodbye the link program ends (on the console: the login comes back)', io.ser.p.poll() is not None)
    io.close()
    after = ssh('cat /proc/sys/kernel/printk')
    check('kernel message level restored', after.stdout.split('\n')[0] == before[0], (before[0], after.stdout))
    finish(removed=not before[1].startswith('/var/lib'))


def finish(removed=True):
    if removed:
        ssh('rm -f /var/lib/ardzy/ardzy_link.py')
    print('\n%d ok, %d failed' % (ok, fail))
    sys.exit(1 if fail else 0)


if __name__ == '__main__':
    main()
