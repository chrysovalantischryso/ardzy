// __NAME__: a JavaScript program (Node.js) on the Ardzy board.
// Press Upload: it runs on the board; everything console.log() prints shows up in the Monitor.
// ardzy.js has the board: led, beep, button, peek/poke (FPGA registers), watch, sleep.
//   - the green status LED blinks
//   - press the IP button (S2): a beep, and the count goes up (see it in the Watch tab)
//   - press the Reset button (S1): the program ends
const ardzy = require('./ardzy');

console.log('hello from __NAME__ (JavaScript): press the IP button, or Reset to end');
let presses = 0;
for (let t = 0; ; t++) {
  ardzy.led('green', t % 10 < 5);
  if (ardzy.button('ip')) {
    presses++;
    console.log(`IP button pressed (${presses})`);
    ardzy.watch({ presses });
    ardzy.beep(0.08);
    while (ardzy.button('ip')) ardzy.sleep(0.02);   // wait until it is released
  }
  if (ardzy.button('reset')) {
    console.log('Reset button pressed: bye!');
    ardzy.beep(0.4);
    break;
  }
  // An FPGA register (only with an FPGA design that has it), for example:
  //   const v = ardzy.reg(1, 0);
  ardzy.sleep(0.1);
}
ardzy.led('green', false);
