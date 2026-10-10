"""Build an Ardzy SD card image from source, from the app (Windows + WSL).

The image is made by the same scripts as always (scripts/00..05_*.sh in the Ardzy sources), run as root in
a WSL Linux (Ubuntu). The app only starts them with the options chosen in its window and shows their output:

    board      s9 | ebaz4205                       which board the image is for (boot loader, device tree)
    packages   extra Debian packages for the image (installed into the root file system)
    examples   the example projects on the card ("" = the board's usual ones)
    version    the version written into the image (/etc/ardzy-release); default 0.2
    steps      'image' (only the card image from the parts already built), 'boot' (+ boot loader, device
               tree), 'all' (+ kernel and root file system: the first time, about an hour)

The first build also installs the build tools and downloads U-Boot and Linux (setup: 00_toolchain.sh,
00_qemu.sh, 01_get_sources.sh), so WSL needs the internet then.
"""
import os, re, shutil, subprocess, threading, time

STEPS = {
    'setup': ['01_get_sources.sh', '00_toolchain.sh', '00_qemu.sh'],     # (00_qemu needs 01's packages)
    'kernel': ['03_build_kernel.sh'],
    'rootfs': ['04_build_rootfs.sh'],
}
PKG_RE = re.compile(r'^[a-z0-9][a-z0-9+.-]{1,60}$')
_proc = {'p': None, 'stop': False}


def _run(cmd, timeout=30):
    r = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=0x08000000)
    out = r.stdout
    # wsl.exe answers in UTF-16 for its own messages
    text = out.decode('utf-16-le', 'replace') if out[1:2] == b'\0' else out.decode('utf-8', 'replace')
    return r.returncode, text.replace('\0', '')


def distros():
    """The WSL Linux systems on this PC (names), or [] when WSL is not installed."""
    if not shutil.which('wsl.exe'):
        return []
    try:
        code, text = _run(['wsl.exe', '-l', '-q'])
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [l.strip() for l in text.splitlines() if l.strip()] if code == 0 else []


def pick_distro(names, wanted=None):
    if wanted and wanted in names:
        return wanted
    for n in names:
        if n.lower().startswith('ubuntu') or n.lower().startswith('debian'):
            return n
    return names[0] if names else None


def wsl_path(win):
    """C:\\Users\\x\\Ardzy -> /mnt/c/Users/x/Ardzy"""
    win = os.path.abspath(win)
    return '/mnt/%s%s' % (win[0].lower(), win[2:].replace('\\', '/'))


def is_sources(d):
    return bool(d) and os.path.isfile(os.path.join(d, 'scripts', '05_make_image.sh')) and \
        os.path.isdir(os.path.join(d, 'boards'))


def find_sources(app_dir, configured=None):
    for d in (configured, os.path.join(app_dir, '..'), os.path.join(app_dir, '..', '..'),
              os.path.join(os.path.expanduser('~'), 'Documents', 'Ardzy-sources')):
        if d and is_sources(d):
            return os.path.normpath(d)
    return None


def status(app_dir, configured_src=None, distro=None):
    names = distros()
    d = pick_distro(names, distro)
    src = find_sources(app_dir, configured_src)
    st = {'wsl': bool(names), 'distros': names, 'distro': d, 'sources': src, 'images': []}
    if src:
        out = os.path.join(src, 'out')
        if os.path.isdir(out):
            for f in sorted(os.listdir(out)):
                if f.startswith('ardzy_debian13') and f.endswith(('.img', '.img.xz')):
                    p = os.path.join(out, f)
                    st['images'].append({'name': f, 'path': p, 'size': os.path.getsize(p),
                                         'date': time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(p)))})
    if d:
        try:     # what is already built inside WSL (then a quick build is enough)
            code, text = _run(['wsl.exe', '-d', d, '-u', 'root', '--exec', 'bash', '-c',
                               'for f in /opt/toolchains/arm/bin /root/s9v2/src/u-boot /root/s9v2/src/linux-xlnx '
                               '/root/s9v2/rootfs/etc/debian_version /root/s9v2/out/modules; do [ -e $f ] && echo $f; done; '
                               'echo ARDZY_CHECKED'], timeout=60)
            have = text.split()
            if 'ARDZY_CHECKED' not in have:      # the check did not run: say "unknown", never "nothing built"
                raise OSError('WSL did not answer: %s' % text.strip()[-200:])
            st['built'] = {'tools': '/opt/toolchains/arm/bin' in have,
                           'sources': '/root/s9v2/src/u-boot' in have and '/root/s9v2/src/linux-xlnx' in have,
                           'rootfs': '/root/s9v2/rootfs/etc/debian_version' in have,
                           'kernel': '/root/s9v2/out/modules' in have}
        except (OSError, subprocess.TimeoutExpired) as e:
            st['built'] = None
            st['error'] = str(e)
    return st


def plan(opts, built):
    """The scripts to run, in order, for these options (and what is already built)."""
    board = opts.get('board', 's9')
    steps = opts.get('steps', 'boot')
    out = []
    if steps == 'all' or not built.get('tools') or not built.get('sources'):
        out += STEPS['setup']
    if steps == 'all' or not built.get('kernel'):
        out += STEPS['kernel']
    if steps == 'all' or not built.get('rootfs') or opts.get('packages'):
        out.append('04_build_rootfs.sh')
    if steps in ('boot', 'all') or board != 's9':
        out.append('02_build_uboot.sh')
        if board != 's9':
            out.append('03b_board_dtb.sh')
    out.append('05_make_image.sh')
    return out


def build(opts, app_dir, settings, log):
    """Run the build (a job of the app). Returns True when the image was made."""
    names = distros()
    d = pick_distro(names, settings.get('wsl_distro'))
    if not d:
        log('WSL is not installed. Open PowerShell as administrator and run: wsl --install -d Ubuntu-20.04, '
            'restart Windows, then try again.', 'err')
        return False
    src = find_sources(app_dir, settings.get('sources_dir'))
    if not src:
        log('The Ardzy sources were not found: press "Get the sources" (or choose the folder of your git clone).', 'err')
        return False
    board = opts.get('board', 's9')
    if not os.path.isfile(os.path.join(src, 'boards', board, 'board.json')):
        log('unknown board %s' % board, 'err')
        return False
    pkgs = [p for p in re.split(r'[\s,]+', opts.get('packages', '') or '') if p]
    bad = [p for p in pkgs if not PKG_RE.match(p)]
    if bad:
        log('not a Debian package name: %s' % ', '.join(bad), 'err')
        return False
    examples = re.sub(r'[^A-Za-z0-9_. -]', '', opts.get('examples', '') or '').strip()
    version = re.sub(r'[^A-Za-z0-9_.-]', '', opts.get('version', '') or '') or '0.2'
    st = status(app_dir, src, d)
    if st.get('built') is None:
        log('Could not ask WSL what is already built (%s): nothing was started.' % st.get('error', '?'), 'err')
        return False
    steps = plan(dict(opts, packages=' '.join(pkgs)), st['built'])
    env = 'BOARD=%s ARDZY_VERSION=%s ARDZY_FALLBACK=0' % (board, version)
    if examples:
        env += " ARDZY_EXAMPLES='%s'" % examples
    if pkgs:
        env += " ARDZY_EXTRA_PKGS='%s'" % ' '.join(pkgs)
    if '04_build_rootfs.sh' in steps and st.get('built', {}).get('rootfs') and opts.get('steps') != 'all':
        env += ' SKIP_DEBOOTSTRAP=1'           # only the settings and the extra packages, not a new Debian
    log('Building an Ardzy image for the %s in WSL (%s): %s' % (board, d, ', '.join(s[:-3] for s in steps)), 'head')
    log('  sources: %s' % src)
    sp = wsl_path(src)
    script = 'set -e; cd "%s"; sed -i "s/\\r$//" scripts/*.sh; ' % sp
    script += '; '.join('echo "=== %s"; %s bash scripts/%s' % (s, env, s) for s in steps)
    script += '; echo "=== image"; ls -l out/ardzy_debian13*.img'
    _proc['stop'] = False
    t0 = time.time()
    p = subprocess.Popen(['wsl.exe', '-d', d, '-u', 'root', '--exec', 'bash', '-c', script], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, creationflags=0x08000000)
    _proc['p'] = p
    last = ''
    for raw in iter(p.stdout.readline, b''):
        line = raw.decode('utf-8', 'replace').rstrip()
        if not line:
            continue
        last = line
        if line.startswith('==='):
            log('step: %s  (%.0f min so far)' % (line.strip('= ').strip(), (time.time() - t0) / 60), 'head')
        elif re.search(r'\b(error|failed|stop)\b', line, re.I) and 'warning' not in line.lower():
            log('  ' + line, 'err')
        else:
            log('  ' + line)
    code = p.wait()
    _proc['p'] = None
    if _proc['stop']:
        log('Image build stopped.', 'warn')
        return False
    if code:
        log('Image build FAILED (exit %d, last line: %s). The whole output is above.' % (code, last), 'err')
        return False
    img = os.path.join(src, 'out', 'ardzy_debian13.img' if board == 's9' else 'ardzy_debian13_%s.img' % board)
    log('Image ready in %.0f minutes: %s. Write it to a card: SD card, Write a card.' % ((time.time() - t0) / 60, img), 'ok')
    return True


def stop():
    p = _proc.get('p')
    if p:
        _proc['stop'] = True
        p.kill()
        return True
    return False


def get_sources(dest, log):
    """git clone the Ardzy sources (inside WSL, which has git) into a Windows folder."""
    names = distros()
    d = pick_distro(names)
    if not d:
        log('WSL is not installed (wsl --install -d Ubuntu-20.04 in an administrator PowerShell).', 'err')
        return None
    if os.path.exists(dest) and os.listdir(dest):
        log('%s already exists and is not empty.' % dest, 'err')
        return None
    os.makedirs(dest, exist_ok=True)
    log('Getting the Ardzy sources into %s ...' % dest, 'head')
    code, text = _run(['wsl.exe', '-d', d, '-u', 'root', '--exec', 'bash', '-c',
                       'command -v git >/dev/null || apt-get install -y -qq git >/dev/null; '
                       'git clone -q --depth 1 https://github.com/chrysovalantischryso/ardzy "%s"' % wsl_path(dest)], timeout=1800)
    if code or not is_sources(dest):
        log('git clone failed: %s' % text.strip()[-400:], 'err')
        return None
    log('Sources ready: %s' % dest, 'ok')
    return dest
