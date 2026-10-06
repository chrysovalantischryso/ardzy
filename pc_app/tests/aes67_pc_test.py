"""End-to-end test of the app's network sound (pc_app/aes67_pc.py) with the radio on a real board:
  1. the PC's own sound: a 1 kHz tone played to the Windows default output, captured from that output
     ("everything this PC plays"), sent straight to the board (unicast over the app's link)
  2. a relay: an AES67 stream from aes67_send.py (multicast on whatever network card Windows picks),
     heard by the app on every card (SAP) and passed on to the board
Each time the board's radio service must receive it and the tone must arrive in the FPGA at its level.
The transmitter stays off; the user's radio.json is put back at the end.

    python aes67_pc_test.py [board]          (default ardzy.local)
"""
import json
import math
import os
import socket
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import aes67_pc  # noqa: E402

NAME = sys.argv[1] if len(sys.argv) > 1 else 'ardzy.local'
BOARD = 'http://' + NAME
P = '12_fm_radio'
PROJ = os.path.normpath(os.path.join(HERE, '..', '..', 'fpga_projects', P))
results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-52s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


def call(method, path, data=None, timeout=60):
    req = urllib.request.Request(BOARD + path, data=data, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def status():
    return json.loads(call('GET', '/api/file?p=%s&f=status.json' % P))


def set_cfg(**kw):
    cfg = json.loads(call('GET', '/api/file?p=%s&f=radio.json' % P))
    for k, v in kw.items():
        if isinstance(v, dict):
            cfg.setdefault(k, {}).update(v)
        else:
            cfg[k] = v
    cfg['rev'] = int(cfg.get('rev', 0)) + 1
    cfg['clock_checked'] = time.time()
    call('PUT', '/api/upload?p=%s&f=radio.json' % P, json.dumps(cfg).encode())
    return cfg['rev']


def tone_in_fpga():
    cid = int(time.time()) % 100000
    set_cfg(capture=cid)
    for _ in range(20):
        time.sleep(0.3)
        try:
            m = json.loads(call('GET', '/api/file?p=%s&f=mpx.json' % P))
        except Exception:
            continue
        if m.get('id') == cid:
            x = m['samples']
            n = len(x)
            acc = sum(v * complex(math.cos(2 * math.pi * 1000 * i / m['fs']), -math.sin(2 * math.pi * 1000 * i / m['fs']))
                      * (0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1))) for i, v in enumerate(x))
            return abs(acc) * 2 / n / 0.5
    return 0.0


# the board's address the way the app uses it (IPv6 link-local with the zone)
info = json.loads(call('GET', '/api/info'))
host = None
for a in socket.getaddrinfo(NAME, 80, 0, socket.SOCK_STREAM):
    if a[0] == socket.AF_INET6:
        host = '%s%%%d' % (a[4][0].split('%')[0], a[4][3]) if a[4][3] else a[4][0]
        break
host = host or socket.getaddrinfo(NAME, 80)[0][4][0]
print('board at', host)
live = status()
if live.get('on'):
    sys.exit('The radio is on air: not testing.')
saved = call('GET', '/api/file?p=%s&f=radio.json' % P)
for f in ('main.py', 'aes67.py'):
    call('PUT', '/api/upload?p=%s&f=%s' % (P, f), open(os.path.join(PROJ, f), 'rb').read())
call('POST', '/api/load?p=' + P, b'', timeout=120)
time.sleep(4)

try:
    # ---------------------------------------------------------------- 1. the PC's own sound
    import pyaudiowpatch as pa
    devs = aes67_pc.devices()
    dev = next(d for d in devs if d['kind'] == 'loopback' and d['default'])
    print('capturing:', dev['name'].encode('ascii', 'replace').decode(), dev['rate'], 'Hz')
    p = pa.PyAudio()
    out_idx = next(i for i in range(p.get_device_count()) if p.get_device_info_by_index(i)['name'] == dev['name']
                   and p.get_device_info_by_index(i)['maxOutputChannels'] > 0 and not p.get_device_info_by_index(i).get('isLoopbackDevice'))
    rate = int(p.get_device_info_by_index(out_idx)['defaultSampleRate'])
    ph = [0]

    def play(a, n, t, s):
        b = bytearray()
        for i in range(n):
            v = int(16383 * math.sin(2 * math.pi * 1000 * (ph[0] + i) / rate))
            b += v.to_bytes(2, 'little', signed=True) * 2
        ph[0] += n
        return bytes(b), pa.paContinue
    player = p.open(format=pa.paInt16, channels=2, rate=rate, output=True, output_device_index=out_idx, stream_callback=play)
    snd = aes67_pc.Sender(dev, host)
    rev = set_cfg(on=False, mode='fm', audio={'source': 'network', 'tone_l': 1000}, network=snd.config())
    time.sleep(5)
    st = status()
    rv = (st.get('network') or {}).get('receiver') or {}
    check('PC sound: sent straight to the board, received', rv.get('receiving') and 900 < (rv.get('packets_per_s') or 0) < 1100,
          '%s packets/s, %s lost, from %s, buffer %s ms' % (rv.get('packets_per_s'), rv.get('lost'), rv.get('from'), rv.get('buffer_ms')))
    amp = tone_in_fpga()
    want = 0.87 * 0.5 * 32767 * 1.048 * 0.5        # tone at half scale, (L+R)/2, 50 us pre-emphasis at 1 kHz, sound share
    want = 0.87 * 16383 * 1.048
    check('PC sound: the 1 kHz tone arrives in the FPGA', 0.8 * want < amp < 1.2 * want, '%.0f (about %.0f)' % (amp, want))
    check('PC sound: the sender state', snd.state()['sending'] and snd.state()['level'] > 0.3, str(snd.state()))
    snd.close()
    player.stop_stream()
    player.close()
    p.terminate()

    # ---------------------------------------------------------------- 2. relay of a multicast stream
    heard = aes67_pc.Heard()
    sender = subprocess.Popen([sys.executable, os.path.join(PROJ, 'aes67_send.py'), '--tone', '1000', '--name', 'Relay test',
                               '--iface', '0.0.0.0', '--address', '239.69.83.68', '--port', '5006', '--seconds', '40'],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    t0 = time.time()
    while time.time() - t0 < 12 and not any(x['name'] == 'Relay test' for x in heard.list()):
        time.sleep(0.5)
    found = [x for x in heard.list() if x['name'] == 'Relay test']
    check('Relay: the PC hears the stream (SAP on every card)', bool(found), str(found[:1]))
    if found:
        rel = aes67_pc.Relay(found[0], host)
        set_cfg(audio={'source': 'network'}, network=rel.config())
        time.sleep(5)
        st = status()
        rv = (st.get('network') or {}).get('receiver') or {}
        check('Relay: the board receives it', rv.get('receiving') and 900 < (rv.get('packets_per_s') or 0) < 1100,
              '%s packets/s, %s lost, from %s, buffer %s ms' % (rv.get('packets_per_s'), rv.get('lost'), rv.get('from'), rv.get('buffer_ms')))
        amp = tone_in_fpga()
        want = 0.87 * 0.5 * 32767 * 1.048
        check('Relay: the 1 kHz tone arrives in the FPGA', 0.8 * want < amp < 1.2 * want, '%.0f (about %.0f)' % (amp, want))
        rel.close()
    sender.terminate()
finally:
    call('PUT', '/api/upload?p=%s&f=radio.json' % P, saved)
print('RESULT: %d of %d ok' % (sum(results), len(results)))
