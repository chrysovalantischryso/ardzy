"""riscv.py - a small RISC-V (RV32I) assembler and simulator for the Ardzy RISC-V project.

    from riscv import assemble, Sim
    words, labels = assemble(open('blink.s').read())
    sim = Sim(words); sim.run(); print(sim.console)

Assembler: every RV32I instruction, labels, comments (# or //), registers x0..x31 and the ABI names
(zero ra sp gp tp t0-t6 s0-s11 fp a0-a7), numbers (decimal, 0x hex, 0b binary, 'c' characters),
label + / - number, and these helpers:
    li rd, value      la rd, label      mv  not  neg  j  jr  ret  call  nop  seqz  snez
    beqz bnez blez bgez bltz bgtz  bgt ble bgtu bleu
    .word a, b, ...   .byte ...   .ascii "text"   .asciz "text"   .align n   .equ NAME, value   .space n
Loads / stores:  lw rd, offset(rs1)   sw rs2, offset(rs1)   (and lb lh lbu lhu sb sh)
The program starts at address 0; RAM is 16 KB (0x0000 .. 0x3FFF).
"""
import re

REGS = {'zero': 0, 'ra': 1, 'sp': 2, 'gp': 3, 'tp': 4, 't0': 5, 't1': 6, 't2': 7, 's0': 8, 'fp': 8, 's1': 9,
        'a0': 10, 'a1': 11, 'a2': 12, 'a3': 13, 'a4': 14, 'a5': 15, 'a6': 16, 'a7': 17, 's2': 18, 's3': 19,
        's4': 20, 's5': 21, 's6': 22, 's7': 23, 's8': 24, 's9': 25, 's10': 26, 's11': 27, 't3': 28, 't4': 29,
        't5': 30, 't6': 31}
for _i in range(32):
    REGS['x%d' % _i] = _i

R = {'add': (0, 0), 'sub': (0, 0x20), 'sll': (1, 0), 'slt': (2, 0), 'sltu': (3, 0), 'xor': (4, 0), 'srl': (5, 0),
     'sra': (5, 0x20), 'or': (6, 0), 'and': (7, 0)}
I = {'addi': 0, 'slti': 2, 'sltiu': 3, 'xori': 4, 'ori': 6, 'andi': 7}
SH = {'slli': (1, 0), 'srli': (5, 0), 'srai': (5, 0x20)}
LOADS = {'lb': 0, 'lh': 1, 'lw': 2, 'lbu': 4, 'lhu': 5}
STORES = {'sb': 0, 'sh': 1, 'sw': 2}
BR = {'beq': 0, 'bne': 1, 'blt': 4, 'bge': 5, 'bltu': 6, 'bgeu': 7}


class AsmError(Exception):
    pass


def _strip(line):
    out, q = [], False
    i = 0
    while i < len(line):
        c = line[i]
        if c == '"':
            q = not q
        if not q and (c == '#' or line.startswith('//', i) or c == ';'):
            break
        out.append(c)
        i += 1
    return ''.join(out).strip()


def _split_args(s):
    parts, cur, q = [], '', False
    for c in s:
        if c == '"':
            q = not q
        if c == ',' and not q:
            parts.append(cur.strip())
            cur = ''
        else:
            cur += c
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _string(s):
    s = s.strip()
    if not (s.startswith('"') and s.endswith('"')):
        raise AsmError('string expected: %s' % s)
    return s[1:-1].encode('latin-1').decode('unicode_escape').encode('latin-1')


class Assembler:
    def __init__(self, text):
        self.lines = text.split('\n')
        self.labels, self.equ = {}, {}
        self.local = {}           # numeric local labels: '1' -> [addresses], used as 1b (back) / 1f (forward)
        self.pc = 0

    def local_label(self, n, d):
        addrs = self.local.get(n, [])
        if d == 'b':
            c = [a for a in addrs if a <= self.pc]
            return max(c) if c else None
        c = [a for a in addrs if a > self.pc]
        return min(c) if c else None

    def value(self, s, final):
        s = s.strip()
        m = re.fullmatch(r"'(\\?.)'", s)
        if m:
            return ord(m.group(1).encode().decode('unicode_escape'))
        terms = re.findall(r'[+-]?\s*[^+-]+', s.replace(' ', ''))
        total = 0
        for t in terms:
            sign = -1 if t.startswith('-') else 1
            t = t.lstrip('+-')
            lm = re.fullmatch(r'(\d+)([bf])', t)
            if lm:
                v = self.local_label(lm.group(1), lm.group(2))
                if v is None:
                    if final:
                        raise AsmError('no local label %s%s' % (lm.group(1), ' before' if lm.group(2) == 'b' else ' after'))
                    v = 0
            elif re.fullmatch(r'0[xX][0-9a-fA-F_]+|0[bB][01_]+|\d+', t):
                v = int(t.replace('_', ''), 0)
            elif t in self.equ:
                v = self.equ[t]
            elif t in self.labels:
                v = self.labels[t]
            elif not final and re.fullmatch(r'[A-Za-z_.][\w.]*', t):
                v = 0
            else:
                raise AsmError('unknown value: %s' % t)
            total += sign * v
        return total

    def reg(self, s):
        s = s.strip().lower()
        if s not in REGS:
            raise AsmError('not a register: %s' % s)
        return REGS[s]

    def mem(self, s, final):
        m = re.fullmatch(r'(.*)\((\w+)\)', s.strip())
        if not m:
            raise AsmError('memory operand like 8(sp) expected: %s' % s)
        return (self.value(m.group(1), final) if m.group(1).strip() else 0), self.reg(m.group(2))

    def li_words(self, arg):
        """li is 1 word for small plain numbers, else 2 (always 2 when a label is used, so the size is
        the same in both passes)."""
        if re.search(r'[A-Za-z_.]', re.sub(r"0[xXbB][0-9a-fA-F_]+|'.*'", '', arg)) and \
                not all(t in self.equ for t in re.findall(r'[A-Za-z_.][\w.]*', re.sub(r"0[xXbB][0-9a-fA-F_]+|'.*'", '', arg))):
            return 2
        v = self.value(arg, False) & 0xFFFFFFFF
        sv = v - (1 << 32) if v & 0x80000000 else v
        return 1 if -2048 <= sv < 2048 else 2

    def run(self):
        for final in (False, True):
            pc, out = 0, bytearray()
            for no, raw in enumerate(self.lines, 1):
                line = _strip(raw)
                try:
                    while True:
                        m = re.match(r'([A-Za-z_.][\w.]*|\d+):\s*', line)
                        if not m:
                            break
                        if not final:
                            if m.group(1).isdigit():
                                self.local.setdefault(m.group(1), []).append(pc)
                            elif m.group(1) in self.labels:
                                raise AsmError('label twice: %s' % m.group(1))
                            else:
                                self.labels[m.group(1)] = pc
                        line = line[m.end():]
                    self.pc = pc
                    if not line:
                        continue
                    op, _, rest = line.partition(' ')
                    op = op.lower()
                    args = _split_args(rest)
                    data = self.encode(op, args, pc, final)
                    if final:
                        out += data
                    pc += len(data)
                except AsmError as e:
                    raise AsmError('line %d: %s  (%s)' % (no, e, raw.strip()))
                except (IndexError, ValueError) as e:
                    raise AsmError('line %d: bad instruction (%s)' % (no, raw.strip()))
        while len(out) % 4:
            out.append(0)
        words = [int.from_bytes(out[i:i + 4], 'little') for i in range(0, len(out), 4)]
        return words, self.labels

    # ---------------------------------------------------------------- encoders
    @staticmethod
    def _r(f7, rs2, rs1, f3, rd, opc):
        return (f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | opc

    @staticmethod
    def _i(imm, rs1, f3, rd, opc):
        if not -2048 <= imm < 2048:
            raise AsmError('number does not fit in 12 bits: %d' % imm)
        return ((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | opc

    @staticmethod
    def _s(imm, rs2, rs1, f3):
        if not -2048 <= imm < 2048:
            raise AsmError('offset does not fit in 12 bits: %d' % imm)
        imm &= 0xFFF
        return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | ((imm & 31) << 7) | 0x23

    @staticmethod
    def _b(off, rs2, rs1, f3, final):
        if final and (not -4096 <= off < 4096 or off & 1):
            raise AsmError('branch too far: %d' % off)
        o = off & 0x1FFF
        return (((o >> 12) & 1) << 31) | (((o >> 5) & 63) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | \
               (((o >> 1) & 15) << 8) | (((o >> 11) & 1) << 7) | 0x63

    @staticmethod
    def _j(off, rd, final):
        if final and (not -(1 << 20) <= off < (1 << 20) or off & 1):
            raise AsmError('jump too far: %d' % off)
        o = off & 0x1FFFFF
        return (((o >> 20) & 1) << 31) | (((o >> 1) & 1023) << 21) | (((o >> 11) & 1) << 20) | \
               (((o >> 12) & 255) << 12) | (rd << 7) | 0x6F

    def _li(self, rd, v):
        v &= 0xFFFFFFFF
        sv = v - (1 << 32) if v & 0x80000000 else v
        if -2048 <= sv < 2048:
            return [self._i(sv, 0, 0, rd, 0x13)]
        lo = sv & 0xFFF
        if lo >= 2048:
            lo -= 4096
        hi = ((v - lo) >> 12) & 0xFFFFF
        return [(hi << 12) | (rd << 7) | 0x37, self._i(lo, rd, 0, rd, 0x13)]

    def encode(self, op, a, pc, final):
        W = lambda *ws: b''.join((w & 0xFFFFFFFF).to_bytes(4, 'little') for w in ws)
        v = lambda s: self.value(s, final)
        if op == '.equ':
            self.equ[a[0]] = v(a[1])
            return b''
        if op == '.word':
            return W(*[v(x) for x in a])
        if op == '.byte':
            return bytes(v(x) & 255 for x in a)
        if op in ('.ascii', '.asciz', '.string'):
            return _string(a[0]) + (b'\0' if op != '.ascii' else b'')
        if op == '.align':
            n = 1 << v(a[0])
            return bytes((-pc) % n)
        if op == '.space':
            return bytes(v(a[0]))
        if op in R:
            f3, f7 = R[op]
            return W(self._r(f7, self.reg(a[2]), self.reg(a[1]), f3, self.reg(a[0]), 0x33))
        if op in I:
            return W(self._i(v(a[2]), self.reg(a[1]), I[op], self.reg(a[0]), 0x13))
        if op in SH:
            f3, f7 = SH[op]
            sh = v(a[2])
            if not 0 <= sh < 32:
                raise AsmError('shift 0..31')
            return W((f7 << 25) | (sh << 20) | (self.reg(a[1]) << 15) | (f3 << 12) | (self.reg(a[0]) << 7) | 0x13)
        if op in LOADS:
            off, rs1 = self.mem(a[1], final)
            return W(self._i(off, rs1, LOADS[op], self.reg(a[0]), 0x03))
        if op in STORES:
            off, rs1 = self.mem(a[1], final)
            return W(self._s(off, self.reg(a[0]), rs1, STORES[op]))
        if op in BR:
            return W(self._b(v(a[2]) - pc, self.reg(a[1]), self.reg(a[0]), BR[op], final))
        if op == 'lui':
            return W(((v(a[1]) & 0xFFFFF) << 12) | (self.reg(a[0]) << 7) | 0x37)
        if op == 'auipc':
            return W(((v(a[1]) & 0xFFFFF) << 12) | (self.reg(a[0]) << 7) | 0x17)
        if op == 'jal':
            if len(a) == 1:
                return W(self._j(v(a[0]) - pc, 1, final))
            return W(self._j(v(a[1]) - pc, self.reg(a[0]), final))
        if op == 'jalr':
            if len(a) == 1:
                return W(self._i(0, self.reg(a[0]), 0, 1, 0x67))
            if '(' in a[1]:
                off, rs1 = self.mem(a[1], final)
            else:
                rs1, off = self.reg(a[1]), (v(a[2]) if len(a) > 2 else 0)
            return W(self._i(off, rs1, 0, self.reg(a[0]), 0x67))
        if op in ('ecall', 'ebreak'):
            return W(0x73 if op == 'ecall' else 0x100073)
        if op == 'fence':
            return W(0x0FF0000F)
        # helpers
        if op == 'nop':
            return W(0x13)
        if op == 'li':
            n = self.li_words(a[1])
            if not final:
                return bytes(4 * n)
            ws = self._li(self.reg(a[0]), v(a[1]))
            if len(ws) < n:                                         # a label that turned out small
                ws = [(self.reg(a[0]) << 7) | 0x37, self._i(v(a[1]), self.reg(a[0]), 0, self.reg(a[0]), 0x13)]
            return W(*ws)
        if op == 'la':
            if not final:
                return bytes(8)
            ws = self._li(self.reg(a[0]), v(a[1]))
            return W(*(ws if len(ws) == 2 else ws + [0x13]))
        if op == 'mv':
            return W(self._i(0, self.reg(a[1]), 0, self.reg(a[0]), 0x13))
        if op == 'not':
            return W(self._i(-1, self.reg(a[1]), 4, self.reg(a[0]), 0x13))
        if op == 'neg':
            return W(self._r(0x20, self.reg(a[1]), 0, 0, self.reg(a[0]), 0x33))
        if op == 'seqz':
            return W(self._i(1, self.reg(a[1]), 3, self.reg(a[0]), 0x13))
        if op == 'snez':
            return W(self._r(0, self.reg(a[1]), 0, 3, self.reg(a[0]), 0x33))
        if op == 'j':
            return W(self._j(v(a[0]) - pc, 0, final))
        if op == 'jr':
            return W(self._i(0, self.reg(a[0]), 0, 0, 0x67))
        if op == 'ret':
            return W(0x00008067)
        if op == 'call':
            return W(self._j(v(a[0]) - pc, 1, final))
        # compare with zero: (branch, register goes first) -> branch rs1, rs2
        z = {'beqz': ('beq', True), 'bnez': ('bne', True), 'bgez': ('bge', True), 'bltz': ('blt', True),
             'blez': ('bge', False), 'bgtz': ('blt', False)}       # blez r = bge x0, r ; bgtz r = blt x0, r
        if op in z:
            base, reg_first = z[op]
            r = self.reg(a[0])
            rs1, rs2 = (r, 0) if reg_first else (0, r)
            return W(self._b(v(a[1]) - pc, rs2, rs1, BR[base], final))
        sw = {'bgt': 'blt', 'ble': 'bge', 'bgtu': 'bltu', 'bleu': 'bgeu'}
        if op in sw:
            return W(self._b(v(a[2]) - pc, self.reg(a[0]), self.reg(a[1]), BR[sw[op]], final))
        raise AsmError('unknown instruction: %s' % op)


def assemble(text):
    """Returns (list of 32-bit words, {label: address})."""
    return Assembler(text).run()


# ------------------------------------------------------------------------------------------ simulator
class Sim:
    """RV32I with the same memory map as the FPGA computer (RAM 16 KB, devices at 0x8000_0000)."""

    def __init__(self, words, mail_in=0, gpio_in=0):
        self.mem = bytearray(16384)
        for i, w in enumerate(words):
            self.mem[4 * i:4 * i + 4] = (w & 0xFFFFFFFF).to_bytes(4, 'little')
        self.x = [0] * 32
        self.pc = 0
        self.console = ''
        self.leds = self.gpio = self.mail_out = 0
        self.mail_in, self.gpio_in = mail_in, gpio_in
        self.cycles = 0
        self.halted = self.illegal = False
        self.retired = 0

    def ld(self, a, n):
        if a >= 0x80000000:
            reg = (a >> 2) & 15
            return {0: self.leds, 1: self.gpio, 2: self.gpio_in, 3: self.cycles & 0xFFFFFFFF, 5: self.mail_in,
                    6: self.mail_out, 7: self.cycles // 100}.get(reg, 0)
        a &= 0x3FFF
        return int.from_bytes(self.mem[a:a + n], 'little')

    def st(self, a, v, n):
        if a >= 0x80000000:
            reg = (a >> 2) & 15
            if reg == 0:
                self.leds = v & 15
            elif reg == 1:
                self.gpio = v & 15
            elif reg == 4:
                self.console += chr(v & 255)
            elif reg == 6:
                self.mail_out = v & 0xFFFFFFFF
            return
        a &= 0x3FFF
        self.mem[a:a + n] = (v & ((1 << (8 * n)) - 1)).to_bytes(n, 'little')

    def step(self):
        s = lambda v: v - (1 << 32) if v & 0x80000000 else v
        ir = self.ld(self.pc, 4)
        op, rd, f3, rs1, rs2, f7 = ir & 127, (ir >> 7) & 31, (ir >> 12) & 7, (ir >> 15) & 31, (ir >> 20) & 31, ir >> 25
        a, b = self.x[rs1], self.x[rs2]
        imm_i = s(ir) >> 20
        imm_s = (s(ir) >> 25 << 5) | ((ir >> 7) & 31)
        imm_b = (s(ir) >> 31 << 12) | (((ir >> 7) & 1) << 11) | (((ir >> 25) & 63) << 5) | (((ir >> 8) & 15) << 1)
        imm_u = ir & 0xFFFFF000
        imm_j = (s(ir) >> 31 << 20) | (((ir >> 12) & 255) << 12) | (((ir >> 20) & 1) << 11) | (((ir >> 21) & 1023) << 1)
        npc, wb = self.pc + 4, None
        M = 0xFFFFFFFF
        if op == 0x37:
            wb = imm_u
        elif op == 0x17:
            wb = (self.pc + imm_u) & M
        elif op == 0x6F:
            wb, npc = self.pc + 4, (self.pc + imm_j) & M
        elif op == 0x67:
            wb, npc = self.pc + 4, (a + imm_i) & M & ~1
        elif op == 0x63:
            t = {0: a == b, 1: a != b, 4: s(a) < s(b), 5: s(a) >= s(b), 6: a < b, 7: a >= b}.get(f3, False)
            if t:
                npc = (self.pc + imm_b) & M
        elif op in (0x13, 0x33):
            y = (imm_i & M) if op == 0x13 else b
            sh = y & 31
            if f3 == 0:
                wb = (a - y) if (op == 0x33 and f7 & 0x20) else (a + y)
            elif f3 == 1:
                wb = a << sh
            elif f3 == 2:
                wb = int(s(a) < s(y))
            elif f3 == 3:
                wb = int(a < y)
            elif f3 == 4:
                wb = a ^ y
            elif f3 == 5:
                wb = (s(a) >> sh) if f7 & 0x20 else (a >> sh)
            elif f3 == 6:
                wb = a | y
            else:
                wb = a & y
            wb &= M
        elif op == 0x03:
            addr = (a + imm_i) & M
            n = {0: 1, 1: 2, 2: 4, 4: 1, 5: 2}[f3]
            w = self.ld(addr & ~3, 4) >> (8 * (addr & 3)) if addr < 0x80000000 else self.ld(addr, 4)
            w &= (1 << (8 * n)) - 1
            if f3 in (0, 1) and w >> (8 * n - 1):
                w -= 1 << (8 * n)
            wb = w & M
        elif op == 0x23:
            addr = (a + imm_s) & M
            n = {0: 1, 1: 2, 2: 4}[f3]
            self.st(addr, b, n)
        elif op == 0x0F:
            pass
        else:
            self.halted = True
            self.illegal = not (op == 0x73 and f3 == 0)
            return False
        if wb is not None and rd:
            self.x[rd] = wb & M
        self.pc = npc
        self.retired += 1
        self.cycles += 5
        return True

    def run(self, max_steps=5_000_000):
        for _ in range(max_steps):
            if not self.step():
                return True
        return False
