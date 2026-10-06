/* Ardzy - FPGA blocks: hardware made from blocks, like Scratch. The blocks become a Verilog design (top.v), its pin
   file (pins.xdc) and a small ARM program (main.py) that shows the values the design gives the ARM in the Watch tab.
   Every clocked block runs on the 100 MHz FPGA clock; "all the time" blocks are wires (no clock).
   Used by blocks.js (the Blocks view) when a project has name.fblocks.json. */

const FB_BALLS = { J1: 'T11 T12 U12 T10', J2: 'R19 V12 W13 V13', J3: 'T14 P14 R14 T15', J4: 'Y16 W14 Y14 Y17', J5: 'T16 V15 W15 U17',
  J6: 'U14 U18 U19 U15', J7: 'T20 V20 W20 U20', J8: 'Y18 V16 W16 Y19', J9: 'R16 T17 R18 R17' };
const FB_PIN_BALL = {};
Object.entries(FB_BALLS).forEach(([j, b]) => b.split(' ').forEach((ball, i) => FB_PIN_BALL[`${j}_${[5, 11, 12, 15][i]}`] = ball));
const FB_LED_BALL = ['F16', 'L19', 'M19', 'M17'];
const FB_PINS = Object.keys(FB_PIN_BALL).map(p => [`${p.replace('_', ' pin ')}`, p]);
const FB_OUTS = [['LED 0', 'LED0'], ['LED 1', 'LED1'], ['LED 2', 'LED2'], ['LED 3', 'LED3']].concat(FB_PINS);
const FB_VKW = new Set('always and assign automatic begin buf case casex casez cell config deassign default defparam design disable edge else end endcase endfunction endgenerate endmodule endprimitive endspecify endtable endtask event for force forever fork function generate genvar if ifnone initial inout input integer join localparam macromodule module nand negedge nor not or output parameter posedge primitive pulldown pullup real realtime reg release repeat scalared signed specify specparam strength supply0 supply1 table task time tran tri tri0 tri1 triand trior trireg unsigned vectored wait wand weak0 weak1 while wire wor xnor xor logic bit byte int clk rstn ctrl status leds top'.split(' '));

function fbRegOptions() {
  const ws = (typeof BK !== 'undefined' && BK.ws) ? BK.ws : null;
  const names = ws ? [...new Set(ws.getBlocksByType('fpga_register', false).map(b => b.getFieldValue('NAME')).filter(Boolean))] : [];
  return names.length ? names.map(n => [n, n]) : [['(make a register first)', '']];
}
const fbIdent = s => { s = String(s || '').trim().replace(/[^A-Za-z0-9_]/g, '_'); if (!/^[A-Za-z_]/.test(s)) s = 'r_' + s; return FB_VKW.has(s) ? s + '_r' : s || 'r'; };

function fbDefine() {
  const C = { start: 30, reg: 210, out: 160, inp: 120, bits: 260, arm: 330 };
  const hat = (type, msg, args, tip) => ({ type, message0: msg + ' %' + (args.length + 1) + ' %' + (args.length + 2),
    args0: args.concat([{ type: 'input_dummy' }, { type: 'input_statement', name: 'DO' }]), colour: C.start, tooltip: tip });
  Blockly.defineBlocksWithJsonArray(i18nBlocks([
    hat('fpga_on_clock', 'on every clock tick (100 MHz)', [], 'Runs its blocks 100 million times a second, at every tick of the FPGA clock.'),
    hat('fpga_every', 'every %1 %2', [{ type: 'field_number', name: 'N', value: 500, min: 1, precision: 1 },
      { type: 'field_dropdown', name: 'UNIT', options: [['ms', 'ms'], ['us', 'us'], ['s', 's'], ['clock ticks', 'ticks']] }],
      'Runs its blocks once every so often. The hardware counts the clock ticks (100 per microsecond). In the simulation these timers run 10 000 times faster.'),
    hat('fpga_on_pin', 'when %1 %2', [{ type: 'field_dropdown', name: 'PIN', options: FB_PINS },
      { type: 'field_dropdown', name: 'EDGE', options: [['goes from 0 to 1 (rises)', 'rise'], ['goes from 1 to 0 (falls)', 'fall'], ['changes', 'change']] }],
      'Runs its blocks once when the pin changes. The pin is read through two flip-flops first (a synchronizer), so the edge is safe. A button to GND falls when pressed.'),
    hat('fpga_always', 'all the time (wires, no clock)', [],
      'Outputs set here follow their inputs at once, like wires: "LED 0 = bit 3 of count". Nothing is stored.'),
    { type: 'fpga_register', message0: 'register %1 with %2 bits, starts at %3',
      args0: [{ type: 'field_input', name: 'NAME', text: 'count' }, { type: 'field_number', name: 'W', value: 8, min: 1, max: 64, precision: 1 },
        { type: 'field_number', name: 'INIT', value: 0, min: 0, precision: 1 }],
      previousStatement: 'fpga_reg', nextStatement: 'fpga_reg', colour: C.reg,
      tooltip: 'A register keeps a number between clock ticks (flip-flops). 8 bits hold 0..255, 16 bits 0..65535, 32 bits 0..4294967295.' },
    { type: 'fpga_out_set', message0: 'set %1 to %2', args0: [{ type: 'field_dropdown', name: 'OUT', options: FB_OUTS }, { type: 'input_value', name: 'V' }],
      inputsInline: true, previousStatement: null, nextStatement: null, colour: C.out,
      tooltip: 'An LED (1 = lit) or a connector pin (1 = 3.3 V). Under a clocked block it keeps the value; under "all the time" it follows the value.' },
    { type: 'fpga_out_flip', message0: 'flip %1', args0: [{ type: 'field_dropdown', name: 'OUT', options: FB_OUTS }],
      previousStatement: null, nextStatement: null, colour: C.out, tooltip: 'On becomes off, off becomes on (only under a clocked block).' },
    { type: 'fpga_fan', message0: 'fans run at %1 of 255', args0: [{ type: 'input_value', name: 'V' }], inputsInline: true,
      previousStatement: null, nextStatement: null, colour: C.out, tooltip: 'All 6 fan headers: a 24 kHz PWM, 0 = slowest, 255 = full speed.' },
    { type: 'fpga_status', message0: 'the ARM can read status %1 = %2', args0: [{ type: 'field_dropdown', name: 'N', options: [0, 1, 2, 3].map(n => [String(n), String(n)]) },
      { type: 'input_value', name: 'V' }], inputsInline: true, previousStatement: null, nextStatement: null, colour: C.arm,
      tooltip: 'A 32-bit value for the program on the ARM: Python  MMIO(0x41200000).read(0x80 + 4 * n). main.py shows it in the Watch tab.' },
    { type: 'fpga_set', message0: 'set %1 to %2', args0: [{ type: 'field_dropdown', name: 'REG', options: fbRegOptions }, { type: 'input_value', name: 'V' }],
      inputsInline: true, previousStatement: null, nextStatement: null, colour: C.reg, tooltip: 'The register takes the value at the clock tick.' },
    { type: 'fpga_add', message0: 'add %1 to %2', args0: [{ type: 'input_value', name: 'V' }, { type: 'field_dropdown', name: 'REG', options: fbRegOptions }],
      inputsInline: true, previousStatement: null, nextStatement: null, colour: C.reg, tooltip: 'Adds to the register (it wraps around: 255 + 1 = 0 in 8 bits).' },
    { type: 'fpga_count', message0: 'count %1 up, back to 0 after %2', args0: [{ type: 'field_dropdown', name: 'REG', options: fbRegOptions }, { type: 'input_value', name: 'N' }],
      inputsInline: true, previousStatement: null, nextStatement: null, colour: C.reg, tooltip: 'Adds 1; after the value N the next one is 0 again (counts 0, 1, ... N).' },
    { type: 'fpga_flip_reg', message0: 'flip all bits of %1', args0: [{ type: 'field_dropdown', name: 'REG', options: fbRegOptions }],
      previousStatement: null, nextStatement: null, colour: C.reg, tooltip: 'Every 0 becomes 1 and every 1 becomes 0 (a 1-bit register toggles).' },
    { type: 'fpga_reg_get', message0: '%1', args0: [{ type: 'field_dropdown', name: 'REG', options: fbRegOptions }], output: null, colour: C.reg, tooltip: 'The value of the register.' },
    { type: 'fpga_pin_in', message0: '%1 is 1', args0: [{ type: 'field_dropdown', name: 'PIN', options: FB_PINS }], output: null, colour: C.inp,
      tooltip: 'The level of a connector pin (1 = 3.3 V). It has a pull-up: open = 1, a button to GND pressed = 0.' },
    { type: 'fpga_arm', message0: 'value from the ARM ctrl %1', args0: [{ type: 'field_dropdown', name: 'N', options: [0, 1, 2, 3].map(n => [String(n), String(n)]) }],
      output: null, colour: C.arm, tooltip: '32 bits the program on the ARM writes: Python  MMIO(0x41200000).write(4 * n, value).' },
    { type: 'fpga_bit', message0: 'bit %1 of %2', args0: [{ type: 'field_number', name: 'B', value: 0, min: 0, max: 63, precision: 1 }, { type: 'input_value', name: 'V' }],
      inputsInline: true, output: null, colour: C.bits, tooltip: 'One bit: bit 0 is the lowest (it changes at every count).' },
    { type: 'fpga_bits', message0: 'bits %1 down to %2 of %3', args0: [{ type: 'field_number', name: 'H', value: 7, min: 0, max: 63, precision: 1 },
      { type: 'field_number', name: 'L', value: 0, min: 0, max: 63, precision: 1 }, { type: 'input_value', name: 'V' }],
      inputsInline: true, output: null, colour: C.bits, tooltip: 'A group of bits, for example bits 7 down to 0 = the lowest byte.' },
    { type: 'fpga_bitop', message0: '%1 %2 %3', args0: [{ type: 'input_value', name: 'A' },
      { type: 'field_dropdown', name: 'OP', options: [['and (bits)', '&'], ['or (bits)', '|'], ['xor (bits)', '^']] }, { type: 'input_value', name: 'B' }],
      inputsInline: true, output: null, colour: C.bits, tooltip: 'Bit by bit: and = 1 where both are 1, or = 1 where any is 1, xor = 1 where they differ.' },
    { type: 'fpga_not', message0: 'invert the bits of %1', args0: [{ type: 'input_value', name: 'V' }], inputsInline: true, output: null, colour: C.bits,
      tooltip: 'Every 0 becomes 1 and every 1 becomes 0.' },
    { type: 'fpga_shift', message0: '%1 shifted %2 by %3', args0: [{ type: 'input_value', name: 'V' },
      { type: 'field_dropdown', name: 'DIR', options: [['left', '<<'], ['right', '>>']] }, { type: 'field_number', name: 'N', value: 1, min: 0, max: 63, precision: 1 }],
      inputsInline: true, output: null, colour: C.bits, tooltip: 'Left by 1 = times 2, right by 1 = divided by 2.' },
    { type: 'fpga_pwm', message0: 'PWM: on for %1 of 256', args0: [{ type: 'input_value', name: 'V' }], inputsInline: true, output: null, colour: C.bits,
      tooltip: '1 for a part of each 2.56 us (390 kHz): on an LED it sets the brightness (0 = off, 255 = full).' },
  ]));
  const fixName = function (v) { return fbIdent(v); };
  Blockly.Blocks['fpga_register'].init = (function (init0) { return function () { init0.call(this); this.getField('NAME').setValidator(fixName); }; })(Blockly.Blocks['fpga_register'].init);
}

/* ---------------------------------------------------------------- blocks -> Verilog */
function fbGenerator() {
  const G = new (Blockly.CodeGenerator || Blockly.Generator)('Verilog');
  const O = { ATOMIC: 0, NONE: 99 };
  G.INDENT = '    ';
  G.init = function () { G.isInitialized = true; };
  G.scrub_ = (block, code, thisOnly) => { const n = block.nextConnection && block.nextConnection.targetBlock(); return code + (n && !thisOnly ? G.blockToCode(n) : ''); };
  G.scrubNakedValue = l => '// (a value block alone does nothing: ' + l + ')\n';
  const v = (b, n, def = "1'b0") => G.valueToCode(b, n, O.NONE) || def;
  const F = G.forBlock;
  const reg = b => { const n = b.getFieldValue('REG'); if (!n) { G.notes.add('A block uses a register, but there is no "register" block yet.'); return 'r_missing'; } G.used.regs.add(n); return n; };
  const asg = () => G.ctx === 'comb' ? ' = ' : ' <= ';
  const out = (name, ctx) => { const o = G.outs[name] = G.outs[name] || { ctx: new Set() }; o.ctx.add(ctx); return 'o_' + name; };
  F.math_number = b => [String(Math.trunc(Number(b.getFieldValue('NUM')))), O.ATOMIC];
  F.logic_boolean = b => [b.getFieldValue('BOOL') === 'TRUE' ? "1'b1" : "1'b0", O.ATOMIC];
  F.logic_negate = b => [`!(${v(b, 'BOOL')})`, O.ATOMIC];
  F.logic_operation = b => [`(${v(b, 'A')} ${b.getFieldValue('OP') === 'AND' ? '&&' : '||'} ${v(b, 'B')})`, O.ATOMIC];
  F.logic_compare = b => [`(${v(b, 'A', '0')} ${{ EQ: '==', NEQ: '!=', LT: '<', LTE: '<=', GT: '>', GTE: '>=' }[b.getFieldValue('OP')]} ${v(b, 'B', '0')})`, O.ATOMIC];
  F.math_arithmetic = b => {
    const op = { ADD: '+', MINUS: '-', MULTIPLY: '*', DIVIDE: '/', POWER: '**' }[b.getFieldValue('OP')];
    if (op === '/' || op === '**') G.notes.add('Divide and power make big, slow hardware: use them only with fixed numbers, or shift right / left instead.');
    return [`(${v(b, 'A', '0')} ${op} ${v(b, 'B', '0')})`, O.ATOMIC];
  };
  F.controls_if = b => {
    let code = '', n = 0;
    do {
      code += (n ? ' else ' : '') + `if (${v(b, 'IF' + n)}) begin\n${G.statementToCode(b, 'DO' + n)}end`;
      n++;
    } while (b.getInput('IF' + n));
    if (b.getInput('ELSE')) code += ` else begin\n${G.statementToCode(b, 'ELSE')}end`;
    return code + '\n';
  };
  F.fpga_register = () => '';
  F.fpga_reg_get = b => [reg(b), O.ATOMIC];
  F.fpga_set = b => { const r = reg(b); G.regDrv(r); return `${r}${asg()}${v(b, 'V', '0')};\n`; };
  F.fpga_add = b => { const r = reg(b); G.regDrv(r); return `${r}${asg()}${r} + ${v(b, 'V', '1')};\n`; };
  F.fpga_count = b => { const r = reg(b); G.regDrv(r); const n = v(b, 'N', '9'); return `${r}${asg()}(${r} >= ${n}) ? 0 : ${r} + 1'b1;\n`; };
  F.fpga_flip_reg = b => { const r = reg(b); G.regDrv(r); return `${r}${asg()}~${r};\n`; };
  F.fpga_out_set = b => `${out(b.getFieldValue('OUT'), G.ctx)}${asg()}${v(b, 'V')};\n`;
  F.fpga_out_flip = b => { if (G.ctx === 'comb') { G.notes.add('"flip" needs a clock: put it under "every ..." or "when ...", not under "all the time".'); return ''; }
    const o = out(b.getFieldValue('OUT'), G.ctx); return `${o} <= ~${o};\n`; };
  F.fpga_fan = b => { G.used.fan = true; return `${out('FAN', G.ctx)}${asg()}${v(b, 'V', '255')};\n`; };
  F.fpga_status = b => { G.used.status.add(+b.getFieldValue('N')); return `${out('STATUS' + b.getFieldValue('N'), G.ctx)}${asg()}${v(b, 'V', '0')};\n`; };
  F.fpga_pin_in = b => { const p = b.getFieldValue('PIN'); G.used.ins.add(p); return [`${p}_in`, O.ATOMIC]; };
  F.fpga_arm = b => { G.used.ctrl.add(+b.getFieldValue('N')); return [`ctrl[${32 * +b.getFieldValue('N') + 31}:${32 * +b.getFieldValue('N')}]`, O.ATOMIC]; };
  F.fpga_bit = b => [`${G.sel(v(b, 'V', '0'))}[${b.getFieldValue('B')}]`, O.ATOMIC];
  F.fpga_bits = b => [`${G.sel(v(b, 'V', '0'))}[${Math.max(b.getFieldValue('H'), b.getFieldValue('L'))}:${Math.min(b.getFieldValue('H'), b.getFieldValue('L'))}]`, O.ATOMIC];
  F.fpga_bitop = b => [`(${v(b, 'A', '0')} ${b.getFieldValue('OP')} ${v(b, 'B', '0')})`, O.ATOMIC];
  F.fpga_not = b => [`(~${v(b, 'V', '0')})`, O.ATOMIC];
  F.fpga_shift = b => [`(${v(b, 'V', '0')} ${b.getFieldValue('DIR')} ${b.getFieldValue('N')})`, O.ATOMIC];
  F.fpga_pwm = b => { G.used.pwm = true; return [`(pwm_n < ${v(b, 'V', '128')})`, O.ATOMIC]; };
  // a bit select needs a name, not an expression: expressions get a wire of their own
  G.sel = e => {
    if (/^[A-Za-z_]\w*$/.test(e) || /^ctrl\[\d+:\d+\]$/.test(e)) return e.replace(/^ctrl\[(\d+):(\d+)\]$/, 'ctrl_$2');
    const n = 'e' + (++G.wires);
    G.exprWires.push(`    wire [63:0] ${n} = ${e};`);
    return n;
  };
  return G;
}

const FB_SIM_SPEEDUP = 10000;
function fbVerilog(ws, project) {
  const G = BK.fgen;
  G.init(ws);
  G.outs = {}; G.notes = new Set(); G.used = { regs: new Set(), ins: new Set(), ctrl: new Set(), status: new Set(), fan: false, pwm: false };
  G.wires = 0; G.exprWires = []; G.regDrivers = {};
  let hatNo = 0;
  G.regDrv = r => { (G.regDrivers[r] = G.regDrivers[r] || new Set()).add(G.ctx === 'comb' ? 'comb' : 'clk'); };
  const regs = {};
  ws.getBlocksByType('fpga_register', false).forEach(b => {
    const n = b.getFieldValue('NAME');
    if (regs[n]) G.notes.add(`There are two registers named "${n}": only one is used.`);
    regs[n] = { w: Math.max(1, Math.min(64, b.getFieldValue('W') | 0)), init: Math.max(0, b.getFieldValue('INIT') | 0) };
  });
  const tops = ws.getTopBlocks(true);
  const timers = [], edges = new Set(), clocked = [], comb = [];
  for (const b of tops) {
    if (b.type === 'fpga_on_clock') { G.ctx = 'clk'; clocked.push(`        // on every clock tick\n${G.statementToCode(b, 'DO').replace(/^/gm, '    ').replace(/^    $/gm, '')}`); }
    else if (b.type === 'fpga_every') {
      const k = ++hatNo, n = b.getFieldValue('N'), u = b.getFieldValue('UNIT');
      const ticks = Math.max(1, Math.round(n * { ticks: 1, us: 100, ms: 100000, s: 100000000 }[u]));
      const simTicks = u === 'ticks' || u === 'us' ? ticks : Math.max(2, Math.round(ticks / FB_SIM_SPEEDUP));
      timers.push({ k, n, u, ticks, simTicks });
      G.ctx = 'clk';
      clocked.push(`        // every ${n} ${u === 'ticks' ? 'clock ticks' : u}\n        if (tick${k}) begin\n${G.statementToCode(b, 'DO').replace(/^/gm, '        ').replace(/^ +$/gm, '')}        end`);
    } else if (b.type === 'fpga_on_pin') {
      const p = b.getFieldValue('PIN'), e = b.getFieldValue('EDGE');
      G.used.ins.add(p); edges.add(p);
      G.ctx = 'clk';
      clocked.push(`        // when ${p.replace('_', ' pin ')} ${{ rise: 'rises', fall: 'falls', change: 'changes' }[e]}\n        if (${p}_${e}) begin\n${G.statementToCode(b, 'DO').replace(/^/gm, '        ').replace(/^ +$/gm, '')}        end`);
    } else if (b.type === 'fpga_always') {
      G.ctx = 'comb';
      comb.push(G.statementToCode(b, 'DO'));
    }
  }
  const loose = tops.filter(b => !['fpga_on_clock', 'fpga_every', 'fpga_on_pin', 'fpga_always', 'fpga_register'].includes(b.type) && !b.outputConnection).length;
  G.used.regs.forEach(r => { if (!regs[r]) G.notes.add(`The register "${r}" has no "register" block.`); });
  Object.entries(G.regDrivers).forEach(([r, s]) => { if (s.size > 1) G.notes.add(`The register "${r}" is set under a clock and under "all the time": use one of the two.`); });
  Object.entries(G.outs).forEach(([o, x]) => { if (x.ctx.size > 1) G.notes.add(`${o} is set under a clock and under "all the time": use one of the two.`); });
  const outPins = Object.keys(G.outs).filter(o => /^J\d_/.test(o));
  outPins.forEach(p => { if (G.used.ins.has(p)) G.notes.add(`${p.replace('_', ' pin ')} is used as an input and as an output: a pin can be only one of the two.`); });
  // ---- the Verilog
  const L = [`// ${project || 'design'}: made with Ardzy FPGA blocks. Written again from the blocks at every change: change the blocks, not this file.`,
    '// (To go on by hand: copy the project, delete the .fblocks.json file, and edit this one.)', '', 'module top ('];
  const ports = ['    output wire [3:0] leds'];
  [...G.used.ins].sort().forEach(p => ports.push(`    input  wire ${p}`));
  outPins.sort().forEach(p => ports.push(`    output wire ${p}`));
  if (G.used.fan) ports.push('    output wire fan_pwm');
  L.push(ports.join(',\n'), ');');
  L.push('    wire clk, rstn;', '    wire [127:0] ctrl;                 // 4 values the ARM writes (0x4120_0000 + 4 * n)',
    '    wire [127:0] status;               // 4 values the ARM reads  (0x4120_0080 + 4 * n)',
    '    ardzy_soc #(.N_CTRL(4), .N_STAT(4)) u_soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));', '');
  [...G.used.ctrl].forEach(n => L.push(`    wire [31:0] ctrl_${32 * n} = ctrl[${32 * n + 31}:${32 * n}];`));
  const regNames = Object.keys(regs);
  if (regNames.length) { L.push('    // registers'); regNames.forEach(n => L.push(`    reg [${regs[n].w - 1}:0] ${n} = ${regs[n].w}'d${regs[n].init};`)); L.push(''); }
  const outDecl = Object.keys(G.outs).map(o => o === 'FAN' ? '    reg [7:0]  o_FAN = 8\'d255;              // fan duty (0..255)'
    : /^STATUS/.test(o) ? `    reg [31:0] o_${o} = 32'd0;` : `    reg        o_${o} = 1'b0;`);
  if (outDecl.length) { L.push('    // outputs (LEDs: 1 = lit)'); L.push(...outDecl); L.push(''); }
  if (G.used.ins.size) {
    L.push('    // inputs: two flip-flops against metastability, a third one for the edges');
    [...G.used.ins].sort().forEach(p => L.push(`    reg [2:0] ${p}_s = 3'b111;`, `    always @(posedge clk) ${p}_s <= {${p}_s[1:0], ${p}};`, `    wire ${p}_in = ${p}_s[1];`,
      ...(edges.has(p) ? [`    wire ${p}_rise = ${p}_s[1] & ~${p}_s[2], ${p}_fall = ~${p}_s[1] & ${p}_s[2], ${p}_change = ${p}_s[1] ^ ${p}_s[2];`] : [])));
    L.push('');
  }
  for (const t of timers) {
    const w = Math.max(1, Math.ceil(Math.log2(t.ticks + 1)));
    L.push(`    // timer ${t.k}: every ${t.n} ${t.u === 'ticks' ? 'clock ticks' : t.u} = ${t.ticks} clock ticks` + (t.simTicks !== t.ticks ? ` (${FB_SIM_SPEEDUP} times faster in the simulation)` : ''));
    if (t.simTicks !== t.ticks) L.push('`ifdef ARDZY_SIM', `    localparam [${w - 1}:0] TICKS${t.k} = ${t.simTicks - 1};`, '`else', `    localparam [${w - 1}:0] TICKS${t.k} = ${t.ticks - 1};`, '`endif');
    else L.push(`    localparam [${w - 1}:0] TICKS${t.k} = ${t.ticks - 1};`);
    L.push(`    reg [${w - 1}:0] timer${t.k} = 0;`, `    wire tick${t.k} = (timer${t.k} == TICKS${t.k});`,
      `    always @(posedge clk) timer${t.k} <= tick${t.k} ? 0 : timer${t.k} + 1'b1;`, '');
  }
  if (G.used.pwm) L.push('    // PWM counter: 256 steps of 10 ns', '    reg [7:0] pwm_n = 8\'d0;', '    always @(posedge clk) pwm_n <= pwm_n + 1\'b1;', '');
  if (G.exprWires.length) L.push(...G.exprWires, '');
  if (clocked.length) L.push('    always @(posedge clk) begin', clocked.join('\n'), '    end', '');
  const combOuts = Object.keys(G.outs).filter(o => G.outs[o].ctx.has('comb'));
  const combRegs = Object.keys(G.regDrivers).filter(r => G.regDrivers[r].has('comb'));
  if (comb.length) {
    L.push('    // all the time (wires)', '    always @(*) begin');
    combOuts.forEach(o => L.push(`        o_${o} = ${o === 'FAN' ? "8'd255" : /^STATUS/.test(o) ? "32'd0" : "1'b0"};`));
    combRegs.forEach(r => L.push(`        ${r} = ${regs[r] ? regs[r].w + "'d" + regs[r].init : 0};`));
    L.push(comb.join('').replace(/^/gm, '    ').replace(/^ +$/gm, '').replace(/\n$/, ''), '    end', '');
  }
  for (let i = 0; i < 4; i++) L.push(G.outs['LED' + i] ? `    assign leds[${i}] = ~o_LED${i};           // the LEDs light at 0` : `    assign leds[${i}] = 1'b1;               // LED ${i} off (not used)`);
  outPins.sort().forEach(p => L.push(`    assign ${p} = o_${p};`));
  if (G.used.fan) L.push('    reg [11:0] fan_n = 12\'d0;                // 100 MHz / 4096 = 24.4 kHz', '    always @(posedge clk) fan_n <= fan_n + 1\'b1;',
    '    assign fan_pwm = (fan_n[11:4] < o_FAN) | (o_FAN == 8\'d255);');
  L.push(`    assign status = {${[3, 2, 1, 0].map(n => G.outs['STATUS' + n] ? 'o_STATUS' + n : "32'd0").join(', ')}};`);
  L.push('endmodule', '');
  // ---- the pins
  const X = ['# pins.xdc: made with Ardzy FPGA blocks (written again at every change).'];
  const pin = (port, ball, pull) => { X.push(`set_property PACKAGE_PIN ${ball} [get_ports {${port}}]`, `set_property IOSTANDARD LVCMOS33 [get_ports {${port}}]`); if (pull) X.push(`set_property PULLTYPE PULLUP [get_ports {${port}}]`); };
  FB_LED_BALL.forEach((ball, i) => pin(`leds[${i}]`, ball));
  [...G.used.ins].sort().forEach(p => pin(p, FB_PIN_BALL[p], true));
  outPins.sort().forEach(p => pin(p, FB_PIN_BALL[p]));
  if (G.used.fan) pin('fan_pwm', 'J18');
  // ---- the ARM program
  const st = [...G.used.status].sort(), ct = [...G.used.ctrl].sort();
  const P = ['# made by Ardzy FPGA blocks (written again at every change while this first line is here: delete it to keep your own version)',
    '# The program on the ARM next to the FPGA design: it shows the values the design gives the ARM in the Watch tab.',
    'import time', 'from ardzy import MMIO, watch', '', 'regs = MMIO(0x41200000)       # ctrl n at 4 * n (the design reads them), status n at 0x80 + 4 * n', ''];
  ct.forEach(n => P.push(`regs.write(${4 * n}, 0)               # "value from the ARM ctrl ${n}": change the 0`));
  if (st.length) P.push('print("FPGA design running: the status values are in the Watch tab.", flush=True)', 'while True:',
    `    watch(${st.map(n => `status${n}=regs.read(0x${(0x80 + 4 * n).toString(16)})`).join(', ')})`, '    time.sleep(0.2)', '');
  else P.push('print("FPGA design running (made with blocks).", flush=True)', '');
  return { code: L.join('\n'), xdc: X.join('\n') + '\n', py: P.join('\n'), notes: [...G.notes],
    hasDesign: tops.some(b => ['fpga_on_clock', 'fpga_every', 'fpga_on_pin', 'fpga_always'].includes(b.type)), loose };
}

/* ---------------------------------------------------------------- examples */
const fbHat = (type, fields, body, y) => Object.assign(bkB(type, fields, body ? { DO: body } : null), { x: 30, y: y || 30 });
const fbRegs = (...r) => bkSeq(...r.map(([n, w, i]) => bkB('fpga_register', { NAME: n, W: w, INIT: i || 0 })));
const fbProg = (...tops) => ({ blocks: { languageVersion: 0, blocks: tops.map((t, i) => Object.assign(t, { x: 30, y: 30 + i * 150 })) } });
const FB_EXAMPLES = {
  'Blink LED 0 (every 500 ms)': () => fbProg(fbHat('fpga_every', { N: 500, UNIT: 'ms' }, bkB('fpga_out_flip', { OUT: 'LED0' }))),
  'Count in binary on the 4 LEDs': () => fbProg(fbRegs(['count', 4, 0]),
    fbHat('fpga_every', { N: 250, UNIT: 'ms' }, bkB('fpga_add', { REG: 'count' }, { V: bkNum(1) })),
    fbHat('fpga_always', null, bkSeq(...[0, 1, 2, 3].map(i => bkB('fpga_out_set', { OUT: 'LED' + i }, { V: bkB('fpga_bit', { B: i }, { V: bkB('fpga_reg_get', { REG: 'count' }) }) }))))),
  'Breathing LED (PWM)': () => fbProg(fbRegs(['level', 8, 0]),
    fbHat('fpga_every', { N: 4, UNIT: 'ms' }, bkB('fpga_count', { REG: 'level' }, { N: bkNum(255) })),
    fbHat('fpga_always', null, bkB('fpga_out_set', { OUT: 'LED0' }, { V: bkB('fpga_pwm', null, { V: bkB('fpga_reg_get', { REG: 'level' }) }) }))),
  'Button on J3 pin 5 flips LED 1': () => fbProg(fbHat('fpga_on_pin', { PIN: 'J3_5', EDGE: 'fall' }, bkB('fpga_out_flip', { OUT: 'LED1' }))),
  'Square wave 1 kHz on J4 pin 5': () => fbProg(fbHat('fpga_every', { N: 500, UNIT: 'us' }, bkB('fpga_out_flip', { OUT: 'J4_5' }))),
  'Count pulses on J3 pin 5 for the ARM': () => fbProg(fbRegs(['pulses', 32, 0]),
    fbHat('fpga_on_pin', { PIN: 'J3_5', EDGE: 'rise' }, bkB('fpga_add', { REG: 'pulses' }, { V: bkNum(1) })),
    fbHat('fpga_always', null, bkB('fpga_status', { N: '0' }, { V: bkB('fpga_reg_get', { REG: 'pulses' }) }))),
  'Fans: speed from the ARM': () => fbProg(fbHat('fpga_always', null, bkB('fpga_fan', null, { V: bkB('fpga_bits', { H: 7, L: 0 }, { V: bkB('fpga_arm', { N: '0' }) }) }))),
  'Knight rider (4 LEDs)': () => fbProg(fbRegs(['pos', 2, 0], ['back', 1, 0]),
    fbHat('fpga_every', { N: 120, UNIT: 'ms' }, Object.assign(bkB('controls_if', null, {
      IF0: bkB('fpga_reg_get', { REG: 'back' }),
      DO0: Object.assign(bkB('controls_if', null, { IF0: bkB('logic_compare', { OP: 'EQ' }, { A: bkB('fpga_reg_get', { REG: 'pos' }), B: bkNum(1) }),
        DO0: bkB('fpga_set', { REG: 'back' }, { V: bkNum(0) }) }), { next: { block: bkB('fpga_add', { REG: 'pos' }, { V: bkNum(-1) }) } }),
      ELSE: Object.assign(bkB('controls_if', null, { IF0: bkB('logic_compare', { OP: 'EQ' }, { A: bkB('fpga_reg_get', { REG: 'pos' }), B: bkNum(2) }),
        DO0: bkB('fpga_set', { REG: 'back' }, { V: bkNum(1) }) }), { next: { block: bkB('fpga_add', { REG: 'pos' }, { V: bkNum(1) }) } }) }), { extraState: { hasElse: true } })),
    fbHat('fpga_always', null, bkSeq(...[0, 1, 2, 3].map(i => bkB('fpga_out_set', { OUT: 'LED' + i }, { V: bkB('logic_compare', { OP: 'EQ' }, { A: bkB('fpga_reg_get', { REG: 'pos' }), B: bkNum(i) }) }))))),
};

function fbToolbox() {
  const sh = n => ({ shadow: { type: 'math_number', fields: { NUM: n } } });
  const k = (type, inputs, fields) => Object.assign({ kind: 'block', type }, inputs ? { inputs } : {}, fields ? { fields } : {});
  return { kind: 'categoryToolbox', contents: [
    { kind: 'category', name: 'Start', colour: '30', contents: [k('fpga_every'), k('fpga_on_pin'), k('fpga_on_clock'), k('fpga_always')] },
    { kind: 'category', name: 'Registers', colour: '210', contents: [k('fpga_register'), k('fpga_set', { V: sh(0) }), k('fpga_add', { V: sh(1) }),
      k('fpga_count', { N: sh(9) }), k('fpga_flip_reg'), k('fpga_reg_get')] },
    { kind: 'category', name: 'Outputs', colour: '160', contents: [k('fpga_out_flip'), k('fpga_out_set', { V: { shadow: { type: 'logic_boolean' } } }),
      k('fpga_fan', { V: sh(128) })] },
    { kind: 'category', name: 'Inputs', colour: '120', contents: [k('fpga_pin_in')] },
    { kind: 'category', name: 'ARM', colour: '330', contents: [k('fpga_status', { V: sh(0) }), k('fpga_arm')] },
    { kind: 'sep' },
    { kind: 'category', name: 'Logic', categorystyle: 'logic_category', contents: [k('controls_if'), { kind: 'block', type: 'controls_if', extraState: { hasElse: true } },
      k('logic_compare', { B: sh(0) }), k('logic_operation'), k('logic_negate'), k('logic_boolean')] },
    { kind: 'category', name: 'Numbers and bits', colour: '260', contents: [k('math_number'), k('math_arithmetic', { A: sh(1), B: sh(1) }),
      k('fpga_bit'), k('fpga_bits'), k('fpga_bitop'), k('fpga_not'), k('fpga_shift'), k('fpga_pwm', { V: sh(64) })] },
  ] };
}
