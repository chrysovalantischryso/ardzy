#!/usr/bin/env python3
"""Builds Documents/04_Board_Manual.html (the complete board reference manual).

Hand-written text lives in docs/board_manual_template.html. The tables that are easy to get
wrong by hand are generated here from data:
  @@MIO_GRID@@ @@MIO_TABLE@@   the 54 ARM-side pins (from schematic sheets 3, 4, 10, 11)
  @@CONN_TABLE@@ @@PL_TABLE@@  FPGA pins (from make_pins.py, the single source of truth)
Run: python scripts/make_board_manual.py
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_pins as P

# (MIO, function on this board, group, notes)
MIO = [
    (0, 'NAND CE#', 'nand', '20k pull-down: must be low for SD boot (schematic note), 1k pull-up on the net'),
    (1, 'NAND WP#', 'nand', '1k pull-up'),
    (2, 'NAND ALE', 'nand', 'boot strap JP1 (JTAG chain mode, 0 = cascade)'),
    (3, 'NAND WE#', 'nand', 'boot strap JP3 (boot device bit 0)'),
    (4, 'NAND I/O2', 'nand', 'boot strap JP2 (boot device bit 1)'),
    (5, 'NAND I/O0', 'nand', 'boot strap JP4 (boot device bit 2)'),
    (6, 'NAND I/O1', 'nand', 'strap: 20k pull-down = PLLs enabled'),
    (7, 'NAND CLE', 'nand', 'strap: 20k pull-down = bank 500 at 2.5/3.3 V'),
    (8, 'NAND RE#', 'nand', 'strap: 20k pull-down = bank 501 at 2.5/3.3 V'),
    (9, 'NAND I/O4', 'nand', ''), (10, 'NAND I/O5', 'nand', ''), (11, 'NAND I/O6', 'nand', ''),
    (12, 'NAND I/O7', 'nand', ''), (13, 'NAND I/O3', 'nand', ''),
    (14, 'NAND R/B#', 'nand', '1k pull-up'),
    (15, 'LED D2 (green)', 'misc', 'active low, 220 ohm to 3.3 V; ardzy.led("ps")'),
    (16, 'ETH TX_CLK', 'eth', 'RGMII to PHY U8'), (17, 'ETH TXD0', 'eth', ''), (18, 'ETH TXD1', 'eth', ''),
    (19, 'ETH TXD2', 'eth', ''), (20, 'ETH TXD3', 'eth', ''), (21, 'ETH TX_CTL', 'eth', ''),
    (22, 'ETH RX_CLK', 'eth', ''), (23, 'ETH RXD0', 'eth', '33 ohm series'), (24, 'ETH RXD1', 'eth', '33 ohm series'),
    (25, 'ETH RXD2', 'eth', '33 ohm series'), (26, 'ETH RXD3', 'eth', '33 ohm series'), (27, 'ETH RX_CTL', 'eth', ''),
] + [(27 + n, 'EN%d (J%d pin 18)' % (n, n), 'io',
      'muxed to I2C1 by the boot loader' if n in (1, 2) else 'free ARM GPIO, 2.5 V') for n in range(1, 10)] + [
    (37, 'LED D3 red', 'misc', 'via transistor Q3, active high; ardzy.led("red")'),
    (38, 'LED D3 green', 'misc', 'via transistor Q2, active high; ardzy.led("green") = Ardzy ready'),
    (39, 'Buzzer BZ1', 'misc', 'via transistor Q1 (MMBT3904), active high; ardzy.beep()'),
    (40, 'SD CLK', 'sd', 'via level shifter U6, 33 ohm series'), (41, 'SD CMD', 'sd', 'via U6'),
    (42, 'SD DAT0', 'sd', 'via U6'), (43, 'SD DAT1', 'sd', 'via U6'), (44, 'SD DAT2', 'sd', 'via U6'),
    (45, 'SD DAT3', 'sd', 'via U6'),
    (46, 'SD card detect', 'sd', '4.7k pull-up to 2.5 V, card switch to GND'),
    (47, 'Button S1 "Reset"', 'misc', '4.7k pull-up, pressed = 0 (a GPIO, not a hardware reset)'),
    (48, 'UART1 TX', 'uart', 'console out, level shifter U7 to J12 pin 3'),
    (49, 'UART1 RX', 'uart', 'console in, from J12 pin 1 via U7'),
    (50, 'SD write protect', 'sd', '4.7k pull-up (microSD has no WP: ignored)'),
    (51, 'Button S2 "IP"', 'misc', '4.7k pull-up, pressed = 0'),
    (52, 'ETH MDC', 'eth', 'PHY management clock, 1k pull-up'),
    (53, 'ETH MDIO', 'eth', 'PHY management data, 1k pull-up'),
]
GROUP = {'nand': ('m-nand', 'NAND flash'), 'eth': ('m-eth', 'Ethernet'), 'sd': ('m-sd', 'SD card'),
         'io': ('m-io', 'EN pins (hash connectors)'), 'uart': ('m-uart', 'UART console'),
         'misc': ('m-misc', 'LEDs, buzzer, buttons')}


def mio_grid():
    cells = ''.join('<div class="%s" title="MIO%d: %s">%d</div>' % (GROUP[g][0], n, f, n) for n, f, g, _ in MIO)
    legend = ''.join('<span class="%s">%s</span>' % (c, t) for c, t in GROUP.values())
    return '<div class="mio">%s</div><p class="legend">%s</p>' % (cells, legend)


def mio_table():
    rows = []
    for n, f, g, note in MIO:
        bank = '500 (3.3 V)' if n <= 15 else '501 (2.5 V)'
        rows.append('<tr><td>MIO%d</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
            n, f, GROUP[g][1], bank, note))
    return ('<table><tr><th>Pin</th><th>Function on this board</th><th>Group</th><th>Bank</th><th>Notes</th></tr>'
            + ''.join(rows) + '</table>')


def conn_table():
    rows = []
    for n, (pins, en) in P.CONN_FPGA.items():
        rows.append('<tr><td><b>J%d</b></td>%s<td>MIO%d</td><td>%s</td></tr>' % (
            n, ''.join('<td><code>%s</code></td>' % p for p in pins), en,
            'I2C1: W19 / W18' if n < 9 else 'I2C2: P18 / N17'))
    return ('<table><tr><th>Conn</th><th>pin 5 (PLUG)</th><th>pin 11 (TXD)</th><th>pin 12 (RXD)</th>'
            '<th>pin 15 (RST)</th><th>pin 18 EN</th><th>pins 3 / 4 SDA / SCL</th></tr>' + ''.join(rows) + '</table>')


def pl_table():
    rows = ''.join('<tr><td>%s</td><td><code>%s</code></td><td><code>%s</code></td><td>%s</td></tr>'
                   % (w, p, port, n) for port, p, w, n in P.PL_OTHER)
    return '<table><tr><th>What</th><th>FPGA pin</th><th>Ardzy port</th><th>Notes</th></tr>%s</table>' % rows


def main():
    tpl = open(os.path.join(HERE, 'docs', 'board_manual_template.html'), encoding='utf-8').read()
    for key, val in (('@@MIO_GRID@@', mio_grid()), ('@@MIO_TABLE@@', mio_table()),
                     ('@@CONN_TABLE@@', conn_table()), ('@@PL_TABLE@@', pl_table())):
        assert key in tpl, key
        tpl = tpl.replace(key, val)
    assert len(MIO) == 54 and [m[0] for m in MIO] == list(range(54))
    out = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'Documents', '04_Board_Manual.html'))
    open(out, 'w', encoding='utf-8', newline='\n').write(tpl)
    print('wrote', out, '(%d KB)' % (len(tpl) // 1024))


if __name__ == '__main__':
    main()
