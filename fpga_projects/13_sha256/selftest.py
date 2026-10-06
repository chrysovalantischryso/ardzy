# 13 SHA-256 miner self-test: the FPGA's hashes against hashlib, the real nonce of a Bitcoin block,
# every nonce the miner reports checked by hashlib, and the speed.
import hashlib
import os
import random
import struct
from blocks import Bus, ShaMiner, require
from sha256_model import zero_bits

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


bus = Bus()
require(bus, 'SHA2')
sha = ShaMiner(bus, slot=1)
check('miner answers', sha.r(127) == 0x53484132)

random.seed(13)
bad = 0
for n in (0, 3, 55, 56, 64, 119, 1000):
    data = bytes(random.getrandbits(8) for _ in range(n))
    bad += sha.sha256(data) != hashlib.sha256(data).digest()
check('SHA-256 of 7 messages (0 .. 1000 bytes) = hashlib', bad == 0, '%d different' % bad)

header = bytes.fromhex(
    '01000000'
    '81cd02ab7e569e8bcd9317e2fe99f2de44d49ab2b8851ba4a308000000000000'
    'e320b6c2fffc8d750423db8b1eb942ae710e951ed797f7affc8892b0f1fc122b'
    'c7f5d74d' 'f2b9441a' '42a14695')
real = struct.unpack('<I', header[76:])[0]
r = sha.mine(header, start=real - 1000, count=5000, zero_bits=32, timeout=5)
want = hashlib.sha256(hashlib.sha256(header).digest()).digest()[::-1].hex()
check('Bitcoin block 125552: the real nonce found', r['found'] and r['nonce'] == real and r['hashes'] == 1001,
      'nonce 0x%08x after %d hashes' % (r['nonce'], r['hashes']))
check('its double hash = hashlib', r['hash'] == want, r['hash'] or '')

# a made-up header: the first nonce with 12 zero bits must be the one hashlib finds first
h = bytearray(os.urandom(80))
first = None
for n in range(200000):
    d = hashlib.sha256(hashlib.sha256(bytes(h[:76]) + struct.pack('<I', n)).digest()).digest()
    if zero_bits(d) >= 12:
        first = n
        break
r = sha.mine(bytes(h), start=0, count=200000, zero_bits=12, timeout=5)
check('random header: the same first nonce as hashlib (12 bits)', r['found'] and r['nonce'] == first,
      'FPGA %s, hashlib %s' % (r['nonce'] if r['found'] else '-', first))

r = sha.mine(bytes(h), start=0, count=300000, zero_bits=32, timeout=5)
check('300000 nonces without a find: finished, all tried', not r['found'] and not r['mining'] and r['hashes'] == 300000,
      '%d hashes' % r['hashes'])
check('speed about 1.13 million double hashes per second (3 units)', 1.08e6 < r['rate'] < 1.18e6, '%.0f per second' % r['rate'])

r = sha.mine(bytes(h), start=0, count=0, zero_bits=32, wait=False)
sha.stop()
r = sha.result()
check('stop ends the search', not r['mining'])
print('RESULT: %d of %d ok' % (sum(results), len(results)))
