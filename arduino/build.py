#!/usr/bin/env python3
"""Ardzy sketch builder (runs on the board): .ino + libraries -> a Linux program.

    build.py <project dir>        builds <project>/.build/sketch

Like the Arduino IDE: all .ino tabs are joined (the one named like the project first),
Arduino.h is included, function prototypes are added, and the libraries the sketch includes
are found and compiled (the project's own libraries/ folder first, then the ones installed
with Ardzy). The core and every library are compiled once and kept in /var/cache/ardzy, so
the next upload only compiles your sketch.
"""
import concurrent.futures, glob, hashlib, os, re, shutil, subprocess, sys, time

HOME = os.path.dirname(os.path.abspath(__file__))           # /usr/lib/ardzy/arduino
CORE = os.path.join(HOME, 'core')
SYSLIBS = os.path.join(HOME, 'libraries')
CACHE = '/var/cache/ardzy/arduino'
JOBS = 2

ARCH = ['-mcpu=cortex-a9', '-mfpu=neon-vfpv3', '-mfloat-abi=hard']
DEFS = ['-DARDUINO=10819', '-DARDUINO_ARDZY_S9', '-DARDUINO_ARCH_ARDZY', '-DHOST', '-D__ARDZY__']
CXXFLAGS = ['-O2', '-std=gnu++17', '-pthread', '-fno-exceptions'] + ARCH + DEFS
CFLAGS = ['-O2', '-std=gnu11', '-pthread'] + ARCH + DEFS
SRC_EXT = ('.c', '.cpp', '.cc', '.cxx', '.S')
SKIP_CORE = ('PluggableUSB.cpp', 'CanMsg.cpp', 'CanMsgRingbuffer.cpp')


def log(msg):
    print(msg, flush=True)


def sha(*parts):
    h = hashlib.sha1()
    for p in parts:
        h.update(p if isinstance(p, bytes) else str(p).encode())
    return h.hexdigest()[:16]


def files_hash(paths):
    h = hashlib.sha1()
    for p in sorted(paths):
        h.update(p.encode())
        with open(p, 'rb') as f:
            h.update(f.read())
    return h.hexdigest()[:16]


# ------------------------------------------------------------------ the sketch
_COMMENT = re.compile(r'//[^\n]*|/\*.*?\*/', re.S)
_STRING = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
_FUNC = re.compile(r'^[ \t]*((?:[A-Za-z_][\w:<>,\*&]*[ \t\*&]+)+)([A-Za-z_]\w*)[ \t]*\(([^()]*)\)[ \t]*(?:const[ \t]*)?\{',
                   re.M)
_NOT_TYPES = {'if', 'for', 'while', 'switch', 'return', 'else', 'do', 'case', 'new', 'delete', 'sizeof'}


def blank(text):
    """Comments and strings replaced by spaces (same length), so positions stay right."""
    text = _COMMENT.sub(lambda m: re.sub(r'[^\n]', ' ', m.group(0)), text)
    return _STRING.sub(lambda m: ' ' * len(m.group(0)), text)


def prototypes(code):
    """[(position of the first function, list of prototypes)] for top-level functions."""
    clean = blank(code)
    depth, top = 0, []
    level = []
    for ch in clean:                         # brace depth at every position
        level.append(depth)
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
    protos, first = [], None
    for m in _FUNC.finditer(clean):
        if level[m.start()] != 0:
            continue
        ret, name, params = m.group(1).strip(), m.group(2), m.group(3).strip()
        if name in _NOT_TYPES or ret.split()[-1] in _NOT_TYPES or '=' in params or ret.startswith(('class', 'struct')):
            continue
        line_start = clean.rfind('\n', 0, m.start()) + 1
        if first is None:
            first = line_start
        real = code[m.start():m.end() - 1].strip()        # the original text of the signature
        protos.append(re.sub(r'\s+', ' ', real) + ';')
    return first, protos


def make_sketch(proj, build):
    """Join the .ino tabs into sketch.ino.cpp. Returns the path (or None if no .ino)."""
    inos = sorted(glob.glob(os.path.join(proj, '*.ino')))
    if not inos:
        return None
    main = os.path.join(proj, os.path.basename(os.path.normpath(proj)) + '.ino')
    if main in inos:
        inos.remove(main)
        inos.insert(0, main)
    parts = []
    for f in inos:
        parts.append('#line 1 "%s"\n' % os.path.basename(f) + open(f, encoding='utf-8', errors='replace').read() + '\n')
    code = ''.join(parts)
    first, protos = prototypes(code)
    if protos and first is not None:
        line = code.count('\n', 0, first) + 1
        # the #line needed after our insertion: find which tab the position is in
        tab, tab_line = inos[0], line
        for m in re.finditer(r'#line 1 "([^"]+)"\n', code[:first]):
            tab = m.group(1)
            tab_line = code.count('\n', m.end(), first) + 1
        code = code[:first] + '\n'.join(protos) + '\n#line %d "%s"\n' % (tab_line, os.path.basename(tab)) + code[first:]
    out = os.path.join(build, 'sketch.ino.cpp')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('#include <Arduino.h>\n' + code)
    return out


# ------------------------------------------------------------------ libraries
class Library:
    def __init__(self, root):
        self.root = root
        self.name = os.path.basename(root)
        src = os.path.join(root, 'src')
        if os.path.isdir(src):                     # 1.5 format: everything under src/
            self.inc = [src]
            self.sources = [p for p in glob.glob(os.path.join(src, '**', '*'), recursive=True) if p.endswith(SRC_EXT)]
        else:                                      # old format: root + utility/
            self.inc = [root] + ([os.path.join(root, 'utility')] if os.path.isdir(os.path.join(root, 'utility')) else [])
            self.sources = [p for d in self.inc for p in glob.glob(os.path.join(d, '*')) if p.endswith(SRC_EXT)]
        self.headers = set()
        for d in self.inc:
            for h in glob.glob(os.path.join(d, '*.h')) + glob.glob(os.path.join(d, '*.hpp')):
                self.headers.add(os.path.basename(h))

    def all_files(self):
        out = []
        for d in self.inc:
            out += [p for p in glob.glob(os.path.join(d, '**', '*'), recursive=True) if os.path.isfile(p)]
        return sorted(set(out))


def find_libraries(dirs):
    libs = []
    for base in dirs:
        if os.path.isdir(base):
            for d in sorted(os.listdir(base)):
                if os.path.isdir(os.path.join(base, d)):
                    libs.append(Library(os.path.join(base, d)))
    return libs


_INCLUDE = re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', re.M)


def includes_of(paths):
    out = set()
    for p in paths:
        try:
            out |= {os.path.basename(i) for i in _INCLUDE.findall(open(p, encoding='utf-8', errors='replace').read())}
        except OSError:
            pass
    return out


def resolve(start_files, libs):
    """The libraries needed by the sketch, following includes inside the libraries too."""
    chosen, todo = [], includes_of(start_files)
    seen = set()
    while todo:
        h = todo.pop()
        if h in seen:
            continue
        seen.add(h)
        for lib in libs:                           # project libraries come first in the list
            if h in lib.headers:
                if lib not in chosen and lib.name not in [c.name for c in chosen]:
                    chosen.append(lib)
                    todo |= includes_of(lib.sources + [os.path.join(d, x) for d in lib.inc for x in lib.headers])
                break
    return chosen


# ------------------------------------------------------------------ compiling
def compile_one(src, obj, incs):
    os.makedirs(os.path.dirname(obj), exist_ok=True)
    if src.endswith('.c'):
        cmd = ['gcc'] + CFLAGS
    else:
        cmd = ['g++'] + CXXFLAGS
    cmd += ['-I' + d for d in incs] + ['-idirafter', os.path.join(CORE, 'api', 'deprecated'), '-c', src, '-o', obj]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return src, r.returncode, (r.stdout + r.stderr).strip()


def compile_many(jobs, label):
    """jobs: [(src, obj, incs)]. Prints errors; returns True when all compiled."""
    ok = True
    with concurrent.futures.ThreadPoolExecutor(JOBS) as ex:
        for src, rc, out in ex.map(lambda j: compile_one(*j), jobs):
            if out:
                log(out)
            if rc:
                ok = False
    if not ok:
        log('compile FAILED (%s)' % label)
    return ok


def archive(objs, lib):
    if os.path.exists(lib):
        os.remove(lib)
    subprocess.run(['ar', 'rcs', lib] + objs, check=True)


def build_core():
    srcs = [p for p in glob.glob(os.path.join(CORE, '*.cpp')) + glob.glob(os.path.join(CORE, 'api', '*.cpp'))
            if os.path.basename(p) not in SKIP_CORE]
    key = files_hash([p for p in glob.glob(os.path.join(CORE, '**', '*'), recursive=True) if os.path.isfile(p)]) + sha(CXXFLAGS)
    d = os.path.join(CACHE, 'core-' + key[:16])
    lib = os.path.join(d, 'core.a')
    if os.path.exists(lib):
        return lib
    log('compiling the Arduino core (first time only) ...')
    shutil.rmtree(d, ignore_errors=True)
    jobs = [(s, os.path.join(d, os.path.basename(s) + '.o'), [CORE]) for s in srcs]
    if not compile_many(jobs, 'core'):
        sys.exit(1)
    archive([j[1] for j in jobs], lib)
    return lib


def build_library(lib, incs, core_key):
    if not lib.sources:
        return None
    key = files_hash(lib.all_files()) + sha(CXXFLAGS, incs, core_key)
    d = os.path.join(CACHE, 'lib-%s-%s' % (re.sub(r'[^\w.-]', '_', lib.name), key[:16]))
    a = os.path.join(d, 'lib.a')
    if os.path.exists(a):
        return a
    log('compiling library %s (kept for next time) ...' % lib.name)
    shutil.rmtree(d, ignore_errors=True)
    jobs = [(s, os.path.join(d, re.sub(r'[^\w.-]', '_', os.path.relpath(s, lib.root)) + '.o'), incs) for s in lib.sources]
    if not compile_many(jobs, 'library ' + lib.name):
        sys.exit(1)
    archive([j[1] for j in jobs], a)
    return a


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    t0 = time.time()
    proj = os.path.abspath(sys.argv[1])
    build = os.path.join(proj, '.build')
    shutil.rmtree(build, ignore_errors=True)
    os.makedirs(build)
    os.makedirs(CACHE, exist_ok=True)
    sketch = make_sketch(proj, build)
    own = [p for p in glob.glob(os.path.join(proj, '*')) if p.endswith(SRC_EXT)]
    if not sketch and not own:
        log('no sketch (.ino) in the project')
        sys.exit(1)
    sources = ([sketch] if sketch else []) + own
    libs = find_libraries([os.path.join(proj, 'libraries'), SYSLIBS])
    used = resolve(sources + glob.glob(os.path.join(proj, '*.h')), libs)
    incs = [CORE, proj] + [d for l in used for d in l.inc]
    log('sketch: %s%s' % (', '.join(os.path.basename(s) for s in ([sketch] if sketch else []) + own),
                          ('  libraries: ' + ', '.join(l.name for l in used)) if used else ''))
    core = build_core()
    core_key = os.path.basename(os.path.dirname(core))
    archives = [a for a in (build_library(l, incs, core_key) for l in used) if a]
    jobs = [(s, os.path.join(build, os.path.basename(s) + '.o'), incs) for s in sources]
    if not compile_many(jobs, 'sketch'):
        sys.exit(1)
    exe = os.path.join(build, 'sketch')
    cmd = ['g++'] + ARCH + ['-pthread', '-o', exe] + [j[1] for j in jobs] + \
          ['-Wl,--start-group'] + archives + [core, '-Wl,--end-group', '-lm']
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        log((r.stdout + r.stderr).strip())
        log('link FAILED')
        sys.exit(1)
    log('built %s (%d KB) in %.1f s' % (os.path.relpath(exe, proj), os.path.getsize(exe) // 1024, time.time() - t0))


if __name__ == '__main__':
    main()
