"""The serial link over a REAL USB-UART cable on the board's console (J12): login, copy, start, speed change,
board calls, speed of the link, terminal, goodbye (the login comes back).

    python tests/link_cable_test.py COM3 [baud 921600]"""
import base64, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import ardzy_link as L  # noqa: E402
import linkpc  # noqa: E402

PORT = sys.argv[1]
BAUD = int(sys.argv[2]) if len(sys.argv) > 2 else 921600
ok = fail = 0


def check(name, cond, extra=''):
    global ok, fail
    ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
    print('  %s %s' % ('ok   ' if cond else 'FAIL ', name), '' if cond else extra, flush=True)


def main():
    t = time.time()
    link, io, hello = linkpc.open_link(PORT, BAUD, log=lambda m, k='': print('    ' + m, flush=True))
    print('    (connected in %.1f s)' % (time.time() - t))
    check('link started (hello from the board end)', hello is not None)
    check('speed %d baud' % BAUD, link.baud == BAUD, link.baud)
    info = json.loads(link.request('GET', '/api/info')[1])
    check('/api/info over the cable: %s, %s' % (info.get('hostname'), info.get('kernel')), info.get('hostname') == 'ardzy')
    st = json.loads(link.request('GET', '/api/status')[1])
    check('/api/status: FPGA %s, %s' % (st.get('fpga'), st.get('temp')), 'fpga' in st)

    # speed: 200 KB to the board (echoed size by a harmless endpoint) and back
    data = os.urandom(200 * 1024)
    t = time.time()
    st_, body, h = link.request('PUT', '/api/bench/upload', data, timeout=60)
    up = len(data) / (time.time() - t) / 1024
    got = json.loads(body).get('bytes')
    check('200 KB to the board arrives whole (%.0f KB/s)' % up, got == len(data), got)
    t = time.time()
    st_, body, h = link.request('GET', '/api/bench/download?mb=1', timeout=60)
    down = len(body) / (time.time() - t) / 1024
    check('1 MB from the board arrives whole (%.0f KB/s)' % down, len(body) == 1 << 20, len(body))

    r = json.loads(link.request('POST', '/api/term/open?cols=100&rows=30')[1])
    tid = r.get('id')
    check('terminal opens', r.get('ok') and tid, r)
    link.request('POST', '/api/term/write?id=%s' % tid, b'echo cable_$((6*7)); tty; uptime\r')
    seen, since, end = b'', 0, time.time() + 10
    while b'cable_42' not in seen and time.time() < end:
        r = json.loads(link.request('GET', '/api/term/read?id=%s&since=%d&wait=2' % (tid, since))[1])
        seen += base64.b64decode(r['data'])
        since = r['next']
    check('a command runs in the terminal over the cable', b'cable_42' in seen, seen[-200:])
    print('    ' + seen.decode(errors='replace').strip().replace('\r', '').split('\n')[-2][:100])
    link.request('POST', '/api/term/close?id=%s' % tid)
    r = json.loads(link.request('GET', '/api/link')[1])
    check('frames: %d good, %d damaged (board side)' % (r.get('good_frames', 0), r.get('bad_frames', 0)), r.get('bad_frames', 1) == 0, r)
    check('frames: %d damaged (PC side)' % link.dec.bad, link.dec.bad == 0)

    link.send('X')
    time.sleep(0.4)
    link.close()
    time.sleep(1.5)
    io.set_baud(L.BASE_BAUD)
    io.write(b'\r')
    tail, end = b'', time.time() + 6
    while b'login:' not in tail and time.time() < end:
        tail += io.read(4096)
    io.close()
    check('after goodbye the console shows its login again (115200)', b'login:' in tail, tail[-200:])
    print('\n%d ok, %d failed' % (ok, fail))
    sys.exit(1 if fail else 0)


if __name__ == '__main__':
    main()
