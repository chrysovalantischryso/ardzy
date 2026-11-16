"""Ardzy bit2fasm: read a Xilinx 7-series .bit back into frames and FASM features, pure Python.

The reverse of fasm2bit.py, used to check it: .bit -> configuration packets -> frames (FDRI data
with the frame address auto-increment of the part) -> the features of the Project X-Ray database
whose bits are in the frames. Like Project X-Ray's bitread + bit2fasm.py (ISC license).

The feature lookup here is written apart from fasm2bit's (only the part's frame order and the
mapping YAML reader are shared), so a mistake in one shows up as a difference in the round trip.

Usage: python bit2fasm.py <db family dir> <part> <in.bit> [out.fasm] [--frames out.frm]
"""
import json, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fasm2bit  # noqa: E402

FRAME_WORDS = fasm2bit.FRAME_WORDS
ECC_WORD, ECC_MASK = 50, 0x1FFF          # word 50, bits 0..12 of every frame: the frame's ECC
SYNC = 0xAA995566
BLOCK_NAMES = {v: k for k, v in fasm2bit.BLOCK_TYPES.items()}


class BitError(Exception):
    pass


# ------------------------------------------------------------------ .bit file
def read_bit(path):
    """({header field: text}, [32-bit words of the configuration data])"""
    data = open(path, 'rb').read()
    head, pos = {}, 0
    if data[:2] == b'\x00\x09':                      # the .bit header: fields a..d, then 'e' + length
        pos = 2 + 9
        if data[pos:pos + 2] != b'\x00\x01':
            raise BitError('bad .bit header')
        pos += 2
        while pos < len(data):
            tag = chr(data[pos])
            pos += 1
            if tag == 'e':
                n = int.from_bytes(data[pos:pos + 4], 'big')
                pos += 4
                if pos + n != len(data):
                    raise BitError('.bit length field says %d bytes, the file has %d' % (n, len(data) - pos))
                break
            n = int.from_bytes(data[pos:pos + 2], 'big')
            head[tag] = data[pos + 2:pos + 2 + n].rstrip(b'\0').decode(errors='replace')
            pos += 2 + n
    body = data[pos:]
    if len(body) % 4:
        raise BitError('configuration data is not whole 32-bit words')
    return head, [int.from_bytes(body[i:i + 4], 'big') for i in range(0, len(body), 4)]


def packets(words):
    """[(register, [data words])] of every register write after the sync word (UG470 type 1 / 2 packets)."""
    try:
        i = words.index(SYNC) + 1
    except ValueError:
        raise BitError('no sync word in the bitstream')
    out, reg = [], None
    while i < len(words):
        w = words[i]
        i += 1
        kind, op = w >> 29, w >> 27 & 3
        if kind == 1:
            reg, n = w >> 13 & 0x1F, w & 0x7FF
        elif kind == 2:
            if reg is None:
                raise BitError('type 2 packet without a type 1 before it (word %d)' % (i - 1))
            n = w & 0x7FFFFFF
        else:
            raise BitError('bad packet header 0x%08X at word %d' % (w, i - 1))
        if i + n > len(words):
            raise BitError('packet at word %d runs past the end' % (i - 1))
        if op == 2 and n:                            # write
            out.append((reg, words[i:i + n]))
        elif op == 2 and kind == 1 and n == 0:
            pass                                     # the header of a type 2 write
        i += n
    return out


def frames_from_packets(pk, part):
    """{frame address: [101 words]} from the FDRI writes, plus {'idcode', 'commands', 'pad_errors'}."""
    frames, info = {}, {'idcode': None, 'commands': [], 'pad_errors': []}
    far = 0
    for reg, data in pk:
        if reg == fasm2bit.R_FAR:
            far = data[-1]
        elif reg == fasm2bit.R_IDCODE:
            info['idcode'] = data[-1]
        elif reg == fasm2bit.R_CMD:
            info['commands'] += data
        elif reg == fasm2bit.R_FDRI:
            a, i = far, 0
            while a is not None and i + FRAME_WORDS <= len(data):
                if a in frames:
                    raise BitError('frame 0x%08X written twice' % a)
                frames[a] = list(data[i:i + FRAME_WORDS])
                i += FRAME_WORDS
                n = part.next(a)
                if n is None or fasm2bit.far_fields(n)[:3] != fasm2bit.far_fields(a)[:3]:
                    pad = data[i:i + 2 * FRAME_WORDS]       # two pad frames at each row / half / type end
                    if len(pad) != 2 * FRAME_WORDS or any(pad):
                        info['pad_errors'].append(a)
                    i += 2 * FRAME_WORDS
                a = n
            if i != len(data):
                raise BitError('FDRI has %d words left after the last frame of the part' % (len(data) - i))
    return frames, info


def ecc_errors(frames):
    """Frame addresses whose ECC word does not match their data."""
    bad = []
    for a, words in frames.items():
        w = list(words)
        fasm2bit.update_ecc(w)
        if w[ECC_WORD] != words[ECC_WORD]:
            bad.append(a)
    return bad


def read_frames_file(path):
    """A frames file: fasm2bit/prjxray '0xADDR 0xW,0xW,...' lines or bitread -o '.frame 0xADDR' blocks."""
    frames, cur = {}, None
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        if line.startswith('.frame'):
            cur = int(line.split()[1], 16)
            frames[cur] = []
        elif line.startswith('0x') and ' ' in line and ',' in line:
            a, w = line.split(None, 1)
            frames[int(a, 16)] = [int(x, 16) for x in w.split(',')]
            cur = None
        elif cur is not None:
            frames[cur] += [int(x, 16) for x in line.split()]
    for a, w in frames.items():
        if len(w) != FRAME_WORDS:
            raise BitError('frame 0x%08X has %d words' % (a, len(w)))
    return frames


# ------------------------------------------------------------------ database (own reader)
class BitDB:
    """Tile grid and segment bits of a Project X-Ray family, for the feature <-> bit lookups."""

    def __init__(self, root, part):
        self.root, self.part = root, part
        parts = fasm2bit._simple_yaml(os.path.join(root, 'mapping', 'parts.yaml'))
        devices = fasm2bit._simple_yaml(os.path.join(root, 'mapping', 'devices.yaml'))
        if part not in parts:
            raise BitError('part %s is not in the database' % part)
        fabric = devices[parts[part]['device']]['fabric']
        self.tilegrid = json.load(open(os.path.join(root, fabric, 'tilegrid.json')))
        self.part_info = fasm2bit.Part(os.path.join(root, part, 'part.json'))
        self._seg, self._ppips = {}, {}

    def segbits(self, tile_type):
        """{block type: {feature name without the tile type: [(col, word bit, isset)]}}"""
        t = tile_type.upper()
        if t not in self._seg:
            out = {}
            for bt, suffix in ((0, ''), (1, '.block_ram')):
                p = os.path.join(self.root, 'segbits_%s%s.db' % (t.lower(), suffix))
                if not os.path.isfile(p):
                    continue
                seg = {}
                for line in open(p):
                    f = line.split()
                    if len(f) < 2 or not f[0].startswith(t + '.'):
                        continue
                    bits = []
                    for b in f[1:]:
                        neg = b.startswith('!')
                        c, w = b.lstrip('!').split('_')
                        bits.append((int(c), int(w), not neg))
                    seg[f[0][len(t) + 1:]] = bits
                out[bt] = seg
            self._seg[t] = out
        return self._seg[t]

    def ppips(self, tile_type):
        t = tile_type.upper()
        if t not in self._ppips:
            s, p = set(), os.path.join(self.root, 'ppips_%s.db' % t.lower())
            if os.path.isfile(p):
                for line in open(p):
                    f = line.split()
                    if len(f) == 2 and f[0].startswith(t + '.'):
                        s.add(f[0][len(t) + 1:])
            self._ppips[t] = s
        return self._ppips[t]

    def tile_layout(self, tile):
        """(segbits tile type, {block type: (base, frames, first word, words, word shift)}, {site: alias site})
        word shift: the word of the segbits that is the tile's first word (aliased tiles start inside)."""
        info = self.tilegrid[tile]
        seg_type, lay, sites = info['type'], {}, {}
        for name, b in info.get('bits', {}).items():
            al = b.get('alias')
            shift = 0
            if al:
                seg_type, shift = al['type'], al['start_offset']
                sites.update(al.get('sites', {}))
            lay[fasm2bit.BLOCK_TYPES[name]] = (int(b['baseaddr'], 0), b['frames'], b['offset'], b['words'], shift)
        return seg_type, lay, sites

    def feature_bits(self, tile, feature):
        """[(frame, word, bit, isset)] of 'feature' (no tile prefix, '[n]' kept) in 'tile'.
        None: not in the database. []: a pseudo pip (no bits)."""
        info = self.tilegrid.get(tile)
        if info is None:
            return None
        if feature in self.ppips(info['type']):
            return []
        seg_type, lay, sites = self.tile_layout(tile)
        parts = feature.split('.')
        if parts[0] in sites:
            parts[0] = sites[parts[0]]
        name = '.'.join(parts)
        cands = [name] if name.endswith(']') else [name, name + '[0]']
        for bt, seg in self.segbits(seg_type).items():
            for n in cands:
                if n in seg and bt in lay:
                    base, _, first, _, shift = lay[bt]
                    out = []
                    for c, wb, isset in seg[n]:
                        wb += (first - shift) * 32
                        out.append((base + c, wb // 32, wb % 32, isset))
                    return out
        return None

    def in_tile(self, tile, bits):
        """True if every (frame, word, bit, _) is inside the tile's own frames and words."""
        _, lay, _ = self.tile_layout(tile)
        for f, w, _b, _s in bits:
            if not any(base <= f < base + nf and first <= w < first + nw for base, nf, first, nw, _ in lay.values()):
                return False
        return True


# ------------------------------------------------------------------ frames to FASM
def disassemble(db, frames):
    """(sorted FASM lines, [(frame, word, bit)] set bits no feature explains).
    A feature is reported when all its set bits are 1 and all its cleared bits are 0 (it must have
    at least one set bit: features of only cleared bits are the default state everywhere)."""
    setbits = set()
    for a, words in frames.items():
        for w, v in enumerate(words):
            if w == ECC_WORD:
                v &= ~ECC_MASK
            while v:
                low = v & -v
                setbits.add((a, w, low.bit_length() - 1))
                v ^= low
    by_frame = defaultdict(list)
    for t, info in db.tilegrid.items():
        for b in info.get('bits', {}).values():
            base = int(b['baseaddr'], 0)
            for i in range(b['frames']):
                by_frame[base + i].append(t)
    tiles = {t for f, _, _ in setbits for t in by_frame.get(f, ())}
    lines, explained = set(), set()
    for tile in sorted(tiles):
        seg_type, lay, sites = db.tile_layout(tile)
        rev = {v: k for k, v in sites.items()}
        for bt, (base, nf, first, nw, shift) in lay.items():
            seg = db.segbits(seg_type).get(bt)
            if not seg:
                continue
            here = {(f - base, w * 32 + b - (first - shift) * 32)
                    for f, w, b in setbits if base <= f < base + nf and first <= w < first + nw}
            if not here:
                continue
            for name, bits in seg.items():
                pos = [(c, wb) for c, wb, s in bits if s]
                if not pos or not all(p in here for p in pos):
                    continue
                if any((c, wb) in here for c, wb, s in bits if not s):
                    continue
                if shift and not all(shift <= wb // 32 < shift + nw for _, wb, _ in bits):
                    continue
                parts = name.split('.')
                if parts[0] in rev:
                    parts[0] = rev[parts[0]]
                lines.add(tile + '.' + '.'.join(parts))
                for c, wb in pos:
                    wb += (first - shift) * 32
                    explained.add((base + c, wb // 32, wb % 32))
    return sorted(lines), sorted(setbits - explained)


def decode(db_root, part, bit_path):
    """Everything about a .bit: {'header', 'frames', 'idcode', 'ecc_errors', 'pad_errors', 'fasm', 'unknown_bits'}"""
    db = BitDB(db_root, part)
    head, words = read_bit(bit_path)
    frames, info = frames_from_packets(packets(words), db.part_info)
    fasm, unknown = disassemble(db, frames)
    return {'header': head, 'frames': frames, 'idcode': info['idcode'], 'commands': info['commands'],
            'ecc_errors': ecc_errors(frames), 'pad_errors': info['pad_errors'], 'fasm': fasm,
            'unknown_bits': unknown}


if __name__ == '__main__':
    a = sys.argv[1:]
    fr = None
    if '--frames' in a:
        i = a.index('--frames')
        fr = a[i + 1]
        del a[i:i + 2]
    if len(a) not in (3, 4):
        print(__doc__)
        sys.exit(2)
    r = decode(a[0], a[1], a[2])
    out = open(a[3], 'w') if len(a) == 4 else sys.stdout
    for line in r['fasm']:
        out.write(line + '\n')
    if fr:
        with open(fr, 'w') as f:
            for addr in sorted(r['frames']):
                f.write('0x%08X ' % addr + ','.join('0x%08X' % x for x in r['frames'][addr]) + '\n')
    print('bit2fasm: %d frames, %d features, %d unknown bits, %d ECC errors, IDCODE 0x%08X' % (
        len(r['frames']), len(r['fasm']), len(r['unknown_bits']), len(r['ecc_errors']), r['idcode'] or 0),
        file=sys.stderr)
    sys.exit(1 if r['ecc_errors'] or r['pad_errors'] else 0)
