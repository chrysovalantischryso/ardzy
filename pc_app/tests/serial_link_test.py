"""Serial link test without a board: starts tests/fake_serial_board.py (a pretend console + web service) and
runs the PC end (linkpc.open_link) against it over socket://. Script style like the other tests.

    python tests/serial_link_test.py"""
import base64, concurrent.futures, hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import ardzy_link as L  # noqa: E402
import linkpc  # noqa: E402

CON, WEB = 9511, 9581
URL = 'socket://127.0.0.1:%d' % CON
ok = fail = 0


def check(name, cond, extra=''):
    global ok, fail
    if cond:
        ok += 1
        print('  ok   ', name)
    else:
        fail += 1
        print('  FAIL ', name, extra)


def main():
    fake = subprocess.Popen([sys.executable, os.path.join(HERE, 'fake_serial_board.py'), str(CON), str(WEB)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(1.0)
    try:
        run()
    finally:
        fake.kill()
        print('--- fake board said:\n' + fake.stdout.read())
    print('\n%d ok, %d failed' % (ok, fail))
    sys.exit(1 if fail else 0)


def run():
    print('frames')
    d = L.Decoder()
    f = L.encode('D', 7, bytes(range(256)))
    got = d.feed(b'noise\r\n' + f[:5] + f[5:] + b'\x7e\x01\x02\x7e')
    check('a frame with every byte value survives noise around it', got == [('D', 7, bytes(range(256)))] and d.bad >= 1)
    bad = bytearray(f)
    bad[10] ^= 0x40
    check('a damaged frame is dropped', L.Decoder().feed(bytes(bad)) == [])

    print('first connect (login, copy, start, speed)')
    logs = []
    t = time.time()
    link, io, hello = linkpc.open_link(URL, 921600, log=lambda m, k='': logs.append(m))
    print('    ' + '\n    '.join(logs))
    check('connected and the board end said hello', hello.get('version') == L.VERSION, hello)
    check('the link program was copied', any('copying' in m for m in logs))
    check('speed agreed at 921600', link.baud == 921600, link.baud)
    print('    (%.1f s)' % (time.time() - t))

    st, body, h = link.request('GET', '/api/info')
    info = json.loads(body)
    check('GET /api/info over the link', st == 200 and info.get('hostname') == 'ardzy', (st, body[:80]))
    data = os.urandom(300 * 1024)
    st, body, h = link.request('PUT', '/api/upload?p=x&f=y.bin', data, timeout=30)
    check('PUT 300 KB arrives whole (sha256)', json.loads(body).get('sha') == hashlib.sha256(data).hexdigest())
    st, body, h = link.request('GET', '/api/big?n=700000', timeout=30)
    check('GET 700 KB comes back whole', body == bytes(i & 0xFF for i in range(700000)), len(body))
    st, body, h = link.request('GET', '/api/missing')
    check('a 404 stays a 404', st == 404, st)
    st, body, h = link.request('GET', '/state', port=8080)
    check('port 8080 (the AI projects) goes through too', st == 200 and json.loads(body).get('path') == '/state')

    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda i: link.request('GET', '/api/echo?i=%d' % i), range(24)))
    check('24 calls at the same time each get their own answer',
          all(json.loads(b)['path'] == '/api/echo?i=%d' % i for i, (s, b, h) in enumerate(res)))

    print('terminal over the link')
    st, body, h = link.request('POST', '/api/term/open?cols=90&rows=20')
    tid = json.loads(body).get('id')
    check('a terminal opens', st == 200 and tid, body)
    link.request('POST', '/api/term/write?id=%s' % tid, b'echo ardzy_%d\r\n' % (6 * 7))
    seen, since, end = b'', 0, time.time() + 10
    while b'ardzy_42' not in seen and time.time() < end:
        r = json.loads(link.request('GET', '/api/term/read?id=%s&since=%d&wait=2' % (tid, since))[1])
        seen += base64.b64decode(r['data'])
        since = r['next']
    check('typed command runs and its output comes back', b'ardzy_42' in seen, seen[-200:])
    r = json.loads(link.request('GET', '/api/term/read?id=%s&since=0&wait=0' % tid)[1])
    check('reading again from 0 gives everything (the app can reload)', b'ardzy_42' in base64.b64decode(r['data']))
    link.request('POST', '/api/term/close?id=%s' % tid)
    r = json.loads(link.request('GET', '/api/term/read?id=%s' % tid)[1])
    check('a closed terminal says so', r.get('ok') is False, r)

    print('goodbye and connect again')
    link.send('X')
    time.sleep(0.6)
    link.close()
    io.close()
    logs = []
    link, io, hello = linkpc.open_link(URL, 921600, log=lambda m, k='': logs.append(m))
    check('second connect logs in again without copying', not any('copying' in m for m in logs) and any('logging in' in m for m in logs), logs)
    check('and works', json.loads(link.request('GET', '/api/info')[1]).get('hostname') == 'ardzy')
    link.send('X')
    time.sleep(0.6)
    link.close()
    io.close()

    print('wrong password')
    try:
        linkpc.open_link(URL, 921600, password='wrong', log=lambda m, k='': None)
        check('wrong password is refused', False)
    except PermissionError as e:
        check('wrong password is refused with a clear message', 'password' in str(e), e)

    print('nothing on the port')
    try:
        linkpc.open_link('socket://127.0.0.1:1', 921600, log=lambda m, k='': None)
        check('a dead port fails', False)
    except Exception as e:
        check('a port with nobody fails cleanly', True, e)


if __name__ == '__main__':
    main()
