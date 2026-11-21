"""The board end of the serial link on a REAL board, over the network instead of the cable
(tests the Linux parts: bash on a pseudo terminal, resizing, Ctrl+C, forwarding to the real web service).
Nothing is installed: the file goes to /tmp and the test process ends by itself.

    python tests/link_board_test.py <board address> [ssh host key]"""
import base64, json, os, socket, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import ardzy_link as L  # noqa: E402

HOST = sys.argv[1]
KEY = sys.argv[2] if len(sys.argv) > 2 else ''
PORT = 9599
ok = fail = 0


def check(name, cond, extra=''):
    global ok, fail
    ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
    print('  %s %s' % ('ok   ' if cond else 'FAIL ', name), '' if cond else extra)


def ssh(cmd, timeout=30):
    args = ['plink', '-batch', '-pw', 'root'] + (['-hostkey', KEY] if KEY else []) + ['root@' + HOST, cmd]
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def term_text(link, tid, since, want, wait=8):
    seen, end = b'', time.time() + wait
    while want.encode() not in seen and time.time() < end:
        r = json.loads(link.request('GET', '/api/term/read?id=%s&since=%d&wait=2' % (tid, since))[1])
        seen += base64.b64decode(r['data'])
        since = r['next']
    return seen.decode(errors='replace'), since


def main():
    src = os.path.join(os.path.dirname(HERE), 'ardzy_link.py')
    r = subprocess.run(['pscp', '-batch', '-q', '-pw', 'root'] + (['-hostkey', KEY] if KEY else []) +
                       [src, 'root@%s:/tmp/ardzy_link_test.py' % HOST], capture_output=True, text=True, timeout=30)
    check('copied to /tmp on the board', r.returncode == 0, r.stderr)
    subprocess.Popen(['plink', '-batch', '-pw', 'root'] + (['-hostkey', KEY] if KEY else []) +
                     ['root@' + HOST, 'nohup python3 /tmp/ardzy_link_test.py board --tcp %d --bind 0.0.0.0 '
                      '>/tmp/ardzy_link_test.log 2>&1 &' % PORT], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sock = None
    for _ in range(30):
        time.sleep(0.5)
        try:
            sock = socket.create_connection((HOST, PORT), timeout=3)
            break
        except OSError:
            pass
    check('the board end listens', sock is not None)
    if not sock:
        return
    link = L.Link(L.SocketIO(sock), 'pc')
    check('ping', link.ping(2))

    st, body, h = link.request('GET', '/api/info')
    info = json.loads(body)
    check('forwarded to the real web service: /api/info', st == 200 and info.get('hostname'), body[:100])
    st, body, h = link.request('GET', '/api/status')
    check('/api/status', st == 200 and 'fpga' in json.loads(body))
    st, body, h = link.request('GET', '/api/link')
    check('/api/link answers from the link itself', json.loads(body).get('version') == L.VERSION)

    r = json.loads(link.request('POST', '/api/term/open?cols=100&rows=30')[1])
    tid = r.get('id')
    check('a terminal opens (bash on a pseudo terminal)', r.get('ok') and tid, r)
    since = 0
    link.request('POST', '/api/term/write?id=%s' % tid, b'echo ardzy_$((6*7)); tty; stty size; echo $TERM\r')
    txt, since = term_text(link, tid, since, 'xterm-256color')
    check('bash runs the command (ardzy_42)', 'ardzy_42' in txt, txt[-300:])
    check('it is a real terminal (/dev/pts)', '/dev/pts/' in txt, txt[-300:])
    check('the size is 30 rows x 100 columns', '30 100' in txt, txt[-300:])
    link.request('POST', '/api/term/resize?id=%s&cols=132&rows=40' % tid)
    link.request('POST', '/api/term/write?id=%s' % tid, b'stty size\r')
    txt, since = term_text(link, tid, since, '40 132')
    check('resize reaches the shell (40 x 132)', '40 132' in txt, txt[-200:])
    link.request('POST', '/api/term/write?id=%s' % tid, b'sleep 30\r')
    time.sleep(0.8)
    link.request('POST', '/api/term/write?id=%s' % tid, b'\x03')        # (Ctrl+C also empties what was typed ahead)
    time.sleep(0.5)
    link.request('POST', '/api/term/write?id=%s' % tid, b'echo after_ctrl_c_$((1+1)); yes | head -3 | wc -l\r')
    txt, since = term_text(link, tid, since, 'after_ctrl_c_2')
    check('Ctrl+C stops a running program', 'after_ctrl_c_2' in txt, txt[-200:])
    txt2, since = term_text(link, tid, since, '3', wait=3)
    check('a pipe ends normally (yes | head: SIGPIPE as usual)', '3' in txt + txt2, (txt + txt2)[-200:])
    link.request('POST', '/api/term/write?id=%s' % tid, b'exit\r')
    time.sleep(1)
    r = json.loads(link.request('GET', '/api/term/read?id=%s&since=%d&wait=3' % (tid, since))[1])
    check('exit ends the shell (alive false)', r.get('alive') is False, r)

    link.send('X')
    time.sleep(1.5)
    link.close()
    sock.close()
    # ("[a]" so pgrep does not find this command line itself)
    r = ssh('pgrep -f "[a]rdzy_link_test.py board" >/dev/null && echo STILL || echo GONE; tail -3 /tmp/ardzy_link_test.log; '
            'rm -f /tmp/ardzy_link_test.py /tmp/ardzy_link_test.log')
    check('the board end has ended after goodbye (and /tmp is cleaned)', 'GONE' in r.stdout, r.stdout + r.stderr)
    print('\n%d ok, %d failed' % (ok, fail))
    sys.exit(1 if fail else 0)


if __name__ == '__main__':
    main()
