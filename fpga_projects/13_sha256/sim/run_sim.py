"""Simulation test of sha_miner.v with Icarus Verilog (PC only).

    python sim/run_sim.py

Checks the raw SHA-256 compression against hashlib ("abc" and a random block) and the miner on a
real Bitcoin block header: it must find the header's own nonce (a hash with 64 leading zero bits).
"""
import hashlib, os, random, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'common'))
from sha256_model import compress, IV, header_job   # noqa: E402


def find_iverilog():
    """Icarus Verilog: ARDZY_IVERILOG, else the copy the Ardzy app makes (%LOCALAPPDATA%\\Ardzy\\icarus),
    else iverilog on the PATH. (Icarus can not work from folders with spaces.)"""
    import shutil
    for d in (os.environ.get('ARDZY_IVERILOG'), os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Ardzy', 'icarus', 'bin')):
        if d and os.path.exists(os.path.join(d, 'iverilog.exe')):
            return d
    exe = shutil.which('iverilog')
    if exe:
        return os.path.dirname(exe)
    sys.exit('Icarus Verilog not found: open Simulation once in the Ardzy app, or set ARDZY_IVERILOG')


IVERILOG = find_iverilog()

# block 125552 (the Bitcoin wiki's example of the block hashing algorithm)
HEADER = bytes.fromhex(
    '01000000'
    '81cd02ab7e569e8bcd9317e2fe99f2de44d49ab2b8851ba4a308000000000000'
    'e320b6c2fffc8d750423db8b1eb942ae710e951ed797f7affc8892b0f1fc122b'
    'c7f5d74d' 'f2b9441a' '42a14695')


def main():
    nonce = struct.unpack('<I', HEADER[76:80])[0]
    h = hashlib.sha256(hashlib.sha256(HEADER).digest()).digest()
    print('header hash (displayed):', h[::-1].hex(), ' nonce', hex(nonce))
    mid, tail = header_job(HEADER)
    # raw mode: "abc", one padded block
    abc = b'abc' + b'\x80' + b'\x00' * (55 - 3) + struct.pack('>Q', 24)
    words = struct.unpack('>16I', abc)
    want_abc = compress(IV, words)
    assert struct.pack('>8I', *want_abc) == hashlib.sha256(b'abc').digest()
    rnd = [random.getrandbits(32) for _ in range(16)]
    hin = [random.getrandbits(32) for _ in range(8)]
    want_rnd = compress(hin, rnd)

    lines = []
    def wr(i, v): lines.append('    wr(%d, 32\'h%08x);' % (i, v))
    def rd(i, tag): lines.append('    rd(%d); $display("%s %%08x", rdata);' % (i, tag))
    def run_raw(h_in, blk, tag):
        for k, v in enumerate(h_in): wr(24 + k, v)
        for k, v in enumerate(blk): wr(32 + k, v)
        wr(0, 1)
        lines.append("    repeat (140) @(posedge clk);")
        for k in range(8): rd(48 + k, '%s%d' % (tag, k))
    run_raw(IV, words, 'ABC')
    run_raw(hin, rnd, 'RND')
    for k, v in enumerate(mid): wr(8 + k, v)
    for k, v in enumerate(tail): wr(16 + k, v)
    wr(2, nonce - 5); wr(3, 12); wr(4, 32); wr(0, 2)
    lines.append("    repeat (4 * 280) @(posedge clk);")
    for i, tag in ((1, 'STATUS'), (5, 'FOUND'), (6, 'HASHES')):
        rd(i, tag)
    for k in range(8): rd(56 + k, 'FH%d' % k)
    rd(127, 'ID')

    tb = open(os.path.join(HERE, 'tb.v.in')).read().replace('__STEPS__', '\n'.join(lines))
    open(os.path.join(HERE, 'tb.v'), 'w').write(tb)
    env = dict(os.environ, PATH=IVERILOG + os.pathsep + os.environ['PATH'])
    subprocess.run([os.path.join(IVERILOG, 'iverilog.exe'), '-g2012', '-o', os.path.join(HERE, 'tb.vvp'),
                    os.path.join(HERE, 'tb.v'), os.path.join(HERE, '..', 'sha_miner.v')], check=True, env=env)
    r = subprocess.run([os.path.join(IVERILOG, 'vvp.exe'), '-n', os.path.join(HERE, 'tb.vvp')],
                       capture_output=True, text=True, env=env)
    got = {}
    for l in r.stdout.splitlines():
        p = l.split()
        if len(p) == 2:
            got[p[0]] = int(p[1], 16)
    ok = []
    def check(name, cond, detail=''):
        ok.append(cond)
        print('%-4s %-46s %s' % ('ok' if cond else 'FAIL', name, detail))
    check('raw: SHA-256("abc")', [got.get('ABC%d' % k) for k in range(8)] == list(want_abc))
    check('raw: a random block and state', [got.get('RND%d' % k) for k in range(8)] == list(want_rnd))
    check('miner: found the real nonce', got.get('STATUS', 0) & 4 and got.get('FOUND') == nonce,
          'status %s, nonce %s' % (hex(got.get('STATUS', 0)), hex(got.get('FOUND', 0))))
    check('miner: tried 6 nonces', got.get('HASHES') == 6, str(got.get('HASHES')))
    check('miner: its double hash = hashlib', struct.pack('>8I', *[got.get('FH%d' % k, 0) for k in range(8)]) == h)
    check('ID "SHA2"', got.get('ID') == 0x53484132)
    print('RESULT: %d of %d ok' % (sum(ok), len(ok)))
    if not all(ok):
        print(r.stdout[-2000:])


if __name__ == '__main__':
    main()
