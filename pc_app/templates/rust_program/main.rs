// __NAME__: a Rust program on the Ardzy board.
// Press Upload: it is compiled on the board (rustc -O, 20 to 60 seconds) and started;
// println! output shows up in the Monitor.
// ardzy.rs has the board: led, beep, button, peek/poke (FPGA registers), watch.
//   - the green status LED blinks
//   - press the IP button (S2): a beep, and the count goes up (see it in the Watch tab)
//   - press the Reset button (S1): the program ends
mod ardzy;

use std::{thread, time::Duration};

fn main() {
    println!("hello from __NAME__ (Rust): press the IP button, or Reset to end");
    let mut presses = 0;
    let mut t = 0;
    loop {
        ardzy::led("green", t % 10 < 5);
        if ardzy::button("ip") {
            presses += 1;
            println!("IP button pressed ({})", presses);
            ardzy::watch("presses", presses);
            ardzy::beep(0.08);
            while ardzy::button("ip") {
                thread::sleep(Duration::from_millis(20)); // wait until it is released
            }
        }
        if ardzy::button("reset") {
            println!("Reset button pressed: bye!");
            ardzy::beep(0.4);
            break;
        }
        // An FPGA register (only with an FPGA design that has it), for example:
        //   let v = ardzy::reg(1, 0);
        thread::sleep(Duration::from_millis(100));
        t += 1;
    }
    ardzy::led("green", false);
}
