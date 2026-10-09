# 18 Image AI demo: the FPGA draws new handwritten digits, and project 16's reader (in the same engine) checks
# them. Then it serves the Ardzy app's Image AI page (port 8080): draw digits, morph one digit into another.
import base64, json, socket, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
import image_model as im
import reader_model
from blocks import Bus, MLP, require, mlp_reference, digit_text, nn_load_model

PORT = 8080
bus = Bus()
require(bus, 'DRAW')
nn = MLP(bus, slot=1)
dec = lambda s, shape: np.frombuffer(base64.b64decode(''.join(s)), dtype=np.int8).reshape(shape)
drawer = [{'w': dec(getattr(im, 'W%d' % (k + 1)), im.SHAPES[k]), 'b': getattr(im, 'B%d' % (k + 1)),
           'shift': im.SHIFTS[k], 'act': im.ACTS[k]} for k in range(len(im.SHAPES))]
r = nn_load_model(reader_model)
reader = [{'w': r['w1'], 'b': r['b1'], 'shift': r['shift'], 'act': 1}, {'w': r['w2'], 'b': r['b2'], 'shift': 0, 'act': 0}]
t0 = time.time()
cfg_draw = nn.load(drawer)
cfg_read = nn.load(reader)
print('Two networks in the FPGA: the drawer (16 + 10 inputs -> 96 -> 784 pixels) and project 16\'s reader, %d weights, sent in %.2f s.'
      % (sum(l['w'].size for l in drawer + reader), time.time() - t0))
lock = threading.Lock()
last = {'draw_us': 0, 'read_us': 0}


def drawer_input(a, b, mix, z):
    """The drawer's 26 input bytes: z * 32 + 128, then the digit: 32 for the chosen one (a mix of two digits:
    32 * (1 - mix) and 32 * mix)."""
    zb = np.clip(np.round(np.asarray(z) * im.ZSCALE) + 128, 0, 255)
    y = np.zeros(10)
    y[a] += im.ZSCALE * (1 - mix)
    y[b] += im.ZSCALE * mix
    return np.concatenate([zb, np.round(y)]).astype(np.uint8)


def draw_and_read(x):
    """One drawing in the FPGA, then the reader on it (both networks are in the engine)."""
    with lock:
        nn.use(cfg_draw)
        _, pix = nn.run(x)
        last['draw_us'] = nn.cycles() / 100.0
        nn.use(cfg_read)
        d, s = nn.run(pix)
        last['read_us'] = nn.cycles() / 100.0
    z = np.array(s, float) * reader_model.SCALE
    p = np.exp(z - z.max()); p /= p.sum()
    return np.array(pix, np.uint8), d, float(p[d])


def pack(pix):
    return base64.b64encode(bytes(pix)).decode()


print('\n1. Bit for bit: the FPGA against the same math in Python')
rs = np.random.RandomState(18)
same = 0
for k in range(10):
    x = drawer_input(k, k, 0, rs.randn(im.Z))
    with lock:
        nn.use(cfg_draw)
        hw = nn.run(x)[1]
    same += [int(v) for v in hw] == mlp_reference(drawer, x)[1]
print('   %d of 10 drawings equal, every one of the 784 pixels' % same)

print('\n2. It draws every digit; the reader checks:')
right = 0
for d in range(10):
    pix, got, p = draw_and_read(drawer_input(d, d, 0, rs.randn(im.Z)))
    right += got == d
    if d in (2, 7):
        print(digit_text(pix))
    print('   asked for %d, drew it, the reader says %d (%.0f %% sure)' % (d, got, 100 * p))
print('   %d of 10 read back as the digit that was asked for' % right)

print('\n3. Speed for one drawing:')
x = drawer_input(5, 5, 0, rs.randn(im.Z))
n, t0 = 0, time.time()
while time.time() - t0 < 1.0:
    mlp_reference(drawer, x); n += 1
arm_us = 1e6 * (time.time() - t0) / n
draw_and_read(x)
print('   the FPGA draws in %.1f microseconds and reads in %.1f; the ARM with numpy needs %.0f microseconds to draw'
      % (last['draw_us'], last['read_us'], arm_us))


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
            with lock:
                st = {'running': True, 'project': '18_image_ai', 'count': nn.count()}
            st.update({'draw_us': last['draw_us'], 'read_us': last['read_us'], 'arm_us': arm_us,
                       'weights': int(sum(l['w'].size for l in drawer)), 'z': im.Z})
            return self.send(200, st)
        self.send(404, {'error': 'not found'})

    def do_POST(self):
        try:
            a = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            rng = np.random.RandomState(a.get('seed') if a.get('seed') is not None else int(time.time() * 1000) % 100000)
            variety = float(a.get('variety', 1.0))
            out = []
            if self.path.startswith('/draw'):              # count new drawings of one digit
                d = int(a.get('digit', 0)) % 10
                for _ in range(max(1, min(24, int(a.get('count', 8))))):
                    pix, got, p = draw_and_read(drawer_input(d, d, 0, rng.randn(im.Z) * variety))
                    out.append({'pixels': pack(pix), 'read': got, 'sure': round(p, 3)})
            elif self.path.startswith('/morph'):           # one style, the digit slowly changing from a to b
                fa, fb = int(a.get('from', 3)) % 10, int(a.get('to', 8)) % 10
                z = rng.randn(im.Z) * variety
                steps = max(2, min(24, int(a.get('steps', 9))))
                for k in range(steps):
                    pix, got, p = draw_and_read(drawer_input(fa, fb, k / (steps - 1), z))
                    out.append({'pixels': pack(pix), 'read': got, 'sure': round(p, 3)})
            elif self.path.startswith('/style'):           # one digit, the style walking from one to another
                d = int(a.get('digit', 0)) % 10
                z0, z1 = rng.randn(im.Z) * variety, rng.randn(im.Z) * variety
                steps = max(2, min(24, int(a.get('steps', 9))))
                for k in range(steps):
                    t = k / (steps - 1)
                    pix, got, p = draw_and_read(drawer_input(d, d, 0, z0 * (1 - t) + z1 * t))
                    out.append({'pixels': pack(pix), 'read': got, 'sure': round(p, 3)})
            else:
                return self.send(404, {'error': 'not found'})
            if self.path.startswith('/morph'):
                print('morphed %d into %d: the reader saw %s' % (fa, fb, ' '.join(str(o['read']) for o in out)), flush=True)
            else:
                print('drew %d pictures of a %d (%s), the reader agrees with %d' % (len(out), d, self.path.strip('/'),
                      sum(1 for o in out if o['read'] == d)), flush=True)
            self.send(200, {'images': out, 'draw_us': last['draw_us'], 'read_us': last['read_us'], 'arm_us': arm_us,
                            'count': nn.count()})
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
print('\n4. Ready: open Ready projects, "Image AI", Open, in the Ardzy app. Every drawing is counted here too.', flush=True)
srv.serve_forever()
