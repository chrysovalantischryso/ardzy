/*
  EEPROM.cpp - 4 KB of "EEPROM" in a memory-mapped file (new bytes read as 0xFF, like a real one).
*/
#include "EEPROM.h"
#include <fcntl.h>
#include <stdio.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

EEPROMClass EEPROM;
static uint8_t *g_mem = nullptr;
static uint8_t g_fallback[4096];

uint8_t *EEPROMClass::data() {
  if (g_mem) return g_mem;
  mkdir("/var/lib/ardzy", 0755);
  const char *path = "/var/lib/ardzy/eeprom.bin";
  bool fresh = access(path, F_OK) != 0;
  int fd = open(path, O_RDWR | O_CREAT, 0644);
  if (fd >= 0 && ftruncate(fd, 4096) == 0) {
    void *p = mmap(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (p != MAP_FAILED) g_mem = (uint8_t *)p;
  }
  if (fd >= 0) close(fd);
  if (!g_mem) {
    fprintf(stderr, "EEPROM: can not use %s, the data will not be kept\n", path);
    g_mem = g_fallback;
    fresh = true;
  }
  if (fresh) memset(g_mem, 0xFF, 4096);
  return g_mem;
}

uint8_t EEPROMClass::read(int idx) { return (idx >= 0 && idx < 4096) ? data()[idx] : 0; }
void EEPROMClass::write(int idx, uint8_t val) { if (idx >= 0 && idx < 4096) data()[idx] = val; }
bool EEPROMClass::commit() { return g_mem && g_mem != g_fallback ? msync(g_mem, 4096, MS_SYNC) == 0 : false; }
