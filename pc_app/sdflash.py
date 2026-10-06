"""Ardzy SD card writer (Windows): puts an Ardzy image (.img or .img.xz) on a microSD card, checks
it, and writes the board's settings file (ardzy.txt) onto the card's boot partition.

Safety rules (a wrong disk would lose its data):
  * only removable disks are offered: bus USB / SD / MMC, 1 to 256 GB, never the boot or system disk
  * the writer runs as administrator in its own process and checks the disk AGAIN (number, size,
    name, bus, not system/boot) right before it writes; any difference stops it
  * the app asks the user to confirm with the card's name and size first

    sdflash.list_disks()                 -> removable disks
    sdflash.start(job) (from the app)    -> runs "<this program> --flash job.json" elevated
    python sdflash.py --flash job.json   -> the elevated writer (progress goes to job['progress'])
"""
import hashlib, json, lzma, os, subprocess, sys, time

MIN_SIZE, MAX_SIZE = 1 << 30, 256 << 30
CHUNK = 4 << 20
OK_BUS = ('USB', 'SD', 'MMC')


def ps(cmd, timeout=60):
    r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', cmd], capture_output=True, text=True,
                       timeout=timeout, creationflags=0x08000000)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[:400])
    return r.stdout


def _json_list(text):
    text = text.strip()
    if not text:
        return []
    v = json.loads(text)
    return v if isinstance(v, list) else [v]


def list_disks():
    """Removable disks that may be written. Each: number, name, bus, size, letters, serial."""
    disks = _json_list(ps('Get-Disk | Select-Object Number,FriendlyName,SerialNumber,BusType,Size,IsBoot,IsSystem,'
                          'IsOffline,PartitionStyle | ConvertTo-Json -Compress'))
    parts = _json_list(ps('Get-Partition | Select-Object DiskNumber,PartitionNumber,DriveLetter,Size | ConvertTo-Json -Compress'))
    out = []
    for d in disks:
        bus = str(d.get('BusType', ''))
        bus = {7: 'USB', 12: 'SD', 13: 'MMC', 11: 'SATA', 17: 'NVMe', 8: 'RAID'}.get(d.get('BusType'), bus) \
            if isinstance(d.get('BusType'), int) else bus
        size = int(d.get('Size') or 0)
        letters = [str(p['DriveLetter']) + ':' for p in parts if p.get('DiskNumber') == d['Number']
                   and p.get('DriveLetter') and str(p['DriveLetter']).strip('\x00')]
        ok = bus in OK_BUS and not d.get('IsBoot') and not d.get('IsSystem') and MIN_SIZE <= size <= MAX_SIZE
        why = '' if ok else ('system or boot disk' if d.get('IsBoot') or d.get('IsSystem') else
                             'not a removable USB/SD disk (%s)' % bus if bus not in OK_BUS else 'size outside 1..256 GB')
        out.append({'number': d['Number'], 'name': (d.get('FriendlyName') or '').strip(), 'serial': (d.get('SerialNumber') or '').strip(),
                    'bus': bus, 'size': size, 'letters': letters, 'ok': ok, 'why': why})
    return out


def find_images(dirs):
    imgs = []
    for d in dirs:
        if d and os.path.isdir(d):
            for f in os.listdir(d):
                if f.lower().endswith(('.img', '.img.xz')) and 'ardzy' in f.lower():
                    p = os.path.join(d, f)
                    imgs.append({'path': p, 'name': f, 'size': os.path.getsize(p), 'date': time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(p)))})
    return sorted(imgs, key=lambda x: x['name'], reverse=True)


def settings_text(s):
    keys = ['hostname', 'password', 'network', 'address', 'gateway', 'dns', 'timezone', 'ssh', 'at_boot']
    head = ('# Ardzy board settings (written by the Ardzy app). Applied at the next boot.\n'
            '# The password line is erased by the board after it is used.\n')
    return head + ''.join('%-9s = %s\n' % (k, str(s.get(k, '') or '').replace('\n', ' ')) for k in keys)


# ------------------------------------------------------------------ start the elevated writer
def start(job_path):
    """Run the writer as administrator (Windows asks the user: UAC)."""
    import ctypes
    if getattr(sys, 'frozen', False):
        exe, args = sys.executable, '--flash "%s"' % job_path
    else:
        exe, args = sys.executable, '"%s" --flash "%s"' % (os.path.abspath(__file__), job_path)
    r = ctypes.windll.shell32.ShellExecuteW(None, 'runas', exe, args, None, 0)
    if r <= 32:
        raise RuntimeError('Windows did not start the card writer (administrator permission refused?)')


# ------------------------------------------------------------------ the writer (administrator)
class Progress:
    def __init__(self, path):
        self.path, self.last = path, 0

    def __call__(self, force=False, **kw):
        if not force and time.time() - self.last < 0.5:
            return
        self.last = time.time()
        tmp = self.path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(dict(kw, t=time.time()), f)
        os.replace(tmp, self.path)


def _varint(b, pos):
    v, shift = 0, 0
    while True:
        c = b[pos]
        pos += 1
        v |= (c & 0x7F) << shift
        shift += 7
        if not c & 0x80:
            return v, pos


def image_size(path):
    """Size of the image once unpacked. An .xz file lists it in its index (end of the file)."""
    if not path.lower().endswith('.xz'):
        return os.path.getsize(path)
    try:
        with open(path, 'rb') as f:
            f.seek(-12, os.SEEK_END)
            footer = f.read(12)
            if footer[-2:] != b'YZ':
                raise ValueError
            back = (int.from_bytes(footer[4:8], 'little') + 1) * 4
            f.seek(-12 - back, os.SEEK_END)
            idx = f.read(back)
        if idx[0] != 0:
            raise ValueError
        n, pos = _varint(idx, 1)
        total = 0
        for _ in range(n):
            _, pos = _varint(idx, pos)               # unpadded size
            u, pos = _varint(idx, pos)               # uncompressed size
            total += u
        return total
    except (ValueError, IndexError, OSError):
        with lzma.open(path) as f:                    # odd file: unpack once to count
            return f.seek(0, os.SEEK_END)


def check_disk(job):
    d = next((x for x in list_disks() if x['number'] == job['disk']), None)
    if not d:
        raise RuntimeError('the card is gone (disk %s)' % job['disk'])
    if not d['ok']:
        raise RuntimeError('disk %s may not be written: %s' % (job['disk'], d['why']))
    if d['size'] != job['size'] or d['name'] != job['name'] or d['serial'] != job.get('serial', d['serial']):
        raise RuntimeError('disk %s is not the card that was chosen (name or size changed): nothing written' % job['disk'])
    return d


def flash(job):
    prog = Progress(job['progress'])
    try:
        prog(phase='check', text='checking the card', force=True)
        total = image_size(job['image'])
        test_file = job.get('test_target')            # tests only: write into a plain file, no disk at all
        if test_file:
            if test_file.lower().startswith(('\\\\', '//')) or 'physicaldrive' in test_file.lower():
                raise RuntimeError('test_target must be a plain file')
            open(test_file, 'wb').close()
            d, dev = {'number': -1, 'name': 'test file', 'size': total}, test_file
        else:
            d = check_disk(job)
            if total > d['size']:
                raise RuntimeError('the image (%d MB) is bigger than the card (%d MB)' % (total >> 20, d['size'] >> 20))
            prog(phase='prepare', text='removing the old partitions of %s' % d['name'], force=True)
            ps('Clear-Disk -Number %d -RemoveData -RemoveOEM -Confirm:$false' % d['number'], timeout=120)
            time.sleep(1)
            check_disk(dict(job, size=d['size']))
            dev = r'\\.\PhysicalDrive%d' % d['number']
        src = lzma.open(job['image']) if job['image'].lower().endswith('.xz') else open(job['image'], 'rb')
        h = hashlib.sha256()
        done, t0 = 0, time.time()
        with src, open(dev, 'r+b', buffering=0) as out:
            # The first block (partition table) is written LAST: if Windows saw the new partitions
            # early it would mount them and refuse the rest of the writes.
            first = src.read(CHUNK)
            h.update(first)
            out.seek(len(first))
            done = len(first)
            while True:
                buf = src.read(CHUNK)
                if not buf:
                    break
                h.update(buf)
                if len(buf) % 512:
                    buf += b'\0' * (512 - len(buf) % 512)
                out.write(buf)
                done += len(buf)
                prog(phase='write', done=done, total=total, mbps=done / 1e6 / max(time.time() - t0, 0.01),
                     text='writing %d of %d MB' % (done >> 20, total >> 20))
            out.seek(0)
            if len(first) % 512:
                first += b'\0' * (512 - len(first) % 512)
            out.write(first)
            os.fsync(out.fileno())
        if job.get('verify', True):
            h2, got, t1 = hashlib.sha256(), 0, time.time()
            with open(dev, 'rb', buffering=0) as f:
                while got < total:
                    n = min(CHUNK, total - got)
                    buf = f.read((n + 511) // 512 * 512)[:n]
                    if not buf:
                        break
                    h2.update(buf)
                    got += len(buf)
                    prog(phase='verify', done=got, total=total, mbps=got / 1e6 / max(time.time() - t1, 0.01),
                         text='checking %d of %d MB' % (got >> 20, total >> 20))
            if h2.hexdigest() != h.hexdigest():
                raise RuntimeError('the card does not read back what was written: the card may be bad')
        if test_file:
            prog(phase='done', ok=True, text='test file written and checked (%d MB)' % (total >> 20), force=True)
            return
        prog(phase='settings', text='writing the board settings (ardzy.txt)', force=True)
        letter = None
        for _ in range(20):                         # Windows needs a moment to see the new partitions
            try:
                ps('Update-Disk -Number %d' % d['number'])
                out = ps('(Get-Partition -DiskNumber %d -PartitionNumber 1).DriveLetter' % d['number']).strip()
                if not out or out in ('\x00', '0'):
                    ps('Add-PartitionAccessPath -DiskNumber %d -PartitionNumber 1 -AssignDriveLetter' % d['number'])
                    out = ps('(Get-Partition -DiskNumber %d -PartitionNumber 1).DriveLetter' % d['number']).strip()
                if out and out[0].isalpha():
                    letter = out[0]
                    break
            except Exception:
                pass
            time.sleep(1)
        if job.get('settings'):
            if not letter:
                raise RuntimeError('written and checked, but the boot partition did not appear: '
                                   'put the card in again and edit ardzy.txt by hand')
            with open('%s:\\ardzy.txt' % letter, 'w', newline='\n') as f:
                f.write(settings_text(job['settings']))
        prog(phase='done', ok=True, text='done: %d MB written%s in %.0f s' % (
            total >> 20, ' and checked' if job.get('verify', True) else '', time.time() - t0), letter=letter, force=True)
    except Exception as e:
        prog(phase='error', ok=False, text=str(e), force=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--flash':
        flash(json.load(open(sys.argv[2])))
    elif len(sys.argv) == 2 and sys.argv[1] == '--list':
        print(json.dumps(list_disks(), indent=1))
