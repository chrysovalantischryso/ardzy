// ardzy.js: the Ardzy board from JavaScript (Node.js).   Use it with:  const ardzy = require('./ardzy');
//
//   ardzy.led('green', true);           // status LED: 'green', 'red' (S9 also 'ps')
//   ardzy.beep(0.1);                    // buzzer, seconds
//   if (ardzy.button('ip')) ...         // true while pressed: 'ip' or 'reset' (EBAZ4205: also 's2', 's3')
//   const v = ardzy.peek(0x41200000);   // 32-bit FPGA register at an address (Vivado's Address Editor)
//   ardzy.poke(0x41200000, 5);
//   ardzy.reg(1, 3); ardzy.regWrite(1, 3, 42);   // word 3 of slot 1 of an Ardzy FPGA project
//   ardzy.watch({ speed: 12.5 });       // live values for the app's Watch tab and Plotter
//   ardzy.sleep(0.5);                   // wait, seconds (blocks, like Arduino's delay)
//
// Only use FPGA registers that the loaded FPGA design really has: reading an address with nothing
// behind it can hang the board until it is reset.
'use strict';
const fs = require('fs');
const { spawn, execFileSync } = require('child_process');

const BUS_BASE = 0x43C00000;
// The board's LEDs, buttons and buzzer: name -> [GPIO, the level that means on / pressed], from
// /run/ardzy/board-io.txt (written at boot; every Ardzy board has its own). Without it: the Antminer S9.
const IO = (() => {
  const io = {};
  try {
    for (const line of fs.readFileSync('/run/ardzy/board-io.txt', 'utf8').split('\n')) {
      const f = line.trim().split(/\s+/);
      if (f.length === 3 && !f[0].startsWith('#')) io[f[0]] = [+f[1], +f[2]];
    }
  } catch (e) { /* an older card */ }
  return Object.keys(io).length ? io : { led_green: [38, 1], led_red: [37, 1], led_ps: [15, 0], buzzer: [39, 1],
    button_ip: [51, 0], button_reset: [47, 0] };
})();

const gpioSet = (n, v) => fs.writeFileSync(`/sys/class/gpio/gpio${n}/value`, v ? '1' : '0');
const gpioGet = n => fs.readFileSync(`/sys/class/gpio/gpio${n}/value`, 'utf8')[0] === '1';

function sleep(seconds) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, Math.max(0, seconds * 1000));
}

function led(name, on = true) {
  const l = IO['led_' + name];
  if (!l) throw new Error(`led: this board has no LED "${name}" (see /run/ardzy/board-io.txt)`);
  gpioSet(l[0], on ? l[1] === 1 : l[1] === 0);
}

function beep(seconds = 0.1) {                   // (a board without a buzzer only waits)
  const b = IO.buzzer;
  if (b) gpioSet(b[0], true);
  sleep(seconds);
  if (b) gpioSet(b[0], false);
}

function button(name = 'ip') {
  const b = IO['button_' + name];
  if (!b) throw new Error(`button: this board has no button "${name}"`);
  return gpioGet(b[0]) === (b[1] === 1);
}

// FPGA registers: through the board's register helper (Node.js cannot map memory by itself).
// It runs beside the program and answers through two named pipes, so every call is synchronous.
let rd = null, wr = null, buf = '';
function regd(cmd) {
  if (wr === null) {
    const h = process.env.ARDZY_REGD;
    if (!h) throw new Error('the register helper is missing (start the program with Upload)');
    const dir = fs.mkdtempSync('/tmp/ardzy-');
    execFileSync('mkfifo', [dir + '/in', dir + '/out']);
    spawn('sh', ['-c', 'exec "$0" < "$1" > "$2"', h, dir + '/in', dir + '/out'], { stdio: ['ignore', 'ignore', 'inherit'] }).unref();
    wr = fs.openSync(dir + '/in', 'w');
    rd = fs.openSync(dir + '/out', 'r');
    fs.rmSync(dir, { recursive: true, force: true });
  }
  fs.writeSync(wr, cmd + '\n');
  while (!buf.includes('\n')) {
    const b = Buffer.alloc(64);
    const n = fs.readSync(rd, b, 0, 64, null);
    if (n <= 0) throw new Error('register helper stopped');
    buf += b.toString('utf8', 0, n);
  }
  const i = buf.indexOf('\n');
  const ans = buf.slice(0, i);
  buf = buf.slice(i + 1);
  if (ans.startsWith('error')) throw new Error(ans);
  return ans;
}

const peek = addr => Number(regd('r ' + (addr >>> 0)));
const poke = (addr, value) => { regd('w ' + (addr >>> 0) + ' ' + (value >>> 0)); };
const reg = (slot, word) => peek(BUS_BASE + slot * 0x1000 + 4 * word);
const regWrite = (slot, word, value) => poke(BUS_BASE + slot * 0x1000 + 4 * word, value);

function watch(values) {
  console.log(Object.entries(values).map(([k, v]) =>
    typeof v === 'number' || typeof v === 'boolean' ? `${k}:${+v}` : `${k}="${String(v).replace(/"/g, "'")}"`).join(' '));
}

module.exports = { led, beep, button, peek, poke, reg, regWrite, watch, sleep, BUS_BASE };
