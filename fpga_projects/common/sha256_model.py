"""SHA-256 written out step by step: the same steps the FPGA's sha256_core takes, one round per clock.

Used by project 13 (the miner needs the "midstate": the hash state after the header's first 64 bytes)
and as a teaching model: compress() is the whole algorithm in 25 lines.
"""
import struct


def _iroot(n, k):
    x = int(round(n ** (1.0 / k)))
    while x ** k > n:
        x -= 1
    while (x + 1) ** k <= n:
        x += 1
    return x


_PRIMES = [p for p in range(2, 312) if all(p % d for d in range(2, int(p ** 0.5) + 1))][:64]
K = [_iroot(p << 96, 3) & 0xFFFFFFFF for p in _PRIMES]          # cube roots of the first 64 primes
IV = [_iroot(p << 64, 2) & 0xFFFFFFFF for p in _PRIMES[:8]]     # square roots of the first 8 primes
M = 0xFFFFFFFF


def rotr(x, n):
    return ((x >> n) | (x << (32 - n))) & M


def compress(state, block_words):
    """One SHA-256 compression: 8 state words + 16 block words -> 8 new state words."""
    w = list(block_words)
    for t in range(16, 64):
        s0 = rotr(w[t - 15], 7) ^ rotr(w[t - 15], 18) ^ (w[t - 15] >> 3)
        s1 = rotr(w[t - 2], 17) ^ rotr(w[t - 2], 19) ^ (w[t - 2] >> 10)
        w.append((w[t - 16] + s0 + w[t - 7] + s1) & M)
    a, b, c, d, e, f, g, h = state
    for t in range(64):
        S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
        ch = (e & f) ^ (~e & g)
        t1 = (h + S1 + ch + K[t] + w[t]) & M
        S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
        maj = (a & b) ^ (a & c) ^ (b & c)
        t2 = (S0 + maj) & M
        a, b, c, d, e, f, g, h = (t1 + t2) & M, a, b, c, (d + t1) & M, e, f, g
    return [(x + y) & M for x, y in zip(state, (a, b, c, d, e, f, g, h))]


def sha256(data):
    """The whole hash (padding + compressions), for learning: equals hashlib.sha256(data).digest()."""
    msg = data + b'\x80' + b'\x00' * ((55 - len(data)) % 64) + struct.pack('>Q', 8 * len(data))
    h = IV
    for i in range(0, len(msg), 64):
        h = compress(h, struct.unpack('>16I', msg[i:i + 64]))
    return struct.pack('>8I', *h)


def header_job(header):
    """An 80-byte block header -> (midstate after its first 64 bytes, the 3 words of bytes 64..75)."""
    mid = compress(IV, struct.unpack('>16I', header[:64]))
    tail = list(struct.unpack('>3I', header[64:76]))
    return mid, tail


def zero_bits(digest):
    """Leading zero bits of the hash as Bitcoin shows it (the digest's bytes reversed)."""
    n = 0
    for byte in reversed(digest):
        if byte == 0:
            n += 8
            continue
        return n + 8 - byte.bit_length()
    return n
