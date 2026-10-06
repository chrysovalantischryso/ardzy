"""Arduino sketches in the Ardzy app: Library Manager, examples, and packing a sketch for the board.

Libraries live in <workspace>/libraries (like the Arduino IDE's sketchbook/libraries). The
board compiles; the app sends the sketch together with exactly the libraries it includes.
Wire, SPI, EEPROM and Servo are built into Ardzy (made for this board) and always win over a
downloaded library of the same name.
"""
import gzip, hashlib, io, json, os, re, shutil, tempfile, time, urllib.request, zipfile

INDEX_URL = 'https://downloads.arduino.cc/libraries/library_index.json.gz'
BUILTIN = {'Wire', 'SPI', 'EEPROM', 'Servo'}
BUILTIN_HEADERS = {'Wire.h', 'SPI.h', 'EEPROM.h', 'Servo.h', 'Arduino.h', 'WProgram.h'}
SRC_EXT = ('.c', '.cpp', '.cc', '.cxx', '.S', '.h', '.hpp', '.hh', '.inc', '.tpp', '.ipp')
SKETCH_EXT = ('.ino', '.h', '.hpp', '.cpp', '.c', '.S')
NAME_RE = re.compile(r'^[A-Za-z0-9_.+-]+$')       # file names in libraries (TinyGPS++.h)
_INCLUDE = re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', re.M)
UA = {'User-Agent': 'Ardzy/1.0'}


def safe_folder(name):
    return re.sub(r'[^A-Za-z0-9_.-]', '_', name).strip('._') or 'library'


def read_properties(path):
    out = {}
    try:
        for line in open(path, encoding='utf-8', errors='replace'):
            if '=' in line and not line.lstrip().startswith('#'):
                k, v = line.split('=', 1)
                out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


class Library:
    def __init__(self, root):
        self.root = root
        self.folder = os.path.basename(root)
        props = read_properties(os.path.join(root, 'library.properties'))
        self.name = props.get('name', self.folder)
        self.version = props.get('version', '')
        self.sentence = props.get('sentence', '')
        self.author = props.get('author', '')
        self.architectures = props.get('architectures', '*')
        src = os.path.join(root, 'src')
        self.dirs = [src] if os.path.isdir(src) else [root] + (
            [os.path.join(root, 'utility')] if os.path.isdir(os.path.join(root, 'utility')) else [])
        self.headers = set()
        for d in self.dirs:
            for f in os.listdir(d):
                if f.endswith(('.h', '.hpp')):
                    self.headers.add(f)

    def sources(self):
        out = []
        for d in self.dirs:
            if d.endswith('src'):
                for root, _, files in os.walk(d):
                    out += [os.path.join(root, f) for f in files if f.endswith(SRC_EXT)]
            else:
                out += [os.path.join(d, f) for f in os.listdir(d) if f.endswith(SRC_EXT)]
        return out

    def info(self):
        return {'name': self.name, 'folder': self.folder, 'version': self.version, 'sentence': self.sentence,
                'author': self.author, 'architectures': self.architectures, 'headers': sorted(self.headers),
                'examples': len(examples_in(os.path.join(self.root, 'examples')))}


def includes_of(paths):
    out = set()
    for p in paths:
        try:
            out |= {os.path.basename(i) for i in _INCLUDE.findall(open(p, encoding='utf-8', errors='replace').read())}
        except OSError:
            pass
    return out


def examples_in(base):
    """[(relative name, folder)] of every folder with an .ino of the same name."""
    out = []
    if not os.path.isdir(base):
        return out
    for root, dirs, files in os.walk(base):
        dirs.sort()
        name = os.path.basename(root)
        if name + '.ino' in files:
            out.append((os.path.relpath(root, base).replace('\\', '/'), root))
    return out


class Arduino:
    def __init__(self, workspace, cache_dir, builtin_examples, log):
        self.ws = workspace
        self.cache = cache_dir
        self.builtin_examples = builtin_examples
        self.log = log
        self._index = None

    # ---------------------------------------------------------------- installed libraries
    @property
    def libdir(self):
        d = os.path.join(self.ws(), 'libraries')
        os.makedirs(d, exist_ok=True)
        return d

    def installed(self):
        out = []
        for f in sorted(os.listdir(self.libdir)):
            p = os.path.join(self.libdir, f)
            if os.path.isdir(p) and not f.startswith('.'):
                out.append(Library(p))
        return out

    def remove(self, name):
        for lib in self.installed():
            if lib.name == name or lib.folder == name:
                shutil.rmtree(lib.root)
                self.log('Library %s removed' % lib.name, 'ok')
                return True
        raise ValueError('library %s is not installed' % name)

    # ---------------------------------------------------------------- the Arduino library index
    def index(self, refresh=False):
        path = os.path.join(self.cache, 'library_index_compact.json')
        if self._index is not None and not refresh:
            return self._index
        if not refresh and os.path.isfile(path) and time.time() - os.path.getmtime(path) < 7 * 86400:
            self._index = json.load(open(path, encoding='utf-8'))
            return self._index
        self.log('Downloading the Arduino library list (5 MB) ...')
        req = urllib.request.Request(INDEX_URL, headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = json.loads(gzip.decompress(r.read()))
        latest = {}
        for e in raw.get('libraries', []):
            n = e.get('name')
            if not n:
                continue
            cur = latest.get(n)
            if cur is None or _vkey(e.get('version', '0')) > _vkey(cur['version']):
                latest[n] = {'name': n, 'version': e.get('version', ''), 'author': e.get('author', ''),
                             'sentence': e.get('sentence', ''), 'paragraph': (e.get('paragraph') or '')[:300],
                             'category': e.get('category', ''), 'url': e.get('url', ''), 'size': e.get('size', 0),
                             'checksum': e.get('checksum', ''), 'architectures': e.get('architectures', []),
                             'website': e.get('website', ''), 'types': e.get('types', []),
                             'dependencies': [d.get('name') for d in e.get('dependencies', []) if d.get('name')],
                             'versions': []}
            latest[n]['versions'] = (latest[n].get('versions') or []) + [e.get('version', '')]
        self._index = sorted(latest.values(), key=lambda x: x['name'].lower())
        os.makedirs(self.cache, exist_ok=True)
        json.dump(self._index, open(path, 'w', encoding='utf-8'))
        self.log('Library list: %d libraries' % len(self._index), 'ok')
        return self._index

    def search(self, q, limit=80):
        q = (q or '').lower().strip()
        have = {l.name: l.version for l in self.installed()}
        res = []
        for e in self.index():
            hay = (e['name'] + ' ' + e['sentence'] + ' ' + e['author'] + ' ' + e['category']).lower()
            if not q or all(w in hay for w in q.split()):
                score = 0 if e['name'].lower() == q else 1 if e['name'].lower().startswith(q) else 2 if q in e['name'].lower() else 3
                res.append((score, e))
        res.sort(key=lambda t: (t[0], t[1]['name'].lower()))
        out = []
        for _, e in res[:limit]:
            d = dict(e)
            d.pop('versions', None)
            d['installed'] = have.get(e['name'], '')
            d['builtin'] = e['name'] in BUILTIN
            out.append(d)
        return {'count': len(res), 'results': out}

    def install(self, name, _seen=None):
        """Download a library (and the libraries it depends on) into <workspace>/libraries."""
        _seen = _seen if _seen is not None else set()
        if name in _seen:
            return True
        _seen.add(name)
        if name in BUILTIN:
            self.log('%s is built into Ardzy (made for this board): nothing to install' % name, 'ok')
            return True
        e = next((x for x in self.index() if x['name'] == name), None)
        if not e:
            raise ValueError('library %s is not in the Arduino library list' % name)
        self.log('Installing %s %s (%d KB) ...' % (name, e['version'], (e['size'] or 0) // 1024), 'head')
        req = urllib.request.Request(e['url'], headers=UA)
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        algo, _, want = (e.get('checksum') or '').partition(':')
        if algo.upper() == 'SHA-256' and hashlib.sha256(data).hexdigest() != want.lower():
            raise ValueError('download of %s is damaged (checksum differs)' % name)
        self._unpack(data, name)
        for dep in e.get('dependencies', []):
            if dep not in {l.name for l in self.installed()}:
                self.install(dep, _seen)
        return True

    def install_zip(self, path):
        data = open(path, 'rb').read()
        return self._unpack(data, None)

    def _unpack(self, data, name):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = [n for n in z.namelist() if not n.endswith('/')]
            tops = {n.split('/')[0] for n in names}
            strip = len(tops) == 1 and any('/' in n for n in names)
            tmp = tempfile.mkdtemp(prefix='ardzy_lib_')
            for m in z.infolist():
                if m.is_dir():
                    continue
                parts = m.filename.replace('\\', '/').split('/')
                if strip:
                    parts = parts[1:]
                if not parts or any(p in ('', '.', '..') for p in parts):
                    continue
                dst = os.path.join(tmp, *parts)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with z.open(m) as src, open(dst, 'wb') as out:
                    shutil.copyfileobj(src, out)
        props = read_properties(os.path.join(tmp, 'library.properties'))
        lib_name = name or props.get('name') or os.path.splitext(os.path.basename(tops.pop() if tops else 'library'))[0]
        dest = os.path.join(self.libdir, safe_folder(lib_name))
        shutil.rmtree(dest, ignore_errors=True)
        shutil.move(tmp, dest)
        self.log('Library %s %s installed in %s' % (lib_name, props.get('version', ''), dest), 'ok')
        return lib_name

    # ---------------------------------------------------------------- sketches
    @staticmethod
    def is_sketch(d):
        return any(f.endswith('.ino') for f in os.listdir(d))

    def resolve(self, d):
        """The installed libraries the sketch needs (following includes inside libraries)."""
        libs = [l for l in self.installed() if l.name not in BUILTIN and l.folder not in BUILTIN]
        start = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(SKETCH_EXT)]
        todo, seen, chosen, missing = set(includes_of(start)), set(), [], []
        while todo:
            h = todo.pop()
            if h in seen:
                continue
            seen.add(h)
            if h in BUILTIN_HEADERS:
                continue
            lib = next((l for l in libs if h in l.headers), None)
            if lib:
                if lib not in chosen:
                    chosen.append(lib)
                    todo |= includes_of(lib.sources())
            elif not os.path.exists(os.path.join(d, h)):
                missing.append(h)
        return chosen, missing

    def pack(self, d):
        """A zip with the sketch and the libraries it uses (for the board's builder)."""
        chosen, missing = self.resolve(d)
        buf = io.BytesIO()
        n = 0
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            for f in sorted(os.listdir(d)):
                p = os.path.join(d, f)
                if os.path.isfile(p) and f.endswith(SKETCH_EXT + ('.txt', '.json')) and NAME_RE.match(f):
                    z.write(p, f)
                    n += 1
            for lib in chosen:
                for root, dirs, files in os.walk(lib.root):
                    rel_root = os.path.relpath(root, lib.root)
                    top = rel_root.split(os.sep)[0]
                    if top in ('examples', 'extras', 'docs', 'test', 'tests', '.git', '.github'):
                        dirs[:] = []
                        continue
                    for f in files:
                        rel = os.path.normpath(os.path.join(rel_root, f)).replace('\\', '/')
                        parts = rel.split('/')
                        if not all(NAME_RE.match(x) for x in parts):
                            continue
                        if not (f.endswith(SRC_EXT) or f == 'library.properties'):
                            continue
                        z.write(os.path.join(root, f), 'libraries/%s/%s' % (lib.folder, rel))
                        n += 1
        return buf.getvalue(), chosen, missing, n

    # ---------------------------------------------------------------- examples
    def examples(self):
        out = [{'group': 'Ardzy', 'name': name, 'path': path} for name, path in examples_in(self.builtin_examples)]
        for lib in self.installed():
            out += [{'group': lib.name, 'name': name, 'path': path}
                    for name, path in examples_in(os.path.join(lib.root, 'examples'))]
        return out

    def new_from_example(self, example_path, project_dir):
        if os.path.exists(project_dir):
            raise ValueError('a project with that name already exists')
        shutil.copytree(example_path, project_dir)
        old = os.path.basename(os.path.normpath(example_path))
        new = os.path.basename(os.path.normpath(project_dir))
        src = os.path.join(project_dir, old + '.ino')
        if os.path.exists(src) and old != new:
            os.rename(src, os.path.join(project_dir, new + '.ino'))
        return project_dir


def _vkey(v):
    parts = []
    for p in re.split(r'[.\-+]', v or '0'):
        parts.append((0, int(p)) if p.isdigit() else (-1, p))
    return parts
