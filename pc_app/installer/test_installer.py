"""Tests the Setup exe without a window: install into a temporary folder, check, upgrade, a running app
blocks setup, uninstall, check that nothing is left. Uses the real Start menu / Desktop / Apps entry of
this Windows user for a moment (the same names the real install uses) and removes them again; refuses to
run when Ardzy is already installed for this user.

    python installer/test_installer.py [path of the Setup exe]"""
import glob, json, os, subprocess, sys, tempfile, time, urllib.request, winreg

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob(os.path.join(HERE, '..', 'dist', 'Ardzy-*-Setup.exe')))[-1]
KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\Ardzy'
START = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Ardzy.lnk')
SETTINGS = os.path.join(os.environ['APPDATA'], 'Ardzy')
SETTINGS_BEFORE = os.path.isdir(SETTINGS)
SETTINGS_FILES = sorted(os.listdir(SETTINGS)) if SETTINGS_BEFORE else []
ok = fail = 0


def check(name, cond, extra=''):
    global ok, fail
    ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
    print('  %s %s' % ('ok   ' if cond else 'FAIL ', name), '' if cond else extra, flush=True)


def desktop():
    import ctypes
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)
    return os.path.join(buf.value, 'Ardzy.lnk')


def reg():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            return {winreg.EnumValue(k, i)[0]: winreg.EnumValue(k, i)[1] for i in range(winreg.QueryInfoKey(k)[1])}
    except OSError:
        return None


def lnk_target(link):
    ps = "(New-Object -ComObject WScript.Shell).CreateShortcut('%s').TargetPath" % link.replace("'", "''")
    return subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True).stdout.strip()


def main():
    if reg() is not None:
        raise SystemExit('Ardzy is installed for this user: this test would replace it. Uninstall first.')
    base = tempfile.mkdtemp(prefix='ardzy_inst_')
    folder = os.path.join(base, 'Ardzy')
    print('Setup: %s (%d MB)\nfolder: %s' % (SETUP, os.path.getsize(SETUP) >> 20, folder))

    t = time.time()
    r = subprocess.run([SETUP, '/S', '/DIR=' + folder], timeout=180)
    print('    install took %.0f s' % (time.time() - t))
    check('silent install exits 0', r.returncode == 0, r.returncode)
    check('Ardzy.exe and the uninstaller are there', os.path.exists(os.path.join(folder, 'Ardzy.exe')) and
          os.path.exists(os.path.join(folder, 'Ardzy-uninstall.exe')))
    check('the app files are all there (ui, tools, term.js, xterm)', all(os.path.exists(os.path.join(folder, '_internal', *p.split('/'))) for p in
          ('ui/index.html', 'ui/term.js', 'ui/vendor/xterm/xterm.js', 'ardzy_link.py', 'tools/fpga/bin/nextpnr-himbaechel.exe')))
    m = json.load(open(os.path.join(folder, 'ardzy-install.json')))
    check('the folder is marked as Ardzy\'s', m.get('app') == 'Ardzy', m)
    g = reg() or {}
    check('listed in Settings > Apps (name, version, uninstaller, size)', g.get('DisplayName', '').startswith('Ardzy 0.') and
          g.get('InstallLocation') == folder and 'Ardzy-uninstall.exe' in g.get('UninstallString', '') and g.get('EstimatedSize', 0) > 100000, g)
    check('Start menu shortcut -> Ardzy.exe', lnk_target(START).lower() == os.path.join(folder, 'Ardzy.exe').lower(), lnk_target(START))
    check('Desktop shortcut -> Ardzy.exe', lnk_target(desktop()).lower() == os.path.join(folder, 'Ardzy.exe').lower(), lnk_target(desktop()))
    zone = os.path.exists(os.path.join(folder, 'Ardzy.exe') + ':Zone.Identifier')
    check('no "downloaded from the internet" mark on the files', not zone)

    # the installed app starts (with its own temporary settings, so nothing of yours is touched)
    tmpset = tempfile.mkdtemp(prefix='ardzy_set_')
    env = dict(os.environ, APPDATA=tmpset, LOCALAPPDATA=tmpset, ARDZY_PORT='8751')
    app = subprocess.Popen([os.path.join(folder, 'Ardzy.exe'), '--serve'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    html = ''
    for _ in range(60):
        time.sleep(0.5)
        try:
            html = urllib.request.urlopen('http://127.0.0.1:8751/', timeout=2).read().decode()
            break
        except OSError:
            pass
    check('the installed Ardzy starts and serves its window', 'Ardzy' in html and 'term.js' in html)
    r = subprocess.run([SETUP, '/S', '/DIR=' + folder], timeout=180)
    check('setup refuses while Ardzy runs (exit 2)', r.returncode == 2, r.returncode)
    r = subprocess.run([os.path.join(folder, 'Ardzy-uninstall.exe'), '/S'], timeout=180)
    check('uninstall refuses while Ardzy runs (and removes nothing)', r.returncode == 2 and os.path.exists(os.path.join(folder, 'Ardzy.exe')), r.returncode)
    app.kill()
    app.wait()
    time.sleep(1)

    # upgrade over it (a stray file of the old version must go)
    open(os.path.join(folder, '_internal', 'old_version_file.txt'), 'w').write('x')
    r = subprocess.run([SETUP, '/S', '/DIR=' + folder, '/NODESKTOP'], timeout=180)
    check('install over it (upgrade) exits 0', r.returncode == 0, r.returncode)
    check('files the new version does not have are gone', not os.path.exists(os.path.join(folder, '_internal', 'old_version_file.txt')))
    check('without /NODESKTOP... with it: the Desktop shortcut is removed', not os.path.exists(desktop()))
    check('the Start menu shortcut stays', os.path.exists(START))

    # refuses a folder with someone else's files
    other = os.path.join(base, 'other')
    os.makedirs(other)
    open(os.path.join(other, 'mine.txt'), 'w').write('keep me')
    r = subprocess.run([SETUP, '/S', '/DIR=' + other], timeout=180)
    check('refuses a folder with other files (they stay)', r.returncode == 1 and open(os.path.join(other, 'mine.txt')).read() == 'keep me')
    check('... and the real install was not moved', (reg() or {}).get('InstallLocation') == folder)

    # uninstall the way Windows does it (QuietUninstallString)
    t = time.time()
    r = subprocess.run((reg() or {}).get('QuietUninstallString', ''), shell=False, timeout=180)
    print('    uninstall took %.0f s' % (time.time() - t))
    check('silent uninstall exits 0', r.returncode == 0, r.returncode)
    time.sleep(8)                                           # (the waiting uninstaller's own file goes a moment later)
    check('the folder is gone', not os.path.exists(folder), os.listdir(folder) if os.path.exists(folder) else '')
    check('the Apps entry is gone', reg() is None)
    check('the shortcuts are gone', not os.path.exists(START) and not os.path.exists(desktop()))
    check('your settings folder is untouched (no /REMOVESETTINGS)', os.path.isdir(SETTINGS) == SETTINGS_BEFORE and
          (not SETTINGS_BEFORE or sorted(os.listdir(SETTINGS)) == SETTINGS_FILES))
    print('\n%d ok, %d failed' % (ok, fail))
    sys.exit(1 if fail else 0)


def cleanup():
    """Whatever happened: no test app running, no test install, entry or shortcuts left behind."""
    import shutil
    subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like '*\\ardzy_inst_*' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"], capture_output=True)
    g = reg()
    if g and 'ardzy_inst_' in g.get('InstallLocation', ''):
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KEY)
    for link in (START, desktop()):
        if os.path.exists(link) and 'ardzy_inst_' in lnk_target(link):
            os.remove(link)
    for d in glob.glob(os.path.join(tempfile.gettempdir(), 'ardzy_inst_*')) + glob.glob(os.path.join(tempfile.gettempdir(), 'ardzy_set_*')):
        shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    try:
        main()
    finally:
        cleanup()
