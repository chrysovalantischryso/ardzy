"""Ardzy fasm2bit: FASM (the output of nextpnr) to a Xilinx 7-series .bit file, pure Python.

A port of Project X-Ray's utils/fasm2frames.py + prjxray/fasm_assembler.py (FASM features to
configuration frames) and tools/xc7frames2bit (frames to a bitstream). Project X-Ray is
(C) The Project X-Ray Authors, ISC license.

Database: a Project X-Ray family folder (for example prjxray-db/zynq7) with
  mapping/parts.yaml, mapping/devices.yaml, <fabric>/tilegrid.json, segbits_*.db, ppips_*.db,
  <part>/part.json, <part>/package_pins.csv, <part>/required_features.fasm

Usage: python fasm2bit.py <db family dir> <part> <in.fasm> <out.bit> [--frames out.frm]
"""
import csv, json, os, re, sys, time
from collections import defaultdict

FRAME_WORDS = 101
BLOCK_TYPES = {'CLB_IO_CLK': 0, 'BLOCK_RAM': 1, 'CFG_CLB': 2}


class FasmError(Exception):
    pass


# ------------------------------------------------------------------ frame addresses / part
def far(block, bottom, row, col, minor):
    return (block & 7) << 23 | (1 if bottom else 0) << 22 | (row & 0x1F) << 17 | (col & 0x3FF) << 7 | (minor & 0x7F)


def far_fields(a):
    return a >> 23 & 7, bool(a >> 22 & 1), a >> 17 & 0x1F, a >> 7 & 0x3FF, a & 0x7F


class Part:
    """Frame layout from part.json, with the same "next frame address" rules as prjxray."""

    def __init__(self, path):
        d = json.load(open(path))
        idc = d['idcode']
        self.idcode = int(idc, 0) if isinstance(idc, str) else int(idc)
        self.iobanks = d.get('iobanks', {})
        # regions[bottom][row][block][col] = frame count, all keys int and sorted
        self.regions = {}
        for half, reg in d['global_clock_regions'].items():
            rows = {}
            for r, row in reg['rows'].items():
                buses = {}
                for bus, b in row['configuration_buses'].items():
                    buses[BLOCK_TYPES[bus]] = {int(c): v['frame_count'] for c, v in b['configuration_columns'].items()}
                rows[int(r)] = buses
            self.regions[half == 'bottom'] = dict(sorted(rows.items()))

    def valid(self, a):
        bt, bot, row, col, minor = far_fields(a)
        reg = self.regions.get(bot)
        if not reg or row not in reg or bt not in reg[row] or col not in reg[row][bt]:
            return False
        return minor < reg[row][bt][col]

    def _next_in_region(self, a):
        bt, bot, row, col, minor = far_fields(a)
        reg = self.regions.get(bot, {})
        if row not in reg:
            return None
        bus = reg[row].get(bt)
        if bus is not None and col in bus and self.valid(a):
            if minor + 1 < bus[col]:                     # same column
                return a + 1
            cols = sorted(bus)
            i = cols.index(col)
            if i + 1 < len(cols):                       # next column
                n = far(bt, bot, row, cols[i + 1], 0)
                if self.valid(n):
                    return n
        rows = list(reg)                                # next row
        i = rows.index(row)
        if i + 1 < len(rows):
            n = far(bt, bot, rows[i + 1], 0, 0)
            if self.valid(n):
                return n
        return None

    def next(self, a):
        n = self._next_in_region(a)
        if n is not None:
            return n
        bt, bot, _, _, _ = far_fields(a)
        if not bot:
            n = far(bt, True, 0, 0, 0)
            if self.valid(n):
                return n
        if bt < 1:
            n = far(1, False, 0, 0, 0)
            if self.valid(n):
                return n
        if bt < 2:
            n = far(2, False, 0, 0, 0)
            if self.valid(n):
                return n
        return None


# ------------------------------------------------------------------ database
def _simple_yaml(path):
    """Two-level YAML of the mapping files: 'name:' then '  key: value' lines."""
    out, cur = {}, None
    for line in open(path):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if not line.startswith(' '):
            cur = line.split(':')[0].strip().strip('"' + "'")
            out[cur] = {}
        elif cur is not None and ':' in line:
            k, v = line.strip().split(':', 1)
            out[cur][k.strip()] = v.strip().strip('\'"')
    return out


def _parse_bit(s):
    isset = not s.startswith('!')
    col, bit = s.lstrip('!').split('_')
    return int(col), int(bit), isset


def _read_segbits(path):
    seg = {}
    if path and os.path.isfile(path):
        for line in open(path):
            p = line.split()
            if len(p) > 1:
                seg[p[0]] = [_parse_bit(b) for b in p[1:]]
    return seg


class TileSegbits:
    def __init__(self, root, tile_type):
        t = tile_type.lower()
        self.segbits = {}
        s = _read_segbits(os.path.join(root, 'segbits_%s.db' % t))
        if s:
            self.segbits[0] = s
        s = _read_segbits(os.path.join(root, 'segbits_%s.block_ram.db' % t))
        if s:
            self.segbits[1] = s
        self.ppips = set()
        pp = os.path.join(root, 'ppips_%s.db' % t)
        if os.path.isfile(pp):
            for line in open(pp):
                p = line.split()
                if len(p) == 2:
                    self.ppips.add(p[0])
        self.addresses = {}
        for bt, seg in self.segbits.items():
            for feat in seg:
                i, j = feat.rfind('['), feat.rfind(']')
                if i != -1 and j != -1:
                    self.addresses.setdefault(feat[:i], {})[int(feat[i + 1:j])] = (bt, feat)

    def feature_bits(self, feature, address):
        """[(block type, word column, word bit, isset)] in tile-relative form, or None if unknown."""
        if feature in self.ppips:
            return []
        if address == 0:
            for bt, seg in self.segbits.items():
                if feature in seg:
                    return [(bt,) + b for b in seg[feature]]
        hit = self.addresses.get(feature, {}).get(address)
        if hit is None:
            return None
        bt, feat = hit
        return [(bt,) + b for b in self.segbits[bt][feat]]


class Database:
    def __init__(self, root, part):
        self.root, self.part = root, part
        parts = _simple_yaml(os.path.join(root, 'mapping', 'parts.yaml'))
        devices = _simple_yaml(os.path.join(root, 'mapping', 'devices.yaml'))
        if part not in parts:
            raise FasmError('part %s is not in the database' % part)
        self.fabric = devices[parts[part]['device']]['fabric']
        self.tilegrid = json.load(open(os.path.join(root, self.fabric, 'tilegrid.json')))
        self.segbits = {}
        self.part_info = Part(os.path.join(root, part, 'part.json'))
        rf = os.path.join(root, part, 'required_features.fasm')
        self.required = [l.strip() for l in open(rf)] if os.path.isfile(rf) else []
        self.required = [l for l in self.required if l]

    def tile_segbits(self, tile_type):
        if tile_type not in self.segbits:
            self.segbits[tile_type] = TileSegbits(self.root, tile_type)
        return self.segbits[tile_type]

    def tile_bits(self, tile):
        """{block type: (base address, frames, offset words, words, alias or None)}"""
        out = {}
        for k, b in self.tilegrid[tile].get('bits', {}).items():
            out[BLOCK_TYPES[k]] = (int(b['baseaddr'], 0), b['frames'], b['offset'], b['words'], b.get('alias'))
        return out


# ------------------------------------------------------------------ FASM
_VAL = re.compile(r"^(\d+)'([bhdo])([0-9a-fA-F_xX]+)$")


def _value(s):
    s = s.strip().replace('_', '')
    m = _VAL.match(s)
    if m:
        return int(m.group(3), {'b': 2, 'h': 16, 'd': 10, 'o': 8}[m.group(2)])
    return int(s, 0)


def parse_fasm(lines):
    """Yields (line text, tile, feature without address, address) for every set bit."""
    for raw in lines:
        line = raw.split('#', 1)[0]
        line = re.sub(r'\{[^}]*\}', '', line).strip()
        if not line:
            continue
        val = 1
        if '=' in line:
            line, v = line.split('=', 1)
            line, val = line.strip(), _value(v)
        m = re.match(r'^([^\[\s]+)(?:\[(\d+)(?::(\d+))?\])?$', line)
        if not m:
            raise FasmError('bad FASM line: %r' % raw.strip())
        name, hi, lo = m.group(1), m.group(2), m.group(3)
        tile, _, feature = name.partition('.')
        if hi is None:
            if val:
                yield raw.strip(), tile, feature, 0
        else:
            hi = int(hi)
            lo = int(lo) if lo is not None else hi
            for i in range(lo, hi + 1):
                if val >> (i - lo) & 1:
                    yield raw.strip(), tile, feature, i


class Assembler:
    def __init__(self, db):
        self.db = db
        self.bits = {}          # (frame, word, bit) -> 0/1
        self.lines = {}
        self.missing = []
        self.warnings = []
        self.set_features = []

    def _set(self, key, v, line):
        frame, word, bit = key
        if word >= FRAME_WORDS:
            return
        old = self.bits.get(key)
        if old is not None and old != v:
            raise FasmError('FASM line "%s" conflicts with "%s" at bit %s' % (line, self.lines[key], key))
        self.bits[key] = v
        self.lines[key] = line

    def enable(self, tile, feature, address, line):
        if tile not in self.db.tilegrid:
            self.missing.append('unknown tile %s (line "%s")' % (tile, line))
            return
        info = self.db.tilegrid[tile]
        ttype = info['type']
        tbits = self.db.tile_bits(tile)
        alias = next((b[4] for b in tbits.values() if b[4]), None)
        if alias:
            seg = self.db.tile_segbits(alias['type'])
            if ttype + '.' + feature in self.db.tile_segbits(ttype).ppips:
                return
            parts = feature.split('.')
            if parts and parts[0] in alias.get('sites', {}):
                parts[0] = alias['sites'][parts[0]]
            feat = '.'.join(parts)
            offsets = {bt: b[2] - b[4]['start_offset'] for bt, b in tbits.items()}
            key = alias['type'] + '.' + feat
        else:
            seg = self.db.tile_segbits(ttype)
            offsets = {bt: b[2] for bt, b in tbits.items()}
            key = ttype + '.' + feature
        found = seg.feature_bits(key, address)
        if found is None:
            if ttype.startswith('CFG_CENTER') and 'DNA_PORT' in feature:
                # site pin wires of the device DNA block: fixed connections, no configuration bits
                self.warnings.append(line)
                return
            self.missing.append('segment DB %s has no feature %s (line "%s")' % (ttype, key, line))
            return
        for bt, col, wbit, isset in found:
            base = tbits[bt][0]
            word_bit = offsets[bt] * 32 + wbit
            self._set((base + col, word_bit // 32, word_bit % 32), 1 if isset else 0, line)

    def add(self, lines):
        for line, tile, feature, addr in parse_fasm(lines):
            self.set_features.append((tile, feature, addr))
            self.enable(tile, feature, addr, line)

    def stepdown(self):
        """Like prjxray: a STEPDOWN feature on one IOB of a bank goes to every unused IOB of that bank."""
        root, part = self.db.root, self.db.part
        tile_to_bank, bank_to_tile = {}, defaultdict(set)
        for bank, loc in self.db.part_info.iobanks.items():
            t = 'HCLK_IOI3_' + loc
            bank_to_tile[bank].add(t)
            tile_to_bank[t] = bank
        pp = os.path.join(root, part, 'package_pins.csv')
        if os.path.isfile(pp):
            for row in csv.DictReader(open(pp)):
                bank_to_tile[row['bank']].add(row['tile'])
                tile_to_bank[row['tile']] = row['bank']
        used, tags, banks = set(), defaultdict(set), set()
        for tile, feature, _ in self.set_features:
            p = feature.split('.', 1)
            if len(p) == 2:
                if 'IOB33' in tile:
                    used.add((tile, p[0]))
                if 'STEPDOWN' in p[1]:
                    banks.add(tile_to_bank[tile])
                    tags[tile_to_bank[tile]].add(p[1])
        extra = []
        for bank in banks:
            for tile in bank_to_tile[bank]:
                if 'IOB33' in tile:
                    for site in self.db.tilegrid[tile]['sites']:
                        s = 'IOB_Y%d' % (int(site[-1]) % 2)
                        if (tile, s) not in used:
                            extra += ['%s.%s.%s' % (tile, s, t) for t in tags[bank]]
                if 'HCLK_IOI3' in tile:
                    extra.append('%s.STEPDOWN' % tile)
        self.add(extra)

    def frames(self):
        """Every frame of every tile (zeros), then the set bits."""
        frames = {}
        for tile, info in self.db.tilegrid.items():
            for k, b in info.get('bits', {}).items():
                base = int(b['baseaddr'], 0)
                for i in range(b['frames']):
                    frames.setdefault(base + i, [0] * FRAME_WORDS)
        for (frame, word, bit), v in self.bits.items():
            words = frames.setdefault(frame, [0] * FRAME_WORDS)
            if v:
                words[word] |= 1 << bit
        return frames


# ------------------------------------------------------------------ frames to bitstream
def _icap_ecc(idx, data, ecc):
    val = idx * 32
    if idx > 0x25:
        val += 0x1360
    elif idx > 0x6:
        val += 0x1340
    else:
        val += 0x1320
    if idx == 0x32:
        data &= 0xFFFFE000
    for i in range(32):
        if data & 1:
            ecc ^= val + i
        data >>= 1
    if idx == 0x64:
        v = ecc & 0xFFF
        v ^= v >> 8
        v ^= v >> 4
        v ^= v >> 2
        v ^= v >> 1
        ecc ^= (v & 1) << 12
    return ecc


def update_ecc(words):
    ecc = 0
    for i, w in enumerate(words):
        ecc = _icap_ecc(i, w, ecc)
    words[0x32] = (words[0x32] & 0xFFFFE000) | (ecc & 0x1FFF)


# 7-series configuration registers and commands (UG470)
R_CRC, R_FAR, R_FDRI, R_CMD, R_CTL0, R_MASK, R_COR0, R_IDCODE, R_COR1, R_WBSTAR, R_TIMER, R_UNKNOWN, R_CTL1 = \
    0x00, 0x01, 0x02, 0x04, 0x05, 0x06, 0x09, 0x0C, 0x0E, 0x10, 0x11, 0x13, 0x18
C_NOP, C_WCFG, C_LFRM, C_START, C_RCRC, C_SWITCH, C_GRESTORE, C_DESYNC = 0x0, 0x1, 0x3, 0x5, 0x7, 0x9, 0xA, 0xD
NOP = 0x20000000


def t1(reg, *data):
    return [1 << 29 | 2 << 27 | reg << 13 | len(data)] + list(data)


def bitstream_words(frames, part):
    """The configuration packets: the same sequence as prjxray's xc7frames2bit."""
    for words in frames.values():
        update_ecc(words)
    a = 0
    while a is not None:                                  # frames the tile grid does not list
        frames.setdefault(a, [0] * FRAME_WORDS)
        a = part.next(a)
    data = []
    for addr in sorted(frames):
        data += frames[addr]
        n = part.next(addr)
        if n is not None and far_fields(n)[:3] != far_fields(addr)[:3]:
            data += [0] * (2 * FRAME_WORDS)               # two zero frames between rows / halves / types
    data += [0] * (2 * FRAME_WORDS)
    cor0 = 1 << 25 | 3 << 12 | 7 << 9 | 7 << 6 | 4 << 3 | 5    # = 0x02003FE5
    w = [0xFFFFFFFF] * 8 + [0x000000BB, 0x11220044, 0xFFFFFFFF, 0xFFFFFFFF, 0xAA995566]
    w += [NOP] + t1(R_TIMER, 0) + t1(R_WBSTAR, 0) + t1(R_CMD, C_NOP) + [NOP] + t1(R_CMD, C_RCRC) + [NOP, NOP]
    w += t1(R_UNKNOWN, 0) + t1(R_COR0, cor0) + t1(R_COR1, 0) + t1(R_IDCODE, part.idcode) + t1(R_CMD, C_SWITCH)
    w += [NOP] + t1(R_MASK, 0x401) + t1(R_CTL0, 0x501) + t1(R_MASK, 0) + t1(R_CTL1, 0) + [NOP] * 8
    w += t1(R_FAR, 0) + t1(R_CMD, C_WCFG) + [NOP]
    w += t1(R_FDRI) + [2 << 29 | 2 << 27 | len(data)] + data
    w += t1(R_CMD, C_RCRC) + [NOP, NOP] + t1(R_CMD, C_GRESTORE) + [NOP] + t1(R_CMD, C_LFRM) + [NOP] * 100
    w += t1(R_CMD, C_START) + [NOP] + t1(R_FAR, 0x3BE0000) + t1(R_MASK, 0x501) + t1(R_CTL0, 0x501)
    w += t1(R_CMD, C_RCRC) + [NOP, NOP] + t1(R_CMD, C_DESYNC) + [NOP] * 400
    return w


def bit_header(part_name, source):
    def field(tag, text):
        b = text.encode() + b'\0'
        return tag + bytes([len(b) >> 8, len(b) & 0xFF]) + b
    t = time.gmtime()
    vivado_part = re.sub(r'^xc', '', part_name).split('-')[0]      # the form Vivado writes: 7z010clg400
    return (bytes([0x0, 0x9, 0x0f, 0xf0, 0x0f, 0xf0, 0x0f, 0xf0, 0x0f, 0xf0, 0x00, 0x00, 0x01])
            + field(b'a', source + ';Generator=ardzy fasm2bit') + field(b'b', vivado_part)
            + field(b'c', time.strftime('%Y/%m/%d', t)) + field(b'd', time.strftime('%H:%M:%S', t)))


def assemble(db_root, part, fasm_path, bit_path, frames_path=None, log=print):
    t0 = time.time()
    db = Database(db_root, part)
    asm = Assembler(db)
    asm.add(open(fasm_path))
    asm.add(db.required)
    if asm.missing:
        raise FasmError('features not in the database:\n  ' + '\n  '.join(asm.missing[:30]))
    asm.stepdown()
    frames = asm.frames()
    if frames_path:
        with open(frames_path, 'w') as f:
            for a in sorted(frames):
                f.write('0x%08X ' % a + ','.join('0x%08X' % x for x in frames[a]) + '\n')
    words = bitstream_words(frames, db.part_info)
    body = b''.join(x.to_bytes(4, 'big') for x in words)
    with open(bit_path, 'wb') as f:
        f.write(bit_header(part, os.path.basename(fasm_path)) + b'e' + len(body).to_bytes(4, 'big') + body)
    log('fasm2bit: %d set bits, %d frames, %d KB bitstream (%.1f s)' % (
        sum(asm.bits.values()), len(frames), len(body) // 1024, time.time() - t0))
    return bit_path


if __name__ == '__main__':
    a = sys.argv[1:]
    fr = None
    if '--frames' in a:
        i = a.index('--frames')
        fr = a[i + 1]
        del a[i:i + 2]
    if len(a) != 4:
        print(__doc__)
        sys.exit(2)
    assemble(a[0], a[1], a[2], a[3], fr)
