# 16 AI in the FPGA demo: load the trained network into the FPGA, read 50 test digits, compare the speed with
# the ARM, then serve a drawing page: draw a digit in your browser and the FPGA reads it.
import base64, json, math, socket, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
import nn_model
from draw_page import PAGE
from blocks import Bus, DigitAI, require, nn_load_model, nn_reference, digit_preprocess, digit_text

PORT = 8080
bus = Bus()
require(bus, 'NNET')
ai = DigitAI(bus, slot=1)
m = nn_load_model(nn_model)
t0 = time.time()
ai.load(m)
print('The network is in the FPGA: 784 inputs -> 64 neurons -> 10 digits, %d weights (8 bit), sent in %.2f s.'
      % (64 * 784 + 640, time.time() - t0))

print('\n1. The 50 test digits it never saw while learning:')
right = same = 0
for n, (x, want) in enumerate(zip(m['test'], m['labels'])):
    got = ai.run(x)
    right += got == want
    same += got == nn_reference(m, x)[0] and ai.scores() == nn_reference(m, x)[1]
    if n % 10 == 3:
        print(digit_text(x))
        print('   the FPGA reads: %d (the right answer: %d)\n' % (got, want))
print('   %d of 50 right; the FPGA and the Python math agree %d of 50 times, to the last bit.' % (right, same))

print('\n2. Speed for one digit:')
fpga_us = ai.cycles() / 100.0
x = m['test'][0]
n, t0 = 0, time.time()
while time.time() - t0 < 1.0:
    nn_reference(m, x); n += 1
arm_us = 1e6 * (time.time() - t0) / n
n, t0 = 0, time.time()
while time.time() - t0 < 1.0:
    ai.run(x); n += 1
total_us = 1e6 * (time.time() - t0) / n
print('   the FPGA computes it in %.1f microseconds (%d clocks at 100 MHz): %.0f x faster than the ARM' % (fpga_us, ai.cycles(), arm_us / fpga_us))
print('   the ARM with numpy needs %.0f microseconds' % arm_us)
print('   with sending the picture from Python (196 writes): %.0f microseconds, %d digits per second' % (total_us, 1e6 / total_us))

lock = threading.Lock()


def guess(px):
    a = np.frombuffer(base64.b64decode(px), dtype=np.uint8).reshape(112, 112)
    if a.max() < 30:
        return {'empty': True}
    x = digit_preprocess(a)
    with lock:
        d = ai.run(x)
        s, h, cycles, count = ai.scores(), ai.hidden(), ai.cycles(), ai.count()
    t0 = time.time()
    nn_reference(m, x)
    arm_us = 1e6 * (time.time() - t0)
    z = [v * m['scale'] for v in s]
    top = max(z)
    e = [math.exp(v - top) for v in z]
    hmax = max(h) or 1
    print('%s\n   a drawing: the FPGA reads %d (%.0f %% sure)' % (digit_text(x), d, 100 * e[d] / sum(e)), flush=True)
    return {'digit': d, 'prob': [v / sum(e) for v in e], 'pixels': [int(v) for v in x.ravel()],
            'hidden': [int(255 * v / hmax) for v in h], 'cycles': cycles, 'fpga_us': cycles / 100.0,
            'arm_us': arm_us, 'count': count}


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, kind):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith('/state'):            # for the Ardzy app's AI page
            with lock:
                st = {'running': True, 'project': '16_digit_ai', 'count': ai.count(), 'cycles': ai.cycles()}
            st.update({'fpga_us': fpga_us, 'arm_us': arm_us, 'per_second': int(1e6 / total_us), 'test_right': right,
                       'trained': round(100 * m['accuracy'], 1), 'hidden': m['hid'], 'weights': 64 * 784 + 640})
            return self.send(200, json.dumps(st), 'application/json')
        if self.path.startswith('/example'):
            i = int(time.time() * 7) % len(m['test'])
            return self.send(200, json.dumps({'pixels': [int(v) for v in m['test'][i]], 'label': m['labels'][i]}), 'application/json')
        self.send(200, PAGE, 'text/html; charset=utf-8')

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            self.send(200, json.dumps(guess(body.get('px', ''))), 'application/json')
        except Exception as e:
            self.send(400, json.dumps({'error': str(e)}), 'application/json')

    def log_message(self, *a):
        pass


class Server(ThreadingHTTPServer):        # IPv6 and IPv4 (a PC on a direct cable often has only IPv6)
    address_family = socket.AF_INET6
    daemon_threads = True

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


srv = Server(('::', PORT), Handler)
host = socket.gethostname()
print('\n3. Draw a digit: open  http://%s.local:%d  in a browser (PC or phone on the same network).' % (host, PORT))
print('   Every digit you draw is read by the FPGA and shown here too.', flush=True)
srv.serve_forever()
