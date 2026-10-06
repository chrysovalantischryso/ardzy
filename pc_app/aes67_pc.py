"""aes67_pc.py - network sound in the Ardzy app (AES67 / RTP L24, 1 ms packets).

    Sender  this PC's sound to the radio: "everything this PC plays" (WASAPI loopback of an output), or an
            input (VB-CABLE, a microphone). It goes straight to the board over the link the app already uses
            (unicast, IPv6 or IPv4), so it does not matter which network card Windows would pick for multicast.
    Relay   AES67 streams this PC hears on ANY network card (SAP announcements, or an address typed in) are
            passed on to the board the same way. A sender program that picks the wrong network card, or a
            stream on the office network the board is not connected to, still reaches the radio.
"""
import socket
import struct
import threading
import time

SAP_GROUP, SAP_PORT = '239.255.255.255', 9875
BOARD_PORT = 5004


def _pa():
    import pyaudiowpatch as pa
    return pa


def devices():
    """Capture devices: the loopbacks of the outputs first ("everything that plays there"), then the inputs."""
    pa = _pa()
    p = pa.PyAudio()
    out = []
    try:
        wasapi = p.get_host_api_info_by_type(pa.paWASAPI)
        default_out = p.get_device_info_by_index(wasapi['defaultOutputDevice'])['name'] if wasapi['defaultOutputDevice'] >= 0 else ''
        for d in p.get_loopback_device_info_generator():
            name = d['name'].replace(' [Loopback]', '')
            out.append({'id': d['index'], 'name': name, 'kind': 'loopback', 'rate': int(d['defaultSampleRate']),
                        'channels': max(1, min(2, d['maxInputChannels'])), 'default': name == default_out})
        for i in range(p.get_device_count()):
            d = p.get_device_info_by_index(i)
            if d['hostApi'] == wasapi['index'] and d['maxInputChannels'] > 0 and not d.get('isLoopbackDevice'):
                out.append({'id': i, 'name': d['name'], 'kind': 'input', 'rate': int(d['defaultSampleRate']),
                            'channels': max(1, min(2, d['maxInputChannels'])), 'default': False})
    finally:
        p.terminate()
    out.sort(key=lambda d: (not d['default'], d['kind'] != 'loopback'))
    return out


def target(host, port=BOARD_PORT):
    """(family, address) to reach the board: the same address the app talks to it on (IPv6 with its zone)."""
    h = host.strip('[]')
    info = socket.getaddrinfo(h, port, 0, socket.SOCK_DGRAM)
    info.sort(key=lambda x: x[0] != (socket.AF_INET6 if ':' in h else socket.AF_INET))
    return info[0][0], info[0][4]


def local_ipv4():
    out = []
    try:
        for x in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if x[4][0] not in out and not x[4][0].startswith('127.'):
                out.append(x[4][0])
    except OSError:
        pass
    return out


class _Out:
    """RTP packets to the board."""

    def __init__(self, host, port=BOARD_PORT):
        self.fam, self.addr = target(host, port)
        self.sock = socket.socket(self.fam, socket.SOCK_DGRAM)
        self.seq, self.ts, self.ssrc = 0, 0, int(time.time()) & 0xFFFFFFFF
        self.packets = 0

    def rtp(self, payload, samples):
        hdr = struct.pack('!BBHII', 0x80, 96, self.seq & 0xFFFF, self.ts & 0xFFFFFFFF, self.ssrc)
        self.sock.sendto(hdr + payload, self.addr)
        self.seq += 1
        self.ts += samples
        self.packets += 1

    def raw(self, data):
        self.sock.sendto(data, self.addr)
        self.packets += 1

    def close(self):
        self.sock.close()


class Sender:
    """This PC's sound to the radio."""

    def __init__(self, dev, host):
        import numpy as np
        self.np, self.dev, self.host = np, dev, host
        self.out = _Out(host)
        self.rate, self.ch = dev['rate'], dev['channels']
        self.per = max(1, self.rate // 1000)            # samples in a 1 ms packet
        self.left = b''
        self.level = 0.0
        self.glitches = 0                               # Windows reported lost sound (capture overflow)
        self.t_data = 0.0
        self.error = ''
        pa = _pa()
        self.p = pa.PyAudio()
        self.keep = None
        if dev['kind'] == 'loopback':
            # a loopback only delivers while something plays: play silence to that output so it never stops
            try:
                for i in range(self.p.get_device_count()):
                    d = self.p.get_device_info_by_index(i)
                    if d['name'] == dev['name'] and d['maxOutputChannels'] > 0 and not d.get('isLoopbackDevice'):
                        self.keep = self.p.open(format=pa.paInt16, channels=1, rate=int(d['defaultSampleRate']),
                                                output=True, output_device_index=i,
                                                stream_callback=lambda a, n, t, s: (bytes(2 * n), pa.paContinue))
                        break
            except Exception:
                self.keep = None
        self.stream = self.p.open(format=pa.paInt16, channels=self.ch, rate=self.rate, input=True,
                                  input_device_index=dev['id'], frames_per_buffer=self.rate // 50,   # 20 ms blocks
                                  stream_callback=self._cb)

    def _cb(self, data, n, t, status):
        np = self.np
        if status:
            self.glitches += 1
        try:
            a = np.frombuffer(data, '<i2').reshape(-1, self.ch)
            if self.ch == 1:
                a = np.repeat(a, 2, axis=1)
            a = a[:, :2]
            self.level = max(self.level * 0.9, float(np.abs(a).max()) / 32768 if len(a) else 0.0)
            be = a.astype('>i2').view(np.uint8).reshape(-1, 2, 2)
            l24 = np.zeros((len(a), 2, 3), np.uint8)
            l24[:, :, 0:2] = be                         # 24-bit big endian: the 16 bits, then a zero byte
            buf = self.left + l24.tobytes()
            step = self.per * 6
            k = 0
            while k + step <= len(buf):
                self.out.rtp(buf[k:k + step], self.per)
                k += step
            self.left = buf[k:]
            self.t_data = time.time()
        except Exception as e:
            self.error = str(e)
        return (None, _pa().paContinue)

    def state(self):
        return {'kind': 'sender', 'device': self.dev['name'], 'format': 'L24/%d/2' % self.rate,
                'sending': time.time() - self.t_data < 0.5, 'packets': self.out.packets, 'level': round(self.level, 3),
                'glitches': self.glitches,
                'to': '%s port %d' % (self.host, BOARD_PORT), 'error': self.error}

    def config(self):
        return {'stream': '', 'address': '', 'port': BOARD_PORT, 'encoding': 'L24', 'rate': self.rate, 'channels': 2}

    def close(self):
        for s in (self.stream, self.keep):
            try:
                if s:
                    s.stop_stream()
                    s.close()
            except Exception:
                pass
        self.p.terminate()
        self.out.close()


def _join_all(sock, group):
    n = 0
    for a in local_ipv4() + ['0.0.0.0']:
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(group) + socket.inet_aton(a))
            n += 1
        except OSError:
            pass
    return n


def parse_sdp(text):
    s = {'name': '', 'address': '', 'port': 5004, 'encoding': 'L24', 'rate': 48000, 'channels': 2}
    for line in text.replace('\r', '').split('\n'):
        if line.startswith('s='):
            s['name'] = line[2:].strip()
        elif line.startswith('c=IN IP4 '):
            s['address'] = line[9:].split('/')[0].strip()
        elif line.startswith('m=audio '):
            s['port'] = int(line.split()[1])
        elif line.startswith('a=rtpmap:'):
            f = (line.split(None, 1)[1] if ' ' in line else '').split('/')
            if f and f[0].upper() in ('L24', 'L16'):
                s['encoding'] = f[0].upper()
                s['rate'] = int(f[1]) if len(f) > 1 else 48000
                s['channels'] = int(f[2]) if len(f) > 2 else 1
    return s


class Heard:
    """SAP on every network card of this PC: the AES67 streams the PC can hear."""

    def __init__(self):
        self.streams = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', SAP_PORT))
        _join_all(self.sock, SAP_GROUP)
        self.sock.settimeout(0.5)
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                data, src = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                time.sleep(1)
                continue
            if len(data) < 8 or data[0] >> 5 != 1:
                continue
            off = 8 + data[1] * 4 + (12 if data[0] & 0x10 else 0)
            body = data[off:]
            if body.startswith(b'application/sdp\0'):
                body = body[16:]
            sdp = parse_sdp(body.decode('utf-8', 'replace'))
            key = '%s:%d' % (sdp['address'], sdp['port'])
            if data[0] & 0x04:
                self.streams.pop(key, None)
            elif sdp['address']:
                sdp['from'], sdp['seen'] = src[0], time.time()
                self.streams[key] = sdp

    def list(self):
        now = time.time()
        return sorted((v for v in self.streams.values() if now - v['seen'] < 300), key=lambda v: v['name'])


class Relay:
    """An AES67 stream this PC hears (on any network card) passed on to the board."""

    def __init__(self, stream, host):
        self.stream, self.host = stream, host
        self.out = _Out(host)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        self.sock.bind(('', int(stream['port'])))
        a = stream['address'].split('.')
        if a[0].isdigit() and 224 <= int(a[0]) <= 239 and not _join_all(self.sock, stream['address']):
            raise OSError('could not join %s on this PC' % stream['address'])
        self.sock.settimeout(0.5)
        self.t_data, self.src, self.error, self.stop_flag = 0.0, None, '', False
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self.stop_flag:
            try:
                data, src = self.sock.recvfrom(9000)
            except socket.timeout:
                continue
            except OSError as e:
                self.error = str(e)
                break
            if len(data) >= 12 and data[0] >> 6 == 2:
                try:
                    self.out.raw(data)
                except OSError as e:
                    self.error = str(e)
                self.t_data, self.src = time.time(), src[0]

    def state(self):
        return {'kind': 'relay', 'device': '%s (%s:%s)' % (self.stream.get('name') or 'stream', self.stream['address'], self.stream['port']),
                'format': '%s/%s/%s' % (self.stream['encoding'], self.stream['rate'], self.stream['channels']),
                'sending': time.time() - self.t_data < 0.5, 'packets': self.out.packets, 'level': None,
                'from': self.src, 'to': '%s port %d' % (self.host, BOARD_PORT), 'error': self.error}

    def config(self):
        return {'stream': '', 'address': '', 'port': BOARD_PORT, 'encoding': self.stream['encoding'],
                'rate': int(self.stream['rate']), 'channels': int(self.stream['channels'])}

    def close(self):
        self.stop_flag = True
        self.sock.close()
        self.out.close()
