# 10 RISC-V self-test: needs nothing connected. Every RV32I instruction type, then 2000 random
# arithmetic / logic instructions: the FPGA core and the simulator in riscv.py must end with the same
# registers and memory. Also the console, the mailboxes, the LEDs and the speed.
import random
import time
from blocks import Bus, RiscV, require
from riscv import assemble, Sim

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


DUMP = '''
dump:   li   t6, 0x3E00          # store x1..x30 at 0x3E04.. (t6 = x31 is the pointer)
        sw   x1, 4(t6)
        sw   x2, 8(t6)
        sw   x3, 12(t6)
        sw   x4, 16(t6)
        sw   x5, 20(t6)
        sw   x6, 24(t6)
        sw   x7, 28(t6)
        sw   x8, 32(t6)
        sw   x9, 36(t6)
        sw   x10, 40(t6)
        sw   x11, 44(t6)
        sw   x12, 48(t6)
        sw   x13, 52(t6)
        sw   x14, 56(t6)
        sw   x15, 60(t6)
        sw   x16, 64(t6)
        sw   x17, 68(t6)
        sw   x18, 72(t6)
        sw   x19, 76(t6)
        sw   x20, 80(t6)
        sw   x21, 84(t6)
        sw   x22, 88(t6)
        sw   x23, 92(t6)
        sw   x24, 96(t6)
        sw   x25, 100(t6)
        sw   x26, 104(t6)
        sw   x27, 108(t6)
        sw   x28, 112(t6)
        sw   x29, 116(t6)
        sw   x30, 120(t6)
        ebreak
'''

ISA = '''
        li   s0, 0x3000          # results go to 0x3000..
        li   a0, -7
        li   a1, 3
        li   a2, 0x80000000
        add  t0, a0, a1
        sw   t0, 0(s0)
        sub  t0, a0, a1
        sw   t0, 4(s0)
        sll  t0, a1, a1
        sw   t0, 8(s0)
        slt  t0, a0, a1
        sw   t0, 12(s0)
        sltu t0, a0, a1
        sw   t0, 16(s0)
        xor  t0, a0, a1
        sw   t0, 20(s0)
        srl  t0, a0, a1
        sw   t0, 24(s0)
        sra  t0, a0, a1
        sw   t0, 28(s0)
        or   t0, a0, a1
        sw   t0, 32(s0)
        and  t0, a0, a1
        sw   t0, 36(s0)
        addi t0, a0, -2048
        sw   t0, 40(s0)
        slti t0, a0, -6
        sw   t0, 44(s0)
        sltiu t0, a1, -1
        sw   t0, 48(s0)
        xori t0, a0, 0x7FF
        sw   t0, 52(s0)
        ori  t0, a1, -16
        sw   t0, 56(s0)
        andi t0, a0, 0x0F0
        sw   t0, 60(s0)
        slli t0, a1, 31
        sw   t0, 64(s0)
        srli t0, a2, 31
        sw   t0, 68(s0)
        srai t0, a2, 31
        sw   t0, 72(s0)
        srai t0, a2, 0
        sw   t0, 76(s0)
        lui  t0, 0xABCDE
        sw   t0, 80(s0)
        auipc t0, 1
        sw   t0, 84(s0)
        # bytes and halves: store at every offset, load signed and unsigned
        li   t1, 0x8899AABB
        sw   t1, 88(s0)
        sb   a0, 92(s0)
        sb   a1, 93(s0)
        sb   a0, 94(s0)
        sb   a1, 95(s0)
        sh   a0, 96(s0)
        sh   t1, 98(s0)
        lb   t0, 88(s0)
        sw   t0, 100(s0)
        lb   t0, 89(s0)
        sw   t0, 104(s0)
        lbu  t0, 90(s0)
        sw   t0, 108(s0)
        lbu  t0, 91(s0)
        sw   t0, 112(s0)
        lh   t0, 88(s0)
        sw   t0, 116(s0)
        lh   t0, 90(s0)
        sw   t0, 120(s0)
        lhu  t0, 90(s0)
        sw   t0, 124(s0)
        # branches: each taken branch adds a different bit
        li   t2, 0
        beq  a1, a1, 1f
        ori  t2, t2, 1
1:      bne  a1, a1, 2f
        ori  t2, t2, 2
2:      blt  a0, a1, 3f
        ori  t2, t2, 4
3:      bge  a0, a1, 4f
        ori  t2, t2, 8
4:      bltu a0, a1, 5f
        ori  t2, t2, 16
5:      bgeu a0, a1, 6f
        ori  t2, t2, 32
6:      sw   t2, 128(s0)
        # jumps and calls (recursion: sum 1..20 with the stack)
        li   sp, 0x3D00
        li   a0, 20
        call sum
        sw   a0, 132(s0)
        la   t3, target
        jalr t4, 0(t3)
        sw   t0, 136(s0)
        j    dump
target: li   t0, 1234
        jr   t4
sum:    beqz a0, 7f
        addi sp, sp, -8
        sw   ra, 0(sp)
        sw   a0, 4(sp)
        addi a0, a0, -1
        call sum
        lw   t5, 4(sp)
        add  a0, a0, t5
        lw   ra, 0(sp)
        addi sp, sp, 8
7:      ret
''' + DUMP


def random_program(n, seed):
    rnd = random.Random(seed)
    regs = ['x%d' % i for i in range(1, 31)]
    lines = ['        li %s, %d' % (r, rnd.getrandbits(32) - (1 << 31)) for r in regs]
    for _ in range(n):
        k = rnd.random()
        rd, r1, r2 = rnd.choice(regs), rnd.choice(regs), rnd.choice(regs)
        if k < 0.45:
            lines.append('        %s %s, %s, %s' % (rnd.choice(['add', 'sub', 'sll', 'slt', 'sltu', 'xor', 'srl', 'sra', 'or', 'and']), rd, r1, r2))
        elif k < 0.8:
            lines.append('        %s %s, %s, %d' % (rnd.choice(['addi', 'slti', 'sltiu', 'xori', 'ori', 'andi']), rd, r1, rnd.randint(-2048, 2047)))
        elif k < 0.95:
            lines.append('        %s %s, %s, %d' % (rnd.choice(['slli', 'srli', 'srai']), rd, r1, rnd.randint(0, 31)))
        else:
            lines.append('        lui %s, %d' % (rd, rnd.getrandbits(20)))
    return '\n'.join(lines) + '\n        j dump\n' + DUMP


def compare(name, src, timeout=5):
    words, _ = assemble(src)
    sim = Sim(words)
    sim.run()
    rv.load(words + [0] * (4096 - len(words)))
    rv.start()
    t = time.time()
    while not rv.status()['halted'] and time.time() - t < timeout:
        time.sleep(0.01)
    st = rv.status()
    bad = []
    for a in range(0x3000, 0x4000, 4):
        hw, sw = rv.peek(a), int.from_bytes(sim.mem[a:a + 4], 'little')
        if hw != sw:
            bad.append('0x%04x: fpga %08x sim %08x' % (a, hw, sw))
    # the core also counts the final ebreak as done, the simulator does not
    check(name, st['halted'] and not st['illegal'] and not bad and st['retired'] == sim.retired + 1,
          '%d instructions, %d memory words differ %s' % (st['retired'], len(bad), bad[:2]))


bus = Bus()
require(bus, 'RV32')
rv = RiscV(bus, slot=1)
check('RISC-V block answers', rv.r(9) == 0x52563332)
compare('every RV32I instruction type, results compared', ISA)
for seed in (1, 2):
    compare('1000 random instructions (seed %d)' % seed, random_program(1000, seed))

words, _ = assemble('''
        li t0, 0x80000010
        li t1, 'H'
        sw t1, 0(t0)
        li t1, 'i'
        sw t1, 0(t0)
        li t0, 0x80000014
        lw t1, 0(t0)
        addi t1, t1, 1
        li t0, 0x80000018
        sw t1, 0(t0)
        li t0, 0x80000000
        li t1, 9
        sw t1, 0(t0)
        ebreak
''')
rv.load(words)
rv.w(5, 41)
rv.start()
time.sleep(0.05)
check('console, mailboxes, LEDs', rv.console() == 'Hi' and rv.r(6) == 42 and (rv.r(8) >> 8) & 15 == 9,
      'mail out %d, LEDs %d' % (rv.r(6), (rv.r(8) >> 8) & 15))
words, _ = assemble('''
        li t0, 0
        li t1, 2000000
1:      addi t0, t0, 1
        bne t0, t1, 1b
        ebreak
''')
rv.load(words)
t = time.time()
rv.start()
while not rv.status()['halted']:
    time.sleep(0.005)
dt = time.time() - t
st = rv.status()
check('speed: 4 million instructions', st['retired'] == 4000004, '%.2f s = %.1f million instructions per second'
      % (dt, st['retired'] / dt / 1e6))
print('RESULT: %d of %d ok' % (sum(results), len(results)))
