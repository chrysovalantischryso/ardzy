# Lesson 5: a state machine. Python watches the traffic light and presses the pedestrian button.
import time
from ardzy import MMIO
results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('CHECK %-4s %-48s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)

regs = MMIO(0x41200000)
CTRL, STATE, LEFT = 0x00, 0x80, 0x84
NAMES = ['GREEN', 'YELLOW', 'RED', 'WALK', 'RED+YELLOW']


def state():
    return regs.read(STATE) & 7


def wait_for(s, timeout):
    t = time.time()
    while state() != s and time.time() - t < timeout:
        time.sleep(0.01)
    return state() == s


check('without a press it settles on GREEN and stays', wait_for(0, 8))
time.sleep(1.5)
check('still GREEN 1.5 s later (nobody pressed)', state() == 0)
regs.write(CTRL, 1); regs.write(CTRL, 0)          # press
seen = []
t = time.time()
while time.time() - t < 12 and (len(seen) < 4):
    s = state()
    if not seen or seen[-1] != s:
        seen.append(s)
    time.sleep(0.02)
check('after a press: GREEN, YELLOW, RED, WALK', seen[:4] == [0, 1, 2, 3], ' -> '.join(NAMES[s] for s in seen))
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nThe light runs on its own. Python presses the button every 15 seconds; watch the LEDs.')
last, t_press = None, time.time()
while True:
    s = state()
    if s != last:
        print('%-11s for %.1f s%s' % (NAMES[s], regs.read(LEFT) / 1e8, '  (someone is waiting)' if regs.read(STATE) & 8 else ''), flush=True)
        last = s
    if time.time() - t_press > 15:
        regs.write(CTRL, 1); regs.write(CTRL, 0)
        print('   * button pressed', flush=True)
        t_press = time.time()
    time.sleep(0.05)
