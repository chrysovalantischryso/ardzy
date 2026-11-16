"""Round-trip test of the built-in bitstream writer (pc_app/fpga/fasm2bit.py).

FASM -> fasm2bit -> .bit -> bit2fasm (an independent reader) -> frames and features, then:
  - the frames read back from the .bit are the frames fasm2bit made (packets, frame order, pad frames)
  - every frame's ECC is right, the IDCODE and the header are the part's
  - every feature of the FASM is found again, and every 1 bit of the bitstream belongs to one of them
  - a damaged bitstream is caught (the checks are not empty)
  - the frames of fixed random designs have not changed (golden hashes, for the same database)

Designs: an empty one, random ones (features of every tile type of the database, picked so they do
not conflict, with multi-bit lines like INIT[63:0] = 64'h...), every .fasm given on the command line
or in ARDZY_FASM_DIR (for example design.fasm files of real builds), and with --build every project
in fpga_projects/ (needs the built-in toolchain, pc_app/tools/fpga).

With Project X-Ray (optional, as in CI) the same designs are also compared with the original tools:
  PRJXRAY_TOOLS = folder with xc7frames2bit and bitread  -> the same .bit, and bitread reads the same frames
  PRJXRAY_ROOT  = a prjxray checkout (+ pip install fasm) -> utils/fasm2frames.py makes the same frames

Database: ARDZY_PRJXRAY_DB (a prjxray-db family folder, e.g. prjxray-db/zynq7), else the app's
pc_app/tools/fpga/db/zynq7. Without one the test is skipped, unless ARDZY_REQUIRE_DB=1.

    python fasm2bit_test.py [--seeds N] [--build] [--update-golden] [design.fasm ...]
"""
import glob, hashlib, json, os, random, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
ROOT = os.path.dirname(APP)
sys.path.insert(0, os.path.join(APP, 'fpga'))
import fasm2bit  # noqa: E402
import bit2fasm  # noqa: E402

PART = 'xc7z010clg400-1'
GOLDEN = os.path.join(HERE, 'data', 'fasm2bit_golden.json')
ECC = bit2fasm.ECC_WORD, bit2fasm.ECC_MASK

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)
        print('   FAIL  ' + what)
    return ok


def find_db():
    for d in (os.environ.get('ARDZY_PRJXRAY_DB'), os.path.join(APP, 'tools', 'fpga', 'db', 'zynq7')):
        if d and os.path.isfile(os.path.join(d, 'mapping', 'parts.yaml')):
            return os.path.abspath(d)
    return None


def db_fingerprint(root):
    """Of the files fasm2bit reads (the same for the app's subset and a full prjxray-db checkout)."""
    files = glob.glob(os.path.join(root, 'segbits_*.db')) + glob.glob(os.path.join(root, 'ppips_*.db'))
    files = [p for p in files if not p.endswith('.origin_info.db')]
    files += glob.glob(os.path.join(root, '*', 'tilegrid.json'))
    files += [os.path.join(root, PART, n) for n in ('part.json', 'package_pins.csv', 'required_features.fasm')]
    h = hashlib.sha256()
    for p in sorted(f for f in files if os.path.isfile(f)):
        h.update(os.path.relpath(p, root).replace('\\', '/').encode())
        h.update(hashlib.sha256(open(p, 'rb').read().replace(b'\r\n', b'\n')).digest())
    return h.hexdigest()[:16]


def masked(words):
    w = list(words)
    w[ECC[0]] &= ~ECC[1]
    return w


def frames_hash(frames):
    """Of every non-zero frame, ECC included (the ECC check above uses fasm2bit's own ECC code)."""
    h = hashlib.sha256()
    for a in sorted(frames):
        if any(frames[a]):
            h.update(('%08X:' % a + ','.join('%08X' % x for x in frames[a])).encode())
    return h.hexdigest()[:16]


# ------------------------------------------------------------------ random designs
def random_design(db, seed, per_type=6):
    """(FASM lines, [(tile, feature)] the lines set): features of every tile type, no two in conflict."""
    rnd = random.Random(seed)
    state = {}                                   # (frame, word, bit) -> 0/1, the bits already decided
    lines, features = [], []

    def take(tile, feat, bits):
        for f, w, b, s in bits:
            if state.get((f, w, b), int(s)) != int(s):
                return False
        for f, w, b, s in bits:
            state[(f, w, b)] = int(s)
        features.append((tile, feat))
        return True

    for line in fasm2bit.Database(db.root, db.part).required:
        tile, _, feat = line.partition('.')
        take(tile, feat, db.feature_bits(tile, feat))
    by_type = {}
    for t in sorted(db.tilegrid):
        if db.tilegrid[t].get('bits'):
            by_type.setdefault(db.tilegrid[t]['type'], []).append(t)
    for ttype in sorted(by_type):
        for tile in rnd.sample(by_type[ttype], min(len(by_type[ttype]), 2)):
            seg_type, lay, sites = db.tile_layout(tile)
            rev = {v: k for k, v in sites.items()}
            names = sorted(n for bt, seg in db.segbits(seg_type).items() if bt in lay for n in seg)
            names = [n for n in names if 'STEPDOWN' not in n]
            if not names:
                continue
            # single features
            for name in rnd.sample(names, min(len(names), per_type)):
                p = name.split('.')
                if p[0] in rev:
                    p[0] = rev[p[0]]
                feat = '.'.join(p)
                bits = db.feature_bits(tile, feat)
                if not bits or not any(s for *_, s in bits) or not db.in_tile(tile, bits):
                    continue
                if take(tile, feat, bits):
                    lines.append('%s.%s' % (tile, feat))
            # one multi-bit line: NAME[hi:lo] = value
            groups = {}
            for n in names:
                if n.endswith(']') and '[' in n:
                    base, idx = n[:n.rfind('[')], int(n[n.rfind('[') + 1:-1])
                    groups.setdefault(base, set()).add(idx)
            groups = {b: ix for b, ix in groups.items() if len(ix) >= 4 and ix == set(range(max(ix) + 1))}
            if groups:
                base = rnd.choice(sorted(groups))
                hi = max(groups[base])
                lo = rnd.randrange(0, hi // 2 + 1)
                val = rnd.getrandbits(hi - lo + 1)
                p = base.split('.')
                if p[0] in rev:
                    p[0] = rev[p[0]]
                fb = '.'.join(p)
                picked = []
                for i in range(lo, hi + 1):
                    if val >> (i - lo) & 1:
                        bits = db.feature_bits(tile, '%s[%d]' % (fb, i))
                        if not bits or not db.in_tile(tile, bits):
                            break
                        picked.append((i, bits))
                else:
                    saved = dict(state), list(features)
                    if all(take(tile, '%s[%d]' % (fb, i), bits) for i, bits in picked):
                        n = hi - lo + 1
                        digits = '%0*X' % ((n + 3) // 4, val)
                        digits = '_'.join(digits[max(0, k - 4):k] for k in range(len(digits), 0, -4)[::-1])
                        lines.append("%s.%s[%d:%d] = %d'h%s" % (tile, fb, hi, lo, n, digits))
                    else:
                        state.clear()
                        state.update(saved[0])
                        features[:] = saved[1]
        # pseudo pips: no bits, fasm2bit must accept and skip them
        pp = sorted(db.ppips(ttype))
        if pp:
            tile = by_type[ttype][0]
            for name in rnd.sample(pp, min(len(pp), 2)):
                lines.append('%s.%s' % (tile, name))
    rnd.shuffle(lines)
    lines.insert(0, '# random design, seed %d' % seed)
    lines.append('{ an annotation } # a comment line')
    return lines, features


# ------------------------------------------------------------------ one design
def roundtrip(db, name, fasm_path, work, expected=None, xray=None):
    """Assemble, read back, check. expected: [(tile, feature)] the FASM sets (else read from the FASM)."""
    print(' - ' + name)
    bit = os.path.join(work, 'out.bit')
    frm = os.path.join(work, 'out.frm')
    try:
        fasm2bit.assemble(db.root, PART, fasm_path, bit, frm, log=lambda s: print('     ' + s))
    except fasm2bit.FasmError as e:
        check(False, '%s: fasm2bit refused it: %s' % (name, e))
        return None
    made = bit2fasm.read_frames_file(frm)
    r = bit2fasm.decode(db.root, PART, bit)
    got = r['frames']
    check(r['idcode'] == db.part_info.idcode, '%s: IDCODE 0x%08X' % (name, r['idcode'] or 0))
    check(r['header'].get('b') == '7z010clg400', '%s: header part %r' % (name, r['header'].get('b')))
    check(not r['ecc_errors'], '%s: %d frames with a wrong ECC, first 0x%08X' % (
        name, len(r['ecc_errors']), (r['ecc_errors'] or [0])[0]))
    check(not r['pad_errors'], '%s: bad pad frames after %s' % (name, ['0x%08X' % a for a in r['pad_errors'][:4]]))
    check(set(made) <= set(got), '%s: %d frames of fasm2bit are not in the bitstream' % (name, len(set(made) - set(got))))
    diff = [a for a in got if masked(got[a]) != masked(made.get(a, [0] * bit2fasm.FRAME_WORDS))]
    check(not diff, '%s: %d frames read back differ from fasm2bit\'s, first 0x%08X' % (name, len(diff), (diff or [0])[0]))
    for cmd in (fasm2bit.C_WCFG, fasm2bit.C_START, fasm2bit.C_DESYNC):
        check(cmd in r['commands'], '%s: command %d missing' % (name, cmd))

    # features: all found again, and they explain every 1 bit
    if expected is None:
        expected = [(t, f + ('[%d]' % a if a or '[' in line.split('=')[0] else ''))
                    for line, t, f, a in fasm2bit.parse_fasm(open(fasm_path))]
        expected += [tuple(l.split('.', 1)) for l in fasm2bit.Database(db.root, PART).required]
    want_bits, want_lines = set(), set()
    for tile, feat in expected:
        bits = db.feature_bits(tile, feat)
        if bits is None:
            check(False, '%s: %s.%s not in the database (bit2fasm)' % (name, tile, feat))
            continue
        for f, w, b, s in bits:
            v = got.get(f, [0] * bit2fasm.FRAME_WORDS)[w] >> b & 1 if 0 <= w < bit2fasm.FRAME_WORDS else None
            if v is not None and v != int(s):
                check(False, '%s: %s.%s: bit %d_%d of frame 0x%08X is %d' % (name, tile, feat, w, b, f, v))
                break
        pos = {(f, w, b) for f, w, b, s in bits if s}
        if pos:
            want_bits |= pos
            want_lines.add(tile + '.' + feat)
    found = set(r['fasm'])
    lost = sorted(l for l in want_lines if l not in found and l.replace('[0]', '') not in found
                  and l + '[0]' not in found)
    check(not lost, '%s: %d features not found in the bitstream, first %s' % (name, len(lost), lost[:3]))
    have = {(a, w, b) for a, words in got.items() for w, v in enumerate(masked(words)) for b in range(32) if v >> b & 1}
    stepdown = any('STEPDOWN' in l for l in want_lines)
    if not stepdown:                         # STEPDOWN adds bits on its own: compare only without it
        extra, missing = sorted(have - want_bits), sorted(want_bits - have)
        check(not extra, '%s: %d bits set by no feature of the FASM, first %s' % (name, len(extra), extra[:3]))
        check(not missing, '%s: %d bits of the FASM not set, first %s' % (name, len(missing), missing[:3]))
    check(not r['unknown_bits'], '%s: %d bits no database feature explains, first %s' % (
        name, len(r['unknown_bits']), r['unknown_bits'][:3]))
    if xray:
        compare_prjxray(db, name, fasm_path, bit, frm, got, work, xray)
    return got


# ------------------------------------------------------------------ Project X-Ray
def compare_prjxray(db, name, fasm_path, bit, frm, got, work, xray):
    tools, root = xray
    part_yaml = os.path.join(db.root, PART, 'part.yaml')
    if tools:
        ref = os.path.join(work, 'ref.bit')
        subprocess.check_call([os.path.join(tools, 'xc7frames2bit'), '--part_file', part_yaml, '--part_name', PART,
                               '--frm_file', frm, '--output_file', ref], stdout=subprocess.DEVNULL)

        def body(p):
            d = open(p, 'rb').read()
            return d[d.index(b'\xaa\x99\x55\x66'):]
        check(body(bit) == body(ref), '%s: the .bit is not the one of prjxray xc7frames2bit' % name)
        rb = os.path.join(work, 'bitread.frm')
        subprocess.check_call([os.path.join(tools, 'bitread'), '-part_file', part_yaml, '-C', '-o', rb, bit],
                              stdout=subprocess.DEVNULL)
        theirs = bit2fasm.read_frames_file(rb)
        diff = [a for a in set(got) | set(theirs)
                if got.get(a, [0] * 101) != theirs.get(a, [0] * 101)]
        check(not diff, '%s: prjxray bitread reads %d frames differently, first 0x%08X' % (name, len(diff), (diff or [0])[0]))
    if root:
        ref = os.path.join(work, 'ref.frm')
        env = dict(os.environ, PYTHONPATH=root + os.pathsep + os.environ.get('PYTHONPATH', ''))
        subprocess.check_call([sys.executable, os.path.join(root, 'utils', 'fasm2frames.py'), '--db-root', db.root,
                               '--part', PART, fasm_path, ref], env=env, stdout=subprocess.DEVNULL)
        theirs = bit2fasm.read_frames_file(ref)
        mine = bit2fasm.read_frames_file(frm)
        diff = [a for a in set(mine) | set(theirs)
                if mine.get(a, [0] * 101) != theirs.get(a, [0] * 101)]
        check(not diff, '%s: prjxray fasm2frames.py makes %d frames differently, first 0x%08X' % (
            name, len(diff), (diff or [0])[0]))


# ------------------------------------------------------------------ STEPDOWN spreads over the bank
def stepdown_test(db, work, xray):
    """A 1.8 V pin (STEPDOWN) on one IOB33: like prjxray, every IOB33 of its bank and its HCLK_IOI3 get it too."""
    import csv
    tag = 'LVCMOS12_LVCMOS15_LVCMOS18_SSTL135_SSTL15.STEPDOWN'
    rows = list(csv.DictReader(open(os.path.join(db.root, PART, 'package_pins.csv'))))
    rows = [r for r in rows if 'IOB33' in r['tile'] and r['tile'] in db.tilegrid]
    bank = sorted({r['bank'] for r in rows})[0]
    tiles = sorted({r['tile'] for r in rows if r['bank'] == bank})
    first = tiles[0]
    p = os.path.join(work, 'stepdown.fasm')
    open(p, 'w').write('%s.IOB_Y0.%s\n' % (first, tag))
    got = roundtrip(db, 'STEPDOWN in bank %s' % bank, p, work, xray=xray)
    if got is None:
        return None
    found = set(bit2fasm.disassemble(db, got)[0])
    hclk = 'HCLK_IOI3_' + db.part_info.iobanks[bank]
    check(hclk + '.STEPDOWN' in found, 'STEPDOWN: %s.STEPDOWN not set' % hclk)
    for t in tiles:
        for site in db.tilegrid[t]['sites']:
            f = '%s.IOB_Y%d.%s' % (t, int(site[-1]) % 2, tag)
            if db.feature_bits(t, f.split('.', 1)[1]):
                check(f in found, 'STEPDOWN: %s not set' % f)
    return got


# ------------------------------------------------------------------ damage must be caught
def damage_test(db, work):
    print(' - damaged bitstreams are caught')
    fasm = os.path.join(work, 'one.fasm')
    tile = next(t for t in sorted(db.tilegrid) if db.tilegrid[t]['type'] == 'CLBLL_L')
    open(fasm, 'w').write('%s.SLICEL_X0.ALUT.INIT[63:0] = 64\'hFFFF0000AAAA5555\n' % tile)
    bit = os.path.join(work, 'one.bit')
    fasm2bit.assemble(db.root, PART, fasm, bit, log=lambda s: None)
    r = bit2fasm.decode(db.root, PART, bit)
    a = next(x for x in sorted(r['frames']) if any(masked(r['frames'][x])))
    data = bytearray(open(bit, 'rb').read())
    head, words = bit2fasm.read_bit(bit)
    start = len(data) - len(words) * 4
    # flip one data bit of that frame (find it by its words in the file)
    needle = b''.join(x.to_bytes(4, 'big') for x in r['frames'][a])
    i = data.index(needle, start)
    data[i + 4 * 3] ^= 0x01
    bad = os.path.join(work, 'bad.bit')
    open(bad, 'wb').write(data)
    rb = bit2fasm.decode(db.root, PART, bad)
    check(a in rb['ecc_errors'], 'a flipped bit was not seen by the ECC check')
    check(rb['fasm'] != r['fasm'] or rb['unknown_bits'], 'a flipped bit did not change the features read back')
    open(bad, 'wb').write(data[:-7])
    try:
        bit2fasm.read_bit(bad)
        check(False, 'a cut .bit was read without an error')
    except bit2fasm.BitError:
        pass


# ------------------------------------------------------------------ main
def main():
    args = sys.argv[1:]
    seeds = 6
    if '--seeds' in args:
        i = args.index('--seeds')
        seeds = int(args[i + 1])
        del args[i:i + 2]
    build = '--build' in args
    update = '--update-golden' in args
    fasms = [a for a in args if not a.startswith('--')]
    if os.environ.get('ARDZY_FASM_DIR'):
        fasms += sorted(glob.glob(os.path.join(os.environ['ARDZY_FASM_DIR'], '**', '*.fasm'), recursive=True))

    root = find_db()
    if not root:
        print('SKIP: no Project X-Ray database (set ARDZY_PRJXRAY_DB to prjxray-db/zynq7)')
        sys.exit(1 if os.environ.get('ARDZY_REQUIRE_DB') == '1' else 0)
    db = bit2fasm.BitDB(root, PART)
    fp = db_fingerprint(root)
    tools = os.environ.get('PRJXRAY_TOOLS') or None
    xroot = os.environ.get('PRJXRAY_ROOT') or None
    xray = (tools, xroot) if tools or xroot else None
    print('fasm2bit round trip, database %s (%s)%s' % (root, fp, ', against Project X-Ray' if xray else ''))

    golden = json.load(open(GOLDEN)) if os.path.isfile(GOLDEN) else {}
    gold = golden.get('databases', {}).get(fp, {})
    new_gold = {}
    work = tempfile.mkdtemp(prefix='fasm2bit_test_')
    try:
        p = os.path.join(work, 'empty.fasm')
        open(p, 'w').write('')
        got = roundtrip(db, 'empty design', p, work, xray=xray)
        if got is not None:
            new_gold['empty'] = frames_hash(got)
        for seed in range(1, seeds + 1):
            lines, feats = random_design(db, seed)
            p = os.path.join(work, 'random_%d.fasm' % seed)
            open(p, 'w').write('\n'.join(lines) + '\n')
            feats_named = [(t, f) for t, f in feats]
            got = roundtrip(db, 'random design %d (%d lines)' % (seed, len(lines)), p, work, feats_named, xray)
            if got is not None:
                new_gold['random_%d' % seed] = frames_hash(got)
        got = stepdown_test(db, work, xray)
        if got is not None:
            new_gold['stepdown'] = frames_hash(got)
        damage_test(db, work)
        for f in fasms:
            roundtrip(db, os.path.relpath(f), f, work, xray=xray)
        if build:
            build_projects(db, work, xray)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if update:
        golden.setdefault('databases', {})[fp] = new_gold
        os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
        json.dump(golden, open(GOLDEN, 'w'), indent=1, sort_keys=True)
        print('golden hashes written for database %s' % fp)
    elif gold:
        print(' - golden hashes (database %s)' % fp)
        for k, v in new_gold.items():
            if k in gold:
                check(gold[k] == v, '%s: frames changed (%s, golden %s); if on purpose: --update-golden' % (k, v, gold[k]))
    else:
        print(' - no golden hashes for this database (%s): run with --update-golden to add them' % fp)

    print('%s: %d failures' % ('FAILED' if failures else 'OK', len(failures)))
    sys.exit(1 if failures else 0)


def build_projects(db, work, xray):
    """Build every ready project with the built-in toolchain and round-trip its design.fasm."""
    import flow
    if not flow.available():
        check(False, '--build: the built-in toolchain (pc_app/tools/fpga) is missing')
        return
    for proj in sorted(glob.glob(os.path.join(ROOT, 'fpga_projects', '[0-9]*'))):
        name = os.path.basename(proj)
        tmp = os.path.join(work, 'proj_' + name)
        shutil.copytree(proj, tmp)
        try:
            flow.build(tmp, log=lambda s: None)
        except Exception as e:
            check(False, '%s: build failed: %s' % (name, e))
            continue
        fasm = sorted(glob.glob(os.path.join(tmp, '**', 'design.fasm'), recursive=True))
        if check(bool(fasm), '%s: the build left no design.fasm' % name):
            roundtrip(db, name, fasm[0], work, xray=xray)


if __name__ == '__main__':
    main()
