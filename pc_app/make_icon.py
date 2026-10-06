"""Draws the Ardzy icon (a chip with an "A") and writes ardzy.ico (PNG-in-ICO, 16..256 px).
Pure Python (no Pillow needed)."""
import struct, zlib, math, os


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def rrect(px, py, x0, y0, x1, y1, r):
    """signed distance to a rounded rectangle (negative inside)"""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    qx, qy = abs(px - cx) - (x1 - x0) / 2 + r, abs(py - cy) - (y1 - y0) / 2 + r
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r


GREEN, DARK, PIN, MINT = (19, 137, 74), (11, 61, 34), (232, 255, 241), (125, 255, 176)


def color_at(x, y):
    """x, y in 0..64 icon units -> RGBA"""
    if rrect(x, y, 4, 4, 60, 60, 12) > 0:
        return None
    c = GREEN
    pins = []                                                # chip pins on all 4 sides
    for k in (22, 32, 42):
        pins += [(12, k, 18, k), (46, k, 52, k), (k, 12, k, 18), (k, 46, k, 52)]
    if any(seg_dist(x, y, *p) < 1.5 for p in pins):
        c = PIN
    d = rrect(x, y, 18, 18, 46, 46, 4)
    if d < 0:
        c = DARK
    if abs(d) < 1.25:
        c = PIN
    if seg_dist(x, y, 25, 39, 32, 24) < 1.6 or seg_dist(x, y, 32, 24, 39, 39) < 1.6 or seg_dist(x, y, 28, 34, 36, 34) < 1.6:
        c = MINT
    return c


def render(size, ss=4):
    rows = []
    for j in range(size):
        row = bytearray([0])
        for i in range(size):
            acc = [0, 0, 0, 0]
            for sj in range(ss):
                for si in range(ss):
                    c = color_at((i + (si + .5) / ss) * 64 / size, (j + (sj + .5) / ss) * 64 / size)
                    if c:
                        acc[0] += c[0]; acc[1] += c[1]; acc[2] += c[2]; acc[3] += 255
            n = ss * ss
            a = acc[3] // n
            row += bytes([acc[0] // max(1, acc[3] // 255), acc[1] // max(1, acc[3] // 255),
                          acc[2] // max(1, acc[3] // 255), a]) if a else b'\0\0\0\0'
        rows.append(bytes(row))
    raw = b''.join(rows)
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    sizes = [16, 24, 32, 48, 64, 128, 256]
    pngs = [render(s) for s in sizes]
    head = struct.pack('<HHH', 0, 1, len(sizes))
    off = 6 + 16 * len(sizes)
    dirs = b''
    for s, p in zip(sizes, pngs):
        dirs += struct.pack('<BBBBHHII', s % 256, s % 256, 0, 0, 1, 32, len(p), off)
        off += len(p)
    open(os.path.join(here, 'ardzy.ico'), 'wb').write(head + dirs + b''.join(pngs))
    open(os.path.join(here, 'ui', 'icon.png'), 'wb').write(pngs[-2])
    print('wrote ardzy.ico')


main()
