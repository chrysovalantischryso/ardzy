/* util/delay.h - compatibility for AVR code. */
#pragma once
#include "Arduino.h"
#define _delay_ms(ms) delay((unsigned long)(ms))
#define _delay_us(us) delayMicroseconds((unsigned int)(us))
