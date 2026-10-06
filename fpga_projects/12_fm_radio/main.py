# 12 FM radio: the radio service. It sets up the transmitter the way radio.json says (FM, NFM, AM, USB,
# LSB, DSB, carrier, CW, RTTY, PSK31, beacons, sweeps), plays songs, pictures (SSTV) and network sound
# (AES67) through the sound chain (processing and delay, audio_chain.py), keeps the RDS data going
# (station name and radio text with lists, loops, scrolling and variables) and writes status.json.
# The radio's page in the Ardzy app (Ready projects, FM radio, Open) writes radio.json and reads
# status.json; you can also edit radio.json by hand (the service notices the change within a second).
#
# A new radio starts with the transmitter OFF. Choose a frequency that is free where you live, keep the
# power low and the antenna short, and follow your country's rules for low-power transmitters.
import datetime
import json
import math
import os
import random
import sys
import threading
import time
import traceback
from blocks import Bus, Radio, require
import aes67
import audio_chain
import modes
import rds
import sstv

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, 'radio.json')
# status and capture change several times a second: they live in RAM (no wear on the SD card); the project
# folder has links to them, so the Ardzy app reads them as before
RUN = '/dev/shm/ardzy_radio' if os.path.isdir('/dev/shm') else HERE
STATUS, MPX = os.path.join(RUN, 'status.json'), os.path.join(RUN, 'mpx.json')
MPX_LIVE = os.path.join(RUN, 'mpx_live.json')  # the app's live spectrum (its own file: other readers of mpx.json stay undisturbed)
CAPTURE = os.path.join(RUN, 'capture.json')     # {"id": n}: the app asks for an MPX capture (in RAM, not in radio.json)
DIGITAL = ('cw', 'rtty', 'psk31', 'beacon', 'sweep')
SOUND = ('fm', 'nfm', 'am', 'usb', 'lsb', 'dsb')      # the modes that send sound
HW_MODE = {'fm': 'fm', 'nfm': 'fm', 'am': 'am', 'usb': 'usb', 'lsb': 'lsb', 'dsb': 'dsb', 'carrier': 'carrier', 'off': 'off'}
SSTV_RATE = 48000                                       # (made at the chain's own rate: no resampling)

DEFAULT = {
    'rev': 0,
    'on': False,
    'mode': 'fm',                      # fm, nfm, am, usb, lsb, dsb, carrier, cw, rtty, psk31, beacon, sweep
    'freq_mhz': 96.0,
    'power': 1.0,                      # 0..1: the carrier's strength at the pin (see clean_power)
    'fm': {'stereo': True, 'preemph': 50, 'deviation_khz': 75.0, 'audio': 0.87, 'pilot': 0.09, 'rds_level': 0.04},
    'nfm': {'deviation_khz': 5.0},
    'am': {'depth': 0.9, 'voice': False},          # voice: the 300 .. 2700 Hz filter (a narrow AM signal)
    'sstv': {'mode': 'martin1', 'image': 'sstv_image.rgb', 'repeat_s': 0.0, 'id': 0},
    # AES67 / RTP network sound: a stream announced on the network (SAP), or these settings by hand
    'network': {'stream': '', 'address': '239.69.83.67', 'port': 5004, 'encoding': 'L24', 'rate': 48000, 'channels': 2,
                'label': '', 'buffer_ms': 150},           # buffer: sound kept in hand against clicks (20 .. 2000 ms)
    'audio': {'source': 'tones', 'volume': 1.0, 'tone_l': 1000.0, 'tone_r': 400.0,     # tones, playlist, sstv, network, silence
              'playlist': [], 'loop': True, 'shuffle': False},
    # the sound chain on the ARM (songs, pictures, network sound; not the FPGA's test tones)
    'process': {'gain_db': 0.0, 'balance': 0.0, 'mono': False, 'swap': False, 'agc': False, 'agc_target_db': -16.0,
                'limiter': True, 'ceiling_db': -1.0, 'bypass': False},
    'delay_s': 0.0,                    # 0 .. 10 s
    'rds': {'on': True, 'pi': '1A2D', 'ps': 'ARDZY FM', 'rt': 'Ardzy FM: {title}', 'pty': 10, 'tp': False,
            'ta': False, 'music': True, 'ct': True, 'af': [],
            'ps_mode': 'fixed',        # fixed, list, scroll, words
            'ps_list': [],             # [{'text': 'ARDZY FM', 's': 4}, ...]
            'scroll': '', 'scroll_s': 1.0,
            'rt_list': [],             # [{'text': 'Now: {song}', 's': 15}, ...]: a loop of texts (else 'rt')
            'ptyn': '', 'ecc': '', 'rtplus': True},
    'digital': {'text': 'CQ CQ DE ARDZY', 'wpm': 18, 'baud': 45.45, 'shift': 170.0, 'offset_hz': 0.0,
                'melody': 'C4 E4 G4 C5*2 - G4 C5*2', 'tempo': 140,
                'sweep_start_khz': -50.0, 'sweep_stop_khz': 50.0, 'sweep_step_khz': 1.0, 'sweep_dwell_ms': 50,
                'repeat_s': 10.0, 'id': 0},
    'capture': 0,                      # change it to ask for an MPX capture (written to mpx.json)
}


def clean_power(level, hz):
    """The pin makes the carrier from samples 2 ns apart (500 million per second). A weaker carrier is a
    shorter pulse, and a pulse shorter than one sample comes out irregular (spurious signals instead of
    a clean weaker carrier). So the power never goes below one sample per period: at 96 MHz that is
    57 %, at 27 MHz 17 %, at 1 MHz 0.6 %. For less, use a resistor or a shorter antenna."""
    lowest = math.sin(math.pi * min(0.5, hz / 500e6))
    return max(0.0, min(1.0, max(level, lowest) if level > 0 else 0.0))


def merged(base, new):
    out = dict(base)
    for k, v in (new or {}).items():
        out[k] = merged(base[k], v) if isinstance(base.get(k), dict) and isinstance(v, dict) else v
    return out


def write_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.replace(tmp, path)            # the app never reads half a file


def link_ram_files():
    if RUN == HERE:
        return
    os.makedirs(RUN, exist_ok=True)
    for name in ('status.json', 'mpx.json', 'mpx_live.json', 'capture.json'):
        here, there = os.path.join(HERE, name), os.path.join(RUN, name)
        if not os.path.exists(there):
            write_json(there, {})
        if os.path.islink(here) and os.readlink(here) == there:
            continue
        try:
            os.remove(here)
        except OSError:
            pass
        os.symlink(there, here)


def song_meta(name):
    """'Artist - Title.wav' -> (title, artist); else (the name, '')."""
    base = os.path.splitext(os.path.basename(name))[0].replace('_', ' ').strip()
    if ' - ' in base:
        a, t = base.split(' - ', 1)
        return t.strip(), a.strip()
    return base, ''


class Service:
    def __init__(self):
        self.bus = Bus()
        require(self.bus, 'FMTX')
        self.r = Radio(self.bus, slot=1)
        self.cfg, self.cfg_mtime, self.applied_rev, self.error = dict(DEFAULT), None, None, ''
        self.written = {}            # register values already written (tones restart when written)
        self.rdsm = None
        self.meta = {'title': '', 'artist': ''}         # what is heard now (follows the delay)
        self.meta_due = []                              # [(time, title, artist)] changes still in the delay line
        self.player, self.player_rate, self.track, self.track_i = None, 48000, None, -1
        self.track_t0, self.track_len, self.order = 0.0, 0.0, []
        self.symbols, self.sym_i, self.next_send, self.sym_key = [], 0, 0.0, None
        self.rds_bits, self.rds_seen = [], {}
        self.ps_i, self.ps_t, self.rt_i, self.rt_t = 0, 0.0, 0, 0.0
        self.capture_id = self.capture_file_id = None
        self.under0 = self.r.underruns()
        self.t_under = time.time()
        self.under_rate = 0
        self.gaps, self.u_last = 0, self.r.underruns()   # gaps: sound missing while a source delivers (clicks)
        self.was_delivering = False
        self.deliver_who = None
        self.feed_pause = 0.0
        self.on_since = None                             # when the transmitter went on (the on-air clock)
        self.clock_ok = False
        self.power_eff = 0.0
        self.lock = threading.RLock()                    # the feeder thread and the settings take turns
        self.pipe = audio_chain.Pipeline(self.r)
        self.hist_t = 0.0
        self.sstv_key, self.sstv_t0, self.sstv_len, self.sstv_next, self.sstv_name = None, 0.0, 0.0, 0.0, ''
        self.net, self.net_key, self.net_error, self.net_streams = None, None, '', []
        try:
            self.disco = aes67.Discovery()
        except OSError as e:
            self.disco, self.net_error = None, 'stream discovery: %s' % e

    def clock_is_set(self):
        """The board has no battery clock: after a power-on without network time or the Ardzy app its
        clock can be wrong, and then no RDS clock time is sent (car radios would copy the wrong time)."""
        return self.clock_ok or os.path.exists('/run/systemd/timesync/synchronized')

    # ------------------------------------------------------------------ settings
    def load(self):
        try:
            m = os.path.getmtime(CFG)
        except OSError:
            if self.cfg_mtime is None:
                write_json(CFG, DEFAULT)                 # a first radio.json to edit
                self.cfg_mtime = os.path.getmtime(CFG)
                self.apply(dict(DEFAULT))
            return
        if m == self.cfg_mtime:
            return
        try:
            with open(CFG) as f:
                new = merged(DEFAULT, json.load(f))
        except (OSError, ValueError) as e:
            self.error = 'radio.json: %s (the last good settings stay)' % e
            return                                       # half-written: try again soon
        self.cfg_mtime = m
        cc = new.get('clock_checked')                    # the PC's time when the app wrote the file
        if cc and abs(float(cc) - time.time()) < 30:
            self.clock_ok = True
        try:
            self.apply(new)
            self.error = ''
        except Exception as e:
            self.error = 'settings: %s' % e
            traceback.print_exc()

    def wr_once(self, key, fn, *args):
        if self.written.get(key) != args:
            fn(*args)
            self.written[key] = args

    def apply(self, c):
        old, self.cfg = self.cfg, c
        r = self.r
        for name in c.get('delete', []):                 # the app removes songs this way
            if name == os.path.basename(name) and name.lower().endswith('.wav') and name != self.track:
                try:
                    os.remove(os.path.join(HERE, name))
                except OSError:
                    pass
        mode = c['mode'] if c['on'] else 'off'
        fm, au, rd, dg = c['fm'], c['audio'], c['rds'], c['digital']
        r.frequency(float(c['freq_mhz']) * 1e6)
        r.deviation(float(c['nfm']['deviation_khz'] if mode == 'nfm' else fm['deviation_khz']) * 1000)
        r.levels(float(fm['audio']), float(fm['pilot']), float(fm['rds_level']))
        r.volume(float(au['volume']))
        r.am_depth(float(c['am']['depth']))
        self.wr_once('tones', r.tones, float(au['tone_l']), float(au['tone_r']))
        self.power_eff = clean_power(float(c['power']), float(c['freq_mhz']) * 1e6)
        r.power(self.power_eff, key=(mode == 'carrier'))
        r.setup(tx=mode != 'off', stereo=bool(fm['stereo']) and mode == 'fm', rds=bool(rd['on']) and mode == 'fm',
                pilot=True, preemph=int(fm['preemph']) if mode == 'fm' else 0, tones=au['source'] == 'tones',
                mute=au['source'] == 'silence', narrow=mode == 'nfm' or (mode == 'am' and bool(c['am']['voice'])))
        r.mode(HW_MODE.get(mode, 'symbols'))
        # the sound chain: processing and delay
        pr = c['process']
        self.pipe.chain.set(**{k: pr[k] for k in DEFAULT['process']})
        self.pipe.set_delay(float(c['delay_s']))
        # network sound (AES67): open the stream the settings name, close it when not wanted
        self.update_network()
        # pictures: a new picture, mode or id starts the sending again
        key = (c['sstv']['mode'], c['sstv']['id'], self.image_mtime(c))
        if au['source'] == 'sstv' and mode in SOUND and key != self.sstv_key:
            self.stop_track()
            self.start_picture()
        self.sstv_key = key if au['source'] == 'sstv' and mode in SOUND else None
        # songs
        if (au['source'] == 'network' and c['mode'] in SOUND) or (au['source'] == 'sstv' and mode in SOUND):
            pass                                         # (the stream / the picture goes on)
        elif au['source'] not in ('playlist', 'sstv') or (au['source'] == 'playlist' and old['audio']['source'] != 'playlist') \
                or au['playlist'] != old['audio']['playlist'] or au['shuffle'] != old['audio']['shuffle'] or mode not in SOUND:
            self.stop_track()
            self.track_i = -1
            self.order = list(range(len(au['playlist'])))
            if au['shuffle']:
                random.shuffle(self.order)
        # RDS: lists and loops start over
        if (rd['ps_mode'], rd['ps_list'], rd['scroll'], rd['rt_list']) != (old['rds']['ps_mode'], old['rds']['ps_list'],
                                                                             old['rds']['scroll'], old['rds']['rt_list']):
            self.ps_i, self.ps_t, self.rt_i, self.rt_t = 0, 0.0, 0, 0.0
        self.update_station()
        # digital modes: a new message, new settings or a new id starts the sending again
        key = (mode, json.dumps(dg, sort_keys=True), c['freq_mhz'], c['power'])
        if mode in DIGITAL and key != self.sym_key:
            r.symbols_flush()
            self.symbols, self.sym_i, self.next_send = self.make_symbols(mode, dg, self.power_eff), 0, 0.0
        elif mode not in DIGITAL:
            self.symbols = []
        self.sym_key = key
        self.applied_rev = c.get('rev')
        print('settings %s: %s %.3f MHz, power %.2f%s' % (
            c.get('rev'), mode.upper(), float(c['freq_mhz']), float(c['power']),
            '' if mode != 'fm' else ', %s, RDS %s "%s"' % ('stereo' if fm['stereo'] else 'mono', 'on' if rd['on'] else 'off', rd['ps'])),
            flush=True)

    # ------------------------------------------------------------------ RDS: what goes on air when
    def subst(self, text):
        """The variables in a name or a text."""
        now = datetime.datetime.now()
        t, a = self.meta['title'], self.meta['artist']
        v = {'{title}': t, '{artist}': a, '{song}': ('%s - %s' % (a, t)) if a and t else t,
             '{time}': now.strftime('%H:%M'), '{date}': now.strftime('%d.%m.%Y'),
             '{freq}': ('%.2f' % float(self.cfg['freq_mhz'])).rstrip('0').rstrip('.'),
             '{station}': self.cfg['rds']['ps'].strip()}
        for k, val in v.items():
            text = text.replace(k, val)
        text = ' '.join(text.split())
        return text.rstrip(':-, ')

    def ps_frames(self):
        """[(name of 8 characters, seconds)] for the chosen way of showing the name."""
        rd = self.cfg['rds']
        step = max(0.3, float(rd['scroll_s']))
        if rd['ps_mode'] == 'list' and rd['ps_list']:
            return [(self.subst(x.get('text', ''))[:8], max(0.5, float(x.get('s', 4)))) for x in rd['ps_list']]
        if rd['ps_mode'] == 'scroll' and rd['scroll'].strip():
            return [(f, step) for f in rds.scroll_frames(self.subst(rd['scroll']))]
        if rd['ps_mode'] == 'words' and rd['scroll'].strip():
            return [(f, step) for f in rds.word_frames(self.subst(rd['scroll']))]
        return [(self.subst(rd['ps'])[:8], 3600.0)]

    def rt_items(self):
        rd = self.cfg['rds']
        if rd['rt_list']:
            return [(self.subst(x.get('text', ''))[:64], max(2.0, float(x.get('s', 10)))) for x in rd['rt_list']]
        return [(self.subst(rd['rt'])[:64], 3600.0)]

    def schedule_rds(self):
        """Move on in the name list and the text loop when their time is up; the variables follow."""
        now = time.time()
        while self.meta_due and self.meta_due[0][0] <= now:   # a new song is heard now (after the delay)
            _, t, a = self.meta_due.pop(0)
            self.meta = {'title': t, 'artist': a}
        frames = self.ps_frames()
        if self.ps_t == 0.0:
            self.ps_t = now + frames[self.ps_i % len(frames)][1]
        elif now >= self.ps_t:
            self.ps_i = (self.ps_i + 1) % len(frames)
            self.ps_t = now + frames[self.ps_i % len(frames)][1]
        items = self.rt_items()
        if self.rt_t == 0.0:
            self.rt_t = now + items[self.rt_i % len(items)][1]
        elif now >= self.rt_t:
            self.rt_i = (self.rt_i + 1) % len(items)
            self.rt_t = now + items[self.rt_i % len(items)][1]
        self.update_station(frames, items)

    def station(self, frames=None, items=None):
        rd = self.cfg['rds']
        frames = frames or self.ps_frames()
        items = items or self.rt_items()
        ps = frames[self.ps_i % len(frames)][0]
        rt = items[self.rt_i % len(items)][0]
        tags = rds.rtplus_tags(rt, self.meta['title'], self.meta['artist']) if rd['rtplus'] else []
        try:
            ecc = int(str(rd['ecc']), 16) if str(rd['ecc']).strip() else None
        except ValueError:
            ecc = None
        return rds.Station(pi=int(str(rd['pi']), 16), ps=ps, rt=rt, pty=int(rd['pty']), tp=rd['tp'],
                           ta=rd['ta'], music=rd['music'], stereo=bool(self.cfg['fm']['stereo']),
                           af=[float(x) for x in rd['af']], ct=rd['ct'] and self.clock_is_set(),
                           ecc=ecc, ptyn=str(rd['ptyn'])[:8], rtplus=tags)

    def update_station(self, frames=None, items=None):
        frames = frames or self.ps_frames()
        st = self.station(frames, items)
        fast = len(frames) > 1 and min(s for _, s in frames) < 6
        if self.rdsm is None:
            self.rdsm = rds.Manager(self.r, st)
        self.rdsm.set_station(st, fast=fast)

    def set_meta(self, title, artist, now=False):
        """A new song: RDS shows it when it is heard, after the delay."""
        due = time.time() + (0 if now else self.pipe.delay_s + self.pipe.level() / audio_chain.RATE)
        self.meta_due = [x for x in self.meta_due if x[0] < due] + [(due, title, artist)]

    @staticmethod
    def make_symbols(mode, d, power):
        off = float(d['offset_hz'])
        if mode == 'cw':
            return modes.cw(d['text'], wpm=float(d['wpm']), offset_hz=off, level=power)
        if mode == 'rtty':
            return modes.rtty(d['text'], baud=float(d['baud']), shift=float(d['shift']), offset_hz=off, level=power)
        if mode == 'psk31':
            return modes.psk31(d['text'], offset_hz=off, level=power)
        if mode == 'beacon':
            return modes.beacon(d['melody'], base_hz=off, tempo=float(d['tempo']), level=power)
        return modes.sweep(float(d['sweep_start_khz']) * 1000, float(d['sweep_stop_khz']) * 1000,
                           float(d['sweep_step_khz']) * 1000, float(d['sweep_dwell_ms']), level=power)

    # ------------------------------------------------------------------ songs
    def stop_track(self):
        if self.player is not None:
            try:
                self.player.close()
            except Exception:
                pass
        self.player, self.track = None, None
        self.set_meta('', '', now=True)
        self.pipe.reset()
        self.gaps = 0

    def next_track(self):
        au = self.cfg['audio']
        n = len(au['playlist'])
        for _ in range(n):
            self.track_i += 1
            if self.track_i >= n:
                if not au['loop']:
                    return False
                self.track_i = 0
                if au['shuffle']:
                    random.shuffle(self.order)
            name = au['playlist'][self.order[self.track_i] if self.track_i < len(self.order) else self.track_i]
            path = os.path.join(HERE, os.path.basename(name))
            try:
                info = modes.wav_info(path)
                self.player = modes.wav_words(path)
            except Exception as e:
                self.error = '%s: %s' % (name, e)
                continue
            self.player_rate = info['rate']
            heard_in = self.pipe.delay_s + self.pipe.level() / audio_chain.RATE
            self.track, self.track_t0, self.track_len = name, time.time() + heard_in, info['seconds']
            self.set_meta(*song_meta(name))
            print('playing %s (%d Hz, %d bit, %s, %.0f s)' % (name, info['rate'], info['bits'],
                  'stereo' if info['channels'] > 1 else 'mono', info['seconds']), flush=True)
            return True
        return False

    # ------------------------------------------------------------------ network sound (AES67)
    def net_settings(self):
        n = dict(self.cfg['network'])
        if n.get('stream'):                              # a stream from the list: its own address and format
            for st in self.net_streams:
                if '%s:%d' % (st['address'], st['port']) == n['stream']:
                    n.update({k: st[k] for k in ('address', 'port', 'encoding', 'rate', 'channels')})
                    n['name'] = st['name']
        return n

    def update_network(self):
        c = self.cfg
        want = c['mode'] in SOUND and c['audio']['source'] == 'network'     # (also off air: the meters show it)
        n = self.net_settings()
        key = (n['address'], int(n['port']), n['encoding'], int(n['rate']), int(n['channels'])) if want else None
        if self.net and key == self.net_key:
            self.net.set_buffer(n.get('buffer_ms', 150))                  # (changes on the fly)
            return
        if key == self.net_key:
            return
        if self.net:
            self.net.close()
            self.net = None
        self.net_key = key
        if not want:
            return
        self.stop_track()
        try:
            self.net = aes67.Receiver(self.r, *key, sink=self.pipe, buffer_ms=float(n.get('buffer_ms', 150)))
            self.gaps = 0
            self.net_error = ''
            name = n.get('name') or n.get('label') or ''
            self.track = 'network: %s' % (name or '%s:%d' % (n['address'] or 'to this board', int(n['port'])))
            self.track_t0, self.track_len = time.time(), 0
            self.set_meta(*song_meta(name) if name else ('', ''))
            print('network sound: %s %s:%d %s/%d/%d' % (name, *key), flush=True)
        except (OSError, ValueError) as e:
            self.net_error = 'network sound: %s' % e

    # ------------------------------------------------------------------ pictures (SSTV)
    def image_mtime(self, c):
        try:
            return os.path.getmtime(os.path.join(HERE, os.path.basename(c['sstv']['image'])))
        except OSError:
            return None

    def start_picture(self):
        s = self.cfg['sstv']
        path = os.path.join(HERE, os.path.basename(s['image']))
        try:
            rgb = open(path, 'rb').read()
            if len(rgb) != sstv.W * sstv.H * 3:
                raise ValueError('the picture file must be 320 x 256 RGB')
        except (OSError, ValueError) as e:
            self.error = 'picture: %s (sending the test picture)' % e
            rgb = sstv.test_picture()
        self.pipe.reset()
        self.player, self.player_rate = sstv.audio_words(rgb, s['mode'], SSTV_RATE), SSTV_RATE
        self.sstv_name = sstv.MODES[s['mode']]['name']
        heard_in = self.pipe.delay_s
        self.sstv_t0, self.sstv_len, self.sstv_next = time.time() + heard_in, sstv.MODES[s['mode']]['seconds'] + 1.0, 0.0
        self.track = 'picture (SSTV %s)' % self.sstv_name
        self.track_t0, self.track_len = self.sstv_t0, self.sstv_len
        self.set_meta('picture, SSTV ' + self.sstv_name, '')
        print('sending a picture: SSTV %s, %.0f s' % (self.sstv_name, self.sstv_len), flush=True)

    def feed_from_player(self):
        """Fill the pipeline from the song or the picture; False at its end."""
        while self.pipe.need() > 0:
            chunk = next(self.player, None)
            if chunk is None:
                self.player = None
                return False
            self.pipe.push(chunk, self.player_rate)
        return True

    def feed_picture(self):
        if self.player is None:
            rep = float(self.cfg['sstv']['repeat_s'])
            if self.sstv_next == 0.0 and self.pipe.level() < 100:
                self.sstv_next = time.time() + rep if rep > 0 else -1
                self.track = None
            if self.sstv_next > 0 and time.time() >= self.sstv_next:
                self.start_picture()
            return
        self.feed_from_player()

    def feed_audio(self):
        c = self.cfg
        src = c['audio']['source']
        if src == 'network' and c['mode'] in SOUND:
            if self.net:
                self.net.poll()
        elif c['on'] and c['mode'] in SOUND and src == 'sstv':
            self.feed_picture()
        elif c['on'] and c['mode'] in SOUND and src == 'playlist':
            if self.player is None and not self.next_track():      # (the next song follows without a gap)
                if self.track is not None or self.meta['title']:
                    self.track = None
                    self.set_meta('', '')
                return
            if not self.feed_from_player():
                self.track = None
                self.next_track()
        self.pipe.pump()

    # ------------------------------------------------------------------ digital modes
    def feed_symbols(self):
        c = self.cfg
        if not c['on'] or c['mode'] not in DIGITAL or not self.symbols:
            return
        now = time.time()
        if self.sym_i >= len(self.symbols):
            rep = float(c['digital']['repeat_s'])
            if self.next_send == 0.0 and self.r.symbols_free() == 512:
                self.next_send = now + rep if rep > 0 else -1
            if self.next_send > 0 and now >= self.next_send:
                self.sym_i, self.next_send = 0, 0.0
            return
        free = self.r.symbols_free()
        while free > 0 and self.sym_i < len(self.symbols):
            self.r.symbol(*self.symbols[self.sym_i])
            self.sym_i += 1
            free -= 1

    # ------------------------------------------------------------------ status
    def watch_rds(self, decode):
        self.rds_bits += self.r.rds_log()          # (read often: the FPGA keeps only 1.7 s of bits)
        if decode and len(self.rds_bits) >= 1200:
            self.rds_bits = self.rds_bits[-6000:]
            d = rds.decode(self.rds_bits)
            if d['groups']:
                self.rds_seen = {k: d[k] for k in ('pi', 'ps', 'rt', 'pty', 'ct', 'groups', 'ecc', 'ptyn', 'rtplus',
                                                   'ps_frames', 'rt_frames', 'types', 'ta', 'tp', 'music')}
                if d['pi'] is not None:
                    self.rds_seen['pi'] = '%04X' % d['pi']

    def status(self):
        r, c, now = self.r, self.cfg, time.time()
        u = r.underruns()
        src = c['audio']['source']
        delivering = (src == 'network' and self.net is not None and self.net.started and self.pipe.ready()
                      and time.time() - self.net.t_last < 0.3) or \
                     (src in ('playlist', 'sstv') and c['on'] and self.player is not None and self.pipe.ready())
        who = (src, id(self.net) if src == 'network' else self.sstv_key if src == 'sstv' else None)   # the same source as last time?
        if delivering and self.was_delivering and who == self.deliver_who:
            self.gaps += u - self.u_last                 # (silence between songs, between two sources, before a stream
        self.u_last, self.was_delivering = u, delivering  # or while the delay fills is no click)
        self.deliver_who = who
        if now - self.t_under >= 1:
            self.under_rate = (u - self.under0) / (now - self.t_under)
            self.under0, self.t_under = u, now
        mode = c['mode'] if c['on'] else 'off'
        dig = None
        if mode in DIGITAL and self.symbols:
            left = modes.duration_s(self.symbols[self.sym_i:])
            dig = {'sent': self.sym_i, 'total': len(self.symbols), 'busy': r.symbols_free() < 512 or self.sym_i < len(self.symbols),
                   'length_s': round(modes.duration_s(self.symbols), 1), 'left_s': round(left, 1),
                   'next_in_s': round(max(0, self.next_send - now), 1) if self.next_send > 0 else None}
        hist = [h for h in self.pipe.chain.history if h[0] > self.hist_t]
        if hist:
            self.hist_t = hist[-1][0]
        frames, items = self.ps_frames(), self.rt_items()
        chain = self.pipe.chain.stats()
        if c['on'] and self.on_since is None:
            self.on_since = now
        elif not c['on']:
            self.on_since = None
        au = c['audio']
        nxt = None
        if self.track and src == 'playlist' and au['playlist']:
            j = self.track_i + 1
            if j >= len(au['playlist']) and au['loop'] and not au['shuffle']:
                j = 0
            if j < len(au['playlist']):
                nxt = au['playlist'][self.order[j] if j < len(self.order) else j]
        peaks = r.peaks()
        dev = float(c['nfm']['deviation_khz'] if mode == 'nfm' else c['fm']['deviation_khz'])
        st = {
            'time': now, 'feed_pause_ms': round(self.feed_pause * 1000), 'on_since': self.on_since, 'next_track': nxt, 'rev': self.applied_rev, 'error': self.error, 'on': c['on'], 'mode': mode,
            'freq_mhz': float(c['freq_mhz']), 'power': float(c['power']), 'power_used': round(self.power_eff, 3),
            'power_lowest': round(clean_power(0.001, float(c['freq_mhz']) * 1e6), 3), 'locked': r.locked(), 'rf_hz': r.rf_hz(),
            'pin_high': round(r.rf_duty(), 4),
            'peaks': {k: round(v, 3) for k, v in peaks.items()},
            'deviation_khz': round(peaks['mpx'] * dev, 1) if mode in ('fm', 'nfm') else None,
            'audio_fifo': r.AUDIO_FIFO - r.audio_free(), 'underruns_per_s': round(self.under_rate),
            'gaps': self.gaps if src in ('playlist', 'sstv', 'network') else None,
            'chain': dict(chain, delay_set_s=self.pipe.delay_s, delay_now_s=self.pipe.delay_now(), filling=self.pipe.delay_s > 0 and not self.pipe.ready() and self.pipe.t_push is not None and time.time() - self.pipe.t_push < 1,
                          scope=self.pipe.chain.scope(), history=hist, active=c['audio']['source'] in ('playlist', 'sstv', 'network')),
            'track': self.track, 'track_pos_s': round(now - self.track_t0, 1) if self.track else None,
            'track_len_s': round(self.track_len, 1) if self.track and self.track_len else None,
            'now_playing': dict(self.meta),
            'rds_on_air': {'ps': self.rdsm.st.ps if self.rdsm else None, 'rt': self.rdsm.st.rt if self.rdsm else None,
                           'ps_frames': [f for f, _ in frames][:40], 'ps_i': self.ps_i % len(frames),
                           'ps_next_s': round(max(0, self.ps_t - now), 1) if len(frames) > 1 else None,
                           'rt_items': [t for t, _ in items], 'rt_i': self.rt_i % len(items),
                           'rt_next_s': round(max(0, self.rt_t - now), 1) if len(items) > 1 else None,
                           'rtplus': self.rdsm.st.rtplus if self.rdsm else []},
            'rds_seen': self.rds_seen, 'digital': dig,
            'network': {'streams': [{k: x[k] for k in ('name', 'address', 'port', 'encoding', 'rate', 'channels', 'from')}
                                    for x in self.net_streams],
                        'receiver': self.net.state() if self.net else None, 'error': self.net_error},
            'picture': {'mode': self.sstv_name, 'sending': self.player is not None, 'pos_s': round(now - self.sstv_t0, 1),
                        'len_s': round(self.sstv_len, 1),
                        'next_in_s': round(max(0, self.sstv_next - now), 1) if self.sstv_next > 0 else None,
                        'have_image': self.image_mtime(c) is not None} if c['audio']['source'] == 'sstv' else None,
            'config': {k: v for k, v in c.items() if k not in ('delete', 'capture')},   # the settings in full
        }
        return st

    def maybe_capture(self):
        """An MPX capture when asked: by capture.json (the app) or the `capture` key of radio.json (older ways)."""
        want, path = None, MPX
        try:
            with open(CAPTURE) as f:
                cid = json.load(f).get('id')
            if cid and cid != self.capture_file_id:
                self.capture_file_id = want = cid
                path = MPX_LIVE
        except (OSError, ValueError, AttributeError):
            pass
        cid = self.cfg.get('capture')
        if want is None and cid and cid != self.capture_id:
            self.capture_id = want = cid
        if want is None:
            return
        t = time.time()
        x = self.r.capture()
        write_json(path, {'id': want, 'fs': self.r.FS_MPX, 'samples': x, 'ms': round((time.time() - t) * 1000)})

    # ------------------------------------------------------------------ the feeder (its own thread)
    def feeder(self):
        """Keeps the sound chain, the FPGA's sound buffer and the symbol queue going, every 5 ms, also while
        the main loop decodes RDS or writes the status."""
        t_prev = time.time()
        while True:
            t = time.time()
            self.feed_pause = max(self.feed_pause, t - t_prev)   # (the longest wait between two rounds, for the status)
            t_prev = t
            with self.lock:
                try:
                    self.feed_audio()
                    self.feed_symbols()
                except Exception as e:
                    self.error = 'feeder: %s' % e
                    traceback.print_exc()
                    time.sleep(1)
            time.sleep(0.005)

    # ------------------------------------------------------------------ main loop
    def run(self):
        print('Ardzy FM radio service. A new radio starts with the transmitter OFF: in the Ardzy app open Ready projects, '
              'FM radio, Open (or edit radio.json) to choose a free frequency and switch it on.', flush=True)
        link_ram_files()
        try:
            os.nice(-10)                                 # before other programs: the sound must never wait
        except OSError:
            pass
        t_cfg = t_rds = t_stat = t_dec = 0.0
        sys.setswitchinterval(0.001)                 # the feeder thread gets its turn within 1 ms (not 5)
        threading.Thread(target=self.feeder, daemon=True).start()
        while True:
            now = time.time()
            try:
                if now >= t_cfg:
                    t_cfg = now + 0.3
                    with self.lock:
                        self.load()
                    self.maybe_capture()                 # (not under the lock: the sound must not wait for it)
                if now >= t_rds:
                    t_rds = now + 0.2
                    with self.lock:
                        self.schedule_rds()
                    if self.rdsm:
                        self.rdsm.tick()
                    self.watch_rds(now >= t_dec)
                    if now >= t_dec:
                        t_dec = now + 2.0
                if now >= t_stat:
                    t_stat = now + 0.5
                    with self.lock:
                        if self.disco:
                            self.net_streams = self.disco.poll()
                            if self.cfg['network'].get('stream'):
                                self.update_network()    # (the stream's announcement may come later)
                        st = self.status()     # (only the snapshot under the lock: the sound must not wait)
                    st['chain']['rta'] = self.pipe.chain.rta()
                    st['files'] = sorted(f for f in os.listdir(HERE) if f.lower().endswith('.wav'))
                    write_json(STATUS, st)
                    self.feed_pause = 0.0
            except Exception as e:
                self.error = 'service: %s' % e
                traceback.print_exc()
                time.sleep(1)
            time.sleep(0.015)


if __name__ == '__main__':
    Service().run()
