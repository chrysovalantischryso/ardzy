# blink.s - the first RISC-V program: a light running over the 4 board LEDs, and a greeting.
# Devices: 0x80000000 LEDS, 0x80000010 CONSOLE, 0x8000001C MICROS (microseconds since the start)
.equ LEDS,    0x80000000
.equ CONSOLE, 0x80000010
.equ MICROS,  0x8000001C

        li   sp, 0x4000            # stack at the top of the 16 KB RAM
        la   a0, hello
        call print
        li   s0, LEDS
        li   s1, MICROS
        li   s2, 1                 # LED pattern
        li   s3, 40                # how many steps
step:   sw   s2, 0(s0)
        lw   t0, 0(s1)             # wait 150 ms using the microsecond counter
        li   t1, 150000
        add  t1, t0, t1
wait:   lw   t0, 0(s1)
        blt  t0, t1, wait
        slli s2, s2, 1             # next LED
        andi t2, s2, 16
        beqz t2, nowrap
        li   s2, 1
nowrap: addi s3, s3, -1
        bnez s3, step
        sw   zero, 0(s0)
        la   a0, bye
        call print
        ebreak                     # stop

# print: write the 0-terminated text at a0 to the console
print:  li   t0, CONSOLE
1:      lbu  t1, 0(a0)
        beqz t1, 2f
        sw   t1, 0(t0)
        addi a0, a0, 1
        j    1b
2:      ret

hello:  .asciz "Hello from the RISC-V inside the FPGA!\n"
bye:    .asciz "Blinked 40 times, bye.\n"
