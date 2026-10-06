/*
  EEPROM.h - Arduino EEPROM library for the Ardzy board: 4096 bytes kept in a file on the SD card
  (/var/lib/ardzy/eeprom.bin). It keeps its contents across programs and power cycles.
  Writes reach the card within a few seconds; EEPROM.commit() makes sure right now.
*/
#ifndef ARDZY_EEPROM_H
#define ARDZY_EEPROM_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>

class EEPROMClass;

struct EERef {
  EERef(int i) : index(i) {}
  uint8_t operator*() const;
  operator uint8_t() const { return **this; }
  EERef &operator=(uint8_t v);
  EERef &operator=(const EERef &r) { return *this = *r; }
  EERef &operator+=(uint8_t v) { return *this = **this + v; }
  EERef &operator-=(uint8_t v) { return *this = **this - v; }
  EERef &operator++() { return *this += 1; }
  EERef &operator--() { return *this -= 1; }
  EERef &update(uint8_t v) { return v != **this ? *this = v : *this; }
  int index;
};

class EEPROMClass {
public:
  uint8_t read(int idx);
  void write(int idx, uint8_t val);
  void update(int idx, uint8_t val) { if (read(idx) != val) write(idx, val); }
  EERef operator[](int idx) { return EERef(idx); }
  uint16_t length() { return 4096; }
  void begin(size_t = 0) { data(); }
  bool commit();
  void end() { commit(); }
  template <typename T> T &get(int idx, T &t) {
    uint8_t *d = data();
    if (idx >= 0 && idx + (int)sizeof(T) <= 4096) memcpy(&t, d + idx, sizeof(T));
    return t;
  }
  template <typename T> const T &put(int idx, const T &t) {
    uint8_t *d = data();
    if (idx >= 0 && idx + (int)sizeof(T) <= 4096) memcpy(d + idx, &t, sizeof(T));
    return t;
  }
  uint8_t *data();
};

extern EEPROMClass EEPROM;

inline uint8_t EERef::operator*() const { return EEPROM.read(index); }
inline EERef &EERef::operator=(uint8_t v) { EEPROM.write(index, v); return *this; }

#endif
