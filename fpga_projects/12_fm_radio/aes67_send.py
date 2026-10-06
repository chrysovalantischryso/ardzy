"""aes67_send.py - send sound from a PC as an AES67 stream (RTP, L24, 1 ms packets) with its SAP announcement,
for the Ardzy radio (or any AES67 receiver). Runs on the PC with plain Python 3, nothing to install.

    python aes67_send.py song.wav                    a WAV file (PCM; any rate, mono or stereo), over and over
    python aes67_send.py --tone 1000                 a test tone
    options:  --iface 192.168.137.1   the PC's address on the network the board is on (default: found)
              --address 239.69.83.67 --port 5004     where the stream goes (multicast)
              --name "My studio"                     the name the radio shows
              --seconds 30                           stop after this long

For live sound from the PC (a microphone, or everything the PC plays through a virtual cable such as
VB-CABLE), ffmpeg can send AES67 itself:
    ffmpeg -f dshow -i audio="CABLE Output (VB-Audio Virtual Cable)" -ac 2 -ar 48000 -c:a pcm_s24be
           -payload_type 96 -f rtp "rtp://239.69.83.67:5004?localaddr=192.168.137.1&pkt_size=300"
and the radio then takes it with the address and port typed in (ffmpeg sends no SAP announcement).
"""
import argparse
import math
import socket
import struct
import sys
import time
import wave


def pick_iface():
    """An IPv4 address of this PC on a wired link to the board: 192.168.137.x (shared) or 169.254.x first."""
    addrs = []
    try:
        addrs = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    for pref in ('192.168.137.', '169.254.'):
        for a in addrs:
            if a.startswith(pref):
                return a
    return addrs[0] if addrs else '0.0.0.0'


def frames_from_wav(path):
    w = wave.open(path, 'rb')
    rate, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()

    def gen():
        while True:
            w.rewind()
            while True:
                data = w.readframes(rate // 10)
                if not data:
                    break
                for i in range(0, len(data) - sw * ch + 1, sw * ch):
                    vals = []
                    for c in range(min(2, ch)):
                        o = i + c * sw
                        if sw == 1:
                            v = (data[o] - 128) << 16
                        else:
                            v = int.from_bytes(data[o:o + sw], 'little', signed=True) << (8 * (3 - sw)) if sw <= 3 \
                                else int.from_bytes(data[o + 1:o + 4], 'little', signed=True)
                        vals.append(v)
                    yield vals[0], vals[-1]
    return rate, gen()


def frames_tone(hz, rate=48000, level=0.5):
    def gen():
        n = 0
        while True:
            v = int(level * 8388607 * math.sin(2 * math.pi * hz * n / rate))
            yield v, v
            n += 1
    return rate, gen()


def main():
    ap = argparse.ArgumentParser(description='Send an AES67 stream (RTP L24) with a SAP announcement.')
    ap.add_argument('wav', nargs='?')
    ap.add_argument('--tone', type=float)
    ap.add_argument('--iface', default=None)
    ap.add_argument('--address', default='239.69.83.67')
    ap.add_argument('--port', type=int, default=5004)
    ap.add_argument('--name', default='Ardzy test stream')
    ap.add_argument('--seconds', type=float, default=0)
    a = ap.parse_args()
    rate, frames = frames_from_wav(a.wav) if a.wav else frames_tone(a.tone or 1000.0)
    iface = a.iface or pick_iface()
    per = rate // 1000 or 1                             # samples per packet: 1 ms
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(iface))
    sdp = ('v=0\r\no=- 1 1 IN IP4 %s\r\ns=%s\r\nc=IN IP4 %s/32\r\nt=0 0\r\nm=audio %d RTP/AVP 96\r\n'
           'a=rtpmap:96 L24/%d/2\r\na=ptime:1\r\na=recvonly\r\n' % (iface, a.name, a.address, a.port, rate)).encode()
    sap = bytes([0x20, 0, 0, 0x01]) + socket.inet_aton(iface) + b'application/sdp\0' + sdp
    print('sending "%s": %s:%d, L24/%d/2, 1 ms packets, from %s (Ctrl+C stops)' % (a.name, a.address, a.port, rate, iface))
    seq, ts, ssrc = 0, 0, 0x41525A59
    t0 = time.perf_counter()
    sent, next_sap = 0, 0.0
    try:
        while True:
            now = time.perf_counter() - t0
            if a.seconds and now > a.seconds:
                break
            if now >= next_sap:
                sock.sendto(sap, ('239.255.255.255', 9875))
                next_sap = now + 5
            while sent * per / rate <= now:             # every packet that is due
                pay = bytearray()
                for _ in range(per):
                    l, r = next(frames)
                    pay += (l & 0xFFFFFF).to_bytes(3, 'big') + (r & 0xFFFFFF).to_bytes(3, 'big')
                hdr = struct.pack('!BBHII', 0x80, 96, seq & 0xFFFF, ts & 0xFFFFFFFF, ssrc)
                sock.sendto(hdr + bytes(pay), (a.address, a.port))
                seq, ts, sent = seq + 1, ts + per, sent + 1
            time.sleep(0.001)
    except KeyboardInterrupt:
        pass
    sock.sendto(bytes([0x24, 0, 0, 0x01]) + socket.inet_aton(iface) + b'application/sdp\0' + sdp, ('239.255.255.255', 9875))
    print('stopped after %d packets' % sent)


if __name__ == '__main__':
    sys.exit(main())
