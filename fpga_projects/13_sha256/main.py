# 13 SHA-256 miner demo: hash a text in the FPGA, find the real nonce of a Bitcoin block, then race the ARM.
import hashlib
import struct
import time
from blocks import Bus, ShaMiner, require
from sha256_model import zero_bits

bus = Bus()
require(bus, 'SHA2')
sha = ShaMiner(bus, slot=1)

text = b'Ardzy: the Antminer S9 control board, mining again.'
d = sha.sha256(text)
print('1. SHA-256 of "%s"' % text.decode())
print('   FPGA    %s' % d.hex())
print('   hashlib %s  %s' % (hashlib.sha256(text).hexdigest(), 'same' if d == hashlib.sha256(text).digest() else 'DIFFERENT'))

# Bitcoin block 125552: version, previous block, merkle root, time, bits, nonce (80 bytes)
header = bytes.fromhex(
    '01000000'
    '81cd02ab7e569e8bcd9317e2fe99f2de44d49ab2b8851ba4a308000000000000'
    'e320b6c2fffc8d750423db8b1eb942ae710e951ed797f7affc8892b0f1fc122b'
    'c7f5d74d' 'f2b9441a' '42a14695')
real = struct.unpack('<I', header[76:])[0]
print('\n2. Bitcoin block 125552: search 1 million nonces around the real one for 32 zero bits')
r = sha.mine(header, start=real - 600000, count=1000000, zero_bits=32)
print('   found nonce 0x%08x (the block\'s own: 0x%08x) after %d hashes in %.3f s' % (r['nonce'], real, r['hashes'], r['seconds']))
print('   its hash   %s  (%d zero bits)' % (r['hash'], zero_bits(bytes.fromhex(r['hash'])[::-1])))
print('   speed: %.0f thousand double hashes per second in the FPGA' % (r['rate'] / 1e3))

print('\n3. The race: 2 seconds each, a made-up header, looking for 20 zero bits')
mine_header = bytearray(header)
mine_header[4:36] = hashlib.sha256(b'my own previous block').digest()
t = time.time()
n, best = 0, None
while time.time() - t < 2:
    h = mine_header[:76] + struct.pack('<I', n)
    dd = hashlib.sha256(hashlib.sha256(h).digest()).digest()
    if best is None and zero_bits(dd) >= 20:
        best = n
    n += 1
arm = n / (time.time() - t)
print('   ARM (Python + hashlib):  %8.0f hashes/s%s' % (arm, ', found nonce %d' % best if best is not None else ''))
r = sha.mine(bytes(mine_header), start=0, count=0, zero_bits=20, timeout=2)
print('   FPGA (one SHA core):     %8.0f hashes/s, %s' % (r['rate'], 'found nonce %d' % r['nonce'] if r['found'] else 'nothing yet'))
print('   the FPGA is %.0f times faster; the real Antminer S9 does 14 000 000 000 000 per second with 189 ASIC chips' % (r['rate'] / arm))

print('\n4. Mining for ever (stop the program to stop): every block found is printed')
info_n, nonce = 0, 0
while True:
    mine_header[68:72] = struct.pack('<I', int(time.time()))      # the time field changes the whole search
    r = sha.mine(bytes(mine_header), start=nonce, count=0, zero_bits=28, timeout=30)
    if r['found']:
        info_n += 1
        print('   block %d: nonce %d, hash %s' % (info_n, r['nonce'], r['hash']), flush=True)
        nonce = r['nonce'] + 1
    else:
        nonce = 0
