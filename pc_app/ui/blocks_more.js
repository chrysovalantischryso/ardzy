/* Ardzy - more blocks for the Blocks view (Arduino programs):
     I2C       find the devices, write / read a register (8 or 16 bit), "device answers"
     Motors    stepper motors: a STEP/DIR driver (A4988, DRV8825, TMC2208 ...) and a 4-wire motor
               through a ULN2003 board (28BYJ-48)
     Monitor   watch a value (the Watch tab and the board's data logger)
     Functions your own blocks (Blockly's procedures): with inputs, with or without a result
   This file adds to blocks.js: it wraps bkDefine, bkGenerator, bkToolbox and bkSketch. */

const BK_I2C_BUS = [['bus 1 (J1..J8)', 'Wire'], ['bus 2 (J9)', 'Wire1']];
const BK_STEP_PINS = () => BK_PINS;

(function bkMore() {
  const define0 = window.bkDefine, gen0 = window.bkGenerator, tb0 = window.bkToolbox, sketch0 = window.bkSketch;

  window.bkDefine = function () {
    define0();
    const C = { i2c: 200, motor: 340, out: 260 };
    const hex = { type: 'field_input', name: 'ADDR', text: '0x76' };
    Blockly.defineBlocksWithJsonArray(i18nBlocks([
      { type: 'ardzy_i2c_scan', message0: 'print the I2C devices on %1', args0: [{ type: 'field_dropdown', name: 'BUS', options: BK_I2C_BUS }],
        previousStatement: null, nextStatement: null, colour: C.i2c,
        tooltip: 'Asks every address 1 .. 126 and prints the ones that answer (in the Monitor). The board has the pull-up resistors already.' },
      { type: 'ardzy_i2c_found', message0: 'I2C device %1 answers on %2', args0: [hex, { type: 'field_dropdown', name: 'BUS', options: BK_I2C_BUS }],
        output: 'Boolean', colour: C.i2c, tooltip: 'True when a device answers at this address (for example 0x76 = BME280, 0x3C = OLED, 0x68 = MPU6050).' },
      { type: 'ardzy_i2c_write', message0: 'I2C write %1 to register %2 of device %3 on %4',
        args0: [{ type: 'input_value', name: 'VALUE', check: 'Number' }, { type: 'field_input', name: 'REG', text: '0x00' }, hex,
          { type: 'field_dropdown', name: 'BUS', options: BK_I2C_BUS }], inputsInline: true,
        previousStatement: null, nextStatement: null, colour: C.i2c, tooltip: 'Sends one byte (0 .. 255) to a register of the device.' },
      { type: 'ardzy_i2c_read', message0: 'I2C read %1 from register %2 of device %3 on %4',
        args0: [{ type: 'field_dropdown', name: 'SIZE', options: [['1 byte', '1'], ['2 bytes, high first', '2'], ['2 bytes, low first', '2L'], ['2 bytes, signed, high first', '2S']] },
          { type: 'field_input', name: 'REG', text: '0x00' }, hex, { type: 'field_dropdown', name: 'BUS', options: BK_I2C_BUS }],
        output: 'Number', colour: C.i2c, tooltip: 'Reads a register. -1 when the device does not answer.' },
      { type: 'ardzy_stepper', message0: 'stepper with STEP %1 DIR %2 : move %3 steps at %4 steps per second',
        args0: [{ type: 'field_dropdown', name: 'STEP', options: BK_STEP_PINS() }, { type: 'field_dropdown', name: 'DIR', options: BK_STEP_PINS() },
          { type: 'input_value', name: 'STEPS', check: 'Number' }, { type: 'input_value', name: 'SPEED', check: 'Number' }], inputsInline: true,
        previousStatement: null, nextStatement: null, colour: C.motor,
        tooltip: 'For a driver board with STEP and DIR inputs (A4988, DRV8825, TMC2208 ...). A minus number of steps turns the other way. Waits until the move is done.' },
      { type: 'ardzy_stepper4', message0: '4-wire stepper on %1 %2 %3 %4 : move %5 steps at %6 steps per second',
        args0: ['A', 'B', 'C', 'D'].map((n, i) => ({ type: 'field_dropdown', name: n, options: BK_STEP_PINS().slice(i).concat(BK_STEP_PINS().slice(0, i)) }))
          .concat([{ type: 'input_value', name: 'STEPS', check: 'Number' }, { type: 'input_value', name: 'SPEED', check: 'Number' }]), inputsInline: true,
        previousStatement: null, nextStatement: null, colour: C.motor,
        tooltip: 'A small motor through a ULN2003 board (28BYJ-48: 2048 steps make one turn, up to about 500 steps per second). Half steps, smooth. Waits until the move is done; the coils are switched off after it.' },
      { type: 'ardzy_watch', message0: 'watch %1 = %2', args0: [{ type: 'field_input', name: 'NAME', text: 'value' }, { type: 'input_value', name: 'V' }],
        inputsInline: true, previousStatement: null, nextStatement: null, colour: C.out,
        tooltip: 'Shows the newest value in the Watch tab (and the board data logger can record it).' },
    ]));
  };

  window.bkGenerator = function () {
    const G = gen0(), O = G.O, F = G.forBlock;
    // after the names are reset: your own functions first, so their helpers and pins are known
    // before the sketch is put together
    const init0 = G.init;
    G.init = ws => {
      init0(ws);
      G.wires = new Set(); G.functions = [];
      ws.getTopBlocks(true).filter(b => /^procedures_def/.test(b.type) && b.isEnabled()).forEach(b => G.blockToCode(b));
    };
    const v = (b, n, ord, def = '0') => G.valueToCode(b, n, ord) || def;
    const num = (s, def) => { const n = parseInt(String(s || '').trim(), /^0x/i.test(String(s).trim()) ? 16 : 10); return isNaN(n) ? def : n; };
    const addr = b => '0x' + Math.max(1, Math.min(127, num(b.getFieldValue('ADDR'), 0x76))).toString(16).padStart(2, '0');
    const reg = b => '0x' + Math.max(0, Math.min(255, num(b.getFieldValue('REG'), 0))).toString(16).padStart(2, '0');
    const wire = b => { const w = b.getFieldValue('BUS') === 'Wire1' ? 'Wire1' : 'Wire'; G.wires = G.wires || new Set(); G.wires.add(w); return w; };
    F.ardzy_i2c_scan = b => {
      G.helpers.i2cScan = 'void i2cScan(TwoWire &bus, const char *name) {\n  int found = 0;\n' +
        '  for (int a = 1; a < 127; a++) {\n    bus.beginTransmission(a);\n    if (bus.endTransmission() == 0) {\n' +
        '      Serial.print(name); Serial.print(": device at 0x"); if (a < 16) Serial.print("0"); Serial.println(a, HEX); found++;\n    }\n  }\n' +
        '  Serial.print(name); Serial.print(": "); Serial.print(found); Serial.println(" device(s)");\n}';
      const w = wire(b);
      return `i2cScan(${w}, "${w === 'Wire1' ? 'bus 2 (J9)' : 'bus 1 (J1..J8)'}");\n`;
    };
    F.ardzy_i2c_found = b => {
      G.helpers.i2cFound = 'bool i2cFound(TwoWire &bus, int addr) { bus.beginTransmission(addr); return bus.endTransmission() == 0; }';
      return [`i2cFound(${wire(b)}, ${addr(b)})`, O.ATOMIC];
    };
    F.ardzy_i2c_write = b => {
      G.helpers.i2cWrite = 'void i2cWrite(TwoWire &bus, int addr, int reg, int value) {\n' +
        '  bus.beginTransmission(addr); bus.write((uint8_t)reg); bus.write((uint8_t)value); bus.endTransmission();\n}';
      return `i2cWrite(${wire(b)}, ${addr(b)}, ${reg(b)}, (int)(${v(b, 'VALUE', O.NONE)}));\n`;
    };
    F.ardzy_i2c_read = b => {
      G.helpers.i2cRead = '// reads 1 or 2 bytes of a register; -1 when the device does not answer\n' +
        'long i2cRead(TwoWire &bus, int addr, int reg, int n, bool lowFirst, bool sign) {\n' +
        '  bus.beginTransmission(addr); bus.write((uint8_t)reg);\n  if (bus.endTransmission(false) != 0) return -1;\n' +
        '  if ((int)bus.requestFrom((uint8_t)addr, (size_t)n) != n) return -1;\n  long a = bus.read();\n  if (n == 1) return a;\n  long c = bus.read();\n' +
        '  long x = lowFirst ? (c << 8) | a : (a << 8) | c;\n  return (sign && x > 32767) ? x - 65536 : x;\n}';
      const s = b.getFieldValue('SIZE');
      return [`i2cRead(${wire(b)}, ${addr(b)}, ${reg(b)}, ${s === '1' ? 1 : 2}, ${s === '2L'}, ${s === '2S'})`, O.ATOMIC];
    };
    F.ardzy_stepper = b => {
      const sp = b.getFieldValue('STEP'), dp = b.getFieldValue('DIR');
      G.pins[sp] = 'OUTPUT'; G.pins[dp] = 'OUTPUT';
      G.helpers.stepDir = '// a STEP/DIR driver: one pulse per step, DIR chooses the way\n' +
        'void stepperMove(int stepPin, int dirPin, long steps, float perSecond) {\n' +
        '  if (perSecond < 1) perSecond = 1;\n  unsigned long gap = (unsigned long)(1000000.0 / perSecond);\n' +
        '  digitalWrite(dirPin, steps < 0 ? LOW : HIGH);\n  delayMicroseconds(5);\n' +
        '  unsigned long t = micros();\n  for (long i = 0; i < labs(steps); i++) {\n' +
        '    digitalWrite(stepPin, HIGH); delayMicroseconds(5); digitalWrite(stepPin, LOW);\n' +
        '    t += gap;\n    long wait = (long)(t - micros());\n    if (wait > 0) delayMicroseconds(wait);\n  }\n}';
      return `stepperMove(${sp}, ${dp}, (long)(${v(b, 'STEPS', O.NONE, '200')}), ${v(b, 'SPEED', O.NONE, '200')});\n`;
    };
    F.ardzy_stepper4 = b => {
      const p = ['A', 'B', 'C', 'D'].map(n => b.getFieldValue(n));
      p.forEach(x => G.pins[x] = 'OUTPUT');
      G.helpers.step4 = '// a 4-wire motor (ULN2003 + 28BYJ-48): 8 half steps, each switches one or two coils\n' +
        'const uint8_t HALF_STEPS[8] = {0b1000, 0b1100, 0b0100, 0b0110, 0b0010, 0b0011, 0b0001, 0b1001};\n' +
        'int stepper4Phase = 0;\n' +
        'void stepper4Move(int a, int b, int c, int d, long steps, float perSecond) {\n' +
        '  const int pins[4] = {a, b, c, d};\n  if (perSecond < 1) perSecond = 1;\n' +
        '  unsigned long gap = (unsigned long)(1000000.0 / perSecond);\n  unsigned long t = micros();\n' +
        '  for (long i = 0; i < labs(steps); i++) {\n    stepper4Phase = (stepper4Phase + (steps > 0 ? 1 : 7)) % 8;\n' +
        '    for (int k = 0; k < 4; k++) digitalWrite(pins[k], (HALF_STEPS[stepper4Phase] >> (3 - k)) & 1);\n' +
        '    t += gap;\n    long wait = (long)(t - micros());\n    if (wait > 0) delayMicroseconds(wait);\n  }\n' +
        '  for (int k = 0; k < 4; k++) digitalWrite(pins[k], LOW);   // no current while standing (cool motor)\n}';
      return `stepper4Move(${p.join(', ')}, (long)(${v(b, 'STEPS', O.NONE, '2048')}), ${v(b, 'SPEED', O.NONE, '400')});\n`;
    };
    F.ardzy_watch = b => {
      const name = (b.getFieldValue('NAME') || 'value').replace(/[^A-Za-z0-9_]/g, '_');
      const x = v(b, 'V', O.NONE, '0'), src = b.getInputTargetBlock('V');
      if (src && (src.type === 'text' || src.type === 'text_join')) return `Ardzy.watch("${name}", String(${x}).c_str());\n`;
      return `Ardzy.watch("${name}", (double)(${x}));\n`;
    };
    // your own blocks (Blockly's "Functions" category); inputs and results are numbers like the variables
    const procName = b => G.nameDB_.getName(b.getFieldValue('NAME'), Blockly.Names.NameType.PROCEDURE);
    const procDef = (b, ret) => {
      const args = b.getVars().map(n => 'float ' + G.nameDB_.getName(n, Blockly.Names.NameType.VARIABLE));
      let body = G.statementToCode(b, 'STACK');
      if (ret) body += `  return ${v(b, 'RETURN', O.NONE, '0')};\n`;
      G.functions = G.functions || [];
      G.functions.push(`${ret ? 'float' : 'void'} ${procName(b)}(${args.join(', ')}) {\n${body}}`);
      return null;
    };
    F.procedures_defnoreturn = b => procDef(b, false);
    F.procedures_defreturn = b => procDef(b, true);
    const call = b => `${procName(b)}(${b.getVars().map((_n, i) => v(b, 'ARG' + i, O.NONE)).join(', ')})`;
    F.procedures_callnoreturn = b => call(b) + ';\n';
    F.procedures_callreturn = b => [call(b), O.ATOMIC];
    F.procedures_ifreturn = b => {
      const c = v(b, 'CONDITION', O.NONE, 'false');
      return b.hasReturnValue_ ? `if (${c}) {\n  return ${v(b, 'VALUE', O.NONE, '0')};\n}\n` : `if (${c}) {\n  return;\n}\n`;
    };
    return G;
  };

  window.bkToolbox = function () {
    const tb = tb0();
    const sh = n => ({ shadow: { type: 'math_number', fields: { NUM: n } } });
    const k = (type, inputs) => Object.assign({ kind: 'block', type }, inputs ? { inputs } : {});
    const cats = tb.contents;
    const at = name => cats.findIndex(c => c.name === name);
    const mon = cats[at('Monitor')];
    if (mon) mon.contents.splice(2, 0, k('ardzy_watch', { V: sh(0) }));
    const i = at('Time') + 1 || cats.length;
    cats.splice(i, 0,
      { kind: 'category', name: 'I2C', colour: '200', contents: [k('ardzy_i2c_scan'), k('ardzy_i2c_found'),
        k('ardzy_i2c_read'), k('ardzy_i2c_write', { VALUE: sh(0) })] },
      { kind: 'category', name: 'Motors', colour: '340', contents: [k('ardzy_servo', { ANGLE: sh(90) }),
        k('ardzy_stepper', { STEPS: sh(200), SPEED: sh(400) }), k('ardzy_stepper4', { STEPS: sh(2048), SPEED: sh(400) })] });
    cats.push({ kind: 'category', name: 'Functions', categorystyle: 'procedure_category', custom: 'PROCEDURE' });
    return tb;
  };

  window.bkSketch = function (ws) {
    const G = BK.gen;
    const defs = ws.getTopBlocks(true).filter(b => /^procedures_def/.test(b.type));
    const r = sketch0(ws);                       // G.init (above) walks the functions, then the program
    let code = r.code;
    const extra = [];
    if (G.wires.size && !/#include <Wire\.h>/.test(code)) extra.push('#include <Wire.h>', '');
    if (G.functions.length) {
      const decl = G.functions.map(f => f.split('\n')[0].replace(/ \{$/, ';'));
      extra.push('// your own blocks', ...decl, '');
    }
    if (extra.length) code = code.replace(/(\/\/ This file is written again[^\n]*\n\n)/, '$1' + extra.join('\n') + '\n');
    if (G.wires.size) code = code.replace('  Serial.begin(115200);\n', '  Serial.begin(115200);\n' + [...G.wires].map(w => `  ${w}.begin();\n`).join(''));
    if (G.functions.length) code = code.replace(/\n(\/\/ ---- helpers used by the blocks|$)/, '\n// ---- your own blocks\n' + G.functions.join('\n\n') + '\n\n$1');
    const loose = Math.max(0, r.loose - defs.length);      // a function is not a loose block
    return Object.assign({}, r, { code: code.replace(/\n{3,}/g, '\n\n'), loose });
  };

  // examples that use the new blocks
  Object.assign(BK_EXAMPLES, {
    'Find I2C devices': () => bkProg(null, bkSeq(bkB('ardzy_i2c_scan', { BUS: 'Wire' }), bkB('ardzy_i2c_scan', { BUS: 'Wire1' }),
      bkB('ardzy_wait', null, { S: bkNum(5) }))),
    'Stepper: one turn each way': () => bkProg(null, bkSeq(
      bkB('ardzy_stepper4', { A: 'J1_5', B: 'J1_11', C: 'J1_12', D: 'J1_15' }, { STEPS: bkNum(2048), SPEED: bkNum(400) }),
      bkB('ardzy_wait', null, { S: bkNum(1) }),
      bkB('ardzy_stepper4', { A: 'J1_5', B: 'J1_11', C: 'J1_12', D: 'J1_15' }, { STEPS: bkNum(-2048), SPEED: bkNum(400) }),
      bkB('ardzy_wait', null, { S: bkNum(1) }))),
  });
})();
