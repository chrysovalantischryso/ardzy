/* Ardzy - Map view: the board drawn (click anything), wiring diagrams, how it all works.
   Live: LEDs, buttons, connector pins, fans, temperature, link, FPGA design. */
const MP = { tab: 'board', sel: 'J1', live: {}, timer: null, photo: false, net: null, find: '', tfind: '',
  layers: { labels: true, pins: true, balls: true, live: true }, view: { x: 0, y: 0, w: 1061, h: 1440 } };
const PCB = { board: '#1d5a3a', edge: '#2f7a52', silk: '#e8f2ec', part: '#20262a', partLine: '#566', pad: '#c9a227', hl: '#ffd84d' };

// ------------------------------------------------------------------ parts of the board
// positions follow the board's pin map (portrait, Ethernet at the top, connectors at the bottom)
const PARTS = [
  // positions measured on the photo of the real board (Documents/img/pin_mapping.png, 1061 x 1440 pixels, top view,
  // the Ethernet edge at the top, the miner connectors and fans at the bottom): the drawing is to scale
  { id: 'eth', x: 456, y: 0, w: 186, h: 206, label: 'Ethernet', ref: 'RJ45', kind: 'rj45', lab: 'top' },
  { id: 'magnetics', x: 456, y: 212, w: 170, h: 142, label: 'magnetics', ref: 'Ethernet', kind: 'chip', info: 'eth' },
  { id: 'front', x: 300, y: 0, w: 140, h: 78, label: 'LEDs + buttons', ref: 'position approximate', kind: 'ui', approx: true, lab: 'below' },
  { id: 'sd', x: 694, y: 0, w: 150, h: 64, label: 'microSD', ref: 'position approximate', kind: 'sd', approx: true, lab: 'below' },
  { id: 'jtag', x: 148, y: 236, w: 50, h: 138, label: 'JTAG', ref: 'J10', kind: 'pins2x7', lab: 'right' },
  { id: 'uart', x: 700, y: 312, w: 62, h: 34, label: 'UART', ref: 'J12', kind: 'pins1x3', lab: 'below' },
  { id: 'boot', x: 896, y: 272, w: 146, h: 84, label: 'Boot JP1-JP4', ref: 'JP1-4', kind: 'jumpers', lab: 'below' },
  { id: 'phy', x: 496, y: 398, w: 82, h: 84, label: 'PHY', ref: 'U8', kind: 'chip' },
  { id: 'nand', x: 762, y: 406, w: 116, h: 186, label: 'NAND', ref: 'MT29F2G08', kind: 'chip' },
  { id: 'buzzer', x: 894, y: 444, w: 112, h: 112, label: 'Buzzer', ref: 'BZ1', kind: 'round' },
  { id: 'ddr', x: 470, y: 612, w: 76, h: 90, label: 'DDR3', ref: 'U3', kind: 'chip' },
  { id: 'ddr2', x: 470, y: 718, w: 76, h: 92, label: 'DDR3', ref: 'U4', kind: 'chip', info: 'ddr' },
  { id: 'zynq', x: 604, y: 638, w: 166, h: 168, label: 'ZYNQ\nXC7Z010', ref: 'U1', kind: 'chip' },
  { id: 'fpgaleds', x: 832, y: 776, w: 34, h: 118, label: 'LED0-3', ref: 'D4-D7', kind: 'leds' },
  { id: 'power', x: 36, y: 1056, w: 112, h: 136, label: '12 V in', ref: 'J14', kind: 'pcie', lab: 'above' },
];
// the 9 miner connectors (on the board "plMiner0..8"): 2 x 9 pins, pin 1 at the top right
[[196, 'pins'], [290, 'pins'], [388, 'pins'], [486, 'pins'], [584, 'pins'], [690, 'shroud'], [786, 'shroud'], [884, 'shroud'], [976, 'shroud']]
  .forEach(([x, k], i) => PARTS.push({ id: 'J' + (i + 1), x, y: 998, w: k === 'shroud' ? 74 : 56, h: 184, label: 'J' + (i + 1),
    ref: 'plMiner' + i, kind: 'header', shroud: k === 'shroud' }));
// the 6 fan connectors ("plFan0..5"), 4 pins each
[300, 434, 564, 698, 828, 958].forEach((x, i) => PARTS.push({ id: 'FAN' + (i + 1), x, y: 1252, w: 56, h: 170, label: 'FAN' + (i + 1),
  ref: 'plFan' + i, kind: 'fan' }));

const J_LAYOUT = [  // pin, function, kind (from the schematic; even pins on one side, odd on the other)
  [1, 'GND', 'gnd'], [2, 'GND', 'gnd'], [3, 'SDA (I2C)', 'i2c'], [4, 'SCL (I2C)', 'i2c'], [5, 'IO0 (PLUG)', 'io'],
  [6, 'A2 strap', 'nc'], [7, 'A1 strap', 'nc'], [8, 'A0 strap', 'nc'], [9, 'GND', 'gnd'], [10, 'GND', 'gnd'],
  [11, 'IO1 (TXD)', 'io'], [12, 'IO2 (RXD)', 'io'], [13, 'GND', 'gnd'], [14, 'GND', 'gnd'], [15, 'IO3 (RST)', 'io'],
  [16, '3.3 V out', 'pwr'], [17, 'not connected', 'nc'], [18, 'EN (ARM, 2.5 V)', 'ps']];
const J_PIN_BIT = { 5: 0, 11: 1, 12: 2, 15: 3 };
const KIND_COL = { gnd: '#7a8580', i2c: '#4f8fe0', io: '#2fbf6c', nc: '#9aa', pwr: '#e3a03a', ps: '#b65fd6' };

function partInfo(id) {
  const L = MP.live, io = L.io, pin = n => io && io.pins.find(p => p.name === n);
  if (/^J\d$/.test(id)) {
    const n = +id.slice(1), fpga = ['T11 T12 U12 T10', 'R19 V12 W13 V13', 'T14 P14 R14 T15', 'Y16 W14 Y14 Y17', 'T16 V15 W15 U17',
      'U14 U18 U19 U15', 'T20 V20 W20 U20', 'Y18 V16 W16 Y19', 'R16 T17 R18 R17'][n - 1].split(' ');
    return {
      title: TF('Connector J{0} (18 pins, 2 x 9)', n),
      body: `Four free FPGA pins (3.3 V): <b>pin 5, 11, 12, 15</b> = <code>j${n}[0..3]</code> = Arduino <code>J${n}_5, J${n}_11, J${n}_12, J${n}_15</code>
        (FPGA balls ${fpga.join(', ')}). Pins 3 and 4 are I2C ${n === 9 ? 'bus 2 (Wire1)' : 'bus 1 (Wire), shared by J1..J8'}, pin 16 gives 3.3 V,
        pins 1, 2, 9, 10, 13, 14 are GND. Pin 18 (EN) is an ARM pin (MIO${27 + n}, 2.5 V).` + jPinout(n, io),
    };
  }
  if (/^FAN\d$/.test(id)) {
    const n = +id.slice(3), rpm = io && io.fan ? io.fan.rpm[n - 1] : null;
    return { title: TF('Fan header FAN{0} (4 pins)', n), body: `Pin 1 GND, pin 2 +12 V, pin 3 speed (tach, FPGA ${['F19', 'G18', 'F20', 'J20', 'G17', 'H20'][n - 1]}),
      pin 4 PWM (shared by all 6, FPGA J18).` + kv([['Speed now', rpm === null ? 'load the pin-control design to measure' : rpm + ' rpm'],
      ['Arduino', `<code>Ardzy.fan(percent)</code>, <code>Ardzy.fanRpm(${n})</code>, pin <code>FAN${n}_TACH</code>`]]) + fanSvg() };
  }
  const s = L.sensors || {}, st = S.status || {};
  const lvl = m => { const p = L.mio && L.mio.pins[m]; return p && p.level !== undefined ? p.level : null; };
  const onOff = v => v === null ? '?' : v ? 'on' : 'off';
  const info = {
    eth: ['Ethernet (RJ45)', 'Gigabit port (Broadcom B50612 PHY at address 1, RGMII to the Zynq GEM0). The board is found by Ardzy over IPv6 link-local even with no router.',
      [['Link', L.net ? `${L.net.speed} Mbit/s ${L.net.duplex}` : '?'], ['MAC', L.net ? L.net.mac : '?'], ['Name', (S.board || {}).hostname + '.local']]],
    sd: ['microSD card slot', '(Drawn dashed: its place on the drawing is approximate.) The card holds everything: boot files (FAT) and Debian 13 (ext4). SDIO0 on MIO 40-46, 4-bit, 50 MHz high speed, card detect on MIO46.',
      [['Card', L.hw ? `${L.hw.storage.card.name} ${fmtMB(L.hw.storage.card.size_mb)}` : '?']]],
    front: ['Front: status LEDs and buttons', '(Drawn dashed: their place on the drawing is approximate.) Green/red status LED (MIO38/37): green = Ardzy ready, red = safe mode. Button S2 "IP" (MIO51) and S1 "Reset" (MIO47) read 0 while pressed.',
      [['Green', onOff(lvl(38))], ['Red', onOff(lvl(37))], ['IP button', lvl(51) === 0 ? 'pressed' : 'released'], ['Reset button', lvl(47) === 0 ? 'pressed' : 'released'],
       ['Arduino', '<code>LED_GREEN, LED_RED, BUTTON_IP, BUTTON_RESET</code>']]],
    jtag: ['J10 JTAG (2 x 7, 2 mm)', 'For a Xilinx JTAG cable (not needed with Ardzy). Odd pins = GND; 2 VREF (3.3 V), 4 TMS, 6 TCK, 8 TDO, 10 TDI, 14 SRST.', []],
    phy: ['Ethernet PHY Broadcom B50612', '10/100/1000 Mbit transceiver, RGMII to the Zynq (MIO 16-27), MDIO on MIO 52/53, 25 MHz crystal.', []],
    uart: ['J12 serial console (3 pins)', 'The Linux console, 115200 8N1, 3.3 V. Pin 1 = RX (into the board), pin 2 = GND, pin 3 = TX. The header is not fitted on all boards: solder 3 pins. See Wiring.', []],
    boot: ['Boot jumpers JP1-JP4', 'Where the chip boots from. Ardzy: SD card = JP2 and JP4 set (0101). Cascade JTAG 0000, QSPI 0001, NOR 0010, NAND 0100.',
      [['Boots from now', L.hw ? L.hw.boot.boot_mode : '?']]],
    nand: ['NAND flash Micron MT29F2G08 (256 MB)', 'The original Bitmain firmware. Ardzy never writes it (read only); Board view, NAND card: scan and back it up.', []],
    buzzer: ['Buzzer BZ1', 'MIO39, on = sound. Arduino <code>Ardzy.beep(ms)</code>, Python <code>ardzy.beep(0.2)</code>.', [['Now', onOff(lvl(39))]]],
    ddr: ['DDR3 memory (2 chips)', '512 MB, 32 bit, DDR3-1066 (533 MHz).', [['Used', s.mem ? `${s.mem.used_mb} of ${s.mem.total_mb} MB` : '?']]],
    zynq: ['Zynq XC7Z010-1CLG400', 'Two ARM Cortex-A9 cores (667 MHz, Linux) and an Artix-7 FPGA (17,600 LUTs, 60 block RAMs, 80 DSPs) in one chip.',
      [['Temperature', s.temp_c !== undefined ? s.temp_c.toFixed(1) + ' &deg;C' : '?'], ['CPU', s.cpu_pct !== null && s.cpu_pct !== undefined ? s.cpu_pct.toFixed(0) + ' %' : '?'],
       ['FPGA', `${st.fpga || '?'}${st.current ? ', project ' + st.current : ''}`]]],
    fpgaleds: ['FPGA LEDs LED0-LED3', 'Four small LEDs on FPGA pins F16, L19, M19, M17, active low (0 = on). Arduino <code>LED0..LED3</code> (HIGH = on), <code>LED_BUILTIN = LED0</code>.',
      [['Now', io ? [0, 1, 2, 3].map(i => { const p = pin(`leds[${i}]`); return `LED${i} ${p && p.mode === 'out' && !p.level ? 'on' : 'off'}`; }).join(', ') : 'load the pin-control design']]],
    power: ['12 V input (6-pin PCIe)', '12 V from the miner power supply or any 12 V adapter (about 0.5 A for the board alone, more with fans). 3 pins +12 V, 3 pins GND.', []],
  }[id];
  return info ? { title: info[0], body: `<p>${info[1]}</p>` + kv(info[2]) } : { title: id, body: '' };
}

function jPinout(n, io) {
  const lv = b => { const p = io && io.pins.find(x => x.name === `j${n}[${b}]`); return p ? p : null; };
  let svg = `<svg viewBox="0 0 360 330" class="jsvg"><rect x="140" y="6" width="80" height="318" rx="6" class="jbody"/>`;
  for (let r = 0; r < 9; r++) {
    for (const side of [0, 1]) {
      const pinNo = side ? 2 * r + 1 : 2 * r + 2, [, f, k] = J_LAYOUT[pinNo - 1];
      const cx = side ? 200 : 160, cy = 24 + r * 34;
      const p = J_PIN_BIT[pinNo] !== undefined ? lv(J_PIN_BIT[pinNo]) : null;
      svg += `<circle cx="${cx}" cy="${cy}" r="12" fill="${KIND_COL[k]}"/><text x="${cx}" y="${cy + 4}" class="jnum">${pinNo}</text>`;
      const tx = side ? 222 : 138, anchor = side ? 'start' : 'end';
      let extra = '';
      if (p) extra = ` ${p.func && p.func !== 'gpio' ? p.func : p.mode === 'out' ? 'out' : 'in'} ${p.level ? '1' : '0'}`;
      svg += `<text x="${tx}" y="${cy + 4}" text-anchor="${anchor}" class="jlab">${esc(f)}${extra ? `<tspan class="jlive">${esc(extra)}</tspan>` : ''}</text>`;
    }
  }
  svg += '</svg>';
  return svg + `<div class="hint">Green = free FPGA pins (live: function, direction, level), blue = I2C, orange = 3.3 V, purple = ARM pin.
    Check the pin-1 mark on your board before wiring. Control the pins in the I/O view.</div>`;
}

function fanSvg() {
  return `<svg viewBox="0 0 300 70" class="jsvg small">${['GND', '+12 V', 'speed', 'PWM'].map((t, i) =>
    `<rect x="${20 + i * 70}" y="10" width="40" height="26" rx="4" fill="${['#7a8580', '#e3a03a', '#2fbf6c', '#4f8fe0'][i]}"/>
     <text x="${40 + i * 70}" y="28" class="jnum">${i + 1}</text><text x="${40 + i * 70}" y="56" class="jlab" text-anchor="middle">${t}</text>`).join('')}</svg>`;
}

// ------------------------------------------------------------------ the board drawing (to scale) and the photo
const J_BALLS = ['T11 T12 U12 T10', 'R19 V12 W13 V13', 'T14 P14 R14 T15', 'Y16 W14 Y14 Y17', 'T16 V15 W15 U17',
  'U14 U18 U19 U15', 'T20 V20 W20 U20', 'Y18 V16 W16 Y19', 'R16 T17 R18 R17'].map(s => s.split(' '));
const FAN_BALLS = ['F19', 'G18', 'F20', 'J20', 'G17', 'H20'];
const NETS = { io: 'FPGA I/O', i2c: 'I2C', pwr: '3.3 V', gnd: 'GND', ps: 'ARM (EN)', fan: 'fans' };

// every connector pin: {part, pin, x, y, kind, label}
function pinSpots() {
  const out = [];
  for (const p of PARTS) {
    if (p.kind === 'header') {
      const n = +p.id.slice(1), x0 = p.x + p.w / 2;
      for (let r = 0; r < 9; r++) for (const c of [0, 1]) {
        const pinNo = c ? 2 * r + 1 : 2 * r + 2, [, f, k] = J_LAYOUT[pinNo - 1];
        const bit = J_PIN_BIT[pinNo];
        out.push({ part: p.id, pin: pinNo, x: x0 + (c ? 11 : -11), y: p.y + 14 + r * 19.6, kind: k, label: f,
          ball: bit !== undefined ? J_BALLS[n - 1][bit] : '', sig: bit !== undefined ? `j${n}[${bit}]` : '' });
      }
    }
    if (p.kind === 'fan') {
      const n = +p.id.slice(3);
      ['GND', '+12 V', 'speed', 'PWM'].forEach((f, i) => out.push({ part: p.id, pin: i + 1, x: p.x + p.w / 2, y: p.y + 30 + i * 36,
        kind: ['gnd', 'fan12', 'fan', 'fan'][i], label: f, ball: i === 2 ? FAN_BALLS[n - 1] : i === 3 ? 'J18' : '',
        sig: i === 2 ? `fan_tach[${n - 1}]` : i === 3 ? 'fan_pwm' : '' }));
    }
  }
  return out;
}

function pinMatches(q, s) {
  if (!q) return false;
  q = q.toLowerCase().trim();
  const m = q.match(/^j(\d)\s*(?:pin)?\s*(\d+)$/);
  if (m) return s.part === 'J' + m[1] && s.pin === +m[2];
  return [s.ball, s.sig, s.label, s.part].some(v => v && v.toLowerCase() === q) || (q.length > 2 && s.label.toLowerCase().includes(q));
}

function boardSvg() {
  const L = MP.live, lvl = m => { const p = L.mio && L.mio.pins[m]; return p && p.level !== undefined ? p.level : null; };
  const io = L.io, ioPin = n => io && io.pins.find(p => p.name === n), Y = MP.layers;
  const vb = MP.view;
  let s = `<svg viewBox="${vb.x} ${vb.y} ${vb.w} ${vb.h}" class="boardsvg${MP.photo ? ' photo' : ''}" role="img" aria-label="Antminer S9 control board" id="boardSvg">
    <defs><pattern id="pcbgrid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#24684a" stroke-width="1"/></pattern></defs>`;
  if (MP.photo) {
    s += `<image href="img/board_top.jpg" x="0" y="0" width="1061" height="1440"/>`;
  } else {
    s += `<rect x="2" y="2" width="1057" height="1436" rx="18" fill="${PCB.board}" stroke="${PCB.edge}" stroke-width="5"/>
      <rect x="2" y="2" width="1057" height="1436" rx="18" fill="url(#pcbgrid)" opacity=".5"/>
      <text x="40" y="520" class="silk big" transform="rotate(-90 40 520)">ANTMINER control board XC7010 V1.01</text>
      <rect x="508" y="900" width="66" height="54" rx="6" fill="#2a2f33"/><text x="541" y="933" class="silk small mid">2R2</text>`;
  }
  const spots = pinSpots(), q = MP.find;
  for (const p of PARTS) {
    const sel = MP.sel === (p.info || p.id) ? ' sel' : '';
    const g0 = `<g class="part${sel}${MP.photo ? ' hot' : ''}${p.approx ? ' approx' : ''}" data-id="${p.info || p.id}">`;
    if (MP.photo) {                                   // the photo: clickable outlines over the real parts
      s += `${g0}<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="6" class="hotbox"/></g>`;
      continue;
    }
    if (p.kind === 'header') {
      s += `${g0}<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="4" fill="${p.shroud ? '#ede6d2' : '#16191b'}" stroke="${p.shroud ? '#b3a988' : '#444'}" stroke-width="2"/>
        ${p.shroud ? `<rect x="${p.x - 4}" y="${p.y + p.h / 2 - 18}" width="6" height="36" fill="#d7cfb5"/>` : ''}</g>`;
    } else if (p.kind === 'fan') {
      const rpm = io && io.fan ? io.fan.rpm[+p.id.slice(3) - 1] : null;
      s += `${g0}<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="5" fill="#ede6d2" stroke="#b3a988" stroke-width="2"/>
        <rect x="${p.x + p.w - 8}" y="${p.y + 20}" width="8" height="${p.h - 40}" fill="#d7cfb5"/>
        ${rpm ? `<text x="${p.x + p.w / 2}" y="${p.y + p.h + 22}" class="silk mid">${rpm} rpm</text>` : ''}</g>`;
    } else if (p.kind === 'round') {
      s += `${g0}<circle cx="${p.x + p.w / 2}" cy="${p.y + p.h / 2}" r="${p.w / 2}" fill="${lvl(39) ? '#c84' : '#16191b'}" stroke="#888" stroke-width="2"/>
        <circle cx="${p.x + p.w / 2}" cy="${p.y + p.h / 2}" r="8" fill="#333"/></g>`;
    } else if (p.kind === 'leds') {
      s += `${g0}<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="3" fill="#20262a" stroke="#566"/>`;
      for (let i = 0; i < 4; i++) {
        const qq = ioPin(`leds[${i}]`), on = qq && qq.mode === 'out' && !qq.level;
        s += `<rect x="${p.x + 7}" y="${p.y + 8 + i * 27}" width="20" height="14" rx="2" fill="${on ? '#5f5' : '#2a3a2e'}" stroke="#6a8"${on ? ' filter="url(#glow)"' : ''}/>`;
      }
      s += '</g>';
    } else if (p.kind === 'rj45') {
      s += `${g0}<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="6" fill="#b9bec2" stroke="#7d8488" stroke-width="2"/>
        <rect x="${p.x + 38}" y="${p.y + 120}" width="110" height="70" rx="4" fill="#2a2f33"/>
        <rect x="${p.x + 12}" y="${p.y + 170}" width="22" height="14" fill="${L.net && L.net.carrier ? '#5f5' : '#454'}"/>
        <rect x="${p.x + p.w - 34}" y="${p.y + 170}" width="22" height="14" fill="${L.net && L.net.carrier ? '#fb4' : '#454'}"/></g>`;
    } else if (p.kind === 'ui') {
      const gg = lvl(38), r = lvl(37), ip = lvl(51) === 0, rs = lvl(47) === 0;
      s += `${g0}<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="6" fill="#20262a" stroke="#566"/>
        <circle cx="${p.x + 22}" cy="${p.y + 38}" r="11" fill="${gg ? '#4f4' : '#243'}"/><circle cx="${p.x + 50}" cy="${p.y + 38}" r="11" fill="${r ? '#f44' : '#422'}"/>
        <rect x="${p.x + 72}" y="${p.y + 24}" width="26" height="28" rx="5" fill="${ip ? PCB.hl : '#8a8f94'}"/><rect x="${p.x + 106}" y="${p.y + 24}" width="26" height="28" rx="5" fill="${rs ? PCB.hl : '#8a8f94'}"/></g>`;
    } else if (p.kind === 'sd') {
      s += `${g0}<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="4" fill="#c6cace" stroke="#7d8488"/><rect x="${p.x + 20}" y="${p.y}" width="${p.w - 40}" height="14" fill="#2a2f33"/></g>`;
    } else if (p.kind === 'pins2x7' || p.kind === 'pins1x3' || p.kind === 'jumpers') {
      s += `${g0}<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="4" fill="#16191b" stroke="#444" stroke-width="2"/>`;
      if (p.kind === 'pins2x7') for (let r = 0; r < 7; r++) for (const c of [0, 1]) s += `<rect x="${p.x + 9 + c * 22}" y="${p.y + 8 + r * 19}" width="10" height="10" fill="${PCB.pad}"/>`;
      if (p.kind === 'pins1x3') for (let c = 0; c < 3; c++) s += `<rect x="${p.x + 8 + c * 18}" y="${p.y + 12}" width="10" height="10" fill="${PCB.pad}"/>`;
      if (p.kind === 'jumpers') for (let c = 0; c < 4; c++) s += `<rect x="${p.x + 10 + c * 34}" y="${p.y + 10}" width="24" height="56" rx="3" fill="${c === 1 || c === 3 ? '#2b5fd0' : '#3a4044'}"/>`;
      s += '</g>';
    } else if (p.kind === 'pcie') {
      s += `${g0}<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="6" fill="#ede6d2" stroke="#b3a988" stroke-width="2"/>
        ${[0, 1, 2].map(r => [0, 1].map(c => `<rect x="${p.x + 18 + c * 42}" y="${p.y + 16 + r * 40}" width="32" height="30" rx="5" fill="${c ? '#e3c21a' : '#4a4a4a'}"/>`).join('')).join('')}</g>`;
    } else {
      s += `${g0}<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="5" fill="#1b1f22" stroke="#4d5559" stroke-width="2"/>
        <circle cx="${p.x + 12}" cy="${p.y + 12}" r="4" fill="#3a4044"/></g>`;
    }
  }
  // the pins of the connectors (pads, live levels, highlighting)
  if (!MP.photo || q || MP.net) for (const sp of spots) {
    const net = MP.net && (sp.kind === MP.net || (MP.net === 'fan' && sp.kind === 'fan'));
    const hit = q && pinMatches(q, sp);
    let col = sp.kind === 'fan12' ? '#e3a03a' : (KIND_COL[sp.kind] || '#4f8fe0');
    if (Y.live && sp.sig && sp.sig.startsWith('j') && io) { const pp = ioPin(sp.sig); if (pp) col = pp.level ? '#7dff9a' : '#1d6f3a'; }
    if (MP.photo && !net && !hit) continue;
    const r = hit || net ? 9 : 7;
    s += (sp.pin === 1 ? `<rect x="${sp.x - r}" y="${sp.y - r}" width="${2 * r}" height="${2 * r}" fill="${col}" class="pad${hit ? ' hit' : ''}${net ? ' net' : ''}"/>`
      : `<circle cx="${sp.x}" cy="${sp.y}" r="${r}" fill="${col}" class="pad${hit ? ' hit' : ''}${net ? ' net' : ''}"/>`);
    if (Y.pins && !MP.photo && MP.view.w < 700) s += `<text x="${sp.x}" y="${sp.y + 3}" class="pinno">${sp.pin}</text>`;
    if (Y.balls && sp.ball && (MP.view.w < 700 || hit)) s += `<text x="${sp.x + (sp.x > PARTS.find(p => p.id === sp.part).x + 28 ? 12 : -12)}" y="${sp.y + 4}" class="ball" text-anchor="${sp.x > PARTS.find(p => p.id === sp.part).x + 28 ? 'start' : 'end'}">${sp.ball}</text>`;
  }
  if (Y.labels) for (const p of PARTS) {
    if (MP.photo && MP.sel !== (p.info || p.id)) continue;   // the photo has its own labels: only name the selected part
    // where the name goes: on big parts inside, next to small ones (never over their pins)
    const lines = p.label.split('\n'), out = ['header', 'fan', 'leds'].includes(p.kind) ? 'above' : p.lab;
    let cx = p.x + p.w / 2, y0, anchor = 'middle';
    if (out === 'above') y0 = p.y - 30 - (lines.length - 1) * 22;
    else if (out === 'below') y0 = p.y + p.h + 24;
    else if (out === 'right') { cx = p.x + p.w + 12; anchor = 'start'; y0 = p.y + p.h / 2 - (lines.length - 1) * 11; }
    else if (out === 'top') y0 = p.y + 40;
    else y0 = p.y + p.h / 2 - (lines.length - 1) * 12 + 6;
    const refY = out === 'above' ? p.y - 8 : y0 + (lines.length - 1) * 24 + 20;
    s += `<g class="lbl${MP.photo ? ' onphoto' : ''}">${lines.map((t, i) => `<text x="${cx}" y="${y0 + i * 24}" class="silk mid" style="text-anchor:${anchor}">${t}</text>`).join('')}
      <text x="${cx}" y="${refY}" class="silk ref" style="text-anchor:${anchor}">${p.ref}</text></g>`;
    if (p.id === 'zynq' && L.sensors && L.sensors.temp_c !== undefined)
      s += `<text x="${cx}" y="${p.y + p.h + 26}" class="silk mid">${L.sensors.temp_c.toFixed(1)} &deg;C</text>`;
  }
  return s + '<defs><filter id="glow"><feGaussianBlur stdDeviation="3"/></filter></defs></svg>';
}

// ------------------------------------------------------------------ the pin table
function pinRows() {
  const rows = [];
  for (let n = 1; n <= 9; n++) for (let pin = 1; pin <= 18; pin++) {
    const [, f, k] = J_LAYOUT[pin - 1], bit = J_PIN_BIT[pin];
    rows.push({ con: 'J' + n, ref: 'plMiner' + (n - 1), pin, func: f, kind: NETS[k] || k,
      ball: bit !== undefined ? J_BALLS[n - 1][bit] : pin === 3 ? (n === 9 ? 'P18' : 'W19') : pin === 4 ? (n === 9 ? 'N17' : 'W18') : pin === 18 ? 'MIO' + (27 + n) : '',
      arduino: bit !== undefined ? `J${n}_${pin}` : pin === 3 ? (n === 9 ? 'SDA1' : 'SDA') : pin === 4 ? (n === 9 ? 'SCL1' : 'SCL') : '',
      verilog: bit !== undefined ? `j${n}[${bit}]` : pin === 3 ? (n === 9 ? 'i2c2_sda' : 'i2c1_sda') : pin === 4 ? (n === 9 ? 'i2c2_scl' : 'i2c1_scl') : '' });
  }
  for (let n = 1; n <= 6; n++) ['GND', '+12 V', 'speed (tach)', 'PWM'].forEach((f, i) => rows.push({ con: 'FAN' + n, ref: 'plFan' + (n - 1), pin: i + 1, func: f,
    kind: 'fans', ball: i === 2 ? FAN_BALLS[n - 1] : i === 3 ? 'J18' : '', arduino: i === 2 ? `FAN${n}_TACH` : i === 3 ? 'FAN_PWM' : '',
    verilog: i === 2 ? `fan_tach[${n - 1}]` : i === 3 ? 'fan_pwm' : '' }));
  ['F16', 'L19', 'M19', 'M17'].forEach((b, i) => rows.push({ con: 'LED' + i, ref: 'D' + (4 + i), pin: '', func: 'FPGA LED (active low)', kind: 'LED',
    ball: b, arduino: 'LED' + i, verilog: `leds[${i}]` }));
  rows.push({ con: 'TP1', ref: 'TP1', pin: '', func: 'test point (FPGA pin)', kind: 'FPGA I/O', ball: 'K18', arduino: 'TP1', verilog: 'tp1' });
  return rows;
}
function pinTableHtml() {
  const f = (MP.tfind || '').toLowerCase();
  const rows = pinRows().filter(r => !f || Object.values(r).join(' ').toLowerCase().includes(f));
  return `<div class="dcard wide"><h3>Every pin<span class="grow"></span><span class="hint">${rows.length} rows</span></h3>
    <div class="row"><input id="ptFind" placeholder="filter: J3, T12, I2C, GND, FAN2 ..." value="${esc(MP.tfind || '')}" style="width:300px" spellcheck="false">
      <button class="small" id="ptCsv">Save as CSV</button><span class="hint">Verilog names are the ones in pins.xdc / project.json; Arduino names for sketches.</span></div>
    <div class="pt-wrap"><table class="pt"><tr><th>Connector</th><th>On the board</th><th>Pin</th><th>Function</th><th>Group</th><th>FPGA / ARM pin</th><th>Arduino</th><th>Verilog</th></tr>
    ${rows.map(r => `<tr data-con="${r.con}"><td><b>${r.con}</b></td><td>${r.ref}</td><td>${r.pin}</td><td>${esc(r.func)}</td><td>${r.kind}</td><td><code>${r.ball}</code></td>
      <td><code>${r.arduino}</code></td><td><code>${r.verilog}</code></td></tr>`).join('')}</table></div></div>`;
}

// ------------------------------------------------------------------ wiring diagrams
function wireCard(title, svg, text) { return `<div class="dcard"><h3>${title}</h3>${svg}<div class="hint">${text}</div></div>`; }
const box = (x, y, w, h, t, fill = '#3a4448', tc = '#fff') => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6" fill="${fill}"/>` +
  t.split('\n').map((l, i, a) => `<text x="${x + w / 2}" y="${y + h / 2 + 4 + (i - (a.length - 1) / 2) * 14}" fill="${tc}" class="wtxt">${l}</text>`).join('');
const wl = (pts, col) => `<polyline points="${pts}" fill="none" stroke="${col}" stroke-width="3" stroke-linejoin="round"/>`;
const lab = (x, y, t, a = 'start') => `<text x="${x}" y="${y}" class="wlab" text-anchor="${a}">${t}</text>`;

function wiringHtml() {
  const W = [];
  W.push(wireCard('An LED on a connector pin',
    `<svg viewBox="0 0 360 150" class="wsvg">${box(10, 30, 90, 90, 'J3\npin 5\n\npin 1 GND', '#e9e3d2', '#222')}
      ${wl('100,52 170,52', '#2fbf6c')}<rect x="170" y="42" width="50" height="20" rx="3" fill="#c9b07a"/>${lab(195, 37, '330 ohm', 'middle')}
      ${wl('220,52 270,52', '#2fbf6c')}<polygon points="270,40 270,64 292,52" fill="#f55"/><line x1="294" y1="40" x2="294" y2="64" stroke="#f55" stroke-width="3"/>${lab(282, 80, 'LED', 'middle')}
      ${wl('294,52 330,52 330,120 100,120 100,108', '#7a8580')}${lab(215, 138, 'GND', 'middle')}</svg>`,
    'The long LED leg toward the pin. <code>pinMode(J3_5, OUTPUT); digitalWrite(J3_5, HIGH);</code> Never more than about 10 mA per pin.'));
  W.push(wireCard('A push button',
    `<svg viewBox="0 0 360 140" class="wsvg">${box(10, 30, 90, 80, 'J3\npin 11\n\npin 1 GND', '#e9e3d2', '#222')}
      ${wl('100,50 190,50 190,40', '#2fbf6c')}<line x1="180" y1="40" x2="240" y2="40" stroke="#ddd" stroke-width="4"/><line x1="200" y1="28" x2="220" y2="28" stroke="#ddd" stroke-width="4"/>
      ${wl('230,40 230,50 300,50 300,100 100,100', '#7a8580')}${lab(210, 18, 'button', 'middle')}</svg>`,
    'The pins have a pull-up inside: no resistor needed. <code>digitalRead(J3_11) == LOW</code> while pressed.'));
  W.push(wireCard('An I2C sensor or display (BME280, SSD1306, ...)',
    `<svg viewBox="0 0 360 170" class="wsvg">${box(10, 20, 100, 130, 'J1\n16  3.3 V\n1  GND\n3  SDA\n4  SCL', '#e9e3d2', '#222')}
      ${box(240, 20, 110, 130, 'sensor\nVCC\nGND\nSDA\nSCL', '#284a72')}
      ${wl('110,63 240,63', '#e3a03a')}${wl('110,80 240,80', '#7a8580')}${wl('110,97 240,97', '#4f8fe0')}${wl('110,114 240,114', '#b65fd6')}</svg>`,
    'Wire on bus 1 (any of J1..J8, pins 3/4), Wire1 on J9. The board has 1 kOhm pull-ups. <code>Wire.begin();</code> then the sensor\'s library. 3.3 V parts only.'));
  W.push(wireCard('USB-UART adapter on the console J12',
    `<svg viewBox="0 0 360 150" class="wsvg">${box(10, 25, 110, 100, 'USB-UART\nTX\nGND\nRX', '#284a72')}${box(240, 25, 110, 100, 'J12\npin 1 RX\npin 2 GND\npin 3 TX', '#e9e3d2', '#222')}
      ${wl('120,68 240,68', '#e05f5f')}${wl('120,84 240,84', '#7a8580')}${wl('120,100 240,100', '#2fbf6c')}</svg>`,
    'Cross TX and RX. 3.3 V adapter only (CP2102, CH340, FT232 set to 3.3 V). 115200 8N1. Then the USB serial tab of Ardzy shows the Linux console (boot messages, login root/root).'));
  W.push(wireCard('A hobby servo',
    `<svg viewBox="0 0 360 150" class="wsvg">${box(10, 25, 100, 100, 'J5\npin 5\n\npin 1 GND', '#e9e3d2', '#222')}${box(250, 25, 100, 100, 'servo\nsignal\n+5 V\nGND', '#3a4448')}
      ${box(130, 112, 90, 32, '5 V supply', '#7a5a1a')}${wl('110,47 250,58', '#e0884f')}${wl('220,124 235,124 235,76 250,76', '#e05f5f')}${wl('110,104 240,104 240,96 250,96', '#7a8580')}${wl('130,135 110,135 110,104', '#7a8580')}</svg>`,
    'Servos need their own 5 V (not the board\'s 3.3 V); connect the GNDs together. The 3.3 V signal works with almost all servos. <code>servo.attach(J5_5); servo.write(90);</code>'));
  W.push(wireCard('A UART device (GPS, ESP32, another Arduino) on Serial1',
    `<svg viewBox="0 0 360 150" class="wsvg">${box(10, 25, 100, 100, 'J1\n11 TX\n12 RX\n1 GND', '#e9e3d2', '#222')}${box(250, 25, 100, 100, 'device\nRX\nTX\nGND', '#284a72')}
      ${wl('110,60 250,60', '#e05f5f')}${wl('110,77 250,77', '#2fbf6c')}${wl('110,94 250,94', '#7a8580')}</svg>`,
    '<code>Serial1.begin(9600);</code> Any other pins: <code>Serial1.setPins(rx, tx)</code>. Up to 3 Mbaud. A 5 V device needs a level shifter (see below).'));
  W.push(wireCard('5 V parts: use a level shifter',
    `<svg viewBox="0 0 360 140" class="wsvg">${box(10, 30, 90, 80, 'board\n3.3 V\npin', '#e9e3d2', '#222')}${box(135, 20, 90, 100, 'level\nshifter\nLV | HV', '#5a3a72')}${box(260, 30, 90, 80, '5 V\ndevice', '#3a4448')}
      ${wl('100,70 135,70', '#2fbf6c')}${wl('225,70 260,70', '#e0884f')}${lab(180, 135, 'LV = 3.3 V (J pin 16), HV = 5 V', 'middle')}</svg>`,
    'Every FPGA pin is 3.3 V: 5 V on a pin can damage the chip. A 4-channel level shifter (BSS138 type) costs very little. Some 5 V parts read 3.3 V as HIGH and need only the board-to-device direction.'));
  W.push(wireCard('Fan headers', fanSvg(), 'Standard 4-pin PC fans. The PWM (pin 4) is shared by all 6 headers; each speed pin is measured separately. Arduino: <code>Ardzy.fan(60)</code>.'));
  return '<div class="dash">' + W.join('') + '</div>';
}

// ------------------------------------------------------------------ how it works
function insideHtml() {
  const L = MP.live, s = L.sensors || {}, st = S.status || {}, n = L.net || {};
  const fpga = st.current ? `${st.fpga}: ${st.current}` : st.fpga || '?';
  const blk = (x, y, w, h, t, col, live) => `<g><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="8" fill="${col}"/>` +
    t.split('\n').map((l, i, a) => `<text x="${x + w / 2}" y="${y + 20 + i * 15}" class="wtxt" fill="#fff">${l}</text>`).join('') +
    (live ? `<text x="${x + w / 2}" y="${y + h - 9}" class="wlive">${esc(live)}</text>` : '') + '</g>';
  const ln = (pts, t, tx, ty) => `<polyline points="${pts}" fill="none" stroke="var(--muted)" stroke-width="2.5"/>${t ? `<text x="${tx}" y="${ty}" class="wlab" text-anchor="middle">${t}</text>` : ''}`;
  const svg = `<svg viewBox="0 0 900 470" class="insidesvg">
    <rect x="200" y="20" width="520" height="430" rx="14" fill="none" stroke="var(--line)" stroke-width="2" stroke-dasharray="6 5"/>
    <text x="460" y="40" class="wlab" text-anchor="middle">Zynq XC7Z010 (one chip)</text>
    ${blk(10, 70, 150, 70, 'Your PC\nArdzy app', '#3a4a5a', '')}
    ${blk(10, 190, 150, 60, 'microSD card\nboot + Debian 13', '#5a4a2a', '')}
    ${blk(10, 300, 150, 60, 'NAND 256 MB\nBitmain (read only)', '#4a4a4a', '')}
    ${blk(10, 390, 150, 50, 'J12 console\n115200 baud', '#4a4a4a', '')}
    ${blk(230, 60, 220, 120, 'ARM: 2 x Cortex-A9\n667 MHz, Linux 6.18\nyour Python / C++ programs', '#284a72', s.cpu_pct !== undefined && s.cpu_pct !== null ? `CPU ${s.cpu_pct.toFixed(0)} %, ${(s.temp_c || 0).toFixed(1)} C` : '')}
    ${blk(230, 200, 220, 60, 'DDR3 controller\n512 MB DDR3-1066', '#3a3a6a', s.mem ? `${s.mem.used_mb} MB used` : '')}
    ${blk(230, 280, 220, 70, 'I/O: Ethernet GEM0, SDIO0,\nSMC (NAND), UART1, GPIO,\nXADC sensors', '#3a5a6a', n.speed ? `link ${n.speed} Mbit/s` : '')}
    ${blk(230, 370, 220, 60, 'ARM GPIO (MIO)\nLEDs, buttons, buzzer', '#3a5a6a', '')}
    ${blk(500, 60, 200, 290, 'FPGA (programmable logic)\n17,600 LUTs, 35,200 FFs\n60 block RAMs, 80 DSPs\n\nyour Verilog, or the\npin-control design with\nPWM, UART, logic analyzer', '#1d6a40', fpga)}
    ${blk(760, 70, 130, 120, 'J1..J9\n36 pins + I2C\n3.3 V', '#6a5a2a', '')}
    ${blk(760, 210, 130, 60, '4 LEDs, TP1', '#6a5a2a', '')}
    ${blk(760, 290, 130, 60, '6 fans\nPWM + speed', '#6a5a2a', '')}
    ${ln('160,105 230,105', 'Ethernet', 195, 98)}${ln('160,220 200,220 200,300 230,300', 'SD', 185, 214)}${ln('160,330 230,330', '', 0, 0)}
    ${ln('160,415 200,415 200,320 230,320', '', 0, 0)}${ln('340,180 340,200', '', 0, 0)}${ln('340,260 340,280', '', 0, 0)}
    ${ln('450,120 500,120', 'AXI', 475, 113)}${ln('450,150 500,150', 'FCLK0', 475, 167)}
    ${ln('700,130 760,130', '', 0, 0)}${ln('700,240 760,240', '', 0, 0)}${ln('700,320 760,320', '', 0, 0)}
  </svg>`;
  return `<div class="dcard wide"><h3>How it works</h3>${svg}
    <p>The ARM runs Linux and your program. It talks to the FPGA through the AXI bus at <code>0x4000_0000 .. 0x7FFF_FFFF</code>
    (memory-mapped registers) and gives it its clock (FCLK0). The FPGA owns the 36 connector pins, the 4 small LEDs, the fan PWM and speed inputs and
    the two I2C buses. The ARM owns the Ethernet, the SD card, the NAND, the console UART and the status LEDs, buttons and buzzer.</p>
    <p class="hint">Arduino sketches and the I/O / Tools views use the pin-control design in the FPGA. Your own Verilog replaces it until you upload a sketch again.</p></div>`;
}

// ------------------------------------------------------------------ view
async function mapShow() {
  clearTimeout(MP.timer);
  const h = location.hash;                                  // links like #view=map&photo=1&net=i2c&find=T12
  if (/photo=1/.test(h)) MP.photo = true;
  if (/net=(\w+)/.test(h)) MP.net = h.match(/net=(\w+)/)[1];
  if (/find=([^&]+)/.test(h)) MP.find = decodeURIComponent(h.match(/find=([^&]+)/)[1]);
  if (/zoom=1/.test(h)) MP.view = { x: 150, y: 950, w: 520, h: 520 * 1440 / 1061 };
  if (/mtab=(\w+)/.test(h)) MP.tab = h.match(/mtab=(\w+)/)[1];
  if (S.connected) await mapLive();
  mapRender();
  MP.timer = setTimeout(mapTick, 2000);
}

async function mapLive() {
  const [sensors, mio, io] = await Promise.all([bget('/api/sensors'), bget('/api/mio'), bget('/api/io')]);
  MP.live.sensors = sensors.ok ? sensors : null;
  MP.live.mio = mio.ok ? mio : null;
  MP.live.io = io.ok ? io : null;
  if (!MP.live.hw) { const hw = await bget('/api/hw'); if (hw.ok) { MP.live.hw = hw; MP.live.net = hw.net; } }
  $('mapState').textContent = S.connected ? (MP.live.io ? 'live (pin-control design running)' : 'live') : 'no board: drawing only';
}

async function mapTick() {
  if (BV.view !== 'map') return;
  if (S.connected) { await mapLive(); if (MP.tab !== 'wiring') mapRender(); }
  MP.timer = setTimeout(mapTick, 2000);
}

function mapRender() {
  $('mapSeg').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.v === MP.tab));
  if (MP.tab === 'wiring') { if (!$('mapBody').querySelector('.wsvg')) $('mapBody').innerHTML = wiringHtml(); return; }
  if (MP.tab === 'inside') { $('mapBody').innerHTML = insideHtml(); return; }
  if (MP.tab === 'pins') { if (!$('ptFind')) mapPinTab(); return; }
  if (!$('mapTools')) mapBoardLayout();
  mapDrawBoard();
}

function mapBoardLayout() {
  const Y = MP.layers;
  $('mapBody').innerHTML = `<div class="map-tools" id="mapTools">
      <span class="seg" id="mpLook"><button data-l="draw">Drawing</button><button data-l="photo">Photo</button></span>
      <label class="check"><input type="checkbox" data-y="labels"> names</label>
      <label class="check"><input type="checkbox" data-y="pins"> pin numbers</label>
      <label class="check"><input type="checkbox" data-y="balls"> FPGA pins</label>
      <label class="check"><input type="checkbox" data-y="live"> live levels</label>
      <span class="seg" id="mpNet"><button data-n="">no net</button>${Object.entries(NETS).map(([k, t]) => `<button data-n="${k}">${t}</button>`).join('')}</span>
      <input id="mpFind" type="search" placeholder="find: T12, SDA, J3 pin 5, fan_pwm" spellcheck="false" style="width:220px">
      <span class="seg"><button id="mpZin" title="zoom in (or the mouse wheel)">+</button><button id="mpZout" title="zoom out">-</button><button id="mpZfit" title="the whole board">fit</button></span>
    </div>
    <div class="map-split"><div class="map-board" id="mapBoardHost"></div><div class="dcard map-info" id="mapInfo"></div></div>`;
  $('mpLook').querySelectorAll('button').forEach(b => b.onclick = () => { MP.photo = b.dataset.l === 'photo'; mapDrawBoard(); });
  // the photo (img/board_top.jpg) is an optional extra, not in the public build: without it, only the drawing
  const probe = new Image();
  probe.onerror = () => { $('mpLook').hidden = true; if (MP.photo) { MP.photo = false; mapDrawBoard(); } };
  probe.src = 'img/board_top.jpg';
  document.querySelectorAll('#mapTools [data-y]').forEach(c => { c.checked = !!Y[c.dataset.y]; c.onchange = () => { Y[c.dataset.y] = c.checked; mapDrawBoard(); }; });
  $('mpNet').querySelectorAll('button').forEach(b => b.onclick = () => { MP.net = b.dataset.n || null; mapDrawBoard(); });
  $('mpFind').value = MP.find;
  $('mpFind').oninput = () => { MP.find = $('mpFind').value; mapDrawBoard(); };
  const zoom = (k, cx, cy) => {
    const v = MP.view, w = Math.max(160, Math.min(1061, v.w * k)), h = w * 1440 / 1061;
    cx = cx === undefined ? v.x + v.w / 2 : cx; cy = cy === undefined ? v.y + v.h / 2 : cy;
    MP.view = { x: Math.max(-200, Math.min(1061 - w + 200, cx - (cx - v.x) * w / v.w)), y: Math.max(-200, Math.min(1440 - h + 200, cy - (cy - v.y) * h / v.h)), w, h };
    if (w >= 1061) MP.view = { x: 0, y: 0, w: 1061, h: 1440 };
    mapDrawBoard();
  };
  $('mpZin').onclick = () => zoom(0.7);
  $('mpZout').onclick = () => zoom(1 / 0.7);
  $('mpZfit').onclick = () => { MP.view = { x: 0, y: 0, w: 1061, h: 1440 }; mapDrawBoard(); };
  const host = $('mapBoardHost');
  host.onwheel = e => {
    e.preventDefault();
    const r = host.querySelector('svg').getBoundingClientRect(), v = MP.view;
    zoom(e.deltaY < 0 ? 0.8 : 1.25, v.x + (e.clientX - r.left) / r.width * v.w, v.y + (e.clientY - r.top) / r.height * v.h);
  };
  host.onmousedown = e => {
    if (MP.view.w >= 1061) return;
    const r = host.querySelector('svg').getBoundingClientRect(), v0 = { ...MP.view }, x0 = e.clientX, y0 = e.clientY;
    let moved = false;
    const mv = ev => {
      if (Math.abs(ev.clientX - x0) + Math.abs(ev.clientY - y0) > 4) moved = true;
      if (!moved) return;
      MP.view = { ...v0, x: v0.x - (ev.clientX - x0) / r.width * v0.w, y: v0.y - (ev.clientY - y0) / r.height * v0.h };
      host.querySelector('svg').setAttribute('viewBox', `${MP.view.x} ${MP.view.y} ${MP.view.w} ${MP.view.h}`);
    };
    const up = () => { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); if (moved) { MP.dragged = Date.now(); mapDrawBoard(); } };
    document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up);
  };
}

function mapDrawBoard() {
  if (!$('mapBoardHost')) return;
  $('mpLook').querySelectorAll('button').forEach(b => b.classList.toggle('on', (b.dataset.l === 'photo') === MP.photo));
  $('mpNet').querySelectorAll('button').forEach(b => b.classList.toggle('on', (b.dataset.n || null) === MP.net));
  $('mapBoardHost').innerHTML = boardSvg();
  mapFit();
  $('mapBoardHost').querySelectorAll('.part').forEach(g => g.onclick = () => {
    if (MP.dragged && Date.now() - MP.dragged < 300) return;
    MP.sel = g.dataset.id; MP.find = ''; $('mpFind').value = ''; mapDrawBoard();
  });
  let html;
  const hits = MP.find ? pinSpots().filter(sp => pinMatches(MP.find, sp)) : [];
  if (MP.find) {
    html = `<h3>Found ${hits.length} pin${hits.length === 1 ? '' : 's'}</h3>` + (hits.length ? '<table class="pt"><tr><th>Where</th><th>Pin</th><th>Function</th><th>FPGA</th><th>Verilog</th></tr>' +
      hits.map(h => `<tr><td>${h.part}</td><td>${h.pin}</td><td>${esc(h.label)}</td><td><code>${h.ball}</code></td><td><code>${h.sig}</code></td></tr>`).join('') + '</table>'
      : '<p class="hint">Nothing matches. Try a connector pin (J3 pin 5), an FPGA pin (T12), a name (SDA, GND, 3.3 V) or a Verilog name (j3[0], fan_pwm).</p>');
  } else {
    const info = partInfo(MP.sel);
    html = `<h3>${esc(info.title)}</h3>${info.body}`;
  }
  const net = MP.net ? `<p class="hint">Highlighted: every <b>${NETS[MP.net]}</b> pin on the connectors.</p>` : '';
  $('mapInfo').innerHTML = html + net + `<p class="hint" style="margin-top:10px">Click any part. Wheel or + / - to zoom, drag to move.
    ${MP.photo ? 'The photo is the real board (the yellow labels are from the pin map).' : 'The drawing is to scale, made from a photo of the board; pin 1 of each connector is the square pad. Dashed parts: position approximate.'}
    ${MP.live.io ? 'Green pads: live pin levels (pin-control design running).' : ''}</p>`;
}

// the whole board fits in the visible part of the view (no scrolling to see the connectors)
function mapFit() {
  const host = $('mapBoardHost'), body = $('mapBody'), svg = host && host.querySelector('svg');
  if (!svg || !body.clientHeight) return;
  const free = body.getBoundingClientRect().bottom - host.getBoundingClientRect().top - 16;
  svg.style.maxHeight = Math.max(620, free) + "px";              // (never so small that the names cannot be read)
}
window.addEventListener('resize', () => { if (BV.view === 'map' && MP.tab === 'board') mapFit(); });

function mapPinTab() {
  $('mapBody').innerHTML = pinTableHtml();
  $('ptFind').oninput = () => {
    MP.tfind = $('ptFind').value;
    const pos = $('ptFind').selectionStart;
    mapPinTab();
    $('ptFind').focus(); $('ptFind').setSelectionRange(pos, pos);
  };
  $('ptCsv').onclick = async () => {
    const rows = pinRows(), head = ['connector', 'on the board', 'pin', 'function', 'group', 'FPGA/ARM pin', 'Arduino', 'Verilog'];
    const csv = [head, ...rows.map(r => [r.con, r.ref, r.pin, r.func, r.kind, r.ball, r.arduino, r.verilog])]
      .map(r => r.map(v => /[",]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : v).join(',')).join('\n');
    const r = await api('/api/savelog', { name: 'ardzy_pins', ext: 'csv', text: csv + '\n' });
    out(r.ok ? 'Pin table saved: ' + r.path : 'Not saved: ' + r.out, r.ok ? 'ok' : 'err');
  };
  $('mapBody').querySelectorAll('tr[data-con]').forEach(tr => tr.ondblclick = () => {
    const c = tr.dataset.con; MP.sel = /^LED|^TP/.test(c) ? 'fpgaleds' : c; MP.tab = 'board'; mapRender();
  });
}

$('mapSeg').querySelectorAll('button').forEach(b => b.onclick = () => { MP.tab = b.dataset.v; mapRender(); });
window.mapShow = mapShow;
