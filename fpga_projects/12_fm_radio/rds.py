"""rds.py - RDS (Radio Data System) for the Ardzy FM transmitter: groups, a bank manager, a decoder.

RDS sends 1187.5 bits per second on a 57 kHz subcarrier. A group is 4 blocks of 26 bits: 16 data bits
and a 10-bit check word. The check word also carries an offset (A, B, C, C' or D) so a receiver
finds where blocks start. Block A of every group is the PI code (the station's ID).
  0A  station name (PS, 8 characters, 2 per group), the PTY / TP / TA / MS flags, alternative frequencies
  1A  the extended country code (ECC): with the first digit of the PI it names the country
  2A  radio text (RT, up to 64 characters, 4 per group) with the A/B flag (flips for a new text)
  3A  announces an open data application: here RT+ in group 11A
  4A  clock time and date (CT): car radios set their clock from it; sent once a minute
  10A programme type name (PTYN, 8 characters): a name of your own for the programme type
  11A RT+ (RadioText Plus): which part of the radio text is the title and which the artist, so car
      radios can show them separately or save them
"""
import datetime
import time
import unicodedata

POLY = 0x5B9                       # g(x) = x^10 + x^8 + x^7 + x^5 + x^4 + x^3 + 1
OFFSET = {'A': 0x0FC, 'B': 0x198, 'C': 0x168, 'Cp': 0x350, 'D': 0x1B4}

# programme types (Europe, RDS). North America (RBDS) uses other names for the same numbers.
PTY = ['None', 'News', 'Current affairs', 'Information', 'Sport', 'Education', 'Drama', 'Culture',
       'Science', 'Varied', 'Pop music', 'Rock music', 'Easy listening', 'Light classical',
       'Serious classical', 'Other music', 'Weather', 'Finance', "Children's", 'Social affairs',
       'Religion', 'Phone-in', 'Travel', 'Leisure', 'Jazz', 'Country', 'National music', 'Oldies',
       'Folk', 'Documentary', 'Alarm test', 'Alarm']

# letters with accents in the RDS character table (EN 50067 annex E); others lose their accent
_RDS_EXTRA = {'á': 0x80, 'à': 0x81, 'é': 0x82, 'è': 0x83, 'í': 0x84, 'ì': 0x85, 'ó': 0x86, 'ò': 0x87,
              'ú': 0x88, 'ù': 0x89, 'Ñ': 0x8A, 'Ç': 0x8B, 'Ş': 0x8C, 'ß': 0x8D, '¡': 0x8E,
              'â': 0x90, 'ä': 0x91, 'ê': 0x92, 'ë': 0x93, 'î': 0x94, 'ï': 0x95, 'ô': 0x96, 'ö': 0x97,
              'û': 0x98, 'ü': 0x99, 'ñ': 0x9A, 'ç': 0x9B, 'ş': 0x9C, 'ğ': 0x9D, 'ı': 0x9E}
_RDS_BACK = {v: k for k, v in _RDS_EXTRA.items()}


def checkword(info16, offset):
    """10-bit check word of a 16-bit information word, with the block's offset added."""
    reg = (info16 & 0xFFFF) << 10
    for i in range(25, 9, -1):
        if (reg >> i) & 1:
            reg ^= POLY << (i - 10)
    return (reg & 0x3FF) ^ offset


def block(info16, offset_name):
    return ((info16 & 0xFFFF) << 10) | checkword(info16, OFFSET[offset_name])


def rds_codes(text, n=None):
    """Text -> RDS character codes (ASCII, plus the accented letters of the RDS table)."""
    out = []
    for ch in text:
        if ch in _RDS_EXTRA:
            out.append(_RDS_EXTRA[ch])
        elif 32 <= ord(ch) < 127:
            out.append(ord(ch))
        else:
            base = unicodedata.normalize('NFKD', ch).encode('ascii', 'ignore').decode()
            out.append(ord(base[0]) if base and 32 <= ord(base[0]) < 127 else ord('?'))
    if n is not None:
        out = (out + [32] * n)[:n]
    return out


def rds_text(codes):
    return ''.join(_RDS_BACK.get(c, chr(c) if 32 <= c < 127 else '?') for c in codes)


def af_code(mhz):
    """An FM frequency (87.6 .. 107.9 MHz) as an AF code 1..204."""
    code = round((mhz - 87.5) * 10)
    if not 1 <= code <= 204:
        raise ValueError('alternative frequency %.1f MHz is outside 87.6 .. 107.9' % mhz)
    return code


class Station:
    """Everything the station sends in RDS."""

    RTP_AID = 0x4BD7                                    # the RT+ application id
    RTP_TITLE, RTP_ARTIST = 1, 4                        # RT+ content types ITEM.TITLE and ITEM.ARTIST

    def __init__(self, pi=0x1A2D, ps='ARDZY FM', rt='', pty=0, tp=False, ta=False, music=True,
                 stereo=True, af=(), ct=True, ct_offset_minutes=None, ecc=None, ptyn='', rtplus=None):
        self.pi, self.ps, self.rt, self.pty = pi & 0xFFFF, ps, rt, pty & 31
        self.tp, self.ta, self.music, self.stereo = bool(tp), bool(ta), bool(music), bool(stereo)
        self.af = list(af)
        self.ct = bool(ct)
        self.ct_offset_minutes = ct_offset_minutes      # None: the board's own time zone
        self.ab = 0                                     # radio text A/B flag
        self.ecc = ecc                                  # extended country code (0xE1 = Greece) or None
        self.ptyn = ptyn or ''                          # programme type name, up to 8 characters
        self.ptyn_ab = 0
        self.rtplus = rtplus or []                      # up to 2 (content type, start, length) in the radio text
        self.rtp_toggle, self.rtp_running = 0, 1

    # ---------------------------------------------------------------- groups (4 blocks each)
    def group_0a(self, seg, ps=None):
        ps = rds_codes(self.ps if ps is None else ps, 8)
        di = (1 if self.stereo else 0) if seg == 3 else 0        # DI bit d0 (stereo) is sent in segment 3
        b = (0 << 12) | (0 << 11) | (self.tp << 10) | (self.pty << 5) | (self.ta << 4) | (self.music << 3) \
            | (di << 2) | seg
        if self.af:
            codes = [af_code(f) for f in self.af[:25]]
            pairs = [(224 + len(codes), codes[0])] + [tuple((codes[1:] + [205])[i:i + 2]) for i in range(0, len(codes) - 1, 2)]
            c = pairs[seg % len(pairs)]
            c = (c[0] << 8) | c[1]
        else:
            c = (224 << 8) | 205                                  # "no AF" + filler
        d = (ps[2 * seg] << 8) | ps[2 * seg + 1]
        return [block(self.pi, 'A'), block(b, 'B'), block(c, 'C'), block(d, 'D')]

    def rt_segments(self):
        codes = rds_codes(self.rt[:64])
        if not codes:
            return []
        if len(codes) < 64:
            codes.append(0x0D)                                    # end of text
        codes += [32] * (-len(codes) % 4)
        return [codes[i:i + 4] for i in range(0, len(codes), 4)]

    def group_2a(self, seg, chars):
        b = (2 << 12) | (0 << 11) | (self.tp << 10) | (self.pty << 5) | (self.ab << 4) | seg
        return [block(self.pi, 'A'), block(b, 'B'), block((chars[0] << 8) | chars[1], 'C'),
                block((chars[2] << 8) | chars[3], 'D')]

    def group_1a(self):
        """ECC: variant 0 of group 1A (paging codes 0, no programme item number)."""
        b = (1 << 12) | (0 << 11) | (self.tp << 10) | (self.pty << 5)
        return [block(self.pi, 'A'), block(b, 'B'), block((0 << 12) | (self.ecc & 0xFF), 'C'), block(0, 'D')]

    def group_10a(self, seg):
        """PTYN: 4 characters per group, 2 groups; the A/B flag flips for a new name."""
        t = rds_codes(self.ptyn, 8)
        b = (10 << 12) | (0 << 11) | (self.tp << 10) | (self.pty << 5) | (self.ptyn_ab << 4) | (seg & 1)
        return [block(self.pi, 'A'), block(b, 'B'), block((t[4 * seg] << 8) | t[4 * seg + 1], 'C'),
                block((t[4 * seg + 2] << 8) | t[4 * seg + 3], 'D')]

    def group_3a(self):
        """Open data application: RT+ (AID 0x4BD7) is carried in group 11A (application group code 22)."""
        b = (3 << 12) | (0 << 11) | (self.tp << 10) | (self.pty << 5) | ((11 << 1) | 0)
        return [block(self.pi, 'A'), block(b, 'B'), block(0, 'C'), block(self.RTP_AID, 'D')]

    def group_11a(self):
        """RT+ tags: content type, start and length (length - 1) of up to 2 parts of the radio text."""
        tags = (list(self.rtplus) + [(0, 0, 1), (0, 0, 1)])[:2]
        (c1, s1, l1), (c2, s2, l2) = tags
        b = (11 << 12) | (0 << 11) | (self.tp << 10) | (self.pty << 5) | (self.rtp_toggle << 4) \
            | (self.rtp_running << 3) | ((c1 >> 3) & 7)
        c = ((c1 & 7) << 13) | ((s1 & 63) << 7) | (((l1 - 1) & 63) << 1) | ((c2 >> 5) & 1)
        d = ((c2 & 31) << 11) | ((s2 & 63) << 5) | ((l2 - 1) & 31)
        return [block(self.pi, 'A'), block(b, 'B'), block(c, 'C'), block(d, 'D')]

    def group_4a(self, when=None):
        """Clock time: the UTC time and date, and the local offset in half hours."""
        now = when or time.time()
        utc = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
        if self.ct_offset_minutes is None:
            off = datetime.datetime.fromtimestamp(now).astimezone().utcoffset().total_seconds() / 60
        else:
            off = self.ct_offset_minutes
        half = int(round(off / 30))
        mjd = utc.date().toordinal() - datetime.date(1858, 11, 17).toordinal()
        b = (4 << 12) | (0 << 11) | (self.tp << 10) | (self.pty << 5) | ((mjd >> 15) & 3)
        c = ((mjd & 0x7FFF) << 1) | ((utc.hour >> 4) & 1)
        d = ((utc.hour & 0xF) << 12) | (utc.minute << 6) | ((1 if half < 0 else 0) << 5) | (abs(half) & 0x1F)
        return [block(self.pi, 'A'), block(b, 'B'), block(c, 'C'), block(d, 'D')]

    def cycle(self, ps=None, rt_part=None, with_ct=False, extras=True):
        """The blocks of one round: (0A, 0A, 2A) repeated, so the name comes often and the text follows,
        with the ECC, PTYN and RT+ groups in between (extras). rt_part: which radio text segments (all when
        None). Up to 64 groups (256 blocks)."""
        segs = self.rt_segments()
        part = list(range(len(segs))) if rt_part is None else [i for i in rt_part if i < len(segs)]
        slots = part or [None, None]
        if len(slots) % 2:
            slots = slots + [slots[0]]
        out = []
        if with_ct:
            out += self.group_4a()
        if extras and self.ecc is not None:
            out += self.group_1a()
        if extras and self.rtplus and segs:
            out += self.group_3a()
        for j, s in enumerate(slots):
            out += self.group_0a((2 * j) % 4, ps) + self.group_0a((2 * j + 1) % 4, ps)
            if s is not None:
                out += self.group_2a(s, segs[s])
            if extras and self.ptyn and j in (0, 1):
                out += self.group_10a(j)
            if extras and self.rtplus and segs and j % 4 == 1:
                out += self.group_11a()
        return out[:256]


def scroll_frames(text, width=8, step=1):
    """Frames of a scrolling station name (dynamic PS): 'HELLO WORLD' -> 'HELLO WO', 'ELLO WOR', ..."""
    text = ' '.join(text.split())
    if len(text) <= width:
        return [text]
    pad = text + ' ' * 3
    return [(pad + pad)[i:i + width] for i in range(0, len(pad), step)]


def word_frames(text, width=8):
    """Word by word: each word in the middle of the 8 places (longer words in 8-character pieces)."""
    out = []
    for w in text.split():
        while len(w) > width:
            out.append(w[:width])
            w = w[width:]
        if w:
            out.append(w.center(width))
    return out or ['']


def rtplus_tags(rt, title='', artist=''):
    """RT+ tags for the title and the artist where they appear in the radio text."""
    tags = []
    for ctype, part in ((Station.RTP_TITLE, title), (Station.RTP_ARTIST, artist)):
        if part:
            i = rt.find(part)
            if i >= 0 and i < 64:
                n = min(len(part), 64 - i, 64 if ctype == Station.RTP_TITLE else 32)
                tags.append((ctype, i, n))
    return tags


class Manager:
    """Keeps the radio's two RDS banks filled: writes only the bank that is not on air, asks for it,
    and the FPGA changes over at the end of the round. The radio service decides what the name and the
    text are (fixed, a list, scrolling, word by word, a loop of texts) and calls set_station(); tick()
    about 5 times a second does the rest, and the clock time once a minute."""

    def __init__(self, radio, station):
        self.radio, self.st = radio, station
        self.want = False
        self.restore = False         # a clock-time round is on air: load the normal round after it
        self.fast = False            # the name changes often: short rounds (2 text groups each)
        self.last_minute = None
        self.part = 0
        self.round = 0
        self.req = radio.rds_bank()[0]
        self.content, self.essential = {}, {}                    # the blocks in each bank, and how many are its round
        self.load(first=True)

    @property
    def frames(self):                # (for the status: the name on air now)
        return [self.st.ps]

    frame = 0

    def set_station(self, station, fast=False):
        station.ab = 1 - self.st.ab if station.rt != self.st.rt else self.st.ab      # a new text: receivers clear the old one
        station.ptyn_ab = 1 - self.st.ptyn_ab if station.ptyn != self.st.ptyn else self.st.ptyn_ab
        station.rtp_toggle = 1 - self.st.rtp_toggle if station.rtplus != self.st.rtplus else self.st.rtp_toggle
        same = (station.ps, station.rt, station.ptyn, station.rtplus, station.pty, station.ta, station.tp, station.music,
                station.ecc, station.af, station.pi, station.stereo) == (self.st.ps, self.st.rt, self.st.ptyn, self.st.rtplus,
                self.st.pty, self.st.ta, self.st.tp, self.st.music, self.st.ecc, self.st.af, self.st.pi, self.st.stereo)
        self.st = station
        self.fast = fast
        if not same:
            self.want = True

    def _blocks(self, with_ct):
        self.round += 1
        if self.fast:                                            # short rounds: 2 text groups each
            n = len(self.st.rt_segments())
            part = [(self.part + i) % n for i in range(2)] if n else None
            self.part = (self.part + 2) % n if n else 0
            return self.st.cycle(self.st.ps, part, with_ct, extras=self.round % 2 == 0)
        return self.st.cycle(self.st.ps, None, with_ct)

    def load(self, with_ct=False, first=False):
        on_air = self.radio.rds_bank()[0]
        bank = 1 - on_air                                        # never the bank on air
        blocks = self._blocks(with_ct)
        if first:                                                # (what is in the FPGA is from before: replace both)
            self.radio.rds_load(blocks, on_air)
            self.content, self.essential = {0: blocks, 1: blocks}, {0: len(blocks), 1: len(blocks)}
        # The FPGA has ONE length for both banks, and the bank on air uses the new length at once. So:
        # - a shorter new round would cut the round on air short (its last groups, e.g. the second half of the
        #   PTYN, would never go out): the new round is made as long as the one on air by repeating its groups;
        # - a longer new round would let the bank on air play on behind its end (old blocks: an old name or
        #   text for a moment): the bank on air gets its own groups repeated up to that length first.
        n = max(len(blocks), self.essential.get(on_air, 0))
        new = [blocks[i % len(blocks)] for i in range(n)]
        cur = self.content.get(on_air)
        if cur and n > len(cur):
            more = [cur[i % len(cur)] for i in range(len(cur), n)]
            for i, b in enumerate(more):
                self.radio.bus.wr(self.radio.slot + 1, on_air * 256 + len(cur) + i, b)
            self.content[on_air] = cur + more
        self.radio.rds_load(new, bank)
        self.content[bank], self.essential[bank] = new, len(blocks)   # (what must go out of it: the rest repeats)
        self.req = bank

    def tick(self):
        on_air, asked = self.radio.rds_bank()
        if on_air != asked:
            return                                               # a change-over is still waiting
        minute = int(time.time() // 60)
        if self.restore:
            self.restore = False
            self.load()
            return
        if self.st.ct and minute != self.last_minute:
            first = self.last_minute is None
            self.last_minute = minute
            if not first:
                self.load(with_ct=True)
                self.restore = True
                return
        if self.want or (self.fast and self.st.rt_segments()):   # (short rounds: the next text segments)
            self.want = False
            self.load()


# ---------------------------------------------------------------- decoder (for the self-test and the app)
def _syndrome_name(word):
    info, chk = word >> 10, word & 0x3FF
    for name, off in OFFSET.items():
        if checkword(info, off) == chk:
            return name
    return None


def decode(bits):
    """RDS data bits -> what a receiver would show: {'pi', 'ps', 'rt', 'pty', 'ct', 'groups', 'types'}."""
    out = {'pi': None, 'ps': None, 'rt': None, 'pty': None, 'ct': None, 'groups': 0, 'types': {}, 'ps_frames': [],
           'ecc': None, 'ptyn': None, 'rtplus': None, 'rt_frames': [], 'ta': None, 'tp': None, 'music': None}
    ps = [None] * 8
    rt = {}
    ptyn = [None] * 8
    oda = {}
    tags = None
    rt_ab = None
    i, n = 0, len(bits)

    def word(at):
        v = 0
        for b in bits[at:at + 26]:
            v = (v << 1) | b
        return v

    while i + 104 <= n:
        if _syndrome_name(word(i)) != 'A':
            i += 1
            continue
        w = [word(i + 26 * k) for k in range(4)]
        names = [_syndrome_name(x) for x in w]
        if names[1] != 'B' or names[2] not in ('C', 'Cp') or names[3] != 'D':
            i += 1
            continue
        a, b, c, d = (x >> 10 for x in w)
        out['pi'], out['groups'] = a, out['groups'] + 1
        gtype = '%d%s' % (b >> 12, 'B' if b >> 11 & 1 else 'A')
        out['types'][gtype] = out['types'].get(gtype, 0) + 1
        out['pty'] = (b >> 5) & 31
        out['tp'] = bool(b >> 10 & 1)
        if gtype == '0A':
            out['ta'], out['music'] = bool(b >> 4 & 1), bool(b >> 3 & 1)
            seg = b & 3
            ps[2 * seg], ps[2 * seg + 1] = d >> 8, d & 0xFF
            if None not in ps:
                name = rds_text(ps)
                if not out['ps_frames'] or out['ps_frames'][-1] != name:
                    out['ps_frames'].append(name)
                out['ps'] = name
        elif gtype == '2A':
            seg = b & 15
            if rt_ab is not None and (b >> 4 & 1) != rt_ab:     # a new text: start it over
                done = _rt_text(rt)
                if done and (not out['rt_frames'] or out['rt_frames'][-1] != done):
                    out['rt_frames'].append(done)
                rt = {}
            rt_ab = b >> 4 & 1
            rt[seg] = [c >> 8, c & 0xFF, d >> 8, d & 0xFF]
        elif gtype == '1A':
            if (c >> 12) & 7 == 0:
                out['ecc'] = '%02X' % (c & 0xFF)
        elif gtype == '10A':
            seg = b & 1
            ptyn[4 * seg:4 * seg + 4] = [c >> 8, c & 0xFF, d >> 8, d & 0xFF]
            if None not in ptyn:
                out['ptyn'] = rds_text(ptyn)
        elif gtype == '3A':
            oda[b & 31] = d
        elif gtype == '11A' and oda.get(22) == Station.RTP_AID:
            c1, s1, l1 = ((b & 7) << 3) | (c >> 13), (c >> 7) & 63, ((c >> 1) & 63) + 1
            c2, s2, l2 = ((c & 1) << 5) | (d >> 11), (d >> 5) & 63, (d & 31) + 1
            tags = [(c1, s1, l1), (c2, s2, l2)]
        elif gtype == '4A':
            mjd = ((b & 3) << 15) | (c >> 1)
            hour = ((c & 1) << 4) | (d >> 12)
            minute = (d >> 6) & 63
            off = (d & 31) * (-30 if d >> 5 & 1 else 30)
            date = datetime.date(1858, 11, 17) + datetime.timedelta(days=mjd)
            out['ct'] = '%s %02d:%02d UTC, local %+.1f h' % (date.isoformat(), hour, minute, off / 60)
        i += 104
    out['rt'] = _rt_text(rt)
    if out['rt'] and (not out['rt_frames'] or out['rt_frames'][-1] != out['rt']):
        out['rt_frames'].append(out['rt'])
    if tags and out['rt']:
        names = {Station.RTP_TITLE: 'title', Station.RTP_ARTIST: 'artist'}
        out['rtplus'] = {names[c]: out['rt'][s0:s0 + n] for c, s0, n in tags if c in names}
    return out


def _rt_text(rt):
    text = []
    for s in range(16):                          # segments 0, 1, 2 ... up to the end mark
        if s not in rt:
            break
        text += rt[s]
        if 0x0D in rt[s]:
            text = text[:text.index(0x0D)]
            break
    return rds_text(text).rstrip() if text else None


if __name__ == '__main__':                      # a quick check on a PC: encode, then decode
    rt = 'Now playing: Daft Punk - One More Time'
    st = Station(pi=0x1A2D, ps='ARDZY FM', rt=rt, pty=10, ecc=0xE1, ptyn='Electro',
                 rtplus=rtplus_tags(rt, 'One More Time', 'Daft Punk'))
    blocks = st.cycle(with_ct=True)
    bits = []
    for x in blocks * 2:
        bits += [(x >> (25 - k)) & 1 for k in range(26)]
    d = decode(bits[7:])
    print(len(blocks) // 4, 'groups ->', {k: d[k] for k in ('ps', 'rt', 'ecc', 'ptyn', 'rtplus', 'ct', 'types')})
    assert d['ps'] == 'ARDZY FM' and d['rt'] == rt and d['ecc'] == 'E1' and d['ptyn'].rstrip() == 'Electro'
    assert d['rtplus'] == {'title': 'One More Time', 'artist': 'Daft Punk'}
    print('word frames:', word_frames('Ardzy FM the FPGA radio station'))
