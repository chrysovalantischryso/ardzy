#!/usr/bin/env python3
"""Ardzy pins plan: ONE source of truth for every usable pin of the Antminer S9 control board.

Source: official schematic "AntMiner_ControlBoard_XC7010 V1.0" (15 sheets, 2016-07-01),
cross-checked with the proven constraints file systemGPIO.xdc (plMinerN / plLED4Bit).

Writes:
  projects/ardzy_pins.xdc      Vivado constraints, every line ready (commented: uncomment what you use)
  pc_app/ui/pins.json          data for the "Pins" tab of the Ardzy app
  pc_app/templates/*/ardzy_pins.xdc   same file inside the FPGA project templates
Run: python scripts/make_pins.py
"""
import json, os, shutil

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------- the 9 hash-board connectors
# 18-pin (2 x 9) connectors J1..J9. From the FPGA's point of view all four signal lines are
# ordinary 3.3 V I/O pins (Bitmain used them as PLUG / TXD / RXD / RST for the hash boards).
CONN_SIGNALS = [  # (connector pin, Bitmain name, bit in jN[3:0])
    (5, 'PLUG', 0), (11, 'TXD', 1), (12, 'RXD', 2), (15, 'RST', 3)]
CONN_FPGA = {      # connector: [PLUG, TXD, RXD, RST] package pins, EN = PS MIO number
    1: (['T11', 'T12', 'U12', 'T10'], 28),
    2: (['R19', 'V12', 'W13', 'V13'], 29),
    3: (['T14', 'P14', 'R14', 'T15'], 30),
    4: (['Y16', 'W14', 'Y14', 'Y17'], 31),
    5: (['T16', 'V15', 'W15', 'U17'], 32),
    6: (['U14', 'U18', 'U19', 'U15'], 33),
    7: (['T20', 'V20', 'W20', 'U20'], 34),
    8: (['Y18', 'V16', 'W16', 'Y19'], 35),
    9: (['R16', 'T17', 'R18', 'R17'], 36),
}
# full 18-pin layout of every connector (as printed on the board's pin map: even pins left)
CONN_LAYOUT = [  # (pin, function, kind)
    (1, 'GND', 'gnd'), (2, 'GND', 'gnd'), (3, 'SDA (I2C)', 'i2c'), (4, 'SCL (I2C)', 'i2c'),
    (5, 'IO0  PLUG', 'io'), (6, 'A2 address strap', 'nc'), (7, 'A1 address strap', 'nc'),
    (8, 'A0 address strap', 'nc'), (9, 'GND', 'gnd'), (10, 'GND', 'gnd'), (11, 'IO1  TXD', 'io'),
    (12, 'IO2  RXD', 'io'), (13, 'GND', 'gnd'), (14, 'GND', 'gnd'), (15, 'IO3  RST', 'io'),
    (16, '3.3 V out', 'pwr'), (17, 'not connected', 'nc'), (18, 'EN (ARM GPIO, 2.5 V)', 'ps')]

# ---------------------------------------------------------------- other FPGA (PL) pins
PL_OTHER = [  # (port name, package pin, what, notes)
    ('leds[0]', 'F16', 'LED', 'on-board LED, ACTIVE LOW (0 = on)'),
    ('leds[1]', 'L19', 'LED', 'on-board LED, ACTIVE LOW (0 = on)'),
    ('leds[2]', 'M19', 'LED', 'on-board LED, ACTIVE LOW (0 = on)'),
    ('leds[3]', 'M17', 'LED', 'on-board LED, ACTIVE LOW (0 = on)'),
    ('fan_pwm', 'J18', 'Fan', 'PWM to pin 4 of all 6 fan headers (shared)'),
    ('fan_tach[0]', 'F19', 'Fan', 'FAN1 speed (pin 3), 10k pull-up'),
    ('fan_tach[1]', 'G18', 'Fan', 'FAN2 speed (pin 3), 10k pull-up'),
    ('fan_tach[2]', 'F20', 'Fan', 'FAN3 speed (pin 3), 10k pull-up'),
    ('fan_tach[3]', 'J20', 'Fan', 'FAN4 speed (pin 3), 10k pull-up'),
    ('fan_tach[4]', 'G17', 'Fan', 'FAN5 speed (pin 3), 10k pull-up'),
    ('fan_tach[5]', 'H20', 'Fan', 'FAN6 speed (pin 3), 10k pull-up'),
    ('i2c1_scl', 'W18', 'I2C', 'SCL on J1..J8 pin 4, 1k pull-up'),
    ('i2c1_sda', 'W19', 'I2C', 'SDA on J1..J8 pin 3, 1k pull-up'),
    ('i2c2_scl', 'N17', 'I2C', 'SCL on J9 pin 4, 1k pull-up'),
    ('i2c2_sda', 'P18', 'I2C', 'SDA on J9 pin 3, 1k pull-up'),
    ('board_id[0]', 'M15', 'ID', 'board version strap (input)'),
    ('board_id[1]', 'M14', 'ID', 'board version strap (input)'),
    ('board_id[2]', 'L15', 'ID', 'board version strap (input)'),
    ('board_id[3]', 'L14', 'ID', 'board version strap (input)'),
    ('tp1', 'K18', 'Test', 'test point TP1 "CLOCK_OUT" (handy scope probe pin)'),
]

# ---------------------------------------------------------------- ARM side (PS / MIO)
PS = [  # (name, MIO, voltage, use from Linux / Python)
    ('Status LED red (D3)', 37, '2.5 V bank', "ardzy.led('red')"),
    ('Status LED green (D3), "Ardzy ready"', 38, '2.5 V bank', "ardzy.led('green')"),
    ('Small green LED D2', 15, '3.3 V bank, active low', "ardzy.led('ps')"),
    ('Buzzer BZ1', 39, '2.5 V bank', 'ardzy.beep(0.2)'),
    ('Button S2 "IP"', 51, '4.7k pull-up, pressed = 0', "ardzy.button('ip')"),
    ('Button S1 "Reset"', 47, '4.7k pull-up, pressed = 0', "ardzy.button('reset')"),
] + [('Connector J%d pin 18 (EN%d)' % (n, n), 27 + n, '2.5 V output',
      'I2C1 SCL/SDA (set by the boot loader)' if n in (1, 2) else '/sys/class/gpio/gpio%d' % (27 + n))
     for n in range(1, 10)] + [
    ('UART console TX (J12 pin 3)', 48, '3.3 V via level shifter', 'Linux ttyPS0, 115200'),
    ('UART console RX (J12 pin 1)', 49, '3.3 V via level shifter', 'Linux ttyPS0, 115200'),
]

BANKS = [
    ('34', '3.3 V', 'PL', 'J1..J9 signals, I2C buses'),
    ('35', '3.3 V', 'PL', 'LEDs, fans, board ID, TP1'),
    ('500 (MIO 0-15)', '3.3 V', 'PS', 'NAND flash, LED D2, boot straps'),
    ('501 (MIO 16-53)', '2.5 V', 'PS', 'Ethernet, SD card, UART, buttons, buzzer, status LED, EN pins'),
]


def conn_rows():
    rows = []
    for n, (pins, en) in CONN_FPGA.items():
        for (cpin, bname, bit), pkg in zip(CONN_SIGNALS, pins):
            rows.append({'conn': 'J%d' % n, 'cpin': cpin, 'bitmain': bname, 'port': 'j%d[%d]' % (n, bit),
                         'pin': pkg, 'old': 'plMiner%d[%d]' % (n - 1, bit)})
    return rows


def xdc():
    L = ['# ardzy_pins.xdc - every usable FPGA pin of the Antminer S9 control board (XC7Z010-CLG400)',
         '# Generated by scripts/make_pins.py from the board schematic. Uncomment the lines you use,',
         '# and name your top-level ports the same (or edit the names here).',
         '# All FPGA (PL) pins on this board are 3.3 V: IOSTANDARD LVCMOS33. Never apply 5 V.',
         '']
    L += ['# ---- hash-board connectors J1..J9: jN[0]=pin 5, jN[1]=pin 11, jN[2]=pin 12, jN[3]=pin 15',
          '#      (pin 3 = SDA, pin 4 = SCL, pin 16 = 3.3 V, pins 1,2,9,10,13,14 = GND)']
    for r in conn_rows():
        L.append('#set_property -dict {PACKAGE_PIN %-3s IOSTANDARD LVCMOS33} [get_ports {%s}] ;# %s pin %-2d (%s)'
                 % (r['pin'], r['port'], r['conn'], r['cpin'], r['bitmain']))
        if r['port'].endswith('[3]'):
            L.append('')
    L.append('# ---- on-board LEDs (ACTIVE LOW: drive 0 to light), fans, I2C, board ID, test point')
    for port, pin, what, notes in PL_OTHER:
        L.append('#set_property -dict {PACKAGE_PIN %-3s IOSTANDARD LVCMOS33} [get_ports {%s}] ;# %s' % (pin, port, notes))
    L += ['', '# LEDs: gentle drive', '#set_property -dict {DRIVE 8 SLEW SLOW} [get_ports {leds[*]}]',
          '# I2C lines need open-drain style logic (IOBUF), the board already has 1k pull-ups.', '']
    return '\n'.join(L)


# ---------------------------------------------------------------- suggested standard plan
PLAN = [  # (connector, use, j[0] pin5, j[1] pin11, j[2] pin12, j[3] pin15, notes)
    ('J1', 'UART (serial)', 'spare', 'TX out', 'RX in', 'spare', 'AXI UART Lite or UART16550; talk to GPS, ESP32, Arduino'),
    ('J2', 'SPI', 'CS', 'MOSI', 'MISO', 'SCLK', 'AXI Quad SPI; displays, ADCs, DACs, SD cards'),
    ('J3', 'I2S audio', 'MCLK', 'BCLK', 'DATA', 'LRCLK', 'audio codec / DAC / microphone'),
    ('J4', '4 x PWM', 'PWM0', 'PWM1', 'PWM2', 'PWM3', 'servos, motor drivers, LED dimming'),
    ('J5', 'Counters', 'IN0', 'IN1', 'IN2', 'IN3', 'quadrature encoder, frequency counter, pulse inputs'),
    ('J6', 'Fast digital', 'D0', 'D1', 'D2', 'D3', 'logic analyzer inputs, parallel bus'),
    ('J7', 'LED strip', 'WS2812 data', 'spare', 'spare', 'spare', 'addressable RGB LEDs (5 V strips need a level shifter)'),
    ('J8', 'General GPIO', 'GPIO0', 'GPIO1', 'GPIO2', 'GPIO3', 'buttons, relays (via a transistor), sensors'),
    ('J9', 'RF out', 'spare', 'RF (T17)', 'spare', 'spare', 'the pin used by the FM/AM transmitter projects ("TXD9" pad)'),
]


def write_doc(path):
    d_conn = conn_rows()
    color = {'gnd': 'd-box', 'i2c': 'd-ps', 'io': 'd-pl', 'nc': 'd-box', 'pwr': 'd-warn', 'ps': 'd-ps'}
    # SVG: the 18-pin connector, drawn as on the board's pin map (even pins left, odd pins right)
    svg = ['<svg viewBox="0 0 900 470" role="img" aria-label="18-pin connector">',
           '<rect x="330" y="20" width="240" height="430" rx="10" class="d-box"/>',
           '<text x="450" y="14" class="d-small" text-anchor="middle">each of J1..J9 (2 x 9 pins)</text>']
    lay = {p: (f, k) for p, f, k in CONN_LAYOUT}
    for row in range(9):
        y = 45 + row * 46
        for side, pin in (('L', 2 * row + 2), ('R', 2 * row + 1)):
            f, k = lay[pin]
            cx = 390 if side == 'L' else 510
            svg.append('<circle cx="%d" cy="%d" r="15" class="%s"/>' % (cx, y, color[k]))
            svg.append('<text x="%d" y="%d" class="d-title" text-anchor="middle">%d</text>' % (cx, y + 5, pin))
            if side == 'L':
                svg.append('<path d="M%d %d H%d" class="d-line"/>' % (cx - 17, y, 300))
                svg.append('<text x="292" y="%d" class="d-text" text-anchor="end">%s</text>' % (y + 5, f))
            else:
                svg.append('<path d="M%d %d H%d" class="d-line"/>' % (cx + 17, y, 600))
                svg.append('<text x="608" y="%d" class="d-text">%s</text>' % (y + 5, f))
    svg.append('</svg>')
    svg = '\n'.join(svg)

    def table(head, rows):
        h = ''.join('<th>%s</th>' % c for c in head)
        b = ''.join('<tr>%s</tr>' % ''.join('<td>%s</td>' % c for c in r) for r in rows)
        return '<table><tr>%s</tr>%s</table>' % (h, b)

    conn_tbl = []
    for n, (pins, en) in CONN_FPGA.items():
        conn_tbl.append(['<b>J%d</b>' % n] + ['<code>%s</code>' % p for p in pins] +
                        ['MIO%d' % en, '<code>j%d[3:0]</code>' % n, 'plMiner%d' % (n - 1)])
    html = DOC_TEMPLATE.format(
        svg=svg,
        conn=table(['Connector', 'pin 5 = jN[0]', 'pin 11 = jN[1]', 'pin 12 = jN[2]', 'pin 15 = jN[3]',
                    'pin 18 EN (ARM)', 'Vivado port', 'old name'], conn_tbl),
        plan=table(['Conn', 'Use', 'pin 5', 'pin 11', 'pin 12', 'pin 15', 'Good for'],
                   [['<b>%s</b>' % a, b, c, d, e, f, g] for a, b, c, d, e, f, g in PLAN]),
        other=table(['What', 'FPGA pin', 'Vivado port', 'Notes'],
                    [[w, '<code>%s</code>' % p, '<code>%s</code>' % port, n] for port, p, w, n in PL_OTHER]),
        ps=table(['What', 'Pin', 'Voltage', 'Use from Linux / Python'],
                 [[a, 'MIO%d' % b, c, '<code>%s</code>' % d] for a, b, c, d in PS]),
        banks=table(['Bank', 'Voltage', 'Side', 'Used for'], [list(b) for b in BANKS]),
        count=len(d_conn) + len(PL_OTHER), nconn=len(d_conn), count_other=len(PL_OTHER))
    open(path, 'w', encoding='utf-8', newline='\n').write(html)


DOC_TEMPLATE = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pins Plan</title>
<link rel="stylesheet" href="docs.css">
</head>
<body>
<header class="top"><div class="wrap">
  <nav class="back"><a href="index.html">&larr; All documents</a></nav>
  <div class="kicker">Document 3 &middot; Pins plan</div>
  <h1>Every usable pin of the board</h1>
  <p>{count} FPGA pins, plus the ARM-side buttons, LEDs and buzzer. From the official schematic, checked against the proven constraints file.</p>
</div></header>
<main class="wrap">
<div class="toc"><b>Contents</b><ol>
  <li><a href="#rules">Rules first</a></li>
  <li><a href="#map">Where everything is</a></li>
  <li><a href="#conn">The 9 connectors</a></li>
  <li><a href="#plan">Suggested standard plan</a></li>
  <li><a href="#other">Other FPGA pins</a></li>
  <li><a href="#ps">ARM-side extras</a></li>
  <li><a href="#use">Using the pins</a></li>
  <li><a href="#banks">Voltages (I/O banks)</a></li>
</ol></div>

<h2 id="rules">1. Rules first</h2>
<div class="box bad"><b>Protect the chip</b>
All FPGA pins are <b>3.3 V</b>. Never connect 5 V signals directly (use a level shifter, or a resistor divider for inputs).
Keep the current small (an LED with a 330 &Omega; resistor is fine; motors and relays need a transistor or a driver board).
Switch the board off before you change wires.</div>
<div class="box info"><b>Names</b>
Bitmain called the four signal lines of each connector PLUG, TXD, RXD and RST. For the FPGA they are <b>ordinary I/O pins</b>:
you decide in your design if each one is an input or an output. In Ardzy they are called <code>jN[0]</code> to <code>jN[3]</code>
(for example <code>j3[1]</code> = connector J3, pin 11).</div>

<h2 id="map">2. Where everything is</h2>
<figure><img src="img/pin_mapping.png" alt="Board pin map" loading="lazy">
<figcaption>J10 JTAG (top left), boot jumpers (top right), UART J12, the 9 connectors plMiner0..8 = <b>J1..J9</b>, fans plFan0..5, LEDs, 12 V input.
On each connector the pin map shows <b>even pins on the left, odd pins on the right</b>, pins 2/1 at the top. Check the pin-1 mark on your board before wiring.</figcaption></figure>

<h2 id="conn">3. The 9 connectors</h2>
<figure>{svg}
<figcaption>All 9 connectors have the same layout. Blue = I2C (shared bus) and ARM EN pin, green = the 4 free FPGA I/O, amber = 3.3 V supply.
Pins 6, 7, 8 are fixed address straps (resistors on the board): do not use them.</figcaption></figure>
{conn}
<p>The I2C pins (3 = SDA, 4 = SCL) of J1..J8 are <b>one shared bus</b> (FPGA pins W19/W18); J9 has its own bus (P18/N17). Both have 1 k&Omega; pull-ups on the board.
Pin 16 gives 3.3 V for small sensors.</p>

<h2 id="plan">4. Suggested standard plan</h2>
<p>A fixed plan means every project uses the same wiring, and old designs keep working with the same cables. This is only a suggestion: any pin can do any job.</p>
{plan}

<h2 id="other">5. Other FPGA pins</h2>
{other}
<div class="box warn"><b>LEDs are active low</b> The LEDs are wired from 3.3 V through 220 &Omega; to the FPGA pin, so a <b>0</b> lights them.
Write <code>assign leds = ~pattern;</code> in Verilog, or <code>~pattern &amp; 0xF</code> in Python.</div>
<p>The fan speed pins are normal 3.3 V inputs with 10 k&Omega; pull-ups, also usable for other signals (the FM transmitter project used them for I2S audio input).
The board-ID pins are fixed straps: read them, never drive them.</p>

<h2 id="ps">6. ARM-side extras</h2>
<p>These belong to the ARM processor (PS), not to the FPGA. Linux sets them up at boot (<code>ardzy-board</code> service): green status LED on = Ardzy ready, red = safe mode.</p>
{ps}
<pre><code>from ardzy import led, beep, button
led('green')            # status LED green on   (led('red'), led('ps'), led('green', False))
beep(0.2)               # buzzer for 0.2 s
if button('ip'):        # True while the IP button (S2) is pressed
    print('pressed')</code></pre>
<p>On the board command line: <code>ardzy beep</code>, <code>ardzy led red on</code>, <code>ardzy buttons -w</code>. Example project: <b>board_hello</b>.</p>

<h2 id="use">7. Using the pins</h2>
<ol class="steps">
  <li>In Vivado, add <code>projects\\ardzy_pins.xdc</code> to your constraints (it is also in every new FPGA project made with the Ardzy app).</li>
  <li>Remove the <code>#</code> in front of the lines you use, and give your top-level ports the same names (for example <code>output [3:0] j4</code>).</li>
  <li>In the Ardzy app, the <b>Pins</b> tab shows all of this; click a row to copy its Vivado line.</li>
</ol>
<pre><code># example: J1 as a UART
set_property -dict {{PACKAGE_PIN T12 IOSTANDARD LVCMOS33}} [get_ports {{j1[1]}}] ;# TX out, J1 pin 11
set_property -dict {{PACKAGE_PIN U12 IOSTANDARD LVCMOS33}} [get_ports {{j1[2]}}] ;# RX in,  J1 pin 12</code></pre>

<h2 id="banks">8. Voltages (I/O banks)</h2>
{banks}
<p>Total: {nconn} connector I/O + {count_other} more FPGA pins. Source: AntMiner_ControlBoard_XC7010 V1.0 schematic (sheets 6, 13, 14 for the FPGA side; 2, 3, 4, 11 for the ARM side).</p>
</main>
</body>
</html>
'''


# ---------------------------------------------------------------- the "pin control" design
# AXI GPIO channel 1 (32 bits) = j1..j8, channel 2 (17 bits) = j9, LEDs, TP1, board ID, I2C
IO_GPIO2 = ['j9[0]', 'j9[1]', 'j9[2]', 'j9[3]', 'leds[0]', 'leds[1]', 'leds[2]', 'leds[3]', 'tp1',
            'board_id[0]', 'board_id[1]', 'board_id[2]', 'board_id[3]',
            'i2c1_scl', 'i2c1_sda', 'i2c2_scl', 'i2c2_sda']


def io_map():
    """[(gpio port, bit, ardzy name, package pin)] for the ardzy_io design (also used by the board API)."""
    pin_of = {r['port']: r['pin'] for r in conn_rows()}
    pin_of.update({p: pkg for p, pkg, _, _ in PL_OTHER})
    m = [('gpio1', i, 'j%d[%d]' % (i // 4 + 1, i % 4), pin_of['j%d[%d]' % (i // 4 + 1, i % 4)]) for i in range(32)]
    m += [('gpio2', i, n, pin_of[n]) for i, n in enumerate(IO_GPIO2)]
    return m


def write_io_xdc(path):
    L = ['# ardzy_io.xdc - generated by scripts/make_pins.py: the 49 FPGA pins of ardzy_ctl (pins[i]),',
         '# index = AXI GPIO channel 1 bit (0..31) or 32 + channel 2 bit, the fan PWM and the 6 fan speed inputs']
    for i, (port, bit, name, pkg) in enumerate(io_map()):
        L.append('set_property -dict {PACKAGE_PIN %s IOSTANDARD LVCMOS33} [get_ports {pins[%d]}] ;# %s'
                 % (pkg, i, name))
    L.append('# the 36 connector pins float when nothing is plugged in: weak pull-ups')
    L += ['set_property PULLTYPE PULLUP [get_ports {pins[%d]}]' % i for i in range(36)]   # one port per line (nextpnr)
    L.append('set_property -dict {PACKAGE_PIN J18 IOSTANDARD LVCMOS33} [get_ports fan_pwm]')
    for i, (port, pkg, _, _) in enumerate([x for x in PL_OTHER if x[0].startswith('fan_tach')]):
        L.append('set_property -dict {PACKAGE_PIN %s IOSTANDARD LVCMOS33} [get_ports {fan_tach[%d]}]' % (pkg, i))
    open(path, 'w', newline='\n').write('\n'.join(L) + '\n')


def main():
    text = xdc()
    io_dir = os.path.join(HERE, 'projects', 'ardzy_io')
    if os.path.isdir(io_dir):
        write_io_xdc(os.path.join(io_dir, 'ardzy_io.xdc'))
        json.dump([{'port': p, 'bit': b, 'name': n, 'pin': k} for p, b, n, k in io_map()],
                  open(os.path.join(HERE, 'board', 'opt', 'ardzy', 'web', 'io_map.json'), 'w'), indent=1)
        print('wrote ardzy_io.xdc and io_map.json (%d pins)' % len(io_map()))
    out = os.path.join(HERE, 'projects', 'ardzy_pins.xdc')
    open(out, 'w', newline='\n').write(text)
    for t in ('fpga_blink', 'fpga_python_leds'):
        shutil.copy(out, os.path.join(HERE, 'pc_app', 'templates', t, 'ardzy_pins.xdc'))
    data = {
        'source': 'AntMiner_ControlBoard_XC7010 V1.0 schematic + systemGPIO.xdc',
        'connectors': conn_rows(),
        'en_pins': {('J%d' % n): 'MIO%d' % en for n, (_, en) in CONN_FPGA.items()},
        'layout': [{'pin': p, 'func': f, 'kind': k} for p, f, k in CONN_LAYOUT],
        'pl_other': [{'port': a, 'pin': b, 'what': c, 'notes': d} for a, b, c, d in PL_OTHER],
        'ps': [{'name': a, 'mio': b, 'volt': c, 'use': d} for a, b, c, d in PS],
        'banks': [{'bank': a, 'volt': b, 'side': c, 'used_for': d} for a, b, c, d in BANKS],
    }
    json.dump(data, open(os.path.join(HERE, 'pc_app', 'ui', 'pins.json'), 'w'), indent=1)
    docs = os.path.normpath(os.path.join(HERE, '..', '..', 'Documents'))
    if os.path.isdir(docs):
        write_doc(os.path.join(docs, '03_Pins_Plan.html'))
        print('wrote', os.path.join(docs, '03_Pins_Plan.html'))
    print('wrote', out, '(%d lines), pins.json, template copies' % text.count('\n'))
    print('PL pins: %d connector I/O + %d other = %d usable FPGA pins'
          % (len(conn_rows()), len(PL_OTHER), len(conn_rows()) + len(PL_OTHER)))


if __name__ == '__main__':
    main()
