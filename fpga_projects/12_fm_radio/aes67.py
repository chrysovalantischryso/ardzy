"""aes67.py - network sound for the Ardzy radio: AES67 / RTP streams (RAVENNA, Dante in AES67 mode, PipeWire,
Livewire+, ffmpeg ...).

AES67 sends uncompressed sound in RTP packets over UDP, usually to a multicast address (239.x.x.x), port
5004, 48 kHz, 24 bit (L24) or 16 bit (L16), 1 ms per packet. Senders announce their streams with SAP
(multicast 239.255.255.255 port 9875): a short SDP text with the name, address, port and format.

    Discovery  listens to SAP and keeps a list of the streams seen in the last 5 minutes
    Receiver   joins the stream (multicast, or unicast to this board), turns every packet into FIFO
               words for the radio and keeps the FPGA's resampler in step with the sender's clock
               (the sound buffer is held near 40 ms by nudging the rate by up to 0.3 %).
AES67 also uses PTP to put many devices on one clock; a receiver like this one simply follows the
stream's own pace, which is all a radio needs.
"""
import array
import socket
import struct
import sys
import time

SAP_GROUP, SAP_PORT = '239.255.255.255', 9875


def local_ipv4():
    """The board's own IPv4 addresses (to join multicast groups on the right network port)."""
    out = []
    try:
        import subprocess
        txt = subprocess.run(['ip', '-4', '-o', 'addr'], capture_output=True, text=True).stdout
        for line in txt.splitlines():
            parts = line.split()
            if 'inet' in parts:
                a = parts[parts.index('inet') + 1].split('/')[0]
                if not a.startswith('127.'):
                    out.append(a)
    except Exception:
        pass
    return out or ['0.0.0.0']


def join(sock, group):
    """Join a multicast group on every network port (a board with no default route needs that)."""
    joined = 0
    for a in local_ipv4():
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(group) + socket.inet_aton(a))
            joined += 1
        except OSError:
            pass
    return joined


def parse_sdp(text):
    """The parts of an SDP description a receiver needs."""
    s = {'name': '', 'address': '', 'port': 5004, 'encoding': 'L24', 'rate': 48000, 'channels': 2, 'pt': 96, 'ptime': 1.0}
    for line in text.replace('\r', '').split('\n'):
        if line.startswith('s='):
            s['name'] = line[2:].strip()
        elif line.startswith('c=IN IP4 '):
            s['address'] = line[9:].split('/')[0].strip()
        elif line.startswith('m=audio '):
            p = line.split()
            s['port'], s['pt'] = int(p[1]), int(p[3]) if len(p) > 3 else 96
        elif line.startswith('a=rtpmap:'):
            fmt = line.split(None, 1)[1] if ' ' in line else ''
            f = fmt.split('/')
            if f and f[0].upper() in ('L24', 'L16'):
                s['encoding'] = f[0].upper()
                s['rate'] = int(f[1]) if len(f) > 1 else 48000
                s['channels'] = int(f[2]) if len(f) > 2 else 1
        elif line.startswith('a=ptime:'):
            try:
                s['ptime'] = float(line[8:])
            except ValueError:
                pass
    return s


class Discovery:
    """SAP listener: the AES67 streams announced on the network."""

    def __init__(self):
        self.streams = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', SAP_PORT))
        join(self.sock, SAP_GROUP)
        self.sock.setblocking(False)

    def poll(self):
        while True:
            try:
                data, src = self.sock.recvfrom(4096)
            except (BlockingIOError, OSError):
                break
            if len(data) < 8 or data[0] >> 5 != 1:
                continue
            delete = bool(data[0] & 0x04)
            auth_len = data[1] * 4
            off = 8 + auth_len
            if data[0] & 0x10:                          # IPv6 origin address
                off += 12
            body = data[off:]
            if body.startswith(b'application/sdp\0'):
                body = body[16:]
            sdp = parse_sdp(body.decode('utf-8', 'replace'))
            key = '%s:%d' % (sdp['address'], sdp['port'])
            if delete:
                self.streams.pop(key, None)
            elif sdp['address']:
                sdp['from'] = src[0]
                sdp['seen'] = time.time()
                self.streams[key] = sdp
        now = time.time()
        for k in [k for k, v in self.streams.items() if now - v['seen'] > 300]:
            del self.streams[k]
        return sorted(self.streams.values(), key=lambda s: s['name'])


class Receiver:
    """One RTP stream into the radio's sound FIFO."""
    TARGET = 0.040                                      # seconds of sound kept in the FPGA's buffer

    def __init__(self, radio, address, port, encoding='L24', rate=48000, channels=2, sink=None, buffer_ms=150):
        """sink: where the sound goes (the radio service's pipeline: resampling, processing, delay), with
        push(words, rate), level() and ready(); without one, straight into the FPGA."""
        self.r, self.address, self.port, self.sink = radio, address, int(port), sink
        self.TARGET = max(0.02, min(2.0, float(buffer_ms) / 1000))   # sound kept in hand: more = no clicks, later
        self.t_fix = 0.0
        self.retarget = False                           # the buffer size was changed: reach it at once
        self.encoding, self.rate, self.channels = encoding.upper(), int(rate), int(channels)
        # IPv4: multicast (the address) and unicast to this board; IPv6: unicast to this board (the Ardzy app
        # sends that way: it reaches the board over the same link the app already uses)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        self.sock.bind(('', self.port))
        a = (address or '').split('.')
        if a and a[0].isdigit() and 224 <= int(a[0]) <= 239:
            if not join(self.sock, address):
                raise OSError('could not join %s on any network port' % address)
        self.sock.setblocking(False)
        self.socks = [self.sock]
        try:
            s6 = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
            s6.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            s6.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
            s6.bind(('::', self.port))
            s6.setblocking(False)
            self.socks.append(s6)
        except OSError:
            pass
        self.nominal = (48000 if sink else self.rate) / radio.FS_AUDIO   # (the pipeline always gives 48 kHz)
        self.ratio = self.nominal
        self.integ = 0.0
        self.lvl = None                                 # the buffer, smoothed (it jumps by a whole block at a time)
        self.t_follow = None
        if not sink:
            radio.input_rate(self.rate)
        self.packets = self.lost = self.late = 0
        self.last_seq = None
        self.ssrc = None                                # the sender's id: a new sender starts its own numbering
        self.late_run = 0
        self.started = False
        self.prefill = []                               # packets kept back until there are 40 ms of sound
        self.pending = array.array('I')
        self.t_last = 0.0
        self.source = None
        self.rate_count, self.rate_t, self.pps = 0, time.time(), 0.0

    def close(self):
        for x in self.socks:
            x.close()

    def _packets(self):
        for x in self.socks:
            while True:
                try:
                    yield x.recvfrom(9000)
                except (BlockingIOError, OSError):
                    break

    def words(self, payload):
        """Payload -> FIFO words (right << 16 | left, 16 bit)."""
        ch = self.channels
        if self.encoding == 'L24':
            n = len(payload) // (3 * ch)
            b = bytearray(4 * n)
            l0 = payload[0:n * 3 * ch:3 * ch]           # the two high bytes of each 24-bit sample
            l1 = payload[1:n * 3 * ch:3 * ch]
            if ch >= 2:
                r0, r1 = payload[3:n * 3 * ch:3 * ch], payload[4:n * 3 * ch:3 * ch]
            else:
                r0, r1 = l0, l1
            b[0::4], b[1::4], b[2::4], b[3::4] = l1, l0, r1, r0
        else:                                           # L16, big endian
            n = len(payload) // (2 * ch)
            b = bytearray(4 * n)
            l0, l1 = payload[0:n * 2 * ch:2 * ch], payload[1:n * 2 * ch:2 * ch]
            if ch >= 2:
                r0, r1 = payload[2:n * 2 * ch:2 * ch], payload[3:n * 2 * ch:2 * ch]
            else:
                r0, r1 = l0, l1
            b[0::4], b[1::4], b[2::4], b[3::4] = l1, l0, r1, r0
        a = array.array('I')
        a.frombytes(bytes(b))
        if sys.byteorder != 'little':
            a.byteswap()
        return a

    def poll(self):
        """Take every packet that came in and keep the buffer near its target. Returns samples pushed."""
        if self.sink:
            return self._poll_sink()
        pushed = 0
        free = self.r.audio_free()
        level = self.r.AUDIO_FIFO - free
        for data, src in self._packets():
            if len(data) < 12 or data[0] >> 6 != 2:
                continue
            cc = data[0] & 15
            off = 12 + 4 * cc
            if data[0] & 0x10 and len(data) >= off + 4:   # header extension
                off += 4 + 4 * struct.unpack('!H', data[off + 2:off + 4])[0]
            seq = struct.unpack('!H', data[2:4])[0]
            ssrc = data[8:12]
            if ssrc != self.ssrc:                       # another sender (or the same one restarted)
                self.ssrc, self.last_seq, self.late_run = ssrc, None, 0
            if self.last_seq is not None:
                gap = (seq - self.last_seq) & 0xFFFF
                if gap == 0 or gap > 0x8000:
                    self.late += 1
                    self.late_run += 1
                    if self.late_run < 50:              # (50 in a row: the numbering jumped, follow it)
                        continue
                elif gap < 1000:
                    self.lost += gap - 1
            self.late_run = 0
            self.last_seq = seq
            self.packets += 1
            self.rate_count += 1
            self.source = src[0]
            self.t_last = time.time()
            w = self.words(data[off:])
            if not self.started:                        # collect 40 ms first, then play it all at once
                self.prefill.append(w)
                if sum(len(x) for x in self.prefill) >= self.TARGET * self.rate:
                    for x in self.prefill:
                        if len(x) <= free:
                            self.r.push(x)
                            free -= len(x)
                            level += len(x)
                            pushed += len(x)
                    self.prefill = []
                    self.started = True
                continue
            if len(w) <= free:
                self.r.push(w)
                pushed += len(w)
                free -= len(w)
                level += len(w)
        # follow the sender's clock: more in the buffer than the target -> take samples a little faster
        if self.started:                                # proportional + integral: the buffer settles on its target
            self.follow(level / self.rate)
        now = time.time()
        if now - self.rate_t >= 1:
            self.pps = self.rate_count / (now - self.rate_t)
            self.rate_count, self.rate_t = 0, now
        if self.started and now - self.t_last > 1:      # the stream stopped: start over when it returns
            self.started = False
            self.prefill = []
        return pushed

    def _parse(self, data, src):
        """An RTP packet -> its FIFO words, or None (not RTP, late, a duplicate)."""
        if len(data) < 12 or data[0] >> 6 != 2:
            return None
        cc = data[0] & 15
        off = 12 + 4 * cc
        if data[0] & 0x10 and len(data) >= off + 4:
            off += 4 + 4 * struct.unpack('!H', data[off + 2:off + 4])[0]
        seq = struct.unpack('!H', data[2:4])[0]
        ssrc = data[8:12]
        if ssrc != self.ssrc:
            self.ssrc, self.last_seq, self.late_run = ssrc, None, 0
        if self.last_seq is not None:
            gap = (seq - self.last_seq) & 0xFFFF
            if gap == 0 or gap > 0x8000:
                self.late += 1
                self.late_run += 1
                if self.late_run < 50:
                    return None
            elif gap < 1000:
                self.lost += gap - 1
        self.late_run = 0
        self.last_seq = seq
        self.packets += 1
        self.rate_count += 1
        self.source = src[0]
        self.t_last = time.time()
        return self.words(data[off:])

    def _poll_sink(self):
        # all the packets that came since the last call, as ONE block: the processing costs per call, not
        # per sample, and 1000 small calls a second would take the ARM's whole time
        got = array.array('I')
        for d, s in self._packets():
            w = self._parse(d, s)
            if w is not None:
                got.extend(w)
            if len(got) >= 48000:                       # (at most 1 s at a time, then the FPGA gets its share)
                break
        pushed = 0
        if len(got):
            self.pending.extend(got)
        if len(self.pending) >= 960 or (self.pending and time.time() - self.t_last > 0.05):
            got, self.pending = self.pending, array.array('I')   # (20 ms pieces: the processing costs per call)
        else:
            got = array.array('I')
        if len(got):
            if not self.started and self.sink:          # (the pipeline fills the buffer itself before it plays)
                self.started = True
            if not self.started:                        # collect the buffer first, then go
                self.prefill.append(got)
                if sum(len(x) for x in self.prefill) >= self.TARGET * self.rate:
                    got = array.array('I')
                    for x in self.prefill:
                        got.extend(x)
                    self.prefill, self.started = [], True
                else:
                    got = None
            if got is not None and len(got):
                self.sink.start_margin = int(self.TARGET * 48000)
                lvl = self.sink.level() / 48000 + len(got) / self.rate     # (what is in hand once this is in)
                if self.retarget and self.sink.ready():  # a new buffer size: silence once, or skip blocks until there
                    if lvl > self.TARGET + 0.02:
                        got = None
                    else:
                        if lvl < self.TARGET - 0.02:
                            self.sink.push(array.array('I', bytes(4 * int((self.TARGET - lvl) * self.rate))), self.rate)
                        self.retarget, self.t_fix = False, time.time()
                elif self.sink.ready() and time.time() - self.t_fix > 2 and lvl > 2 * self.TARGET + 0.05:
                    self.t_fix, got = time.time(), None  # far too much in hand (the buffer was made smaller): drop a piece
                elif self.sink.ready() and time.time() - self.t_fix > 2 and lvl < 0.5 * self.TARGET:
                    self.t_fix = time.time()             # far too little (made bigger, or a stall): a moment of silence
                    self.sink.push(array.array('I', bytes(4 * int((self.TARGET - lvl) * self.rate))), self.rate)
                if got is not None:
                    self.sink.push(got, self.rate)
                    pushed = len(got)
        now = time.time()
        if self.started and self.sink.ready():           # follow the sender's clock (not while the delay fills)
            self.follow(self.sink.level() / 48000)
        if now - self.rate_t >= 1:
            self.pps = self.rate_count / (now - self.rate_t)
            self.rate_count, self.rate_t = 0, now
        if self.started and now - self.t_last > 1:
            self.started = False
            self.prefill = []
        return pushed

    def set_buffer(self, ms):
        t = max(0.02, min(2.0, float(ms) / 1000))
        if abs(t - self.TARGET) > 0.02:
            self.retarget = True
        self.TARGET = t

    def follow(self, level_s):
        """Follow the sender's clock: more in hand than the target -> the FPGA takes samples a little faster.
        The level is smoothed over about 1 s; 10 ms too much gives 1000 ppm (gone in about 10 s), and a slow
        integral (a minute) learns the real clock difference, so the buffer settles without swinging."""
        now = time.time()
        dt = min(0.1, now - self.t_follow) if self.t_follow else 0.0
        self.t_follow = now
        self.lvl = level_s if self.lvl is None else self.lvl + (level_s - self.lvl) * min(1.0, dt / 1.0)
        e = self.lvl - self.TARGET
        if dt and abs(e) < 0.05:                        # (not while far off: a buffer change, a stall)
            self.integ = max(-0.0005, min(0.0005, self.integ + 0.0017 * e * dt))
        adj = max(-0.004, min(0.004, 0.1 * e + self.integ))
        self.ratio = self.nominal * (1 + adj)
        self.r.w(8, round(self.ratio * 65536))

    def state(self):
        return {'address': self.address, 'port': self.port, 'format': '%s/%d/%d' % (self.encoding, self.rate, self.channels),
                'receiving': time.time() - self.t_last < 1, 'packets_per_s': round(self.pps), 'lost': self.lost,
                'late': self.late, 'from': self.source, 'rate_adjust_ppm': round((self.ratio / self.nominal - 1) * 1e6),
                'buffer_ms': round((self.lvl if self.lvl is not None and self.sink else self.sink.level() / 48000 if self.sink else (self.r.AUDIO_FIFO - self.r.audio_free()) / self.rate) * 1000)}
