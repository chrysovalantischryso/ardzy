"""Runs the Ardzy app's system update code against an emulated Ardzy 1.0 board
(scripts/test_legacy_update_qemu.sh start, web API forwarded to 127.0.0.1:8080)."""
import glob, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import ardzy_app  # noqa: E402

ardzy_app.log = lambda msg, kind='': print('[%s] %s' % (kind or 'info', msg), flush=True)
ardzy_app.board.host, ardzy_app.board.port = '127.0.0.1', 8080
bundle = sorted(glob.glob(os.path.join(HERE, '..', '..', 'out', 'release', 'Ardzy-*-update.tar.gz')))[-1]
ok = ardzy_app.system_update(bundle)
print('RESULT', ok, ardzy_app.RESULTS.get('update'))
leftover = ardzy_app.board.call('GET', '/api/status')
print('projects on the board:', leftover.get('projects', leftover)[:10] if isinstance(leftover.get('projects'), list) else '')
sys.exit(0 if ok else 1)
