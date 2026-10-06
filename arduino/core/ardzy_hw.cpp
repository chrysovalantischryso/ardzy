/*
  ardzy_hw.cpp - register access for the Ardzy Arduino core (one 32-bit access per read/write).
*/
#include "ardzy_hw.h"
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <math.h>

namespace ardzy {

static volatile uint32_t *g_gpio, *g_ctl, *g_ps, *g_slcr;
static bool g_ready = false;
static pthread_mutex_t g_mx = PTHREAD_RECURSIVE_MUTEX_INITIALIZER_NP;
static volatile uint32_t g_dummy_port, g_dummy_mode;   // for pins that have no port
static int g_pwm_owner[8] = {-1, -1, -1, -1, -1, -1, -1, -1};

void lock() { pthread_mutex_lock(&g_mx); }
void unlock() { pthread_mutex_unlock(&g_mx); }

void fatal(const char *msg) {
  fprintf(stderr, "ardzy: %s\n", msg);
  fflush(stdout);
  exit(1);
}

static volatile uint32_t *map(int fd, uint32_t base, size_t size, int prot) {
  void *p = mmap(nullptr, size, prot, MAP_SHARED, fd, base);
  if (p == MAP_FAILED) fatal("can not map the hardware registers (run as root)");
  return (volatile uint32_t *)p;
}

static bool pin_control_loaded() {
  char buf[64] = {0};
  FILE *f = fopen("/var/lib/ardzy/fpga_design", "r");
  if (!f) return false;
  size_t n = fread(buf, 1, sizeof(buf) - 1, f);
  fclose(f);
  while (n && (buf[n - 1] == '\n' || buf[n - 1] == ' ')) buf[--n] = 0;
  return strcmp(buf, "ardzy_io") == 0;
}

bool begin() {
  if (g_ps) return g_ready;
  int fd = open("/dev/mem", O_RDWR | O_SYNC);
  if (fd < 0) fatal("can not open /dev/mem (run as root)");
  g_ps = map(fd, PS_GPIO, 0x1000, PROT_READ | PROT_WRITE);
  g_slcr = map(fd, 0xF8000000, 0x1000, PROT_READ);
  if (pin_control_loaded()) {
    g_gpio = map(fd, GPIO_BASE, 0x10000, PROT_READ | PROT_WRITE);
    g_ctl = map(fd, CTL_BASE, 0x10000, PROT_READ | PROT_WRITE);
    g_ready = (g_ctl[0] == CTL_ID_V2);
  }
  close(fd);
  if (g_ready) {                    // a clean start, like the reset of an Arduino
    for (int i = 0; i < 7; i++) g_ctl[(0x40 >> 2) + i] = 0;          // every pin back to GPIO
    g_gpio[0] = 0; g_gpio[2] = 0;
    g_gpio[1] = 0xFFFFFFFF; g_gpio[3] = 0x1FFFF;                      // every pin an input
    g_ctl[0xE0 >> 2] = 868 | (2u << 16);                              // UART off
  }
  return g_ready;
}

bool ready() { return g_ready; }
volatile uint32_t *gpio() { return g_gpio; }
volatile uint32_t *ctl() { return g_ctl; }
volatile uint32_t *psgpio() { return g_ps; }

PinInfo pin(int p) {
  if (p >= 0 && p <= 35) return {FPGA_IO, p, false};
  if (p >= 36 && p <= 39) return {FPGA_IO, p, true};            // LEDs are active low
  if (p == 40) return {FPGA_IO, 40, false};
  if (p >= 41 && p <= 44) return {FPGA_IN, p, false};
  if (p >= 45 && p <= 48) return {FPGA_IO, p, false};
  if (p >= 49 && p <= 54) return {FPGA_IN, p, false};
  if (p == 55) return {FAN_OUT, 55, false};
  switch (p) {
    case 60: return {PS_PIN, 38, false};   // green status LED
    case 61: return {PS_PIN, 37, false};   // red status LED
    case 62: return {PS_PIN, 15, true};    // LED D2, active low
    case 63: return {PS_PIN, 39, false};   // buzzer
    case 64: return {PS_PIN, 51, false};   // IP button (pressed = LOW)
    case 65: return {PS_PIN, 47, false};   // Reset button (pressed = LOW)
  }
  if (p >= 100 && p <= 106) return {ANALOG, p - 100, false};
  return {NONE, -1, false};
}

static void need() {
  if (!g_ps) begin();                // a library may use a pin in a global constructor, before main()
  if (!g_ready) fatal("the pin-control FPGA design is not loaded (sketches load it automatically: upload again)");
}

// map the hardware before any global constructor of the sketch or its libraries runs
__attribute__((constructor(101))) static void early_init() { begin(); }

void fpgaFunc(int idx, int func) {
  need();
  lock();
  volatile uint32_t &r = g_ctl[(0x40 >> 2) + idx / 8];
  int sh = 4 * (idx % 8);
  r = (r & ~(0xFu << sh)) | ((uint32_t)func << sh);
  unlock();
}

int fpgaFuncOf(int idx) {
  need();
  return (g_ctl[(0x40 >> 2) + idx / 8] >> (4 * (idx % 8))) & 0xF;
}

void fpgaOutput(int idx, bool on) {
  need();
  int b = idx < 32 ? 0 : 1, bit = idx < 32 ? idx : idx - 32;
  lock();
  volatile uint32_t &tri = g_gpio[b ? 3 : 1];
  tri = on ? (tri & ~(1u << bit)) : (tri | (1u << bit));
  unlock();
}

void fpgaWrite(int idx, bool v) {
  need();
  int b = idx < 32 ? 0 : 1, bit = idx < 32 ? idx : idx - 32;
  lock();                            // DATA reads the pins: an output pin reads its own value
  volatile uint32_t &r = g_gpio[b ? 2 : 0];
  r = v ? (r | (1u << bit)) : (r & ~(1u << bit));
  unlock();
}

uint64_t fpgaLive() {
  need();
  uint32_t lo = g_ctl[0x128 >> 2], hi = g_ctl[0x12C >> 2];
  return (uint64_t)hi << 32 | lo;
}

bool fpgaRead(int sig) {
  need();
  if (sig < 32) return (g_ctl[0x128 >> 2] >> sig) & 1;
  return (g_ctl[0x12C >> 2] >> (sig - 32)) & 1;
}

void psWrite(int mio, bool v) {
  int bank = mio / 32, bit = mio % 32;
  uint32_t off = bank * 8 + (bit >= 16 ? 4 : 0);
  int b = bit % 16;
  g_ps[off >> 2] = ((~(1u << b) & 0xFFFFu) << 16) | ((v ? 1u : 0u) << b);
}

bool psRead(int mio) {
  return (g_ps[(0x60 >> 2) + mio / 32] >> (mio % 32)) & 1;
}

double fclk() {
  if (!g_slcr) return 100e6;
  uint32_t io = g_slcr[0x108 >> 2], f0 = g_slcr[0x170 >> 2];
  double pll = 33333333.3 * ((io >> 12) & 0x7F);
  int d0 = (f0 >> 8) & 0x3F, d1 = (f0 >> 20) & 0x3F;
  return (d0 && d1) ? pll / d0 / d1 : 100e6;
}

int pwmFor(int idx, bool allocate) {
  lock();
  int ch = -1;
  for (int c = 0; c < 8; c++)
    if (g_pwm_owner[c] == idx) ch = c;
  if (ch < 0 && allocate) {
    for (int c = 0; c < 8 && ch < 0; c++)
      if (g_pwm_owner[c] < 0) { g_pwm_owner[c] = idx; ch = c; }
    if (ch < 0) { unlock(); fatal("all 8 PWM channels are in use (analogWrite / tone / Servo)"); }
  }
  unlock();
  return ch;
}

void pwmRelease(int idx) {
  lock();
  for (int c = 0; c < 8; c++)
    if (g_pwm_owner[c] == idx) g_pwm_owner[c] = -1;
  unlock();
}

void pwmSet(int ch, double hz, double duty) {
  need();
  double f = fclk();
  uint32_t per = (uint32_t)fmax(2.0, llround(f / hz));
  uint32_t hi = (uint32_t)llround(per * fmin(1.0, fmax(0.0, duty)));
  g_ctl[(0x60 >> 2) + 2 * ch] = per;
  g_ctl[(0x64 >> 2) + 2 * ch] = hi;
}

void pwmSetPulse(int ch, double hz, double high_us) {
  need();
  double f = fclk();
  uint32_t per = (uint32_t)fmax(2.0, llround(f / hz));
  uint32_t hi = (uint32_t)fmin((double)per, (double)llround(high_us * f / 1e6));
  g_ctl[(0x60 >> 2) + 2 * ch] = per;
  g_ctl[(0x64 >> 2) + 2 * ch] = hi;
}

}  // namespace ardzy

// the classic "fast pin" registers (see pins_ardzy.h)
extern "C" volatile uint32_t *ardzy_port_out(uint8_t port) {
  using namespace ardzy;
  if (!g_ps) begin();
  if (!g_ready || port > 1) return &g_dummy_port;
  return &g_gpio[port ? 2 : 0];
}

extern "C" volatile uint32_t *ardzy_port_mode(uint8_t) {
  return &ardzy::g_dummy_mode;     // pin directions: use pinMode()
}
