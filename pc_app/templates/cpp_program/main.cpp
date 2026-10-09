// __NAME__: a C++ program on the Ardzy board.
// Press Upload: it is compiled on the board (g++, C++17) and started; std::cout shows up in the Monitor.
// ardzy.hpp has the board: LEDs, buzzer, buttons, FPGA registers, watch().
//   - the green status LED blinks
//   - press the IP button (S2): a beep, and the count goes up (see it in the Watch tab)
//   - press the Reset button (S1): the program ends
#include <chrono>
#include <iostream>
#include <thread>

#include "ardzy.hpp"

int main()
{
    std::cout << "hello from __NAME__ (C++): press the IP button, or Reset to end" << std::endl;
    int presses = 0;
    for (int t = 0;; t++) {
        ardzy::led("green", t % 10 < 5);         // on half a second, off half a second
        if (ardzy::button("ip")) {
            presses++;
            std::cout << "IP button pressed (" << presses << ")" << std::endl;
            ardzy::watch("presses", presses);
            ardzy::beep(0.08);
            while (ardzy::button("ip"))         // wait until it is released
                std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
        if (ardzy::button("reset")) {
            std::cout << "Reset button pressed: bye!" << std::endl;
            ardzy::beep(0.4);
            break;
        }
        // An FPGA register (only with an FPGA design that has it), for example:
        //   uint32_t v = ardzy::reg(1, 0);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    ardzy::led("green", false);
    return 0;
}
