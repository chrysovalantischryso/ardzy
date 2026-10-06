# primes.s - counts the prime numbers below N with the sieve of Eratosthenes and prints the count
# and the clock cycles it took. N comes from the mailbox (MAIL_IN), 10000 when it is 0.
# RV32I has no multiply / divide: the sieve needs only adds, and print_dec subtracts powers of ten.
.equ CONSOLE,  0x80000010
.equ MAIL_IN,  0x80000014
.equ MAIL_OUT, 0x80000018
.equ CYCLES,   0x8000000C
.equ SIEVE,    0x1000          # the sieve: one byte per number, from 0x1000 (N up to 12000)

        li   sp, 0x4000
        li   t0, MAIL_IN
        lw   s0, 0(t0)                 # s0 = N
        bnez s0, 1f
        li   s0, 10000
1:      li   t0, CYCLES
        lw   s5, 0(t0)                 # start time
        li   s1, SIEVE
        li   t1, 0                     # clear the sieve
clear:  add  t2, s1, t1
        sb   zero, 0(t2)
        addi t1, t1, 1
        blt  t1, s0, clear
        li   s2, 0                     # count
        li   t1, 2                     # i
next:   bge  t1, s0, done
        add  t2, s1, t1
        lbu  t3, 0(t2)
        bnez t3, skip                  # crossed out: not a prime
        addi s2, s2, 1
        add  t4, t1, t1                # cross out 2i, 3i, ...
mark:   bge  t4, s0, skip
        add  t2, s1, t4
        li   t5, 1
        sb   t5, 0(t2)
        add  t4, t4, t1
        j    mark
skip:   addi t1, t1, 1
        j    next
done:   li   t0, CYCLES
        lw   s6, 0(t0)
        sub  s6, s6, s5                # cycles used
        li   t0, MAIL_OUT
        sw   s2, 0(t0)
        la   a0, t_found
        call print
        mv   a0, s2
        call print_dec
        la   a0, t_below
        call print
        mv   a0, s0
        call print_dec
        la   a0, t_in
        call print
        mv   a0, s6
        call print_dec
        la   a0, t_cycles
        call print
        ebreak

# print the 0-terminated text at a0
print:  li   t0, CONSOLE
1:      lbu  t1, 0(a0)
        beqz t1, 2f
        sw   t1, 0(t0)
        addi a0, a0, 1
        j    1b
2:      ret

# print a0 as a decimal number (no division: subtract each power of ten)
print_dec:
        li   t0, CONSOLE
        la   t1, tens
        li   t4, 0                     # 1 once a digit was printed
1:      lw   t2, 0(t1)
        beqz t2, 4f
        li   t3, 0
2:      bltu a0, t2, 3f
        sub  a0, a0, t2
        addi t3, t3, 1
        j    2b
3:      or   t4, t4, t3
        beqz t4, 5f
        addi t3, t3, '0'
        sw   t3, 0(t0)
5:      addi t1, t1, 4
        j    1b
4:      bnez t4, 6f
        li   t3, '0'
        sw   t3, 0(t0)
6:      ret

        .align 2
tens:   .word 1000000000, 100000000, 10000000, 1000000, 100000, 10000, 1000, 100, 10, 1, 0
t_found:  .asciz "Found "
t_below:  .asciz " primes below "
t_in:     .asciz " in "
t_cycles: .asciz " clock cycles\n"
