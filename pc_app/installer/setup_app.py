"""Ardzy Setup: installs the Ardzy app for this Windows user (no administrator needed), and removes it again.

One program, built twice by make_installer.py:
  Ardzy-<version>-Setup.exe     carries the app (payload.zip) and installs it
  Ardzy-uninstall.exe           goes into the app's folder; Windows Settings > Apps calls it

What the installer does:
  * the app goes to %LOCALAPPDATA%\\Programs\\Ardzy (or a folder you choose)
  * a Start menu shortcut, and one on the Desktop if you want
  * an entry in Windows Settings > Apps (Installed apps), with the uninstaller
  * an older Ardzy in the same folder is replaced (your projects and settings are never touched:
    they live in Documents\\Ardzy and %APPDATA%\\Ardzy, not in the app's folder)

Silent use (scripts, tests):
  Setup.exe /S [/DIR=<folder>] [/NODESKTOP] [/NOSTARTMENU] [/RUN]
  Ardzy-uninstall.exe /S [/REMOVESETTINGS]
Exit code 0 = done, 1 = failed, 2 = Ardzy is running (close it first).
"""
import ctypes, json, os, shutil, subprocess, sys, tempfile, threading, time, zipfile

APP = 'Ardzy'
HERE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
META = json.load(open(os.path.join(HERE, 'setup_meta.json'))) if os.path.exists(os.path.join(HERE, 'setup_meta.json')) \
    else {'version': '0.0', 'stage': '', 'publisher': 'chryso', 'url': 'https://github.com/chrysovalantischryso/ardzy'}
PAYLOAD = os.path.join(HERE, 'payload.zip')
MARKER = 'ardzy-install.json'                 # in the app's folder: "this folder belongs to the Ardzy installer"
UNINSTALLER = 'Ardzy-uninstall.exe'
REG_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\Ardzy'
NO_WINDOW = 0x08000000
FULL_NAME = ('%s %s %s' % (APP, META['version'], META.get('stage', ''))).strip()

# colours of the app (ui/app.css)
C = {'bg': '#f3f5f4', 'panel': '#ffffff', 'text': '#18211c', 'muted': '#5b6a62', 'line': '#d6ddd9',
     'accent': '#13894a', 'accent_dark': '#0e6d3a', 'head': '#101512', 'head_text': '#e8f3ec', 'err': '#c42b2b'}


# ------------------------------------------------------------------ places
def default_dir():
    return os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'Programs', APP)


def start_menu_link():
    return os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs', APP + '.lnk')


def desktop_link():
    # the real Desktop folder (it can be moved, or be in OneDrive)
    try:
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0:     # CSIDL_DESKTOPDIRECTORY
            return os.path.join(buf.value, APP + '.lnk')
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'Desktop', APP + '.lnk')


def settings_dir():
    return os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), APP)


def workspace():
    """Where this user's projects are (the app's setting), or None when Ardzy never ran here."""
    try:
        w = json.load(open(os.path.join(settings_dir(), 'settings.json'), encoding='utf-8')).get('workspace')
        return w if w and os.path.isdir(w) else None
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ checks
def running_from(folder):
    """The programs that run from this folder now (Ardzy.exe, or a tool it started). Windows lets a running
    program be renamed, so the process list is asked, not the files."""
    from ctypes import wintypes
    folder = os.path.normcase(os.path.abspath(folder)) + os.sep
    psapi, k32 = ctypes.WinDLL('psapi'), ctypes.WinDLL('kernel32')
    k32.OpenProcess.restype = wintypes.HANDLE
    arr = (wintypes.DWORD * 8192)()
    got = wintypes.DWORD()
    if not psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(got)):
        return []
    out = []
    for pid in arr[:got.value // ctypes.sizeof(wintypes.DWORD)]:
        h = k32.OpenProcess(0x1000, False, pid)                  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            continue
        try:
            buf, n = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
            if k32.QueryFullProcessImageNameW(wintypes.HANDLE(h), 0, buf, ctypes.byref(n)):
                if os.path.normcase(buf.value).startswith(folder) and pid != os.getpid():
                    out.append(buf.value)
        finally:
            k32.CloseHandle(wintypes.HANDLE(h))
    return out


def app_running(folder, ignore=()):
    """Ardzy (or a tool it started) runs from this folder. `ignore`: file names that do not count
    (the uninstaller that waits in the folder while its copy in %TEMP% does the work)."""
    return any(os.path.basename(p).lower() not in [i.lower() for i in ignore] for p in running_from(folder))


def swap_out(folder, suffix):
    """Rename the folder away (fails with RuntimeError when a file in it is in use: then nothing changed)."""
    away = folder + suffix
    if os.path.exists(away):
        shutil.rmtree(away, ignore_errors=True)
    for _ in range(3):
        try:
            os.rename(folder, away)
            return away
        except OSError:
            time.sleep(0.5)
    raise RuntimeError('A file in %s is in use (Ardzy, or a window showing that folder). Close it, then try again.' % folder)


def folder_problem(folder):
    """None when the folder can be used; else why not."""
    folder = os.path.abspath(folder)
    if len(folder) < 8 or os.path.dirname(folder) == folder:
        return 'Choose a folder of its own for Ardzy (not a drive).'
    if os.path.isdir(folder) and os.listdir(folder) and not os.path.exists(os.path.join(folder, MARKER)):
        return 'This folder has other files in it. Choose an empty folder or a new one.'
    return None


def installed():
    """(folder, version) of the installed Ardzy for this user, or (None, None)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
            return winreg.QueryValueEx(k, 'InstallLocation')[0], winreg.QueryValueEx(k, 'DisplayVersion')[0]
    except OSError:
        return None, None


# ------------------------------------------------------------------ work
def make_shortcut(link, target, folder, description):
    os.makedirs(os.path.dirname(link), exist_ok=True)
    q = lambda s: "'" + s.replace("'", "''") + "'"
    ps = ('$s = (New-Object -ComObject WScript.Shell).CreateShortcut(%s); $s.TargetPath = %s; $s.WorkingDirectory = %s; '
          '$s.IconLocation = %s; $s.Description = %s; $s.Save()') % (q(link), q(target), q(folder), q(target + ',0'), q(description))
    r = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', ps],
                       capture_output=True, text=True, creationflags=NO_WINDOW)
    if r.returncode != 0 or not os.path.exists(link):
        raise OSError('could not make the shortcut %s: %s' % (link, (r.stderr or r.stdout).strip()[:200]))


def register(folder, size_kb):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
        un = os.path.join(folder, UNINSTALLER)
        for name, val in (('DisplayName', FULL_NAME), ('DisplayVersion', META['version']),
                          ('Publisher', META['publisher']), ('DisplayIcon', os.path.join(folder, 'Ardzy.exe') + ',0'),
                          ('InstallLocation', folder), ('UninstallString', '"%s"' % un),
                          ('QuietUninstallString', '"%s" /S' % un), ('URLInfoAbout', META['url']),
                          ('HelpLink', META['url']), ('Comments', 'Zynq boards (Antminer S9) used like an Arduino'),
                          ('InstallDate', time.strftime('%Y%m%d'))):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
        for name, val in (('EstimatedSize', int(size_kb)), ('NoModify', 1), ('NoRepair', 1)):
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, val)


def unregister(folder):
    """Remove the Apps entry, but only when it is the entry of this folder (another install keeps its own)."""
    import winreg
    where = installed()[0]
    if where and os.path.normcase(os.path.abspath(where)) != os.path.normcase(os.path.abspath(folder)):
        return
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY)
    except OSError:
        pass


def install(folder, desktop=True, start_menu=True, progress=lambda f, t: None):
    """Returns the path of Ardzy.exe. Raises on problems (the folder is then as clean as it can be)."""
    folder = os.path.abspath(folder)
    why = folder_problem(folder)
    if why:
        raise ValueError(why)
    if app_running(folder):
        raise RuntimeError('Ardzy is running. Close it, then try again.')
    # the new version is unpacked next to the folder first, then the folders are swapped: an older
    # Ardzy stays whole until the new one is complete, and a file in use stops it before anything changes
    stage = folder + '.setup-new'
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    try:
        json.dump({'app': APP, 'version': META['version'], 'stage': META.get('stage', ''), 'installed': time.strftime('%Y-%m-%d %H:%M'),
                   'desktop': desktop, 'start_menu': start_menu}, open(os.path.join(stage, MARKER), 'w'), indent=1)
        with zipfile.ZipFile(PAYLOAD) as z:
            items = [i for i in z.infolist() if not i.is_dir()]
            total = sum(i.file_size for i in items) or 1
            done = 0
            for i in items:
                parts = [p for p in i.filename.replace('\\', '/').split('/') if p not in ('', '.', '..')]
                dst = os.path.join(stage, *parts)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with z.open(i) as src, open(dst, 'wb') as out:
                    shutil.copyfileobj(src, out, 1 << 20)
                done += i.file_size
                progress(done / total * 0.97, 'Copying %s' % parts[-1])
        old = None
        if os.path.isdir(folder):
            progress(0.98, 'Replacing the older version ...')
            if os.listdir(folder):
                old = swap_out(folder, '.setup-old')               # (RuntimeError: in use, nothing changed)
            else:
                os.rmdir(folder)
        os.makedirs(os.path.dirname(folder), exist_ok=True)
        os.rename(stage, folder)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    if old:
        shutil.rmtree(old, ignore_errors=True)
    exe = os.path.join(folder, 'Ardzy.exe')
    progress(1, 'Making the shortcuts ...')
    desc = 'Ardzy: Zynq boards like an Arduino'
    for link, want in ((start_menu_link(), start_menu), (desktop_link(), desktop)):
        if want:
            make_shortcut(link, exe, folder, desc)
        elif os.path.exists(link) and shortcut_is_ours(link, folder):
            os.remove(link)
    register(folder, total // 1024)
    progress(1, 'Done')
    return exe


def shortcut_is_ours(link, folder):
    try:
        return os.path.abspath(folder).lower().encode('utf-16-le') in open(link, 'rb').read().lower() or \
            os.path.abspath(folder).lower().encode() in open(link, 'rb').read().lower()
    except OSError:
        return False


def uninstall(folder, remove_settings=False, progress=lambda f, t: None):
    folder = os.path.abspath(folder)
    if not os.path.exists(os.path.join(folder, MARKER)):
        raise ValueError('%s is not an Ardzy folder (no %s): nothing removed.' % (folder, MARKER))
    if app_running(folder, ignore=(UNINSTALLER,)):
        raise RuntimeError('Ardzy is running. Close it, then try again.')
    progress(0.1, 'Removing the app ...')
    gone = swap_out(folder, '.removing')                # first: a file in use stops it here, nothing removed yet
    progress(0.4, 'Removing the shortcuts ...')
    for link in (start_menu_link(), desktop_link()):
        if os.path.exists(link) and shortcut_is_ours(link, folder):
            os.remove(link)
    unregister(folder)
    progress(0.6, 'Removing the app ...')
    shutil.rmtree(gone, ignore_errors=True)
    if os.path.exists(gone):          # the uninstaller that started us still waits in there: it goes when it ends
        subprocess.Popen('cmd /c ping -n 5 127.0.0.1 >nul & rmdir /s /q "%s"' % gone,
                         creationflags=NO_WINDOW | 0x00000008, close_fds=True)
    if remove_settings:
        progress(0.9, 'Removing the settings ...')
        shutil.rmtree(settings_dir(), ignore_errors=True)
        shutil.rmtree(os.path.join(os.environ.get('LOCALAPPDATA', ''), APP), ignore_errors=True)
    progress(1, 'Done')


def launch(exe):
    """Start the installed app (not as a child of this packaged program: fresh DLL folder and environment)."""
    try:
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    except Exception:
        pass
    env = {k: v for k, v in os.environ.items() if not k.startswith(('_MEI', '_PYI'))}
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    subprocess.Popen([exe], cwd=os.path.dirname(exe), env=env, close_fds=True,
                     creationflags=0x00000008 | 0x00000200)            # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def delete_later(path):
    """The uninstaller can not delete its own running file: a hidden cmd does it a moment later."""
    subprocess.Popen('cmd /c ping -n 3 127.0.0.1 >nul & del /f /q "%s" & rmdir "%s"' % (path, os.path.dirname(path)),
                     creationflags=NO_WINDOW | 0x00000008, close_fds=True)


# ------------------------------------------------------------------ the window
def run_gui(mode, folder=None):
    import tkinter as tk
    from tkinter import ttk, filedialog

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)            # sharp text on scaled screens
    except Exception:
        pass
    root = tk.Tk()
    root.title(('%s Setup' if mode == 'install' else 'Uninstall %s') % FULL_NAME)
    root.configure(bg=C['bg'])
    root.resizable(False, False)
    ico = os.path.join(HERE, 'ardzy.ico')
    if os.path.exists(ico):
        root.iconbitmap(ico)
    scale = root.winfo_fpixels('1i') / 96
    W, H = int(640 * scale), int(430 * scale)
    root.geometry('%dx%d+%d+%d' % (W, H, (root.winfo_screenwidth() - W) // 2, (root.winfo_screenheight() - H) // 3))

    st = ttk.Style(root)
    st.theme_use('clam')
    font = ('Segoe UI', 10)
    st.configure('.', background=C['bg'], foreground=C['text'], font=font)
    # checkboxes drawn here: a green box with a white tick (on), a light box with a grey border (off)
    def box(on, n):
        im = tk.PhotoImage(width=n, height=n)
        b = max(1, n // 12)
        fill, edge = (C['accent'], C['accent']) if on else (C['panel'], '#9aa8a0')
        im.put(edge, to=(0, 0, n, n))
        im.put(fill, to=(b, b, n - b, n - b))
        if on:                                               # the tick: two strokes, about n/8 thick
            t = max(2, n // 8)
            pts = [(n * 0.22 + i * 0.01 * n, n * 0.52 + i * 0.01 * n) for i in range(22)] + \
                  [(n * 0.44 + i * 0.01 * n, n * 0.74 - i * 0.0155 * n) for i in range(36)]
            for x, y in pts:
                im.put('white', to=(int(x), int(y - t / 2), int(x) + t, int(y + t / 2)))
        return im
    n = max(14, int(round(16 * scale)))
    root._boxes = (box(False, n), box(True, n))
    st.element_create('Ardzy.indicator', 'image', root._boxes[0], ('selected', root._boxes[1]),
                      width=n + int(9 * scale), sticky='w')
    st.layout('TCheckbutton', [('Checkbutton.padding', {'sticky': 'nswe', 'children': [
        ('Ardzy.indicator', {'side': 'left', 'sticky': ''}),
        ('Checkbutton.focus', {'side': 'left', 'sticky': 'w', 'children': [('Checkbutton.label', {'sticky': 'nswe'})]})]})])
    st.configure('TCheckbutton', background=C['bg'], foreground=C['text'], padding=(0, 3, 0, 3))
    st.map('TCheckbutton', background=[('active', C['bg'])])
    st.configure('Accent.TButton', background=C['accent'], foreground='white', borderwidth=0, padding=(18, 7),
                 font=('Segoe UI Semibold', 10))
    st.map('Accent.TButton', background=[('disabled', '#9fc9b0'), ('active', C['accent_dark'])])
    st.configure('TButton', padding=(14, 7), background=C['panel'], bordercolor=C['line'])
    st.map('TButton', background=[('active', '#e4ebe7')])
    st.configure('TEntry', fieldbackground=C['panel'], bordercolor=C['line'], padding=5)
    st.configure('green.Horizontal.TProgressbar', troughcolor='#e1e8e4', background=C['accent'], bordercolor=C['line'],
                 lightcolor=C['accent'], darkcolor=C['accent'], thickness=int(10 * scale))

    # header: icon, name, version
    head = tk.Frame(root, bg=C['head'], height=int(84 * scale))
    head.pack(fill='x')
    head.pack_propagate(False)
    png = os.path.join(HERE, 'icon.png')
    if os.path.exists(png):
        img = tk.PhotoImage(file=png)                        # (128 px: made smaller to about 52 px at 100 %)
        k = max(1, int(round(img.width() / (52 * scale))))
        img = img.subsample(k) if k > 1 else img
        root._img = img
        tk.Label(head, image=img, bg=C['head']).pack(side='left', padx=(int(22 * scale), int(12 * scale)))
    tbox = tk.Frame(head, bg=C['head'])
    tbox.pack(side='left', fill='y', pady=int(16 * scale))
    tk.Label(tbox, text=FULL_NAME, bg=C['head'], fg=C['head_text'], font=('Segoe UI Semibold', 17)).pack(anchor='w')
    tk.Label(tbox, text='Zynq boards (Antminer S9) used like an Arduino', bg=C['head'], fg='#9fbfac',
             font=('Segoe UI', 10)).pack(anchor='w')
    tk.Frame(root, bg=C['accent'], height=max(2, int(3 * scale))).pack(fill='x')

    body = tk.Frame(root, bg=C['bg'])
    body.pack(fill='both', expand=True, padx=int(26 * scale), pady=(int(18 * scale), 0))
    foot = tk.Frame(root, bg=C['bg'])
    foot.pack(fill='x', padx=int(26 * scale), pady=int(18 * scale))
    state = {'result': 1}

    def clear():
        for w in body.winfo_children():
            w.destroy()
        for w in foot.winfo_children():
            w.destroy()

    def text(t, muted=False, size=10, wrap=True, **kw):
        lab = tk.Label(body, text=t, bg=C['bg'], fg=C['muted'] if muted else C['text'], font=('Segoe UI', size),
                       justify='left', anchor='w', wraplength=int(580 * scale) if wrap else 0)
        lab.pack(anchor='w', fill='x', **kw)
        return lab

    def close(code):
        state['result'] = code
        root.destroy()

    def progress_page(title):
        clear()
        text(title, size=12, pady=(0, 10))
        bar = ttk.Progressbar(body, style='green.Horizontal.TProgressbar', mode='determinate', maximum=1000)
        bar.pack(fill='x', pady=(6, 8))
        lab = text('', muted=True)
        return bar, lab

    def run_job(job, title, done_page):
        bar, lab = progress_page(title)
        q = {'f': 0, 't': '', 'end': None}

        def worker():
            try:
                q['end'] = ('ok', job(lambda f, t: q.update(f=f, t=t)))
            except Exception as e:
                q['end'] = ('err', e)
        threading.Thread(target=worker, daemon=True).start()

        def tick():
            bar['value'] = int(q['f'] * 1000)
            lab['text'] = q['t'][:90]
            if q['end'] is None:
                return root.after(60, tick)
            kind, val = q['end']
            if kind == 'ok':
                done_page(val)
            else:
                error_page(val)
        tick()

    def error_page(err):
        clear()
        text('Something went wrong', size=12, pady=(0, 8))
        tk.Label(body, text=str(err), bg=C['bg'], fg=C['err'], font=font, justify='left', anchor='w',
                 wraplength=int(580 * scale)).pack(anchor='w', fill='x')
        ttk.Button(foot, text='Close', command=lambda: close(1)).pack(side='right')
        ttk.Button(foot, text='Try again', style='Accent.TButton',
                   command=lambda: (install_page() if mode == 'install' else uninstall_page())).pack(side='right', padx=8)

    # ---------------- installing
    def install_page():
        clear()
        old_dir, old_ver = installed()
        text('Welcome', size=13, pady=(0, 4))
        if old_dir and os.path.exists(os.path.join(old_dir, MARKER)):
            if old_ver == META['version']:
                msg = '%s is already installed. Setup installs it again (this repairs it).' % FULL_NAME
            else:
                msg = 'Ardzy %s is installed. Setup updates it to %s.' % (old_ver, FULL_NAME.replace(APP + ' ', ''))
            text(msg + ' Your projects and settings stay as they are.', muted=True, pady=(0, 12))
        else:
            ws = workspace()
            text('Setup puts Ardzy on this PC for you (no administrator rights needed). ' +
                 ('Your projects in %s and your settings stay as they are.' % ws if ws else
                  'Your projects go to Documents\\Ardzy, your settings to your Windows profile.'), muted=True, pady=(0, 12))
        text('Folder', pady=(0, 3))
        row = tk.Frame(body, bg=C['bg'])
        row.pack(fill='x', pady=(0, 12))
        var = tk.StringVar(value=old_dir or folder or default_dir())
        ttk.Entry(row, textvariable=var).pack(side='left', fill='x', expand=True)

        def browse():
            d = filedialog.askdirectory(initialdir=os.path.dirname(var.get()) or os.path.expanduser('~'), title='Folder for Ardzy')
            if d:
                d = os.path.normpath(d)
                var.set(d if os.path.basename(d).lower() == APP.lower() else os.path.join(d, APP))
        ttk.Button(row, text='Change ...', command=browse).pack(side='left', padx=(8, 0))
        v_start, v_desk, v_run = tk.BooleanVar(value=True), tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        ttk.Checkbutton(body, text='Shortcut in the Start menu', variable=v_start).pack(anchor='w', pady=2)
        ttk.Checkbutton(body, text='Shortcut on the Desktop', variable=v_desk).pack(anchor='w', pady=2)
        ttk.Checkbutton(body, text='Start Ardzy when Setup is done', variable=v_run).pack(anchor='w', pady=2)
        size = sum(i.file_size for i in zipfile.ZipFile(PAYLOAD).infolist()) if os.path.exists(PAYLOAD) else 0
        tk.Label(foot, text='Needs %d MB on the disk' % (size >> 20), bg=C['bg'], fg=C['muted'], font=font).pack(side='left')

        def go():
            target = os.path.abspath(var.get().strip())
            why = folder_problem(target)
            if why:
                return error_page(why)
            if app_running(target):
                return error_page('Ardzy is running from this folder. Close Ardzy, then press Try again.')
            run_job(lambda p: install(target, v_desk.get(), v_start.get(), p), 'Installing %s ...' % FULL_NAME,
                    lambda exe: finished(exe, v_run.get()))
        ttk.Button(foot, text='Cancel', command=lambda: close(1)).pack(side='right')
        ttk.Button(foot, text='Install', style='Accent.TButton', command=go).pack(side='right', padx=8)

    def finished(exe, run):
        clear()
        text('Ardzy is installed', size=13, pady=(0, 6))
        text('Start it from the Start menu or the Desktop shortcut. To remove it later: Windows Settings, Apps, '
             'Installed apps, Ardzy.', muted=True, pady=(0, 10))
        text('Folder: ' + os.path.dirname(exe), muted=True)
        state['result'] = 0

        def done():
            if run:
                launch(exe)
            close(0)
        ttk.Button(foot, text='Finish', style='Accent.TButton', command=done).pack(side='right')

    # ---------------- removing
    def uninstall_page():
        clear()
        f = folder or installed()[0]
        if not f or not os.path.exists(os.path.join(f, MARKER)):
            text('Ardzy is not installed for this Windows user.', size=12)
            ttk.Button(foot, text='Close', command=lambda: close(1)).pack(side='right')
            return
        text('Remove Ardzy from this PC?', size=13, pady=(0, 6))
        text('The app and its shortcuts are removed. Your projects always stay%s.' % (' (%s)' % workspace() if workspace() else ''),
             muted=True, pady=(0, 8))
        text('App folder: ' + f, muted=True, pady=(0, 12))
        v_set = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text='Also remove my Ardzy settings (window, editor, boards)', variable=v_set).pack(anchor='w')
        text(settings_dir(), muted=True, size=9, padx=(int(25 * scale), 0))

        def go():
            if app_running(f, ignore=(UNINSTALLER,)):
                return error_page('Ardzy is running. Close it, then press Try again.')
            run_job(lambda p: uninstall(f, v_set.get(), p), 'Removing Ardzy ...', lambda _: removed())
        ttk.Button(foot, text='Cancel', command=lambda: close(1)).pack(side='right')
        ttk.Button(foot, text='Remove', style='Accent.TButton', command=go).pack(side='right', padx=8)

    def removed():
        clear()
        text('Ardzy is removed', size=13, pady=(0, 6))
        ws = workspace()
        text(('Your projects are still in %s.' % ws) if ws else 'Your projects are still there.', muted=True)
        state['result'] = 0
        ttk.Button(foot, text='Close', style='Accent.TButton', command=lambda: close(0)).pack(side='right')

    # keys: Enter = the green button of the page, Esc = Cancel / Close (nothing while it works)
    def key(primary):
        for w in foot.winfo_children():
            if isinstance(w, ttk.Button) and str(w.cget('state')) != 'disabled':
                is_primary = str(w.cget('style')) == 'Accent.TButton'
                if is_primary == primary and (primary or w.cget('text') in ('Cancel', 'Close')):
                    w.invoke()
                    return 'break'
    root.bind('<Return>', lambda e: key(True))
    root.bind('<KP_Enter>', lambda e: key(True))
    root.bind('<Escape>', lambda e: key(False))
    install_page() if mode == 'install' else uninstall_page()
    root.protocol('WM_DELETE_WINDOW', lambda: close(state['result']))
    root.after(150, lambda: (root.lift(), root.focus_force()))      # in front, with the keyboard
    root.mainloop()
    return state['result']


# ------------------------------------------------------------------ start
LOG = os.path.join(tempfile.gettempdir(), 'ardzy-setup.log')


def say(text):
    """A message of the silent mode. This is a window program: it has no console (sys.stderr is None),
    so the message goes to %TEMP%/ardzy-setup.log (and to the console when there is one)."""
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write('%s  %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), text.rstrip('\n')))
    except OSError:
        pass
    if sys.stderr is not None:
        try:
            sys.stderr.write(text)
        except Exception:
            pass


def arg(name):
    for a in sys.argv[1:]:
        if a.upper().startswith('/' + name + '='):
            return a.split('=', 1)[1]
    return None


def flag(name):
    return any(a.upper() == '/' + name for a in sys.argv[1:])


def main():
    uninstall_mode = flag('UNINSTALL') or 'uninstall' in os.path.basename(sys.executable).lower()
    silent = flag('S')
    folder = arg('DIR')
    if uninstall_mode:
        # which Ardzy: /DIR, else the folder this uninstaller is in (Settings > Apps starts the one of that
        # install), and only without either the one in the Apps entry
        here = os.path.dirname(os.path.abspath(sys.executable))
        folder = folder or (here if os.path.exists(os.path.join(here, MARKER)) else None) or installed()[0] or here
        me = os.path.abspath(sys.executable)
        # running from the folder it removes: work from a copy in %TEMP% (the copy goes a moment later)
        if getattr(sys, 'frozen', False) and os.path.dirname(me).lower() == os.path.abspath(folder).lower() and not flag('FROMTEMP'):
            tmp = os.path.join(tempfile.mkdtemp(prefix='ardzy-un-'), UNINSTALLER)
            shutil.copy2(me, tmp)
            args = [tmp, '/UNINSTALL', '/FROMTEMP', '/DIR=' + folder] + [a for a in sys.argv[1:] if a.upper() in ('/S', '/REMOVESETTINGS')]
            launch_env = {k: v for k, v in os.environ.items() if not k.startswith(('_MEI', '_PYI'))}
            launch_env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
            try:
                ctypes.windll.kernel32.SetDllDirectoryW(None)
            except Exception:
                pass
            p = subprocess.Popen(args, env=launch_env)
            if silent:                        # a silent caller waits for the real result
                return p.wait()
            return 0
        try:
            if silent:
                uninstall(folder, flag('REMOVESETTINGS'))
                code = 0
            else:
                code = run_gui('uninstall', folder)
        except RuntimeError:
            code = 2
        except Exception as e:
            say(str(e) + '\n')
            code = 1
        if flag('FROMTEMP'):
            delete_later(me)
        return code
    if not os.path.exists(PAYLOAD):
        say('this Setup has no app inside (payload.zip missing)\n')
        return 1
    if silent:
        try:
            exe = install(folder or installed()[0] or default_dir(), not flag('NODESKTOP'), not flag('NOSTARTMENU'))
        except RuntimeError as e:
            say(str(e) + '\n')
            return 2
        except Exception as e:
            say(str(e) + '\n')
            return 1
        if flag('RUN'):
            launch(exe)
        return 0
    return run_gui('install', folder)


if __name__ == '__main__':
    try:
        code = main()
    except Exception:                        # never an error box that waits for a click (silent mode, scripts)
        import traceback
        say(traceback.format_exc())
        code = 1
    sys.exit(code)
