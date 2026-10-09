# 19 AI Studio: three big neural networks in the board's DDR memory, run by the FPGA's DDR engine. Serves the
# Ardzy app's AI page (port 8080): Read (the digit reader), Write (the text model), Draw (the digit drawer).
import base64, importlib, json, math, os, socket, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
from blocks import Bus, MLPDDR, DDRStore, require, mlp_reference, digit_preprocess, digit_text
from nn_train import load_layers, load_array

PORT = 8080
HERE = os.path.dirname(os.path.abspath(__file__))
bus = Bus()
require(bus, 'AIST')
t0 = time.time()
MHZ = bus.rd(0, 6) / 1e6 or 100.0               # the design's clock (AI Studio runs at 75 MHz)
ports = bus.rd(1, 11) or 4                     # how many HP ports the engine uses (2 or 4)
store = DDRStore(region=(16 // ports) << 20, ports=ports)     # 16 MB of locked memory, split over the ports
nn = MLPDDR(bus, slot=1, store=store)
print('16 MB of memory locked for the FPGA (%d pages, %d HP ports) in %.1f s' % (len(store.pages), ports, time.time() - t0), flush=True)
lock = threading.Lock()
M = {}                                            # name -> {'layers', 'handle', 'mod'}


def load(name, module):
    mod = importlib.import_module(module)
    layers = load_layers(mod)
    M[name] = {'layers': layers, 'handle': nn.load(layers), 'mod': mod, 'file': module}
    return sum(l['w'].size for l in layers)


def run(name, x):
    with lock:
        if nn.cur is not M[name]['handle']:
            nn.use(M[name]['handle'])
        r = nn.run(x)
        return r, nn.cycles(), nn.stalls()


reader_file = 'reader_mine' if os.path.exists(os.path.join(HERE, 'reader_mine.py')) else 'reader_big'
sizes = {'read': load('read', reader_file), 'write': load('write', 'writer_big'), 'draw': load('draw', 'drawer_big')}
nn.ready()                                        # the HP ports read the DDR: push the ARM's caches out first
print('In the DDR: the reader (%s, %d weights), the text model (%d), the drawer (%d): %.1f MB in all.'
      % (reader_file, sizes['read'], sizes['write'], sizes['draw'], store.next * ports / 1e6), flush=True)

W = M['write']['mod']
EMB = load_array(W, 'EMBED')
V = W.VOCAB
DZ, DS = M['draw']['mod'].Z, M['draw']['mod'].ZSCALE
TEST = load_array(M['read']['mod'], 'TEST') if hasattr(M['read']['mod'], 'TEST') else None
stats = {}

# ---- check every network once against the Python math, and time it
rs = np.random.RandomState(19)
for name in ('read', 'write', 'draw'):
    L = M[name]['layers']
    good = 0
    for _ in range(3):
        x = rs.randint(0, 256, L[0]['w'].shape[1]).astype(np.uint8)
        (d, out), cyc, st = run(name, x)
        good += [int(v) for v in out] == mlp_reference(L, x)[1]
    n, t1 = 0, time.time()
    while time.time() - t1 < 0.5:
        mlp_reference(L, x); n += 1
    stats[name] = {'fpga_us': cyc / MHZ, 'stalls': st, 'arm_us': 5e5 / n}
    print('   %-5s %d of 3 = the math, to the bit; %.0f microseconds in the FPGA (%.0f %% of it waiting for the DDR), '
          'the ARM with numpy: %.0f' % (name, good, cyc / MHZ, 100.0 * st / max(cyc, 1), 5e5 / n), flush=True)


# ---- Read
def guess(px):
    a = np.frombuffer(base64.b64decode(px), dtype=np.uint8).reshape(112, 112)
    if a.max() < 30:
        return {'empty': True}
    x = digit_preprocess(a)
    (d, s), cyc, st = run('read', x)
    z = np.array(s, float) * M['read']['mod'].SCALE
    p = np.exp(z - z.max()); p /= p.sum()
    print('%s\n   read: %d (%.0f %% sure)' % (digit_text(x), d, 100 * p[d]), flush=True)
    return {'digit': int(d), 'prob': [float(v) for v in p], 'pixels': [int(v) for v in x.ravel()], 'hidden': [],
            'cycles': cyc, 'fpga_us': cyc / MHZ, 'arm_us': stats['read']['arm_us'], 'count': nn.count()}


# ---- Write
PAD = 'the ardzy board has an fpga and two arm cores that run linux.' + chr(10)   # what comes before your start


def ids_of(text):
    return [V.index(c) for c in PAD + text.lower() if c in V]


def letter_probs(ids, temp):
    (_, s), cyc, st = run('write', EMB[ids[-W.CTX:]].ravel())
    z = np.array(s, float) * W.SCALE / max(temp, 0.05)
    p = np.exp(z - z.max())
    return p / p.sum(), cyc


def write(start, n, temp, seed):
    rng = np.random.RandomState(seed if seed is not None else int(time.time() * 1000) % 100000)
    ids, out, sure = ids_of(start), '', []
    for _ in range(n):
        p, cyc = letter_probs(ids, temp)
        c = int(rng.choice(len(V), p=p))
        ids.append(c); out += V[c]; sure.append(round(float(p[c]), 3))
    return out, sure, cyc


# ---- Draw
def drawer_input(a, b, mix, z):
    zb = np.clip(np.round(np.asarray(z) * DS) + 128, 0, 255)
    y = np.zeros(10); y[a] += DS * (1 - mix); y[b] += DS * mix
    return np.concatenate([zb, np.round(y)]).astype(np.uint8)


def draw_and_read(x):
    (_, pix), cyc_d, _ = run('draw', x)
    pix = np.array(pix, np.uint8)
    (d, s), cyc_r, _ = run('read', pix)
    z = np.array(s, float) * M['read']['mod'].SCALE
    p = np.exp(z - z.max()); p /= p.sum()
    return pix, int(d), float(p[d]), cyc_d, cyc_r


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith('/state'):
            return self.send(200, {'running': True, 'project': '19_ai_studio', 'models': ['read', 'write', 'draw'],
                                   'reader': M['read']['file'], 'count': nn.count(), 'stats': stats, 'sizes': sizes,
                                   'fpga_us': stats['write']['fpga_us'], 'arm_us': stats['write']['arm_us'], 'letters': V,
                                   'mb': store.next * ports / 1e6})
        if self.path.startswith('/example') and TEST is not None:
            i = int(time.time() * 7) % len(TEST)
            return self.send(200, {'pixels': [int(v) for v in TEST[i]], 'label': M['read']['mod'].TEST_LABELS[i]})
        self.send(404, {'error': 'not found'})

    def do_POST(self):
        try:
            a = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            path = self.path
            if path.startswith('/reload_reader'):          # a reader taught your handwriting (reader_mine.py)
                import sys
                sys.modules.pop('reader_mine', None)
                importlib.invalidate_caches()
                mod = importlib.import_module('reader_mine')
                layers = load_layers(mod)
                with lock:
                    h = nn.load(layers)
                    nn.ready()
                    M['read'] = {'layers': layers, 'handle': h, 'mod': mod, 'file': 'reader_mine'}
                    nn.cur = None
                print('The reader now knows your handwriting (%d of your drawings).' % getattr(mod, 'MINE', 0), flush=True)
                return self.send(200, {'reader': 'reader_mine', 'mine': getattr(mod, 'MINE', 0)})
            if path.startswith('/guess'):
                return self.send(200, guess(a.get('px', '')))
            if path.startswith('/write'):
                n = max(1, min(800, int(a.get('length', 200))))
                t1 = time.time()
                text, sure, cyc = write(a.get('start', ''), n, float(a.get('temperature', 0.7)), a.get('seed'))
                dt = time.time() - t1
                print('[%s]%s' % (a.get('start', ''), text.replace('\n', ' ')), flush=True)
                return self.send(200, {'text': text, 'sure': sure, 'seconds': dt, 'per_second': n / dt, 'fpga_us': cyc / MHZ,
                                       'arm_us': stats['write']['arm_us'], 'count': nn.count()})
            if path.startswith('/next'):
                p, _ = letter_probs(ids_of(a.get('text', '')), 1.0)
                top = np.argsort(-p)[:8]
                return self.send(200, {'next': [[V[i], round(float(p[i]), 3)] for i in top]})
            if path.startswith(('/draw', '/morph', '/style')):
                rng = np.random.RandomState(a.get('seed') if a.get('seed') is not None else int(time.time() * 1000) % 100000)
                var = float(a.get('variety', 1.0))
                d = int(a.get('digit', 0)) % 10
                steps = max(2, min(24, int(a.get('steps', 9))))
                if path.startswith('/draw'):
                    xs = [drawer_input(d, d, 0, rng.randn(DZ) * var) for _ in range(max(1, min(24, int(a.get('count', 8)))))]
                elif path.startswith('/morph'):
                    fa, fb = int(a.get('from', 3)) % 10, int(a.get('to', 8)) % 10
                    z = rng.randn(DZ) * var
                    xs = [drawer_input(fa, fb, k / (steps - 1), z) for k in range(steps)]
                else:
                    z0, z1 = rng.randn(DZ) * var, rng.randn(DZ) * var
                    xs = [drawer_input(d, d, 0, z0 * (1 - k / (steps - 1)) + z1 * k / (steps - 1)) for k in range(steps)]
                out, cd, cr = [], 0, 0
                for x in xs:
                    pix, got, p, cd, cr = draw_and_read(x)
                    out.append({'pixels': base64.b64encode(bytes(pix)).decode(), 'read': got, 'sure': round(p, 3)})
                print('drew %d pictures (%s), read back as %s' % (len(out), path.strip('/'), ''.join(str(o['read']) for o in out)), flush=True)
                return self.send(200, {'images': out, 'draw_us': cd / MHZ, 'read_us': cr / MHZ, 'arm_us': stats['draw']['arm_us'],
                                       'count': nn.count()})
            self.send(404, {'error': 'not found'})
        except Exception as e:
            self.send(400, {'error': str(e)})

    def log_message(self, *a):
        pass


class Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6
    daemon_threads = True

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


srv = Server(('::', PORT), Handler)
print('Ready: open Ready projects, "AI Studio", Open, in the Ardzy app (Read, Write, Draw).', flush=True)
srv.serve_forever()
