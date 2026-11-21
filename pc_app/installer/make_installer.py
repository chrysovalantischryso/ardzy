"""Builds the Windows installer: pc_app/dist/Ardzy-<version>-<stage>-Setup.exe

    python installer/make_installer.py            (uses pc_app/dist/Ardzy: run build_exe.bat first)

Steps: Ardzy-uninstall.exe (setup_app.py without the app inside) -> payload.zip (dist/Ardzy + the uninstaller,
LZMA) -> the Setup exe (setup_app.py + payload). Work files go to %TEMP%/ardzy_setup_build.
Needs: PyInstaller (the same as build_exe.bat)."""
import json, os, re, shutil, subprocess, sys, time, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
DIST = os.path.join(APP_DIR, 'dist', 'Ardzy')
WORK = os.path.join(os.environ.get('TEMP', HERE), 'ardzy_setup_build')
PUBLISHER = 'chryso'
URL = 'https://github.com/chrysovalantischryso/ardzy'


def app_version():
    src = open(os.path.join(APP_DIR, 'ardzy_app.py'), encoding='utf-8').read()
    return re.search(r"^APP_VERSION = '([^']+)'", src, re.M).group(1), re.search(r"^APP_STAGE = '([^']*)'", src, re.M).group(1)


def version_file(path, version, stage, desc, name):
    nums = [int(x) for x in re.findall(r'\d+', version)][:4]
    nums += [0] * (4 - len(nums))
    t = tuple(nums)
    open(path, 'w', encoding='utf-8').write('''VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(t)s, prodvers=%(t)s, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', '%(pub)s'), StringStruct('FileDescription', '%(desc)s'),
    StringStruct('FileVersion', '%(v)s'), StringStruct('InternalName', '%(name)s'),
    StringStruct('LegalCopyright', 'GPL-3.0, %(pub)s'), StringStruct('OriginalFilename', '%(name)s.exe'),
    StringStruct('ProductName', 'Ardzy'), StringStruct('ProductVersion', '%(v)s')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
''' % {'t': t, 'pub': PUBLISHER, 'desc': desc, 'v': ('%s %s' % (version, stage)).strip(), 'name': name})


def pyinstaller(name, datas, vfile):
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed', '--name', name,
           '--icon', os.path.join(APP_DIR, 'ardzy.ico'), '--version-file', vfile,
           '--distpath', os.path.join(WORK, 'out'), '--workpath', os.path.join(WORK, 'pyi_' + name),
           '--specpath', os.path.join(WORK, 'pyi_' + name), '--exclude-module', 'numpy']
    for src, dst in datas:
        cmd += ['--add-data', '%s%s%s' % (src, os.pathsep, dst)]
    cmd.append(os.path.join(HERE, 'setup_app.py'))
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = os.path.join(WORK, 'out', name + '.exe')
    if r.returncode != 0 or not os.path.exists(out):
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise SystemExit('PyInstaller failed for ' + name)
    return out


def main():
    if not os.path.exists(os.path.join(DIST, 'Ardzy.exe')):
        raise SystemExit('pc_app/dist/Ardzy/Ardzy.exe missing: run build_exe.bat first')
    version, stage = app_version()
    t0 = time.time()
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    meta = os.path.join(WORK, 'setup_meta.json')
    json.dump({'version': version, 'stage': stage, 'publisher': PUBLISHER, 'url': URL}, open(meta, 'w'))
    common = [(meta, '.'), (os.path.join(APP_DIR, 'ardzy.ico'), '.'), (os.path.join(APP_DIR, 'ui', 'icon.png'), '.')]

    print('1/3 the uninstaller ...', flush=True)
    vf = os.path.join(WORK, 'version_uninstall.txt')
    version_file(vf, version, stage, 'Ardzy uninstaller', 'Ardzy-uninstall')
    un = pyinstaller('Ardzy-uninstall', common, vf)

    print('2/3 the app, packed (LZMA) ...', flush=True)
    payload = os.path.join(WORK, 'payload.zip')
    n = size = 0
    with zipfile.ZipFile(payload, 'w', zipfile.ZIP_LZMA) as z:
        for root, dirs, files in os.walk(DIST):
            dirs.sort()
            for f in sorted(files):
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, DIST).replace('\\', '/'))
                n += 1
                size += os.path.getsize(p)
        z.write(un, 'Ardzy-uninstall.exe')
    print('    %d files, %d MB -> %d MB' % (n, size >> 20, os.path.getsize(payload) >> 20), flush=True)

    print('3/3 the Setup program ...', flush=True)
    name = 'Ardzy-%s-%sSetup' % (version, stage + '-' if stage else '')
    vf = os.path.join(WORK, 'version_setup.txt')
    version_file(vf, version, stage, 'Ardzy %s %s Setup' % (version, stage), name)
    exe = pyinstaller(name, common + [(payload, '.')], vf)
    final = os.path.join(APP_DIR, 'dist', name + '.exe')
    shutil.copy2(exe, final)
    import hashlib
    h = hashlib.sha256(open(final, 'rb').read()).hexdigest()
    print('OK: %s  (%d MB, sha256 %s..., %.0f s)' % (final, os.path.getsize(final) >> 20, h[:16], time.time() - t0))


if __name__ == '__main__':
    main()
