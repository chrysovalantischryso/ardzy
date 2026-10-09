# 17 Text AI demo: load the language model into the FPGA's network engine, let it write, compare the speed with
# the ARM, then serve the Ardzy app's Text AI page (port 8080): write on from your start, guess the next letter.
import base64, json, socket, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
import text_model as tm
from blocks import Bus, MLP, require, mlp_reference

PORT = 8080
bus = Bus()
require(bus, 'TEXT')
nn = MLP(bus, slot=1)
dec = lambda s, shape: np.frombuffer(base64.b64decode(''.join(s)), dtype=np.int8).reshape(shape)
layers = [{'w': dec(getattr(tm, 'W%d' % (k + 1)), tm.SHAPES[k]), 'b': getattr(tm, 'B%d' % (k + 1)),
           'shift': tm.SHIFTS[k], 'act': tm.ACTS[k]} for k in range(len(tm.SHAPES))]
emb = np.frombuffer(base64.b64decode(''.join(tm.EMBED)), dtype=np.uint8).reshape(len(tm.VOCAB), -1)
V = tm.VOCAB
t0 = time.time()
cfg = nn.load(layers)
nn.use(cfg)
print('The language model is in the FPGA: 16 letters -> 192 numbers -> 256 -> 256 -> %d letter scores, %d weights, sent in %.2f s.'
      % (len(V), sum(l['w'].size for l in layers), time.time() - t0))
lock = threading.Lock()


def ids_of(text):
    ids = [V.index(c) for c in text.lower() if c in V]
    return [V.index(' ')] * tm.CTX + ids


def scores(ids, fpga=True):
    x = emb[ids[-tm.CTX:]].ravel()
    return nn.run(x)[1] if fpga else mlp_reference(layers, x)[1]


def probs(s, temp):
    z = np.array(s, float) * tm.SCALE / max(temp, 0.05)
    p = np.exp(z - z.max())
    return p / p.sum()


def write(start, n=200, temp=0.7, seed=None):
    rng = np.random.RandomState(seed if seed is not None else int(time.time() * 1000) % 100000)
    ids = ids_of(start)
    out, sure = '', []
    for _ in range(n):
        with lock:
            p = probs(scores(ids), temp)
        c = int(rng.choice(len(V), p=p))
        ids.append(c)
        out += V[c]
        sure.append(round(float(p[c]), 3))
    return out, sure


def guesses(text, k=8):
    with lock:
        p = probs(scores(ids_of(text)), 1.0)
    top = np.argsort(-p)[:k]
    return [[V[i], round(float(p[i]), 3)] for i in top]


print('\n1. Bit for bit: the FPGA against the same math in Python')
same = 0
for k in range(20):
    ids = ids_of('the fpga reads the pins of the board and the program runs on the arm'[k:k + 30])
    same += scores(ids) == scores(ids, fpga=False)
print('   %d of 20 letter predictions equal, every one of the %d scores' % (same, len(V)))

print('\n2. It writes (the start is in [brackets]):')
for start in ('the fpga ', 'a project ', 'press upload '):
    text, _ = write(start, 160, 0.6, seed=1)
    print('   [%s]%s\n' % (start, text.replace('\n', ' ')))

print('3. Speed for one letter:')
ids = ids_of('the speed test of the network engine')
x = emb[ids[-tm.CTX:]].ravel()
n, t0 = 0, time.time()
while time.time() - t0 < 1.0:
    mlp_reference(layers, x); n += 1
arm_us = 1e6 * (time.time() - t0) / n
nn.run(x)
fpga_us = nn.cycles() / 100.0
n, t0 = 0, time.time()
while time.time() - t0 < 1.0:
    scores(ids); n += 1
total_us = 1e6 * (time.time() - t0) / n
print('   the FPGA: %.1f microseconds (%d clocks), %.0f x faster than the ARM with numpy (%.0f microseconds)'
      % (fpga_us, nn.cycles(), arm_us / fpga_us, arm_us))
print('   with Python sending the letters and reading the scores: %d letters per second' % (1e6 / total_us))


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, kind='application/json'):
        data = (body if isinstance(body, str) else json.dumps(body)).encode()
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith('/state'):
            with lock:
                st = {'running': True, 'project': '17_text_ai', 'count': nn.count(), 'cycles': nn.cycles()}
            st.update({'fpga_us': fpga_us, 'arm_us': arm_us, 'per_second': int(1e6 / total_us), 'letters': V,
                       'weights': int(sum(l['w'].size for l in layers)), 'info': tm.__doc__ or ''})
            return self.send(200, st)
        self.send(404, {'error': 'not found'})

    def do_POST(self):
        try:
            a = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            if self.path.startswith('/write'):
                n = max(1, min(800, int(a.get('length', 200))))
                t0 = time.time()
                text, sure = write(a.get('start', ''), n, float(a.get('temperature', 0.7)), a.get('seed'))
                dt = time.time() - t0
                print('[%s]%s' % (a.get('start', ''), text.replace('\n', ' ')), flush=True)
                return self.send(200, {'text': text, 'sure': sure, 'seconds': dt, 'per_second': n / dt,
                                       'fpga_us': fpga_us, 'arm_us': arm_us, 'count': nn.count()})
            if self.path.startswith('/next'):
                return self.send(200, {'next': guesses(a.get('text', ''))})
            self.send(404, {'error': 'not found'})
        except Exception as e:
            self.send(400, {'error': str(e)})

    def log_message(self, *a):
        pass


class Server(ThreadingHTTPServer):        # IPv6 and IPv4 (a PC on a direct cable often has only IPv6)
    address_family = socket.AF_INET6
    daemon_threads = True

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


srv = Server(('::', PORT), Handler)
print('\n4. Ready: open Ready projects, "Text AI", Open, in the Ardzy app. Every text it writes is shown here too.', flush=True)
srv.serve_forever()
