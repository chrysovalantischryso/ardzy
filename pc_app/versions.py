"""Ardzy - versions of a project (like a small git, nothing to install).

Every version is a list of the project's files with the sha256 of their bytes. The bytes
themselves are kept once per content in <workspace>/_versions/<project>/objects/, so a
hundred versions of a project where only main.py changes take little space.

  <workspace>/_versions/<project>/
      versions.json        [{id, time, message, auto, files: {relpath: sha}}...] oldest first
      objects/ab/abcdef... the file contents (zlib)

Build outputs are not part of a version (Vivado runs, caches, the .build folder): they
are made again from the sources. A .bit is kept (it can take long to make).
"""
import difflib, hashlib, json, os, shutil, time, zlib

SKIP_DIRS = ('.build', '__pycache__', '.git', '.ardzy_sim')
SKIP_DIR_ENDS = ('.runs', '.cache', '.hw', '.sim', '.ip_user_files', '.gen', '.srcs_bak')
SKIP_FILES = ('.ardzy_build.json',)
MAX_FILE = 32 * 1024 * 1024          # bigger files are left out of a version
KEEP_AUTO = 40                       # automatic versions (before an upload, before a restore) kept per project
TEXT_EXT = ('.py', '.c', '.h', '.v', '.sv', '.vhd', '.xdc', '.tcl', '.sh', '.txt', '.json', '.md', '.dtsi', '.dts',
            '.csv', '.ino', '.cpp', '.hpp', '.s', '.S', '.pl', '.pm', '.lua', '.js', '.mjs', '.go', '.rs', '.html', '.css')


def is_text(name):
    return name.endswith(TEXT_EXT) or os.path.basename(name) in ('Makefile', 'run.sh')


class Store:
    def __init__(self, workspace, project, project_dir):
        self.dir = os.path.join(workspace, '_versions', project)
        self.project, self.src = project, project_dir

    # ---------------------------------------------------------------- the store
    def _index_path(self):
        return os.path.join(self.dir, 'versions.json')

    def load(self):
        try:
            with open(self._index_path(), encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def _save(self, vs):
        os.makedirs(self.dir, exist_ok=True)
        tmp = self._index_path() + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(vs, f, indent=1)
        os.replace(tmp, self._index_path())

    def _obj(self, sha):
        return os.path.join(self.dir, 'objects', sha[:2], sha)

    def _put(self, data):
        sha = hashlib.sha256(data).hexdigest()
        p = self._obj(sha)
        if not os.path.exists(p):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p + '.tmp', 'wb') as f:
                f.write(zlib.compress(data, 6))
            os.replace(p + '.tmp', p)
        return sha

    def blob(self, sha):
        with open(self._obj(sha), 'rb') as f:
            return zlib.decompress(f.read())

    # ---------------------------------------------------------------- the project folder now
    def scan(self):
        """{relpath: absolute path} of the files that belong in a version."""
        out = {}
        for root, dirs, files in os.walk(self.src):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.endswith(SKIP_DIR_ENDS))
            for f in sorted(files):
                p = os.path.join(root, f)
                if f in SKIP_FILES or f.endswith(('.pyc', '.tmp', '.vcd')):
                    continue
                try:
                    if os.path.getsize(p) > MAX_FILE:
                        continue
                except OSError:
                    continue
                out[os.path.relpath(p, self.src).replace('\\', '/')] = p
        return out

    def current(self):
        """{relpath: sha} of the folder now (hashes only, nothing stored)."""
        cur = {}
        for rel, p in self.scan().items():
            with open(p, 'rb') as f:
                cur[rel] = hashlib.sha256(f.read()).hexdigest()
        return cur

    # ---------------------------------------------------------------- actions
    def save(self, message='', auto=False):
        """A new version of the folder as it is now. Returns it, or None when nothing changed
        since the newest version."""
        vs = self.load()
        files = {}
        for rel, p in self.scan().items():
            with open(p, 'rb') as f:
                files[rel] = self._put(f.read())
        if vs and vs[-1]['files'] == files:
            return None
        v = {'id': (vs[-1]['id'] + 1) if vs else 1, 'time': time.strftime('%Y-%m-%d %H:%M:%S'),
             'message': (message or '').strip()[:200], 'auto': bool(auto), 'files': files}
        vs.append(v)
        if auto:                                          # only the newest automatic ones stay
            autos = [x for x in vs if x.get('auto')]
            drop = {x['id'] for x in autos[:-KEEP_AUTO]}
            if drop:
                vs = [x for x in vs if x['id'] not in drop]
                self._gc(vs)
        self._save(vs)
        return v

    def get(self, vid):
        for v in self.load():
            if v['id'] == int(vid):
                return v
        raise ValueError('no version %s of %s' % (vid, self.project))

    def listing(self):
        """Newest first, with what changed against the version before."""
        vs, out, prev = self.load(), [], {}
        for v in vs:
            f = v['files']
            out.append({'id': v['id'], 'time': v['time'], 'message': v['message'], 'auto': v.get('auto', False),
                        'pinned': v.get('pinned', False), 'files': len(f),
                        'added': sorted(set(f) - set(prev)), 'removed': sorted(set(prev) - set(f)),
                        'changed': sorted(k for k in f if k in prev and prev[k] != f[k])})
            prev = f
        out.reverse()
        cur = self.current()
        last = vs[-1]['files'] if vs else {}
        changes = {'added': sorted(set(cur) - set(last)), 'removed': sorted(set(last) - set(cur)),
                   'changed': sorted(k for k in cur if k in last and last[k] != cur[k])}
        same = next((v['id'] for v in reversed(vs) if v['files'] == cur), None)
        return {'versions': out, 'now': changes, 'clean': bool(vs) and cur == last, 'same_as': same, 'size': self.size()}

    def diff(self, vid, other=None, context=3):
        """What is different between version vid and `other` (a version id, or None = the folder now).
        Text files: unified diff lines; other files: only that they differ."""
        a = self.get(vid)['files']
        if other in (None, '', 'now'):
            cur = self.scan()
            b_sha = self.current()
            read_b = lambda rel: open(cur[rel], 'rb').read()
            b_label = 'now'
        else:
            b_sha = self.get(other)['files']
            read_b = lambda rel: self.blob(b_sha[rel])
            b_label = 'v%s' % other
        files = []
        for rel in sorted(set(a) | set(b_sha)):
            sa, sb = a.get(rel), b_sha.get(rel)
            if sa == sb:
                continue
            item = {'file': rel, 'state': 'added' if sa is None else 'removed' if sb is None else 'changed'}
            if is_text(rel):
                ta = self.blob(sa).decode('utf-8', 'replace').splitlines() if sa else []
                tb = read_b(rel).decode('utf-8', 'replace').splitlines() if sb else []
                lines = list(difflib.unified_diff(ta, tb, 'v%s/%s' % (vid, rel), '%s/%s' % (b_label, rel),
                                                  n=context, lineterm=''))
                item['plus'] = sum(1 for l in lines if l.startswith('+') and not l.startswith('+++'))
                item['minus'] = sum(1 for l in lines if l.startswith('-') and not l.startswith('---'))
                item['lines'] = lines[2:4000]
            files.append(item)
        return {'a': 'v%s' % vid, 'b': b_label, 'files': files}

    def file_text(self, vid, rel):
        sha = self.get(vid)['files'].get(rel)
        if not sha:
            raise ValueError('%s is not in version %s' % (rel, vid))
        if not is_text(rel):
            raise ValueError('%s is not a text file' % rel)
        return self.blob(sha).decode('utf-8', 'replace')

    def restore(self, vid, only=None):
        """Put the project back as it was in version vid (or only the file `only`).
        The folder as it is now is saved first as an automatic version, so a restore can be undone."""
        v = self.get(vid)
        before = self.save('before going back to v%s' % vid, auto=True)
        if only:
            if only not in v['files']:
                raise ValueError('%s is not in version %s' % (only, vid))
            self._write(only, v['files'][only])
            return {'restored': [only], 'saved_before': before and before['id']}
        cur = self.scan()
        for rel in cur:                                     # files that version did not have go away ...
            if rel not in v['files']:
                os.remove(cur[rel])
        for rel, sha in v['files'].items():                 # ... and its files come back
            self._write(rel, sha)
        self._prune_empty_dirs()
        return {'restored': sorted(v['files']), 'saved_before': before and before['id']}

    def _write(self, rel, sha):
        p = os.path.join(self.src, *rel.split('/'))
        if os.path.isfile(p):
            with open(p, 'rb') as f:
                if hashlib.sha256(f.read()).hexdigest() == sha:
                    return
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p + '.ardzy_tmp', 'wb') as f:
            f.write(self.blob(sha))
        os.replace(p + '.ardzy_tmp', p)

    def _prune_empty_dirs(self):
        for root, dirs, files in os.walk(self.src, topdown=False):
            if root != self.src and not dirs and not files and not os.path.basename(root).endswith(SKIP_DIR_ENDS):
                try:
                    os.rmdir(root)
                except OSError:
                    pass

    def edit(self, vid, message=None, pinned=None):
        vs = self.load()
        for v in vs:
            if v['id'] == int(vid):
                if message is not None:
                    v['message'] = str(message).strip()[:200]
                if pinned is not None:
                    v['pinned'] = bool(pinned)
                    if v['pinned']:
                        v['auto'] = False                   # a pinned version is never dropped
                self._save(vs)
                return v
        raise ValueError('no version %s' % vid)

    def delete(self, vid):
        vs = [v for v in self.load() if v['id'] != int(vid)]
        self._save(vs)
        self._gc(vs)

    def _gc(self, vs):
        """Remove stored contents no version uses any more."""
        used = {sha for v in vs for sha in v['files'].values()}
        od = os.path.join(self.dir, 'objects')
        if not os.path.isdir(od):
            return
        for sub in os.listdir(od):
            for sha in os.listdir(os.path.join(od, sub)):
                if sha not in used:
                    try:
                        os.remove(os.path.join(od, sub, sha))
                    except OSError:
                        pass

    def size(self):
        n = 0
        for root, _d, files in os.walk(os.path.join(self.dir, 'objects')):
            for f in files:
                n += os.path.getsize(os.path.join(root, f))
        return n


def rename(workspace, old, new):
    """A renamed project keeps its versions."""
    a, b = os.path.join(workspace, '_versions', old), os.path.join(workspace, '_versions', new)
    if os.path.isdir(a) and not os.path.exists(b):
        shutil.move(a, b)
