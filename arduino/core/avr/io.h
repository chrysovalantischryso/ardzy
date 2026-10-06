/* avr/io.h - compatibility for sketches and libraries written for AVR boards (no AVR registers here). */
#pragma once
#include <stdint.h>
#ifndef _BV
#define _BV(bit) (1 << (bit))
#endif
#define cli()
#define sei()
