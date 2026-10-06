"""ardzy_env: read and change U-Boot's settings file /boot/uboot.env from Linux.

The file is what U-Boot loads at power-on (and writes with saveenv): a CRC32 of the data area,
then name=value strings, each ending in a zero byte, then padding. Used for the safe kernel
update: ardzy_try=1 makes the next boot a trial; if Linux does not confirm it, U-Boot goes back
to the previous kernel (see boot.scr).
"""
import os, struct, zlib

PATH = '/boot/uboot.env'


def read(path=PATH):
    data = open(path, 'rb').read()
    crc, body = struct.unpack_from('<I', data, 0)[0], data[4:]
    if zlib.crc32(body) & 0xFFFFFFFF != crc:
        raise ValueError('%s: CRC does not match (damaged?)' % path)
    env, pos = {}, 0
    while pos < len(body) and body[pos] != 0:
        end = body.index(b'\0', pos)
        k, _, v = body[pos:end].decode('latin-1').partition('=')
        env[k] = v
        pos = end + 1
    pad = body[-1:] if body[-1:] in (b'\0', b'\xff') else b'\0'
    return env, len(data), pad


def write(env, path=PATH, size=None, pad=b'\0'):
    if size is None:
        size = os.path.getsize(path) if os.path.exists(path) else 0x20000
    body = b''.join(('%s=%s' % (k, v)).encode('latin-1') + b'\0' for k, v in env.items()) + b'\0'
    if len(body) > size - 4:
        raise ValueError('U-Boot settings too big')
    body = body + pad * (size - 4 - len(body))
    data = struct.pack('<I', zlib.crc32(body) & 0xFFFFFFFF) + body
    tmp = path + '.new'
    with open(tmp, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    os.sync()


def get(name, default=None, path=PATH):
    return read(path)[0].get(name, default)


def set(path=PATH, **values):
    env, size, pad = read(path)
    for k, v in values.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = str(v)
    write(env, path, size, pad)
