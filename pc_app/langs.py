"""Programming languages for the Ardzy board.

Built in (the SD card image has the tools): Python, C, C++, Arduino, Shell (bash), Perl, ARM assembly.
Installed from the app: JavaScript (Node.js), Lua, Go, Rust. The board has no internet of its own (it hangs
on the PC's cable), so this PC does what apt would do: it reads Debian's package lists, works out which
packages the board is missing, downloads them (every file checked against Debian's SHA256 sums) and sends
them as an Ardzy update bundle; the board's installer (ardzy-update, as root) installs them with dpkg.
The board's system version does not change.

Every language gets a small "ardzy" library in the project (LEDs, buzzer, buttons, FPGA registers,
watch()), and a run.sh made at upload time that builds and starts the program.
"""
import hashlib, io, json, lzma, os, re, tarfile, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ARCH = 'armhf'
SUITES = [('https://deb.debian.org/debian', 'trixie'),
          ('https://deb.debian.org/debian', 'trixie-updates'),
          ('https://deb.debian.org/debian-security', 'trixie-security')]

# id: name, main file, Debian packages (None = built into the image), the command that must exist on the
# board, about how big it is (MB to download, MB on the board; Debian's numbers in October 2026)
LANGS = {
    'python': dict(name='Python', main='main.py', pkgs=None, cmd='python3'),
    'c':      dict(name='C', main='main.c', pkgs=None, cmd='gcc'),
    'cpp':    dict(name='C++', main='main.cpp', pkgs=None, cmd='g++'),
    'arduino': dict(name='Arduino (C++)', main='.ino', pkgs=None, cmd='g++'),
    'sh':     dict(name='Shell (bash)', main='main.sh', pkgs=None, cmd='bash'),
    'perl':   dict(name='Perl', main='main.pl', pkgs=None, cmd='perl'),
    'asm':    dict(name='ARM assembly', main='main.S', pkgs=None, cmd='gcc'),
    'js':     dict(name='JavaScript (Node.js)', main='main.js', pkgs=['nodejs'], cmd='node', size=(21, 87)),
    'lua':    dict(name='Lua', main='main.lua', pkgs=['lua5.4'], cmd='lua5.4', size=(0.1, 0.3)),
    'go':     dict(name='Go', main='main.go', pkgs=['golang-go'], cmd='go', size=(44, 244)),
    'rust':   dict(name='Rust', main='main.rs', pkgs=['rustc'], cmd='rustc', size=(84, 344)),
}
INSTALLABLE = [k for k, v in LANGS.items() if v['pkgs']]


def lang_of(files):
    """The language of a project from its files (None: not one of the run.sh languages)."""
    for k in ('cpp', 'sh', 'perl', 'asm', 'js', 'lua', 'go', 'rust'):
        m = LANGS[k]['main']
        if m in files or (k == 'asm' and 'main.s' in files):
            return k
    return None


# ---------------------------------------------------------------- run.sh made at upload
# The libraries of Perl, Lua and JavaScript reach the FPGA registers through this small helper
# (those languages cannot map memory themselves): it is compiled once on the board, then each program
# keeps one running and talks to it through a pipe ("r ADDR" / "w ADDR VALUE", one line each).
REG_HELPER = r'''
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>
static volatile uint32_t *page[16]; static uint32_t base[16]; static int n, fd;
static volatile uint32_t *at(uint32_t a) {
    uint32_t b = a & ~0xfffu;
    for (int i = 0; i < n; i++) if (base[i] == b) return page[i] + ((a & 0xfff) >> 2);
    void *m = mmap64(0, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, (off64_t)b);
    if (m == MAP_FAILED) return 0;
    int i = n < 16 ? n++ : 15;
    if (i == 15 && page[15]) munmap((void *)page[15], 4096);
    page[i] = m; base[i] = b;
    return page[i] + ((a & 0xfff) >> 2);
}
int main(void) {
    char line[128];
    fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) { perror("/dev/mem"); return 1; }
    setvbuf(stdout, 0, _IOLBF, 0);
    while (fgets(line, sizeof line, stdin)) {
        char *s = line, *e;
        while (*s == ' ' || *s == '\t') s++;
        char op = *s ? *s++ : 0;
        unsigned long a = strtoul(s, &e, 0);         /* unsigned, base 0: 123 or 0x43c00000 */
        int has_a = e != s;
        s = e;
        unsigned long v = strtoul(s, &e, 0);
        int has_v = e != s;
        if (op == 's' && has_a) { usleep(a); puts("ok"); continue; }    /* s MICROSECONDS: a sleep, for Lua */
        volatile uint32_t *p = (has_a && !(a & 3)) ? at((uint32_t)a) : 0;
        if (!p) { puts("error: bad address"); continue; }
        if (op == 'r') printf("%u\n", *p);
        else if (op == 'w' && has_v) { *p = (uint32_t)v; puts("ok"); }
        else puts("error: use r ADDR or w ADDR VALUE");
    }
    return 0;
}
'''

HEAD = '''#!/bin/bash
# Made by the Ardzy app at upload time ({name}). Your own run.sh in the project replaces it.
export ARDZY_LANG={lang}
need() {{ command -v "$1" >/dev/null || {{ echo "{name} is not installed on the board: in the Ardzy app open Settings, Languages, and install it."; exit 1; }}; }}
need {cmd}
'''

HELPER = '''# the register helper for the ardzy library (compiled once)
H=/var/lib/ardzy/regd-{tag}
if [ ! -x "$H" ]; then
  mkdir -p /var/lib/ardzy
  cat > "$H.c" <<'ARDZY_EOF'
{src}
ARDZY_EOF
  gcc -O2 -o "$H" "$H.c" || {{ echo "could not build the register helper"; exit 1; }}
fi
export ARDZY_REGD="$H"
'''

# newer(): rebuild only when a source file is newer than the program
NEWER = '''newer() { [ ! -x "$1" ] && return 0; shift; for f in "$@"; do [ "$f" -nt app ] && return 0; done; return 1; }
'''

RUN = {
    'cpp': NEWER + '''SRC=$(ls *.cpp *.c 2>/dev/null)
if newer app $SRC *.h *.hpp; then
  echo "compiling $(echo $SRC) (g++, C++17) ..."
  g++ -O2 -Wall -std=gnu++17 -o app $SRC -lm -lpthread || { echo "compile failed: see the errors above"; exit 1; }
fi
exec ./app
''',
    'asm': NEWER + '''SRC=$(ls *.S *.s *.c 2>/dev/null)
if newer app $SRC; then
  echo "assembling $(echo $SRC) (gcc) ..."
  gcc -O2 -Wall -o app $SRC || { echo "assembly failed: see the errors above"; exit 1; }
fi
exec ./app
''',
    'sh': 'exec bash main.sh\n',
    'perl': 'exec perl -I. main.pl\n',
    'lua': 'export LUA_PATH="./?.lua;;"\nexec lua5.4 main.lua\n',
    'js': 'export NODE_PATH=.\nexec node main.js\n',
    'go': NEWER + '''export HOME=/root GOCACHE=/var/cache/ardzy-go GOPATH=/var/lib/ardzy/go GOTOOLCHAIN=local GOFLAGS=-mod=mod GO111MODULE=off
if newer app *.go; then
  [ -d "$GOCACHE" ] || echo "the first Go build on this board compiles Go's own library too: one to three minutes, later builds take seconds"
  echo "compiling $(echo *.go) (go build) ..."
  go build -o app *.go || { echo "compile failed: see the errors above"; exit 1; }
fi
exec ./app
''',
    'rust': NEWER + '''if newer app *.rs; then
  echo "compiling main.rs (rustc -O; on this board that takes 20 to 60 seconds) ..."
  rustc -O --edition 2021 -o app main.rs || { echo "compile failed: see the errors above"; exit 1; }
fi
exec ./app
''',
}


def run_script(lang):
    """The run.sh for a project in one of the run.sh languages."""
    L = LANGS[lang]
    s = HEAD.format(name=L['name'], lang=lang, cmd=L['cmd'])
    if lang in ('perl', 'lua', 'js'):
        src = REG_HELPER.strip()
        s += HELPER.format(tag=hashlib.sha256(src.encode()).hexdigest()[:10], src=src)
    s += 'cd "$(dirname "$0")"\n' + RUN[lang]
    return s.replace('\r\n', '\n').encode()


# ---------------------------------------------------------------- Debian versions and dependencies
def _order(c):
    if c.isdigit():
        return 0
    if c.isalpha():
        return ord(c)
    if c == '~':
        return -1
    return ord(c) + 256 if c else 0


def _verrevcmp(a, b):
    i = j = 0
    while i < len(a) or j < len(b):
        while (i < len(a) and not a[i].isdigit()) or (j < len(b) and not b[j].isdigit()):
            ac = _order(a[i]) if i < len(a) else 0
            bc = _order(b[j]) if j < len(b) else 0
            if ac != bc:
                return ac - bc
            i, j = i + 1, j + 1
        while i < len(a) and a[i] == '0':
            i += 1
        while j < len(b) and b[j] == '0':
            j += 1
        first = 0
        while i < len(a) and j < len(b) and a[i].isdigit() and b[j].isdigit():
            if not first:
                first = ord(a[i]) - ord(b[j])
            i, j = i + 1, j + 1
        if i < len(a) and a[i].isdigit():
            return 1
        if j < len(b) and b[j].isdigit():
            return -1
        if first:
            return first
    return 0


def vercmp(a, b):
    """Compare two Debian versions like dpkg does (<0, 0, >0)."""
    def split(v):
        e, _, rest = v.partition(':') if ':' in v else ('0', '', v)
        up, _, rev = rest.rpartition('-') if '-' in rest else (rest, '', '')
        return int(e or 0), up, rev
    ea, ua, ra = split(a)
    eb, ub, rb = split(b)
    if ea != eb:
        return ea - eb
    return _verrevcmp(ua, ub) or _verrevcmp(ra, rb)


def satisfies(have, op, want):
    if not op:
        return True
    if have is None:
        return False
    c = vercmp(have, want)
    return {'<<': c < 0, '<=': c <= 0, '=': c == 0, '>=': c >= 0, '>>': c > 0, '<': c <= 0, '>': c >= 0}[op]


DEP_RE = re.compile(r'^\s*([a-z0-9][a-z0-9+.-]*)(?::[a-z0-9]+)?\s*(?:\(\s*(<<|<=|=|>=|>>|<|>)\s*([^)\s]+)\s*\))?\s*(?:\[[^]]*\])?\s*$')


def parse_deps(text):
    """'a (>= 1) | b, c' -> [[('a', '>=', '1'), ('b', None, None)], [('c', None, None)]]"""
    out = []
    for clause in (text or '').split(','):
        alts = []
        for alt in clause.split('|'):
            m = DEP_RE.match(alt)
            if m:
                alts.append(m.groups())
        if alts:
            out.append(alts)
    return out


def parse_stanzas(text):
    for block in text.split('\n\n'):
        d, key = {}, None
        for line in block.splitlines():
            if line[:1] in (' ', '\t'):
                if key:
                    d[key] += '\n' + line.strip()
            elif ':' in line:
                key, _, v = line.partition(':')
                d[key] = v.strip()
        if 'Package' in d:
            yield d


def board_packages():
    """Packages of the 0.2 image: {name: version}, {virtual: [(provider, version or None)]}."""
    have, prov = {}, {}
    for line in open(os.path.join(HERE, 'board_packages.txt'), encoding='utf-8'):
        if line.startswith('#') or not line.strip():
            continue
        name, ver, rest = (line.rstrip('\n').split(' ', 2) + [''])[:3]
        have[name] = ver
        for alts in parse_deps(rest):
            for n, op, v in alts:
                prov.setdefault(n, []).append((name, v if op == '=' else None))
    return have, prov


class Repo:
    """Debian's package lists for the board (trixie, armhf), read on this PC."""

    def __init__(self, cache_dir, log=print):
        self.cache, self.log = cache_dir, log
        os.makedirs(cache_dir, exist_ok=True)
        self.pkgs, self.prov = {}, {}

    def fetch(self, url, timeout=60):
        req = urllib.request.Request(url, headers={'User-Agent': 'Ardzy'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()

    def load(self):
        for mirror, suite in SUITES:
            rel = self.fetch('%s/dists/%s/InRelease' % (mirror, suite)).decode('utf-8', 'replace')
            want = None
            sha = rel.split('\nSHA256:', 1)[1] if '\nSHA256:' in rel else ''
            for line in sha.splitlines()[1:]:
                if not line.startswith(' '):
                    break
                h, size, path = line.split()
                if path == 'main/binary-%s/Packages.xz' % ARCH:
                    want = (h, int(size))
            if not want:
                raise RuntimeError('%s: no package list for %s' % (suite, ARCH))
            p = os.path.join(self.cache, '%s_%s_Packages.xz' % (suite, ARCH))
            data = open(p, 'rb').read() if os.path.exists(p) else b''
            if hashlib.sha256(data).hexdigest() != want[0]:
                self.log('  reading the Debian package list (%s, %.1f MB) ...' % (suite, want[1] / 2**20))
                data = self.fetch('%s/dists/%s/main/binary-%s/Packages.xz' % (mirror, suite, ARCH), timeout=300)
                if hashlib.sha256(data).hexdigest() != want[0]:
                    raise RuntimeError('%s: the package list is damaged (SHA256 does not match)' % suite)
                open(p, 'wb').write(data)
            for d in parse_stanzas(lzma.decompress(data).decode('utf-8', 'replace')):
                d['_mirror'] = mirror
                old = self.pkgs.get(d['Package'])
                if old is None or vercmp(d['Version'], old['Version']) > 0:
                    self.pkgs[d['Package']] = d
        for name, d in self.pkgs.items():
            for alts in parse_deps(d.get('Provides')):
                for n, op, v in alts:
                    self.prov.setdefault(n, []).append((name, v if op == '=' else None))
        return self

    def resolve(self, wanted, have, have_prov):
        """The packages to install for `wanted`: what the board lacks, with their dependencies."""
        chosen = {}

        def ok_now(n, op, v):
            if n in chosen and satisfies(chosen[n]['Version'], op, v):
                return True
            if n in have and satisfies(have[n], op, v):
                return True
            for pn, pv in have_prov.get(n, []) + [(p, pv) for p, pv in self.prov.get(n, []) if p in chosen]:
                if not op or (pv and satisfies(pv, op, v)):
                    return True
            return False

        def pick(n, op, v):
            d = self.pkgs.get(n)
            if d and satisfies(d['Version'], op, v):
                return d
            for pn, pv in self.prov.get(n, []):
                if pn in self.pkgs and (not op or (pv and satisfies(pv, op, v))):
                    return self.pkgs[pn]
            return None

        todo, done = [], set()
        for n in wanted:
            d = pick(n, None, None)
            if d is None:
                raise RuntimeError('package %s is not in Debian %s for %s' % (n, SUITES[0][1], ARCH))
            if have.get(d['Package']) != d['Version']:
                chosen[d['Package']] = d
                todo.append(d['Package'])
        while todo:
            d = chosen[todo.pop(0)]
            if d['Package'] in done:
                continue
            done.add(d['Package'])
            for alts in parse_deps(d.get('Pre-Depends')) + parse_deps(d.get('Depends')):
                if any(ok_now(*a) for a in alts):
                    continue
                for a in alts:
                    c = pick(*a)
                    if c is not None:
                        chosen[c['Package']] = c
                        todo.append(c['Package'])
                        break
                else:
                    raise RuntimeError('%s needs %s, which is not in Debian %s'
                                       % (d['Package'], ' | '.join(a[0] for a in alts), SUITES[0][1]))
        return sorted(chosen.values(), key=lambda d: d['Package'])

    def download(self, d):
        p = os.path.join(self.cache, os.path.basename(d['Filename']))
        if os.path.exists(p) and hashlib.sha256(open(p, 'rb').read()).hexdigest() == d['SHA256']:
            return p
        data = self.fetch('%s/%s' % (d['_mirror'], d['Filename']), timeout=600)
        if hashlib.sha256(data).hexdigest() != d['SHA256']:
            raise RuntimeError('%s: the download is damaged (SHA256 does not match Debian\'s list)' % d['Package'])
        open(p, 'wb').write(data)
        return p


def make_bundle(lang, debs, out_path, marker):
    """An Ardzy update bundle that only installs packages (the system version stays as it is)."""
    man = {'version': 'language %s' % LANGS[lang]['name'], 'date': time.strftime('%Y-%m-%d'),
           'notes': 'adds the %s language (%d Debian package%s)' % (LANGS[lang]['name'], len(debs), '' if len(debs) == 1 else 's'),
           'restart_web': False}
    sums = []
    with tarfile.open(out_path, 'w') as t:
        for p in debs:
            name = 'debs/' + os.path.basename(p)
            t.add(p, name)
            sums.append('%s  %s' % (hashlib.sha256(open(p, 'rb').read()).hexdigest(), name))
        # the marker the app reads back (GET /api/file?p=.lang-<id>&f=info.json): this language is installed
        mk = 'rootfs/opt/ardzy/projects/.lang-%s/info.json' % lang
        mdata = json.dumps(marker, indent=1).encode()
        sums.append('%s  %s' % (hashlib.sha256(mdata).hexdigest(), mk))
        for name, data in ((mk, mdata), ('manifest.json', json.dumps(man, indent=1).encode()),
                           ('sha256sums.txt', ('\n'.join(sums) + '\n').encode())):
            ti = tarfile.TarInfo(name)
            ti.size, ti.mtime = len(data), int(time.time())
            t.addfile(ti, io.BytesIO(data))
    return out_path
