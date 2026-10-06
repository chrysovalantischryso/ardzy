/*
  wiring.cpp - the Arduino pin, time and analog functions for the Ardzy core.
*/
#include "Arduino.h"
#include "ardzy_hw.h"
#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <vector>

using namespace ardzy;

// ------------------------------------------------------------------ time
static struct timespec t_start;
static bool t_started = false;

static void time_init() {
  if (!t_started) { clock_gettime(CLOCK_MONOTONIC, &t_start); t_started = true; }
}

static uint64_t now_us() {
  time_init();
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (uint64_t)(t.tv_sec - t_start.tv_sec) * 1000000ULL + (t.tv_nsec - t_start.tv_nsec) / 1000;
}

unsigned long millis(void) { return (unsigned long)(now_us() / 1000); }
unsigned long micros(void) { return (unsigned long)now_us(); }

void delay(unsigned long ms) {
  if (!ms) { yield(); return; }
  struct timespec t = {(time_t)(ms / 1000), (long)(ms % 1000) * 1000000L};
  while (nanosleep(&t, &t) != 0) {}
}

void delayMicroseconds(unsigned int us) {
  if (us > 200) {                       // long waits: let other programs run
    struct timespec t = {(time_t)(us / 1000000), (long)(us % 1000000) * 1000L};
    while (nanosleep(&t, &t) != 0) {}
    return;
  }
  uint64_t end = now_us() + us;         // short waits: exact busy wait
  while (now_us() < end) {}
}

void yield(void) { sched_yield(); }

// ------------------------------------------------------------------ digital
static PinMode g_mode[NUM_DIGITAL_PINS];

void pinMode(pin_size_t p, PinMode mode) {
  PinInfo pi = pin(p);
  if (pi.kind == FPGA_IO) {
    pwmRelease(pi.index);
    if (fpgaFuncOf(pi.index)) fpgaFunc(pi.index, 0);
    // pull-ups: the connector pins always have a weak pull-up, so INPUT and INPUT_PULLUP are the same
    fpgaOutput(pi.index, mode == OUTPUT || mode == OUTPUT_OPENDRAIN);
  } else if (pi.kind == FAN_OUT) {
    ctl()[0x04 >> 2] = 0;               // fan PWM off = held high (full speed)
  }
  if (p < NUM_DIGITAL_PINS) g_mode[p] = mode;
}

void digitalWrite(pin_size_t p, PinStatus v) {
  PinInfo pi = pin(p);
  bool on = (v == HIGH);
  if (pi.active_low) on = !on;
  switch (pi.kind) {
    case FPGA_IO:
      if (pwmFor(pi.index, false) >= 0) { pwmRelease(pi.index); fpgaFunc(pi.index, 0); }
      if (p < NUM_DIGITAL_PINS && g_mode[p] == OUTPUT_OPENDRAIN) {     // 0 = drive low, 1 = let go
        fpgaWrite(pi.index, false);
        fpgaOutput(pi.index, !on);
      } else
        fpgaWrite(pi.index, on);
      break;
    case FAN_OUT:
      ctl()[0x0C >> 2] = on ? ctl()[0x08 >> 2] : 0;
      ctl()[0x04 >> 2] = 1;
      break;
    case PS_PIN:
      psWrite(pi.index, on);
      break;
    default:
      break;
  }
}

PinStatus digitalRead(pin_size_t p) {
  PinInfo pi = pin(p);
  bool v = false;
  switch (pi.kind) {
    case FPGA_IO: case FPGA_IN: case FAN_OUT: v = fpgaRead(pi.index); break;
    case PS_PIN: v = psRead(pi.index); break;
    default: return LOW;
  }
  if (pi.active_low) v = !v;
  return v ? HIGH : LOW;
}

// ------------------------------------------------------------------ analog
static int g_aw_bits = 8, g_ar_bits = 10;
static float g_pwm_hz[NUM_DIGITAL_PINS];

void analogWriteResolution(int bits) { g_aw_bits = bits < 1 ? 1 : bits > 16 ? 16 : bits; }
void analogReadResolution(int bits) { g_ar_bits = bits < 1 ? 1 : bits > 16 ? 16 : bits; }

void analogWriteFrequency(pin_size_t p, float hz) {
  if (p < NUM_DIGITAL_PINS) g_pwm_hz[p] = hz;
}

void analogWrite(pin_size_t p, int value) {
  PinInfo pi = pin(p);
  int maxv = (1 << g_aw_bits) - 1;
  if (value < 0) value = 0;
  if (value > maxv) value = maxv;
  double duty = (double)value / maxv;
  if (pi.active_low) duty = 1.0 - duty;
  double hz = (p < NUM_DIGITAL_PINS && g_pwm_hz[p] > 0) ? g_pwm_hz[p] : 1000.0;
  if (pi.kind == FAN_OUT) {
    uint32_t per = (uint32_t)(fclk() / 25000.0);
    ctl()[0x08 >> 2] = per;
    ctl()[0x0C >> 2] = (uint32_t)(per * duty);
    ctl()[0x04 >> 2] = 1;
    return;
  }
  if (pi.kind != FPGA_IO) return;
  int ch = pwmFor(pi.index, true);
  pwmSet(ch, hz, duty);
  fpgaFunc(pi.index, 1 + ch);
  if (p < NUM_DIGITAL_PINS) g_mode[p] = OUTPUT;
}

static const char *XADC_NAMES[] = {"temp", "vccint", "vccaux", "vccbram", "vccpint", "vccpaux", "vccoddr"};

static long read_long(const char *path, long dflt) {
  FILE *f = fopen(path, "r");
  if (!f) return dflt;
  long v = dflt;
  if (fscanf(f, "%ld", &v) != 1) v = dflt;
  fclose(f);
  return v;
}

int analogRead(pin_size_t p) {
  PinInfo pi = pin(p);
  if (pi.kind != ANALOG) return 0;
  char path[128];
  if (pi.index == 0)
    snprintf(path, sizeof path, "/sys/bus/iio/devices/iio:device0/in_temp0_raw");
  else {
    // the label files tell which voltage channel is which
    long raw = 0;
    for (int ch = 0; ch < 16; ch++) {
      char lab[128], name[32] = {0};
      snprintf(lab, sizeof lab, "/sys/bus/iio/devices/iio:device0/in_voltage%d_label", ch);
      FILE *f = fopen(lab, "r");
      if (!f) continue;
      if (fscanf(f, "%31s", name) == 1 && strcmp(name, XADC_NAMES[pi.index]) == 0) {
        fclose(f);
        snprintf(path, sizeof path, "/sys/bus/iio/devices/iio:device0/in_voltage%d_raw", ch);
        raw = read_long(path, 0);
        return (int)(g_ar_bits >= 12 ? raw << (g_ar_bits - 12) : raw >> (12 - g_ar_bits));
      }
      fclose(f);
    }
    return (int)raw;
  }
  long raw = read_long(path, 0);
  return (int)(g_ar_bits >= 12 ? raw << (g_ar_bits - 12) : raw >> (12 - g_ar_bits));
}

void analogReference(uint8_t) {}

// ------------------------------------------------------------------ tone
static pthread_mutex_t tone_mx = PTHREAD_MUTEX_INITIALIZER;
struct ToneStop { int pin; unsigned long until; };
static std::vector<ToneStop> tone_stops;
static pthread_t tone_thread;
static bool tone_thread_on = false;

static void *tone_worker(void *) {
  for (;;) {
    usleep(1000);
    pthread_mutex_lock(&tone_mx);
    unsigned long now = millis();
    for (size_t i = 0; i < tone_stops.size();)
      if ((long)(now - tone_stops[i].until) >= 0) {
        int p = tone_stops[i].pin;
        tone_stops.erase(tone_stops.begin() + i);
        pthread_mutex_unlock(&tone_mx);
        noTone(p);
        pthread_mutex_lock(&tone_mx);
      } else
        i++;
    pthread_mutex_unlock(&tone_mx);
  }
  return nullptr;
}

void tone(uint8_t p, unsigned int frequency, unsigned long duration) {
  PinInfo pi = pin(p);
  if (pi.kind == PS_PIN && pi.index == 39) {      // the buzzer has its own sound: just switch it
    psWrite(39, frequency > 0);
  } else if (pi.kind == FPGA_IO) {
    if (!frequency) { noTone(p); return; }
    int ch = pwmFor(pi.index, true);
    pwmSet(ch, frequency, 0.5);
    fpgaFunc(pi.index, 1 + ch);
  } else
    return;
  if (duration) {
    pthread_mutex_lock(&tone_mx);
    tone_stops.push_back({p, millis() + duration});
    if (!tone_thread_on) { pthread_create(&tone_thread, nullptr, tone_worker, nullptr); tone_thread_on = true; }
    pthread_mutex_unlock(&tone_mx);
  }
}

void noTone(uint8_t p) {
  PinInfo pi = pin(p);
  if (pi.kind == PS_PIN && pi.index == 39) { psWrite(39, false); return; }
  if (pi.kind != FPGA_IO) return;
  pwmRelease(pi.index);
  fpgaFunc(pi.index, 0);
  fpgaWrite(pi.index, false);
}

// ------------------------------------------------------------------ pulses and shifting
unsigned long pulseIn(uint8_t p, uint8_t state, unsigned long timeout) {
  uint64_t start = now_us();
  auto expired = [&]() { return now_us() - start > timeout; };
  while (digitalRead(p) == (state ? HIGH : LOW)) if (expired()) return 0;    // wait for the previous pulse to end
  while (digitalRead(p) != (state ? HIGH : LOW)) if (expired()) return 0;    // wait for the pulse to start
  uint64_t t0 = now_us();
  while (digitalRead(p) == (state ? HIGH : LOW)) if (expired()) return 0;
  return (unsigned long)(now_us() - t0);
}

unsigned long pulseInLong(uint8_t p, uint8_t state, unsigned long timeout) { return pulseIn(p, state, timeout); }

void shiftOut(pin_size_t dataPin, pin_size_t clockPin, BitOrder order, uint8_t val) {
  for (int i = 0; i < 8; i++) {
    int b = order == LSBFIRST ? (val >> i) & 1 : (val >> (7 - i)) & 1;
    digitalWrite(dataPin, b ? HIGH : LOW);
    digitalWrite(clockPin, HIGH);
    digitalWrite(clockPin, LOW);
  }
}

uint8_t shiftIn(pin_size_t dataPin, pin_size_t clockPin, BitOrder order) {
  uint8_t v = 0;
  for (int i = 0; i < 8; i++) {
    digitalWrite(clockPin, HIGH);
    int b = digitalRead(dataPin) == HIGH;
    v |= order == LSBFIRST ? (b << i) : (b << (7 - i));
    digitalWrite(clockPin, LOW);
  }
  return v;
}

// ------------------------------------------------------------------ "interrupts": a fast watcher thread
struct Isr { int pin; voidFuncPtrParam fn; void *param; voidFuncPtr fn0; PinStatus mode; int last; };
static std::vector<Isr> isrs;
static pthread_mutex_t isr_mx = PTHREAD_MUTEX_INITIALIZER;
static pthread_t isr_thread;
static bool isr_thread_on = false;
static volatile bool isr_enabled = true;

static void *isr_worker(void *) {
  for (;;) {
    if (isr_enabled) {
      pthread_mutex_lock(&isr_mx);
      for (auto &i : isrs) {
        int v = digitalRead(i.pin) == HIGH;
        bool fire = (i.mode == CHANGE && v != i.last) || (i.mode == RISING && v && !i.last) ||
                    (i.mode == FALLING && !v && i.last) || (i.mode == LOW && !v) || (i.mode == HIGH && v);
        i.last = v;
        if (fire) {
          if (i.fn) i.fn(i.param);
          else if (i.fn0) i.fn0();
        }
      }
      pthread_mutex_unlock(&isr_mx);
    }
    usleep(50);                    // about 10 to 20 thousand checks per second
  }
  return nullptr;
}

static void add_isr(pin_size_t p, voidFuncPtr f0, voidFuncPtrParam f, void *param, PinStatus mode) {
  detachInterrupt(p);
  pthread_mutex_lock(&isr_mx);
  isrs.push_back({p, f, param, f0, mode, digitalRead(p) == HIGH});
  if (!isr_thread_on) { pthread_create(&isr_thread, nullptr, isr_worker, nullptr); isr_thread_on = true; }
  pthread_mutex_unlock(&isr_mx);
}

void attachInterrupt(pin_size_t p, voidFuncPtr callback, PinStatus mode) { add_isr(p, callback, nullptr, nullptr, mode); }
void attachInterruptParam(pin_size_t p, voidFuncPtrParam callback, PinStatus mode, void *param) {
  add_isr(p, nullptr, callback, param, mode);
}
void detachInterrupt(pin_size_t p) {
  pthread_mutex_lock(&isr_mx);
  for (size_t i = 0; i < isrs.size();)
    if (isrs[i].pin == p) isrs.erase(isrs.begin() + i); else i++;
  pthread_mutex_unlock(&isr_mx);
}
void interrupts(void) { isr_enabled = true; }
void noInterrupts(void) { isr_enabled = false; }

// ------------------------------------------------------------------ math and number helpers
static unsigned long rnd_state = 1;
void randomSeed(unsigned long seed) { if (seed) { rnd_state = seed; srandom(seed); } }
long random(long howbig) { return howbig <= 0 ? 0 : ::random() % howbig; }
long random(long howsmall, long howbig) { return howsmall >= howbig ? howsmall : random(howbig - howsmall) + howsmall; }

extern "C" {
static char *to_base(unsigned long long v, char *s, int radix, bool neg) {
  char tmp[72];
  int n = 0;
  if (radix < 2 || radix > 36) { s[0] = 0; return s; }
  do { int d = v % radix; tmp[n++] = d < 10 ? '0' + d : 'a' + d - 10; v /= radix; } while (v);
  int k = 0;
  if (neg) s[k++] = '-';
  while (n) s[k++] = tmp[--n];
  s[k] = 0;
  return s;
}
char *itoa(int v, char *s, int r) { return r == 10 && v < 0 ? to_base(-(long long)v, s, r, true) : to_base((unsigned)v, s, r, false); }
char *ltoa(long v, char *s, int r) { return r == 10 && v < 0 ? to_base(-(long long)v, s, r, true) : to_base((unsigned long)v, s, r, false); }
char *utoa(unsigned v, char *s, int r) { return to_base(v, s, r, false); }
char *ultoa(unsigned long v, char *s, int r) { return to_base(v, s, r, false); }
char *dtostrf(double val, signed char width, unsigned char prec, char *sout) {
  char fmt[20];
  snprintf(fmt, sizeof fmt, "%%%d.%df", width, prec);
  sprintf(sout, fmt, val);
  return sout;
}
}

// ------------------------------------------------------------------ the board object
ArdzyBoard Ardzy;

void ArdzyBoard::beep(unsigned int ms) { psWrite(39, true); delay(ms); psWrite(39, false); }

float ArdzyBoard::temperature() {
  long raw = read_long("/sys/bus/iio/devices/iio:device0/in_temp0_raw", 0);
  long off = read_long("/sys/bus/iio/devices/iio:device0/in_temp0_offset", 0);
  FILE *f = fopen("/sys/bus/iio/devices/iio:device0/in_temp0_scale", "r");
  double sc = 0;
  if (f) { if (fscanf(f, "%lf", &sc) != 1) sc = 0; fclose(f); }
  return (float)((raw + off) * sc / 1000.0);
}

float ArdzyBoard::voltage(const char *rail) {
  for (int ch = 0; ch < 16; ch++) {
    char lab[128], name[32] = {0}, path[128];
    snprintf(lab, sizeof lab, "/sys/bus/iio/devices/iio:device0/in_voltage%d_label", ch);
    FILE *f = fopen(lab, "r");
    if (!f) continue;
    bool hit = fscanf(f, "%31s", name) == 1 && strcmp(name, rail) == 0;
    fclose(f);
    if (!hit) continue;
    snprintf(path, sizeof path, "/sys/bus/iio/devices/iio:device0/in_voltage%d_raw", ch);
    long raw = read_long(path, 0);
    snprintf(path, sizeof path, "/sys/bus/iio/devices/iio:device0/in_voltage%d_scale", ch);
    double sc = 0;
    if ((f = fopen(path, "r"))) { if (fscanf(f, "%lf", &sc) != 1) sc = 0; fclose(f); }
    return (float)(raw * sc / 1000.0);
  }
  return 0;
}

void ArdzyBoard::fan(int percent) {
  if (!ready()) return;
  if (percent < 0) { ctl()[0x04 >> 2] = 0; return; }
  uint32_t per = (uint32_t)(fclk() / 25000.0);
  ctl()[0x08 >> 2] = per;
  ctl()[0x0C >> 2] = (uint32_t)(per * (percent > 100 ? 100 : percent) / 100);
  ctl()[0x04 >> 2] = 1;
}

int ArdzyBoard::fanRpm(int n) {
  if (!ready() || n < 1 || n > 6) return 0;
  double gate_s = ctl()[0x28 >> 2] / fclk();
  return (int)(ctl()[(0x10 >> 2) + n - 1] / gate_s * 60 / 2);
}

unsigned long ArdzyBoard::fpgaClock() { return (unsigned long)fclk(); }

const char *ArdzyBoard::chipId() {
  static char id[24] = {0};
  if (ready()) {
    uint32_t hi = ctl()[0x38 >> 2], lo = ctl()[0x34 >> 2];
    if ((hi >> 31) && ((hi & 0x1FFFFFF) || lo)) {
      snprintf(id, sizeof id, "%07X%08X", hi & 0x1FFFFFF, lo);
      return id;
    }
  }
  FILE *f = fopen("/var/lib/ardzy/dna", "r");
  if (f) { if (!fgets(id, sizeof id, f)) id[0] = 0; fclose(f); }
  for (char *c = id; *c; c++) if (*c == '\n') *c = 0;
  return id;
}

bool ArdzyBoard::pinControlLoaded() { return ready(); }

// watch lines: one value per line, the same format the app's Plotter and Watch tab and the data logger read
void ArdzyBoard::watch(const char *name, double value) { Serial.print(name); Serial.print(':'); Serial.println(value, 4); }
void ArdzyBoard::watch(const char *name, long value) { Serial.print(name); Serial.print(':'); Serial.println(value); }
void ArdzyBoard::watch(const char *name, const char *text) {
  Serial.print(name); Serial.print("=\""); Serial.print(text); Serial.println('"');
}
