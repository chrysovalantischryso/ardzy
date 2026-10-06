# Lesson 7: a UART. Python sends bytes through the FPGA's transmitter; the FPGA's receiver reads them back.
import time
from ardzy import MMIO
results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('CHECK %-4s %-48s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)

regs = MMIO(0x41200000)
TX, CFG, RX, SENT = 0x00, 0x04, 0x80, 0x84
LOOP, POP = 1 << 31, 1 << 30
BAUD = 115200
cfg = (100_000_000 // BAUD) | LOOP
regs.write(CFG, cfg)
n_written = 0


def send(byte):
    global n_written
    while regs.read(RX) >> 16 & 1:          # wait while the transmitter is busy
        pass
    n_written += 1
    regs.write(TX, (n_written << 8) | byte)  # (the upper bits change at every write, so the same byte twice is sent twice)


def receive(timeout=0.2):
    t = time.time()
    while not (regs.read(RX) >> 8) & 0x1F:
        if time.time() - t > timeout:
            return None
    b = regs.read(RX) & 0xFF
    regs.write(CFG, cfg | POP); regs.write(CFG, cfg)
    return b


def flush():
    """Throw away what the receiver caught before: while it listened to the pin, a low pin looked like a 0 byte."""
    time.sleep(0.01)
    while (regs.read(RX) >> 8) & 0x1F:
        regs.write(CFG, cfg | POP); regs.write(CFG, cfg)


flush()
text = b'Hello, Ardzy!'
got = bytearray()
for ch in text:
    send(ch)
    r = receive()
    if r is not None:
        got.append(r)
print('sent %r, received %r over the internal loopback at %d baud' % (text, bytes(got), BAUD))
check('loopback: every byte comes back', bytes(got) == text)
for baud in (9600, 1_000_000):
    cfg = (100_000_000 // baud) | LOOP
    regs.write(CFG, cfg)
    flush()
    send(0x5A)
    r = receive(0.1)
    check('the same at %d baud' % baud, r == 0x5A, hex(r) if r is not None else 'nothing')
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nNow at 115200 baud on the pins: connect a USB-UART cable (its RX to J1 pin 11, its TX to J1 pin 12,')
print('GND to pin 1) and open the app\'s USB serial tab. Everything you type there comes back in capitals.')
cfg = 100_000_000 // 115200                 # loopback off: the pins
regs.write(CFG, cfg)
for ch in b'Ardzy UART lesson: type something\r\n':
    send(ch)
while True:
    r = receive(1.0)
    if r is not None:
        send(ord(chr(r).upper()))
