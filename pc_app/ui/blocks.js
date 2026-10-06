/* Ardzy - Blocks view: make programs by snapping blocks together, like Scratch. The blocks become a real Arduino
   sketch (C++) shown next to them; Upload and run builds it on the board like any sketch (the pin-control
   design is loaded for it). A blocks project keeps name.blocks.json (the blocks) and name.ino (the sketch).
   Blockly (Google, Apache 2.0) draws the blocks: ui/vendor/blockly. Helpers from app.js: $, esc, api, out, S. */
const BK = { ws: null, project: null, saveT: null, cm: null, loading: false, injected: false, mode: 'ino' };   // mode: ino = Arduino program, fpga = FPGA design

const BK_PINS = [];
for (let n = 1; n <= 9; n++) for (const p of [5, 11, 12, 15]) BK_PINS.push([`J${n} pin ${p}`, `J${n}_${p}`]);
const BK_OUTS = [['LED0 (FPGA)', 'LED0'], ['LED1 (FPGA)', 'LED1'], ['LED2 (FPGA)', 'LED2'], ['LED3 (FPGA)', 'LED3'], ['green status LED', 'LED_GREEN'], ['red status LED', 'LED_RED']];
const BK_NOTES = (() => {
  const names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'], out = [];
  for (let o = 3; o <= 6; o++) names.forEach((n, i) => out.push([n + o, String(Math.round(440 * Math.pow(2, (o - 4) + (i - 9) / 12)))]));
  return out;
})();

/* ---------------------------------------------------------------- the blocks */
function bkDefine() {
  const C = { start: 45, pins: 160, light: 190, sound: 300, board: 20, time: 120, out: 260, math: 230 };
  Blockly.defineBlocksWithJsonArray(i18nBlocks([
    { type: 'ardzy_program', message0: 'when the board starts %1 %2 forever %3 %4',
      args0: [{ type: 'input_dummy' }, { type: 'input_statement', name: 'SETUP' }, { type: 'input_dummy' }, { type: 'input_statement', name: 'LOOP' }],
      colour: C.start, tooltip: 'The program: the blocks under "when the board starts" run once, then the blocks under "forever" run again and again.' },
    { type: 'ardzy_pin_write', message0: 'set pin %1 to %2', args0: [{ type: 'field_dropdown', name: 'PIN', options: BK_PINS },
      { type: 'field_dropdown', name: 'LEVEL', options: [['HIGH (3.3 V)', 'HIGH'], ['LOW (0 V)', 'LOW']] }],
      previousStatement: null, nextStatement: null, colour: C.pins, tooltip: 'Makes a connector pin an output and sets it.' },
    { type: 'ardzy_pin_toggle', message0: 'toggle pin %1', args0: [{ type: 'field_dropdown', name: 'PIN', options: BK_PINS.concat(BK_OUTS) }],
      previousStatement: null, nextStatement: null, colour: C.pins, tooltip: 'HIGH becomes LOW, LOW becomes HIGH.' },
    { type: 'ardzy_pin_read', message0: 'pin %1 is HIGH', args0: [{ type: 'field_dropdown', name: 'PIN', options: BK_PINS }],
      output: 'Boolean', colour: C.pins, tooltip: 'Reads a connector pin (with its pull-up: a button to GND reads LOW when pressed).' },
    { type: 'ardzy_led', message0: 'turn %1 %2', args0: [{ type: 'field_dropdown', name: 'LED', options: BK_OUTS },
      { type: 'field_dropdown', name: 'STATE', options: [['on', 'HIGH'], ['off', 'LOW']] }],
      previousStatement: null, nextStatement: null, colour: C.light, tooltip: 'The 4 small FPGA LEDs or the status LEDs of the board.' },
    { type: 'ardzy_button', message0: 'button %1 is pressed', args0: [{ type: 'field_dropdown', name: 'BTN', options: [['IP', 'BUTTON_IP'], ['Reset', 'BUTTON_RESET']] }],
      output: 'Boolean', colour: C.light, tooltip: 'The two buttons on the board.' },
    { type: 'ardzy_pwm', message0: 'set brightness of %1 to %2 %%', args0: [{ type: 'field_dropdown', name: 'PIN', options: BK_PINS.concat(BK_OUTS.slice(0, 4)) },
      { type: 'input_value', name: 'VALUE', check: 'Number' }], inputsInline: true,
      previousStatement: null, nextStatement: null, colour: C.light, tooltip: 'PWM: 0 % off, 100 % fully on, anything between.' },
    { type: 'ardzy_servo', message0: 'turn servo on %1 to %2 degrees', args0: [{ type: 'field_dropdown', name: 'PIN', options: BK_PINS },
      { type: 'input_value', name: 'ANGLE', check: 'Number' }], inputsInline: true,
      previousStatement: null, nextStatement: null, colour: C.pins, tooltip: 'A hobby servo: 0 .. 180 degrees. It needs its own 5 V supply.' },
    { type: 'ardzy_tone', message0: 'play %1 Hz on %2 for %3 ms', args0: [{ type: 'input_value', name: 'FREQ', check: 'Number' },
      { type: 'field_dropdown', name: 'PIN', options: BK_PINS }, { type: 'input_value', name: 'MS', check: 'Number' }], inputsInline: true,
      previousStatement: null, nextStatement: null, colour: C.sound, tooltip: 'Plays a tone on a pin and waits until it ends (a small speaker or passive buzzer from the pin to GND, with 100 ohm in series).' },
    { type: 'ardzy_note', message0: 'note %1', args0: [{ type: 'field_dropdown', name: 'NOTE', options: BK_NOTES }], output: 'Number',
      colour: C.sound, tooltip: 'The frequency of a musical note (A4 = 440 Hz).' },
    { type: 'ardzy_beep', message0: 'beep for %1 ms', args0: [{ type: 'input_value', name: 'MS', check: 'Number' }], inputsInline: true,
      previousStatement: null, nextStatement: null, colour: C.sound, tooltip: 'The buzzer on the board.' },
    { type: 'ardzy_fan', message0: 'set the fans to %1 %%', args0: [{ type: 'input_value', name: 'P', check: 'Number' }], inputsInline: true,
      previousStatement: null, nextStatement: null, colour: C.board, tooltip: 'All 6 fan headers, 0 .. 100 %.' },
    { type: 'ardzy_temp', message0: 'chip temperature (C)', output: 'Number', colour: C.board, tooltip: 'The temperature of the Zynq chip in degrees Celsius.' },
    { type: 'ardzy_fan_rpm', message0: 'speed of fan %1 (rpm)', args0: [{ type: 'field_dropdown', name: 'FAN', options: [['1', '1'], ['2', '2'], ['3', '3'], ['4', '4'], ['5', '5'], ['6', '6']] }],
      output: 'Number', colour: C.board, tooltip: 'Fan speed measured from its tach wire.' },
    { type: 'ardzy_wait', message0: 'wait %1 seconds', args0: [{ type: 'input_value', name: 'S', check: 'Number' }], inputsInline: true,
      previousStatement: null, nextStatement: null, colour: C.time, tooltip: 'Does nothing for that long (0.5 = half a second).' },
    { type: 'ardzy_every', message0: 'every %1 ms %2 %3', args0: [{ type: 'input_value', name: 'MS', check: 'Number' }, { type: 'input_dummy' }, { type: 'input_statement', name: 'DO' }],
      inputsInline: true, previousStatement: null, nextStatement: null, colour: C.time,
      tooltip: 'Runs its blocks every so many milliseconds without stopping the rest (put it under "forever"; several can run side by side).' },
    { type: 'ardzy_millis', message0: 'milliseconds since start', output: 'Number', colour: C.time, tooltip: 'A clock that counts from 0 when the program starts.' },
    { type: 'ardzy_print', message0: 'print %1', args0: [{ type: 'input_value', name: 'V' }], previousStatement: null, nextStatement: null,
      colour: C.out, tooltip: 'A line in the Monitor of the app.' },
    { type: 'ardzy_plot', message0: 'plot %1 = %2', args0: [{ type: 'field_input', name: 'NAME', text: 'value' }, { type: 'input_value', name: 'V', check: 'Number' }],
      inputsInline: true, previousStatement: null, nextStatement: null, colour: C.out, tooltip: 'A point on the Plotter tab (several names draw several lines).' },
    { type: 'ardzy_map', message0: 'map %1 from %2 .. %3 to %4 .. %5', args0: ['X', 'A', 'B', 'C', 'D'].map(n => ({ type: 'input_value', name: n, check: 'Number' })),
      inputsInline: true, output: 'Number', colour: C.math, tooltip: 'Scales a number from one range to another (for example a temperature 30 .. 80 to fan 0 .. 100 %).' },
  ]));
}

/* ---------------------------------------------------------------- blocks -> C++ (an Arduino sketch) */
function bkGenerator() {
  const G = new (Blockly.CodeGenerator || Blockly.Generator)('Cpp');
  const O = { ATOMIC: 0, UNARY: 2, MULT: 3, ADD: 4, REL: 6, EQ: 7, AND: 11, OR: 12, COND: 13, NONE: 99 };
  G.O = O;
  G.INDENT = '  ';
  G.addReservedWords('setup,loop,delay,millis,int,float,long,char,bool,true,false,if,else,for,while,do,return,break,continue,switch,case,default,' +
    'void,String,Serial,Ardzy,Servo,tone,random,map,abs,min,max,pow,sqrt,round,floor,ceil,HIGH,LOW,INPUT,OUTPUT,class,new,delete,auto,const,static,unsigned,signed,struct');
  G.init = function (ws) {
    G.pins = {}; G.servos = new Set(); G.helpers = {}; G.counter = 0;
    G.isInitialized = true;
    if (!G.nameDB_) G.nameDB_ = new Blockly.Names(G.RESERVED_WORDS_); else G.nameDB_.reset();
    G.nameDB_.setVariableMap(ws.getVariableMap());
    G.nameDB_.populateVariables(ws);
  };
  G.scrub_ = function (block, code, thisOnly) {
    const next = block.nextConnection && block.nextConnection.targetBlock();
    return code + (next && !thisOnly ? G.blockToCode(next) : '');
  };
  G.scrubNakedValue = line => line + ';\n';
  const v = (b, n, ord, def = '0') => G.valueToCode(b, n, ord) || def;
  const st = (b, n) => G.statementToCode(b, n);
  const mode = (pin, m) => { if (G.pins[pin] !== 'OUTPUT') G.pins[pin] = m; };
  const varName = id => G.nameDB_.getName(id, Blockly.Names.NameType.VARIABLE);
  const F = G.forBlock;
  F.ardzy_program = () => '';
  F.ardzy_pin_write = b => { mode(b.getFieldValue('PIN'), 'OUTPUT'); return `digitalWrite(${b.getFieldValue('PIN')}, ${b.getFieldValue('LEVEL')});\n`; };
  F.ardzy_pin_toggle = b => { const p = b.getFieldValue('PIN'); mode(p, 'OUTPUT'); return `digitalWrite(${p}, !digitalRead(${p}));\n`; };
  F.ardzy_pin_read = b => { mode(b.getFieldValue('PIN'), 'INPUT_PULLUP'); return [`(digitalRead(${b.getFieldValue('PIN')}) == HIGH)`, O.ATOMIC]; };
  F.ardzy_led = b => { mode(b.getFieldValue('LED'), 'OUTPUT'); return `digitalWrite(${b.getFieldValue('LED')}, ${b.getFieldValue('STATE')});\n`; };
  F.ardzy_button = b => [`(digitalRead(${b.getFieldValue('BTN')}) == LOW)`, O.ATOMIC];
  F.ardzy_pwm = b => `analogWrite(${b.getFieldValue('PIN')}, (int)(constrain(${v(b, 'VALUE', O.NONE)}, 0, 100) * 255 / 100));\n`;
  F.ardzy_servo = b => { const p = b.getFieldValue('PIN'); G.servos.add(p); return `servo_${p}.write((int)(${v(b, 'ANGLE', O.NONE, '90')}));\n`; };
  F.ardzy_tone = b =>                                        // plays the whole note, then goes on (like Scratch)
    `{ unsigned long ms = (unsigned long)(${v(b, 'MS', O.NONE, '200')}); tone(${b.getFieldValue('PIN')}, (unsigned int)(${v(b, 'FREQ', O.NONE, '440')}), ms); delay(ms); }\n`;
  F.ardzy_note = b => [b.getFieldValue('NOTE'), O.ATOMIC];
  F.ardzy_beep = b => `Ardzy.beep((unsigned int)(${v(b, 'MS', O.NONE, '100')}));\n`;
  F.ardzy_fan = b => `Ardzy.fan((int)(${v(b, 'P', O.NONE)}));\n`;
  F.ardzy_temp = () => ['Ardzy.temperature()', O.ATOMIC];
  F.ardzy_fan_rpm = b => [`Ardzy.fanRpm(${b.getFieldValue('FAN')})`, O.ATOMIC];
  F.ardzy_wait = b => `delay((unsigned long)((${v(b, 'S', O.NONE, '1')}) * 1000));\n`;
  F.ardzy_millis = () => ['millis()', O.ATOMIC];
  F.ardzy_every = b => {
    const t = 'every_' + (++G.counter);
    return `{\n  static unsigned long ${t} = 0;\n  if (millis() - ${t} >= (unsigned long)(${v(b, 'MS', O.NONE, '1000')})) {\n    ${t} = millis();\n` +
      st(b, 'DO').replace(/^(?=.)/gm, '  ') + '  }\n}\n';
  };
  const txtHelper = () => {                                  // numbers as text: 3 instead of 3.00 (block variables are float)
    G.helpers.txt = '// numbers as text: whole numbers without ".00"\n' +
      'String txt(const String &s) { return s; }\nString txt(const char *s) { return String(s); }\n' +
      'String txt(bool b) { return b ? "true" : "false"; }\n' +
      'String txt(double v) { return v == (double)(long)v ? String((long)v) : String(v, 3); }\n' +
      'String txt(float v) { return txt((double)v); }\nString txt(int v) { return String(v); }\n' +
      'String txt(long v) { return String(v); }\nString txt(unsigned long v) { return String(v); }';
  };
  F.ardzy_print = b => {
    const x = v(b, 'V', O.NONE, '""');
    if (/^"([^"\\]|\\.)*"$/.test(x)) return `Serial.println(${x});\n`;      // plain text: no helper needed
    txtHelper();
    return `Serial.println(txt(${x}));\n`;
  };
  F.ardzy_plot = b => {
    const name = (b.getFieldValue('NAME') || 'value').replace(/[^A-Za-z0-9_]/g, '_');
    return `Serial.print("${name}:"); Serial.println(${v(b, 'V', O.NONE)});\n`;
  };
  F.ardzy_map = b => {
    G.helpers.map = 'float mapf(float x, float a, float b, float c, float d) { return b == a ? c : c + (x - a) * (d - c) / (b - a); }';
    return [`mapf(${['X', 'A', 'B', 'C', 'D'].map(n => v(b, n, O.NONE)).join(', ')})`, O.ATOMIC];
  };
  // the standard Blockly blocks
  F.controls_if = b => {
    let code = '', n = 0;
    do {
      code += (n ? ' else ' : '') + `if (${v(b, 'IF' + n, O.NONE, 'false')}) {\n${st(b, 'DO' + n)}}`;
      n++;
    } while (b.getInput('IF' + n));
    if (b.getInput('ELSE')) code += ` else {\n${st(b, 'ELSE')}}`;
    return code + '\n';
  };
  F.controls_repeat_ext = b => {
    const i = G.nameDB_.getDistinctName('i', Blockly.Names.NameType.VARIABLE);
    return `for (int ${i} = 0; ${i} < (int)(${v(b, 'TIMES', O.NONE)}); ${i}++) {\n${st(b, 'DO')}}\n`;
  };
  F.controls_whileUntil = b => {
    const c = v(b, 'BOOL', O.NONE, 'false');
    return `while (${b.getFieldValue('MODE') === 'UNTIL' ? '!(' + c + ')' : c}) {\n${st(b, 'DO')}}\n`;
  };
  F.controls_for = b => {
    const x = varName(b.getFieldValue('VAR'));
    return `for (${x} = ${v(b, 'FROM', O.NONE)}; ${x} <= ${v(b, 'TO', O.NONE)}; ${x} += ${v(b, 'BY', O.NONE, '1')}) {\n${st(b, 'DO')}}\n`;
  };
  F.controls_flow_statements = b => b.getFieldValue('FLOW') === 'BREAK' ? 'break;\n' : 'continue;\n';
  F.logic_compare = b => {
    const op = { EQ: '==', NEQ: '!=', LT: '<', LTE: '<=', GT: '>', GTE: '>=' }[b.getFieldValue('OP')];
    return [`${v(b, 'A', O.REL)} ${op} ${v(b, 'B', O.REL)}`, op.length === 2 && op[0] !== '<' && op[0] !== '>' ? O.EQ : O.REL];
  };
  F.logic_operation = b => {
    const and = b.getFieldValue('OP') === 'AND', o = and ? O.AND : O.OR;
    return [`${v(b, 'A', o, 'false')} ${and ? '&&' : '||'} ${v(b, 'B', o, 'false')}`, o];
  };
  F.logic_negate = b => [`!${v(b, 'BOOL', O.UNARY, 'false')}`, O.UNARY];
  F.logic_boolean = b => [b.getFieldValue('BOOL') === 'TRUE' ? 'true' : 'false', O.ATOMIC];
  F.math_number = b => [String(Number(b.getFieldValue('NUM'))), O.ATOMIC];
  F.math_arithmetic = b => {
    const op = b.getFieldValue('OP');
    if (op === 'POWER') return [`pow(${v(b, 'A', O.NONE)}, ${v(b, 'B', O.NONE)})`, O.ATOMIC];
    const [s, o] = { ADD: ['+', O.ADD], MINUS: ['-', O.ADD], MULTIPLY: ['*', O.MULT], DIVIDE: ['/', O.MULT] }[op];
    return [`${v(b, 'A', o)} ${s} ${op === 'DIVIDE' ? '(float)' : ''}${v(b, 'B', o)}`, o];
  };
  F.math_single = b => {
    const x = v(b, 'NUM', O.NONE), op = b.getFieldValue('OP');
    const f = { ROOT: `sqrt(${x})`, ABS: `fabs(${x})`, NEG: `-(${x})`, LN: `log(${x})`, LOG10: `log10(${x})`, EXP: `exp(${x})`, POW10: `pow(10, ${x})` }[op];
    return [f || x, O.UNARY];
  };
  F.math_round = b => [`${{ ROUND: 'round', ROUNDUP: 'ceil', ROUNDDOWN: 'floor' }[b.getFieldValue('OP')]}(${v(b, 'NUM', O.NONE)})`, O.ATOMIC];
  F.math_modulo = b => [`fmod(${v(b, 'DIVIDEND', O.NONE)}, ${v(b, 'DIVISOR', O.NONE, '1')})`, O.ATOMIC];
  F.math_random_int = b => [`random((long)(${v(b, 'FROM', O.NONE)}), (long)(${v(b, 'TO', O.NONE, '100')}) + 1)`, O.ATOMIC];
  F.math_constrain = b => [`constrain(${v(b, 'VALUE', O.NONE)}, ${v(b, 'LOW', O.NONE)}, ${v(b, 'HIGH', O.NONE, '100')})`, O.ATOMIC];
  F.text = b => [`"${(b.getFieldValue('TEXT') || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`, O.ATOMIC];
  F.text_join = b => {
    const parts = [];
    txtHelper();
    for (let i = 0; i < b.itemCount_; i++) parts.push(`txt(${v(b, 'ADD' + i, O.NONE, '""')})`);
    return [parts.length ? parts.join(' + ') : 'String("")', O.ADD];
  };
  F.variables_get = b => [varName(b.getFieldValue('VAR')), O.ATOMIC];
  F.variables_set = b => `${varName(b.getFieldValue('VAR'))} = ${v(b, 'VALUE', O.NONE)};\n`;
  F.math_change = b => `${varName(b.getFieldValue('VAR'))} += ${v(b, 'DELTA', O.NONE, '1')};\n`;
  return G;
}

function bkSketch(ws) {
  const G = BK.gen;
  G.init(ws);
  const prog = ws.getTopBlocks(true).filter(b => b.type === 'ardzy_program');
  const setup = prog.length ? G.statementToCode(prog[0], 'SETUP') : '';
  const loop = prog.length ? G.statementToCode(prog[0], 'LOOP') : '';
  const loose = ws.getTopBlocks(false).filter(b => b.type !== 'ardzy_program' && !b.outputConnection).length;
  const vars = ws.getAllVariables().map(x => G.nameDB_.getName(x.getId(), Blockly.Names.NameType.VARIABLE));
  const lines = [`// ${BK.project || 'sketch'}: made with Ardzy Blocks.`,
    '// This file is written again from the blocks every time they change: change the blocks, not this file.', ''];
  if (G.servos.size) lines.push('#include <Servo.h>', '');
  if (vars.length) lines.push(...vars.map(n => `float ${n} = 0;`), '');
  G.servos.forEach(p => lines.push(`Servo servo_${p};`));
  if (G.servos.size) lines.push('');
  lines.push('void setup() {', '  Serial.begin(115200);');
  Object.entries(G.pins).forEach(([p, m]) => lines.push(`  pinMode(${p}, ${m});`));
  G.servos.forEach(p => lines.push(`  servo_${p}.attach(${p});`));
  lines.push(setup.replace(/\n$/, ''), '}', '', 'void loop() {', loop.replace(/\n$/, '') || '  // (nothing yet: put blocks under "forever")', '}', '');
  if (Object.keys(G.helpers).length) lines.push('// ---- helpers used by the blocks', ...Object.values(G.helpers).flatMap(h => [h, '']));
  return { code: lines.filter((l, i, a) => !(l === '' && a[i - 1] === '')).join('\n').replace(/\n\n}/g, '\n}'), loose, hasProgram: prog.length > 0 };
}

/* ---------------------------------------------------------------- examples */
const bkB = (type, fields, inputs, next) => {
  const o = { type };
  if (fields) o.fields = fields;
  if (inputs) o.inputs = Object.fromEntries(Object.entries(inputs).map(([k, x]) => [k, { block: x }]));
  if (next) o.next = { block: next };
  return o;
};
const bkSeq = (...bs) => { for (let i = bs.length - 2; i >= 0; i--) bs[i].next = { block: bs[i + 1] }; return bs[0]; };
const bkNum = n => bkB('math_number', { NUM: n });
const bkProg = (setup, loop) => ({ blocks: { languageVersion: 0, blocks: [Object.assign(bkB('ardzy_program', null,
  Object.assign({}, setup ? { SETUP: setup } : {}, loop ? { LOOP: loop } : {})), { x: 30, y: 30 })] } });
const BK_EXAMPLES = {
  'Blink an LED': () => bkProg(bkB('ardzy_print', null, { V: bkB('text', { TEXT: 'Blinking LED0' }) }),
    bkSeq(bkB('ardzy_led', { LED: 'LED0', STATE: 'HIGH' }), bkB('ardzy_wait', null, { S: bkNum(0.5) }),
      bkB('ardzy_led', { LED: 'LED0', STATE: 'LOW' }), bkB('ardzy_wait', null, { S: bkNum(0.5) }))),
  'Button lights the LEDs': () => bkProg(null, Object.assign(bkB('controls_if', null, { IF0: bkB('ardzy_button', { BTN: 'BUTTON_IP' }),
    DO0: bkSeq(bkB('ardzy_led', { LED: 'LED0', STATE: 'HIGH' }), bkB('ardzy_led', { LED: 'LED_GREEN', STATE: 'HIGH' })),
    ELSE: bkSeq(bkB('ardzy_led', { LED: 'LED0', STATE: 'LOW' }), bkB('ardzy_led', { LED: 'LED_GREEN', STATE: 'LOW' })) }),
    { extraState: { hasElse: true } })),
  'Breathing LED (PWM)': () => {
    const s = bkProg(null, bkSeq(
      bkB('controls_for', { VAR: { id: 'vb' } }, { FROM: bkNum(0), TO: bkNum(100), BY: bkNum(2),
        DO: bkSeq(bkB('ardzy_pwm', { PIN: 'LED0' }, { VALUE: bkB('variables_get', { VAR: { id: 'vb' } }) }), bkB('ardzy_wait', null, { S: bkNum(0.02) })) }),
      bkB('controls_for', { VAR: { id: 'vb' } }, { FROM: bkNum(0), TO: bkNum(100), BY: bkNum(2),
        DO: bkSeq(bkB('ardzy_pwm', { PIN: 'LED0' }, { VALUE: bkB('math_arithmetic', { OP: 'MINUS' }, { A: bkNum(100), B: bkB('variables_get', { VAR: { id: 'vb' } }) }) }),
          bkB('ardzy_wait', null, { S: bkNum(0.02) })) })));
    s.variables = [{ name: 'brightness', id: 'vb' }];
    return s;
  },
  'Thermometer on the Plotter': () => bkProg(bkB('ardzy_print', null, { V: bkB('text', { TEXT: 'Open the Plotter tab' }) }),
    bkSeq(bkB('ardzy_plot', { NAME: 'temperature' }, { V: bkB('ardzy_temp') }), bkB('ardzy_wait', null, { S: bkNum(0.5) }))),
  'Fans follow the temperature': () => bkProg(null, bkB('ardzy_every', null, { MS: bkNum(1000),
    DO: bkSeq(bkB('ardzy_fan', null, { P: bkB('math_constrain', null, { VALUE: bkB('ardzy_map', null, { X: bkB('ardzy_temp'), A: bkNum(45), B: bkNum(70), C: bkNum(0), D: bkNum(100) }), LOW: bkNum(0), HIGH: bkNum(100) }) }),
      bkB('ardzy_plot', { NAME: 'celsius' }, { V: bkB('ardzy_temp') }), bkB('ardzy_plot', { NAME: 'fan_rpm' }, { V: bkB('ardzy_fan_rpm', { FAN: '1' }) })) })),
  'Beep a melody': () => bkProg(bkSeq(...['C5', 'E5', 'G5', 'C6'].map(n => bkB('ardzy_tone', { PIN: 'J1_5' }, { FREQ: bkB('ardzy_note', { NOTE: String(Math.round(440 * Math.pow(2, { C5: 3, E5: 7, G5: 10, C6: 15 }[n] / 12))) }), MS: bkNum(200) })),
    bkB('ardzy_beep', null, { MS: bkNum(150) })), null),
  'Count and print': () => {
    const s = bkProg(bkB('variables_set', { VAR: { id: 'vc' } }, { VALUE: bkNum(0) }),
      bkSeq(bkB('math_change', { VAR: { id: 'vc' } }, { DELTA: bkNum(1) }),
        bkB('ardzy_print', null, { V: bkB('text_join', null, { ADD0: bkB('text', { TEXT: 'count = ' }), ADD1: bkB('variables_get', { VAR: { id: 'vc' } }) }) }),
        bkB('ardzy_wait', null, { S: bkNum(1) })));
    s.variables = [{ name: 'count', id: 'vc' }];
    return s;
  },
  'Servo sweep': () => bkProg(null, bkSeq(bkB('ardzy_servo', { PIN: 'J5_5' }, { ANGLE: bkNum(0) }), bkB('ardzy_wait', null, { S: bkNum(1) }),
    bkB('ardzy_servo', { PIN: 'J5_5' }, { ANGLE: bkNum(180) }), bkB('ardzy_wait', null, { S: bkNum(1) }))),
};

/* ---------------------------------------------------------------- toolbox */
function bkToolbox() {
  const sh = n => ({ shadow: { type: 'math_number', fields: { NUM: n } } });
  const k = (type, inputs) => Object.assign({ kind: 'block', type }, inputs ? { inputs } : {});
  return { kind: 'categoryToolbox', contents: [
    { kind: 'category', name: 'Start', colour: '45', contents: [k('ardzy_program')] },
    { kind: 'category', name: 'Pins', colour: '160', contents: [k('ardzy_pin_write'), k('ardzy_pin_toggle'), k('ardzy_pin_read'), k('ardzy_servo', { ANGLE: sh(90) })] },
    { kind: 'category', name: 'Lights', colour: '190', contents: [k('ardzy_led'), k('ardzy_pwm', { VALUE: sh(50) }), k('ardzy_button')] },
    { kind: 'category', name: 'Sound', colour: '300', contents: [k('ardzy_beep', { MS: sh(100) }), k('ardzy_tone', { FREQ: { shadow: { type: 'ardzy_note' } }, MS: sh(200) }), k('ardzy_note')] },
    { kind: 'category', name: 'Board', colour: '20', contents: [k('ardzy_temp'), k('ardzy_fan', { P: sh(50) }), k('ardzy_fan_rpm')] },
    { kind: 'category', name: 'Time', colour: '120', contents: [k('ardzy_wait', { S: sh(1) }), k('ardzy_every', { MS: sh(1000) }), k('ardzy_millis')] },
    { kind: 'category', name: 'Monitor', colour: '260', contents: [k('ardzy_print', { V: { shadow: { type: 'text', fields: { TEXT: 'hello' } } } }), k('ardzy_plot', { V: sh(0) }),
      k('text'), k('text_join')] },
    { kind: 'sep' },
    { kind: 'category', name: 'Logic', categorystyle: 'logic_category', contents: [k('controls_if'), { kind: 'block', type: 'controls_if', extraState: { hasElse: true } },
      k('logic_compare'), k('logic_operation'), k('logic_negate'), k('logic_boolean')] },
    { kind: 'category', name: 'Loops', categorystyle: 'loop_category', contents: [k('controls_repeat_ext', { TIMES: sh(10) }), k('controls_whileUntil'),
      k('controls_for', { FROM: sh(1), TO: sh(10), BY: sh(1) }), k('controls_flow_statements')] },
    { kind: 'category', name: 'Math', categorystyle: 'math_category', contents: [k('math_number'), k('math_arithmetic', { A: sh(1), B: sh(1) }),
      k('math_single', { NUM: sh(9) }), k('math_round', { NUM: sh(3.1) }), k('math_modulo', { DIVIDEND: sh(64), DIVISOR: sh(10) }),
      k('math_random_int', { FROM: sh(1), TO: sh(100) }), k('math_constrain', { VALUE: sh(50), LOW: sh(1), HIGH: sh(100) }),
      k('ardzy_map', { X: sh(50), A: sh(0), B: sh(100), C: sh(0), D: sh(255) })] },
    { kind: 'category', name: 'Variables', categorystyle: 'variable_category', custom: 'VARIABLE' },
  ] };
}

/* ---------------------------------------------------------------- the view */
function bkTheme() {
  const dark = document.documentElement.dataset.theme === 'dark' ||
    (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
  return dark ? Blockly.Theme.defineTheme('ardzyDark', { name: 'ardzyDark', base: Blockly.Themes.Classic,
    componentStyles: { workspaceBackgroundColour: '#121915', toolboxBackgroundColour: '#151c18', toolboxForegroundColour: '#e2ebe6',
      flyoutBackgroundColour: '#1d2722', flyoutForegroundColour: '#e2ebe6', flyoutOpacity: 0.95, scrollbarColour: '#3a4a40',
      insertionMarkerColour: '#ffffff', insertionMarkerOpacity: 0.3, cursorColour: '#d0d0d0' } })
    : Blockly.Themes.Classic;
}

function bkInject() {
  if (BK.injected) return;
  BK.injected = true;
  bkDefine();
  fbDefine();
  BK.gen = bkGenerator();
  BK.fgen = fbGenerator();
  BK.ws = Blockly.inject($('bkWs'), { toolbox: i18nToolbox(BK.mode === 'fpga' ? fbToolbox() : bkToolbox()), theme: bkTheme(), renderer: 'zelos', trashcan: true, sounds: false,
    zoom: { controls: true, wheel: true, startScale: 0.9, maxScale: 2, minScale: 0.4 }, grid: { spacing: 24, length: 2, colour: '#3a4a40', snap: true },
    move: { scrollbars: true, drag: true, wheel: false } });
  BK.ws.addChangeListener(e => {
    if (BK.loading || e.isUiEvent) return;
    bkRefreshCode();
    clearTimeout(BK.saveT);
    BK.saveT = setTimeout(bkSave, 800);
  });
  BK.cm = CodeMirror($('bkCode'), { readOnly: true, lineNumbers: true, lineWrapping: true, mode: 'text/x-c++src' });
  new ResizeObserver(() => { Blockly.svgResize(BK.ws); }).observe($('bkWs'));
}

// the two kinds of blocks projects
function bkSetMode(m) {
  if (BK.injected && BK.mode !== m) {
    BK.mode = m;
    BK.ws.updateToolbox(i18nToolbox(m === 'fpga' ? fbToolbox() : bkToolbox()));
    BK.cm.setOption('mode', m === 'fpga' ? 'verilog' : 'text/x-c++src');
  }
  BK.mode = m;
  $('bkSim').hidden = m !== 'fpga';
  $('bkUpload').textContent = m === 'fpga' ? 'Build and run' : 'Upload and run';
  $('bkUpload').title = m === 'fpga' ? 'Save, build the FPGA design (about a minute), then load it on the board' : 'Save, build and run the blocks on the board';
  $('bkCodeBtn').textContent = m === 'fpga' ? 'Verilog' : 'C++ code';
  $('bkKind').textContent = m === 'fpga' ? 'FPGA design' : 'Arduino program';
  $('bkKind').className = 'bk-kind ' + m;
}
const bkExamples = () => BK.mode === 'fpga' ? FB_EXAMPLES : BK_EXAMPLES;
const bkStateFile = (name, m) => name + (m === 'fpga' ? '.fblocks.json' : '.blocks.json');

function bkRefreshCode() {
  if (BK.mode === 'fpga') {
    const r = fbVerilog(BK.ws, BK.project);
    BK.code = r.code; BK.xdc = r.xdc; BK.py = r.py;
    BK.cm.setValue(r.code);
    $('bkNote').textContent = !BK.project ? 'These blocks are not saved yet: press + FPGA design to make a project, then Simulate or Build and run.'
      : !r.hasDesign ? 'Start with a block from Start ("every ...", "when ...", "all the time"): the design is made of what is inside them.'
      : r.notes.length ? r.notes.join(' ') : r.loose ? `${r.loose} block${r.loose > 1 ? 's are' : ' is'} not inside a Start block and ${r.loose > 1 ? 'do' : 'does'} nothing yet.` : '';
    $('bkNote').classList.toggle('warn', !!r.notes.length);
    return;
  }
  $('bkNote').classList.remove('warn');
  const r = bkSketch(BK.ws);
  BK.code = r.code;
  BK.cm.setValue(r.code);
  $('bkNote').textContent = !BK.project ? 'These blocks are not saved yet: press + New to make a blocks project, then Upload and run.'
    : !r.hasProgram ? 'Drag the "when the board starts / forever" block from Start: the program begins there.'
    : r.loose ? `${r.loose} block${r.loose > 1 ? 's are' : ' is'} not inside the program and ${r.loose > 1 ? 'do' : 'does'} nothing yet.` : '';
}

async function bkSave() {
  if (!BK.project) return;
  const state = JSON.stringify(Blockly.serialization.workspaces.save(BK.ws), null, 1);
  if (BK.mode === 'fpga') {
    const P = BK.project, w = (name, text) => api('/api/file', { project: P, name, text });
    const res = [await w(P + '.fblocks.json', state), await w('top.v', BK.code || ''), await w('pins.xdc', BK.xdc || '')];
    const cur = await api('/api/file?project=' + encodeURIComponent(P) + '&name=main.py');      // main.py: only while it is still ours
    if (!cur.ok || !cur.text.trim() || cur.text.startsWith('# made by Ardzy FPGA blocks')) res.push(await w('main.py', BK.py || ''));
    for (const [f, txt] of [['top.v', BK.code], ['pins.xdc', BK.xdc]]) {
      const t = (S.tabs || []).find(t => t.key === P + '/' + f);
      if (t) { t.loading = true; t.doc.setValue(txt); t.saved = txt; t.dirty = false; t.loading = false; }
    }
    const bad = res.find(r => !r.ok);
    $('bkSaved').textContent = bad ? 'not saved: ' + bad.out : 'saved ' + new Date().toTimeString().slice(0, 8);
    return;
  }
  const a = await api('/api/file', { project: BK.project, name: BK.project + '.blocks.json', text: state });
  const b = await api('/api/file', { project: BK.project, name: BK.project + '.ino', text: BK.code || '' });
  const t = (S.tabs || []).find(t => t.key === BK.project + '/' + BK.project + '.ino');      // an open editor tab follows
  if (t) { t.loading = true; t.doc.setValue(BK.code); t.saved = BK.code; t.dirty = false; t.loading = false; }
  $('bkSaved').textContent = a.ok && b.ok ? 'saved ' + new Date().toTimeString().slice(0, 8) : 'not saved: ' + (a.out || b.out);
}

function bkProjects() {
  return (S.projects || []).filter(p => p.files.includes(p.name + '.blocks.json') || p.files.includes(p.name + '.fblocks.json'));
}
const bkModeOf = p => p && p.files.includes(p.name + '.fblocks.json') ? 'fpga' : 'ino';

async function bkOpen(name) {
  BK.project = name;
  try { localStorage.setItem('ardzy.blocks', name); } catch (e) { }
  bkSetMode(bkModeOf((S.projects || []).find(p => p.name === name)));
  const r = await api('/api/file?project=' + encodeURIComponent(name) + '&name=' + encodeURIComponent(bkStateFile(name, BK.mode)));
  let state = null;
  try { state = r.ok && r.text.trim() ? JSON.parse(r.text) : null; } catch (e) { state = null; }
  BK.loading = true;
  BK.ws.clear();
  try { Blockly.serialization.workspaces.load(state && state.blocks ? state : (BK.mode === 'fpga' ? FB_EXAMPLES['Blink LED 0 (every 500 ms)'] : BK_EXAMPLES['Blink an LED'])(), BK.ws); }
  catch (e) { out('Blocks could not be read: ' + e, 'err'); }
  BK.loading = false;
  bkRefreshCode();
  if (!state || !state.blocks) bkSave();
  bkHead();
}

function bkHead() {
  const list = bkProjects();
  $('bkProj').innerHTML = list.length ? list.map(p => `<option value="${esc(p.name)}" ${p.name === BK.project ? 'selected' : ''}>${esc(p.name)}${bkModeOf(p) === 'fpga' ? '  (FPGA)' : ''}</option>`).join('')
    : '<option value="">(no blocks project yet)</option>';
  $('bkEx').innerHTML = '<option value="">Start from an example ...</option>' + Object.keys(bkExamples()).map(k => `<option>${esc(k)}</option>`).join('');
}

async function bkNew(kind) {
  const fpga = kind === 'fpga';
  const name = prompt(fpga ? 'Name of the new FPGA design (letters, digits, _ . -):' : 'Name of the new blocks program (letters, digits, _ . -):', fpga ? 'my_fpga' : 'my_blocks');
  if (!name) return;
  if (!/^[A-Za-z0-9_.-]+$/.test(name)) { out('Use only letters, digits, _ . -', 'err'); return; }
  const r = await api('/api/project/new', { name, template: fpga ? 'blocks_fpga' : 'blocks_sketch' });
  if (!r.ok) { out(r.out || 'could not create the project', 'err'); return; }
  await refreshProjects();
  await bkOpen(name);
}

async function blocksShow() {
  const fresh = !BK.injected;
  bkInject();
  if (!fresh) BK.ws.setTheme(bkTheme());                    // (the app theme may have changed)
  setTimeout(() => Blockly.svgResize(BK.ws), 0);
  if (!S.projects || !S.projects.length) await refreshProjects();
  const hashP = !fresh ? null : (location.hash.match(/project=([\w.-]+)/) || [])[1];      // a link: #view=blocks&project=name
  const want = hashP || BK.project || (() => { try { return localStorage.getItem('ardzy.blocks'); } catch (e) { return null; } })();
  if (hashP && bkProjects().some(p => p.name === hashP)) BK.project = null;
  const list = bkProjects();
  if (!BK.project || !list.find(p => p.name === BK.project)) {
    const p = list.find(x => x.name === want) || list[0];
    if (p) await bkOpen(p.name); else { bkSetMode('ino'); bkHead(); BK.loading = true; BK.ws.clear(); Blockly.serialization.workspaces.load(BK_EXAMPLES['Blink an LED'](), BK.ws); BK.loading = false; bkRefreshCode(); }
  } else bkHead();
}

$('bkNew').onclick = () => bkNew('ino');
$('bkNewF').onclick = () => bkNew('fpga');
$('bkProj').onchange = e => e.target.value && bkOpen(e.target.value);
$('bkEx').onchange = e => {
  const k = e.target.value; e.target.value = '';
  const ex = bkExamples();
  if (!k || !ex[k]) return;
  if (BK.ws.getAllBlocks(false).length > 1 && !confirm(`Replace the blocks with the example "${k}"?`)) return;
  BK.ws.clear();
  Blockly.serialization.workspaces.load(ex[k](), BK.ws);
};
$('bkUpload').onclick = async () => {
  if (!BK.project) { out('Press New first: the blocks need a project to be uploaded.', 'err'); return; }
  if (!S.connected) { out('No board connected: click Scan.', 'err'); return; }
  clearTimeout(BK.saveT); await bkSave();
  selectProject(BK.project);
  if (BK.mode === 'fpga') {                                   // build first; the upload follows when the build is done (app.js)
    BK.uploadAfterBuild = BK.project;
    out('Building the FPGA design made with blocks (about a minute); it is loaded on the board when the build is done.', 'head');
    await doBuild();
    return;
  }
  await doUpload();
  showTab('monitor');
};
$('bkSim').onclick = async () => {                            // FPGA blocks: a testbench (made once) and the simulation
  if (!BK.project) { out('Press + FPGA design first.', 'err'); return; }
  clearTimeout(BK.saveT); await bkSave();
  selectProject(BK.project);
  const inf = await api('/api/sim/info?project=' + encodeURIComponent(BK.project));
  if (inf.ok && !inf.testbenches.length) { const r = await api('/api/sim/newtb', { project: BK.project, run_ns: 1000000, wiggle: true }); if (!r.ok) return out(r.out, 'err'); await refreshProjects(); }
  showTab('simulation');
  await simInfo();
  $('simTime').value = '1000000';                              // 1 ms: the timers run 10 000 times faster in the simulation
  simRun();
};
$('bkStop').onclick = () => boardAction('stop');
$('bkCodeBtn').onclick = () => { $('bkSplit').classList.toggle('nocode'); setTimeout(() => { Blockly.svgResize(BK.ws); BK.cm.refresh(); }, 0); };
window.blocksShow = blocksShow;
window.BK_after = async ok => {                               // the build of an FPGA blocks design ended
  const p = BK.uploadAfterBuild; BK.uploadAfterBuild = null;
  if (!p) return;
  if (!ok) { out('The FPGA build did not work: see above (and Problems).', 'err'); return; }
  if (S.project !== p) selectProject(p);
  await doUpload();
};
