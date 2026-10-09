// ardzy.hpp: the Ardzy board from C++ (board LEDs, buzzer, buttons, FPGA registers, watch).
//
//   ardzy::led("green", true);          // status LED: "green", "red" or "ps"
//   ardzy::beep(0.1);                   // buzzer, seconds
//   if (ardzy::button("ip")) ...        // true while pressed: "ip" (S2) or "reset" (S1)
//   uint32_t v = ardzy::peek(0x41200000);   // 32-bit FPGA register at an address (Vivado's Address Editor)
//   ardzy::poke(0x41200000, 5);
//   ardzy::reg(1, 3);  ardzy::reg_write(1, 3, 42);   // word 3 of slot 1 of an Ardzy FPGA project
//   ardzy::watch("speed", 12.5);        // a live value for the app's Watch tab and Plotter
//
// Only use FPGA registers that the loaded FPGA design really has: reading an address with nothing
// behind it can hang the board until it is reset.
#pragma once
#include <fcntl.h>
#include <stdint.h>
#include <sys/mman.h>
#include <unistd.h>

#include <chrono>
#include <cstdio>
#include <map>
#include <stdexcept>
#include <string>
#include <thread>

namespace ardzy {

const uint32_t BUS_BASE = 0x43C00000;     // the register window of Ardzy FPGA projects (16 slots of 4 KB)

inline void gpio_set(int n, bool v)
{
    std::string p = "/sys/class/gpio/gpio" + std::to_string(n) + "/value";
    FILE *f = std::fopen(p.c_str(), "w");
    if (!f) throw std::runtime_error("cannot open " + p);
    std::fputs(v ? "1" : "0", f);
    std::fclose(f);
}

inline bool gpio_get(int n)
{
    std::string p = "/sys/class/gpio/gpio" + std::to_string(n) + "/value";
    FILE *f = std::fopen(p.c_str(), "r");
    if (!f) throw std::runtime_error("cannot open " + p);
    int c = std::fgetc(f);
    std::fclose(f);
    return c == '1';
}

inline void led(const std::string &name, bool on = true)
{
    if (name == "green") gpio_set(38, on);
    else if (name == "red") gpio_set(37, on);
    else if (name == "ps") gpio_set(15, !on);          // the PS LED is on when the pin is low
    else throw std::invalid_argument("led: green, red or ps");
}

inline void beep(double seconds = 0.1)
{
    gpio_set(39, true);
    std::this_thread::sleep_for(std::chrono::duration<double>(seconds));
    gpio_set(39, false);
}

inline bool button(const std::string &name = "ip")
{
    if (name == "ip") return !gpio_get(51);
    if (name == "reset") return !gpio_get(47);
    throw std::invalid_argument("button: ip or reset");
}

inline volatile uint32_t *reg_ptr(uint32_t addr)
{
    static int fd = -1;
    static std::map<uint32_t, volatile uint32_t *> pages;
    if (addr & 3) throw std::invalid_argument("register addresses are multiples of 4");
    uint32_t page = addr & ~0xfffu;
    auto it = pages.find(page);
    if (it == pages.end()) {
        if (fd < 0 && (fd = open("/dev/mem", O_RDWR | O_SYNC)) < 0) throw std::runtime_error("cannot open /dev/mem");
        void *m = mmap64(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, (off64_t)page);   // 64-bit offset: addresses above 2 GB too
        if (m == MAP_FAILED) throw std::runtime_error("mmap failed");
        it = pages.emplace(page, static_cast<volatile uint32_t *>(m)).first;
    }
    return it->second + ((addr & 0xfff) >> 2);
}

inline uint32_t peek(uint32_t addr) { return *reg_ptr(addr); }
inline void poke(uint32_t addr, uint32_t value) { *reg_ptr(addr) = value; }
inline uint32_t reg(int slot, int word) { return peek(BUS_BASE + slot * 0x1000 + 4 * word); }
inline void reg_write(int slot, int word, uint32_t v) { poke(BUS_BASE + slot * 0x1000 + 4 * word, v); }

inline void watch(const std::string &name, double value) { std::printf("%s:%g\n", name.c_str(), value); std::fflush(stdout); }
inline void watch(const std::string &name, const std::string &text) { std::printf("%s=\"%s\"\n", name.c_str(), text.c_str()); std::fflush(stdout); }

}  // namespace ardzy
