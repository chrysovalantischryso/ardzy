# 10 RISC-V demo: assembles the .s programs of this project on the ARM, loads them into the RISC-V's RAM
# and runs them. Write your own: copy blink.s, change it, and add its name to PROGRAMS.
import os
import time
from blocks import Bus, RiscV, require
from riscv import assemble, AsmError

PROGRAMS = ['blink.s', 'primes.s']
here = os.path.dirname(os.path.abspath(__file__))
bus = Bus()
require(bus, 'RV32')
rv = RiscV(bus, slot=1)


def run(name, mail=0, timeout=30):
    try:
        words, labels = assemble(open(os.path.join(here, name)).read())
    except AsmError as e:
        print('%s: %s' % (name, e))
        return
    print('== %s: %d instructions / words, loaded at address 0' % (name, len(words)), flush=True)
    rv.load(words)
    rv.w(5, mail)                                  # MAIL_IN: what the program reads at 0x80000014
    t = time.time()
    rv.start()
    out = ''
    while time.time() - t < timeout:
        text = rv.console()
        if text:
            print(text, end='', flush=True)
        if rv.status()['halted']:
            break
        time.sleep(0.02)
    print(rv.console(), end='')
    st = rv.status()
    print('   stopped after %.2f s, %d instructions%s' % (time.time() - t, st['retired'],
                                                          ' (ILLEGAL instruction at 0x%x)' % st['pc'] if st['illegal'] else ''), flush=True)


def python_primes(n):
    sieve, count = bytearray(n), 0
    for i in range(2, n):
        if not sieve[i]:
            count += 1
            for j in range(2 * i, n, i):
                sieve[j] = 1
    return count


for name in PROGRAMS:
    run(name, mail=12000 if name == 'primes.s' else 0)
t = time.time()
c = python_primes(12000)
print('The same sieve in Python on the 667 MHz ARM: %d primes in %.0f ms' % (c, (time.time() - t) * 1000))
