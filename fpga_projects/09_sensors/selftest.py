# 09 Sensors self-test: needs nothing connected. The distance part uses the echo simulator inside the FPGA,
# the IR part an IR transmitter inside, and the touch part measures the real pin (J8 pin 15).
import time
from blocks import Bus, Sensors, require

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


bus = Bus()
require(bus, 'SENS')
s = Sensors(bus, slot=1)
check('sensor block answers', s.r(16) == 0x53454E53)
for us, mm in ((583, 100), (5831, 1000), (23324, 4000)):
    s.simulate_echo(us)
    s.setup(distance=True, echo_sim=True, touch=False)
    time.sleep(0.2)
    check('echo %d us -> %d mm' % (us, mm), abs(s.echo_us() - us) <= 1 and abs(s.distance_mm() - mm) <= 1,
          '%d us, %d mm' % (s.echo_us(), s.distance_mm()))
r = s.rangings()
check('measures every 60 ms', r['done'] >= 9, '%d measurements' % r['done'])
s.setup(distance=True, echo_sim=False, touch=False)        # real ECHO pin, nothing connected: no echo
time.sleep(0.3)
check('no sensor: timeouts, no distance', s.rangings()['timeouts'] >= 2 and s.distance_mm() is None)

s.setup(distance=False, ir_test=True)
for addr, cmd in ((0x00, 0x45), (0x04, 0x08), (0xA5, 0x5A)):
    n0 = s.ir()['count']
    s.ir_send_test(addr, cmd)
    time.sleep(0.12)                                       # one NEC frame is 67.5 ms
    ir = s.ir()
    check('IR code address 0x%02X command 0x%02X' % (addr, cmd),
          ir['count'] == n0 + 1 and ir['valid'] and ir['address'] == addr and ir['command'] == cmd,
          'got 0x%02X / 0x%02X, errors %d' % (ir['address'], ir['command'], ir['errors']))
s.setup(distance=False, ir_test=False, touch=True)
time.sleep(0.3)
t = s.touch()
check('touch pin charges (nothing touching)', 5 < t['raw'] < 60000 and not t['touched'],
      'raw %d clocks (%.2f us), base %d' % (t['raw'], t['raw'] / 100, t['base']))
print('RESULT: %d of %d ok' % (sum(results), len(results)))
