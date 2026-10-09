@ __NAME__: ARM assembly on the Ardzy board (the Zynq's Cortex-A9, 32-bit ARM, Thumb-2).
@ Press Upload: it is assembled and linked on the board (gcc), then started; printf output shows up in the Monitor.
@ It uses the C library for printing and sleeping, so it stays short. Add .c files next to it and call
@ them, or call this code from C: gcc builds every .S, .s and .c of the project into one program.
@
@ What it does: counts 1, 2, 3 ... once a second and prints the count and its square,
@ the square worked out by the ARM's own multiply instruction (MUL).

        .syntax unified
        .thumb
        .text
        .global main
        .type   main, %function
main:
        push    {r4, r5, lr}            @ r4 = the count; keep r5 too, so the stack stays 8-byte aligned
        movs    r0, #0
        bl      fflush_all              @ make printf send each line at once
        movs    r4, #1
loop:
        mul     r2, r4, r4              @ r2 = count * count
        mov     r1, r4                  @ printf(fmt, count, square)
        ldr     r0, =fmt
        bl      printf
        movs    r0, #0
        bl      fflush_all
        movs    r0, #1                  @ sleep(1)
        bl      sleep
        adds    r4, r4, #1
        cmp     r4, #1000               @ stop after 1000 rounds
        ble     loop
        movs    r0, #0                  @ return 0
        pop     {r4, r5, pc}

@ fflush_all: fflush(NULL), every open output
        .type   fflush_all, %function
fflush_all:
        push    {r3, lr}
        movs    r0, #0
        bl      fflush
        pop     {r3, pc}

        .section .rodata
fmt:    .asciz  "__NAME__ (ARM assembly): %d squared is %d\n"
