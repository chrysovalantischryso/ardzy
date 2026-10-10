/*
  pins_ardzy.h - pin numbers of the Antminer S9 board for Arduino sketches.

  D0..D35   the 9 connectors J1..J9, 4 free pins each (3.3 V, never 5 V):
            J<n>_5, J<n>_11, J<n>_12, J<n>_15  = connector J<n>, pin 5 / 11 / 12 / 15
  D36..D39  the 4 small FPGA LEDs (HIGH = on; LED_BUILTIN = LED0)
  D40       test point TP1
  D41..D44  board version straps (read only)
  D45..D48  I2C: SDA/SCL on J1..J8 (Wire), SDA1/SCL1 on J9 (Wire1); 1 kOhm pull-ups on the board
  D49..D54  fan speed inputs FAN1..FAN6 (read only)
  D55       fan PWM (all 6 fan headers)
  D60..D65  ARM side: green and red status LEDs, LED D2, buzzer, IP button, Reset button
*/
#ifndef PINS_ARDZY_H
#define PINS_ARDZY_H
#if defined(ARDZY_BOARD_EBAZ4205)
/*
  EBAZ4205 (the pin-control design puts its pins in the same places as the S9's):
  D0..D13   header DATA1, pins 5 6 7 8 9 11 13 14 15 16 17 18 19 20  (DATA1_5 .. DATA1_20)
  D14..D27  header DATA2, the same pins                               (DATA2_5 .. DATA2_20)
  D28..D40  header DATA3, pins 5 .. 19; D45 = DATA3 pin 20              (DATA3_5 .. DATA3_20)
  D46       J5 fan PWM output        D49, D50  fan speed J3, J5 (read only)   D55  fan PWM J3
  D60, D61  green and red LED (LED_BUILTIN = green)   D64, D65  buttons S2, S3 (LOW while pressed)
  3.3 V pins with no protection. No buzzer on this board (tone() on BUZZER does nothing).
*/
#define DATA1_5 0
#define DATA1_6 1
#define DATA1_7 2
#define DATA1_8 3
#define DATA1_9 4
#define DATA1_11 5
#define DATA1_13 6
#define DATA1_14 7
#define DATA1_15 8
#define DATA1_16 9
#define DATA1_17 10
#define DATA1_18 11
#define DATA1_19 12
#define DATA1_20 13
#define DATA2_5 14
#define DATA2_6 15
#define DATA2_7 16
#define DATA2_8 17
#define DATA2_9 18
#define DATA2_11 19
#define DATA2_13 20
#define DATA2_14 21
#define DATA2_15 22
#define DATA2_16 23
#define DATA2_17 24
#define DATA2_18 25
#define DATA2_19 26
#define DATA2_20 27
#define DATA3_5 28
#define DATA3_6 29
#define DATA3_7 30
#define DATA3_8 31
#define DATA3_9 32
#define DATA3_11 33
#define DATA3_13 34
#define DATA3_14 35
#define DATA3_15 36
#define DATA3_16 37
#define DATA3_17 38
#define DATA3_18 39
#define DATA3_19 40
#define DATA3_20 45
#define J5_PWM      46
#define FAN1_TACH   49
#define FAN2_TACH   50
#define FAN_PWM     55
#define LED_GREEN    60
#define LED_RED      61
#define LED_BUILTIN  LED_GREEN
#define BUZZER       63
#define BUTTON_S2    64      // reads LOW while pressed
#define BUTTON_S3    65
#define BUTTON_IP    BUTTON_S2
#define BUTTON_RESET BUTTON_S3
#define NUM_DIGITAL_PINS 66
#define NUM_ANALOG_INPUTS 7
// SPI (DATA1): chip select 5, MOSI 6, MISO 7, clock 8
#define SS    DATA1_5
#define MOSI  DATA1_6
#define MISO  DATA1_7
#define SCK   DATA1_8
// Serial1 (DATA1): TX pin 9, RX pin 11 (any other pins: Serial1.setPins(rx, tx))
#define PIN_SERIAL1_TX DATA1_9
#define PIN_SERIAL1_RX DATA1_11
// I2C (Wire): DATA2 pins 5 (SCL) and 6 (SDA); add your own pull-ups (4.7 kOhm to 3.3 V)
#define SCL   DATA2_5
#define SDA   DATA2_6
#define SCL1  DATA2_7
#define SDA1  DATA2_8
// The S9's names work too (the same places, so a sketch or a Blocks program made for the S9 compiles here):
// J1_5 .. J9_15 = places 0..35 = DATA1_5 .. DATA3_14 in the order above; LED0..LED3 = the green / red LED
#define J1_5 0
#define J1_11 1
#define J1_12 2
#define J1_15 3
#define J2_5 4
#define J2_11 5
#define J2_12 6
#define J2_15 7
#define J3_5 8
#define J3_11 9
#define J3_12 10
#define J3_15 11
#define J4_5 12
#define J4_11 13
#define J4_12 14
#define J4_15 15
#define J5_5 16
#define J5_11 17
#define J5_12 18
#define J5_15 19
#define J6_5 20
#define J6_11 21
#define J6_12 22
#define J6_15 23
#define J7_5 24
#define J7_11 25
#define J7_12 26
#define J7_15 27
#define J8_5 28
#define J8_11 29
#define J8_12 30
#define J8_15 31
#define J9_5 32
#define J9_11 33
#define J9_12 34
#define J9_15 35
#define LED0 LED_GREEN
#define LED1 LED_RED
#define LED2 LED_GREEN
#define LED3 LED_RED
#else

#define J1_5   0
#define J1_11  1
#define J1_12  2
#define J1_15  3
#define J2_5   4
#define J2_11  5
#define J2_12  6
#define J2_15  7
#define J3_5   8
#define J3_11  9
#define J3_12  10
#define J3_15  11
#define J4_5   12
#define J4_11  13
#define J4_12  14
#define J4_15  15
#define J5_5   16
#define J5_11  17
#define J5_12  18
#define J5_15  19
#define J6_5   20
#define J6_11  21
#define J6_12  22
#define J6_15  23
#define J7_5   24
#define J7_11  25
#define J7_12  26
#define J7_15  27
#define J8_5   28
#define J8_11  29
#define J8_12  30
#define J8_15  31
#define J9_5   32
#define J9_11  33
#define J9_12  34
#define J9_15  35

#define LED0        36
#define LED1        37
#define LED2        38
#define LED3        39
#define LED_BUILTIN LED0
#define TP1         40
#define BOARD_ID0   41
#define BOARD_ID1   42
#define BOARD_ID2   43
#define BOARD_ID3   44
#define SCL         45
#define SDA         46
#define SCL1        47
#define SDA1        48
#define FAN1_TACH   49
#define FAN2_TACH   50
#define FAN3_TACH   51
#define FAN4_TACH   52
#define FAN5_TACH   53
#define FAN6_TACH   54
#define FAN_PWM     55

#define LED_GREEN    60
#define LED_RED      61
#define LED_D2       62
#define BUZZER       63
#define BUTTON_IP    64      // reads LOW while pressed
#define BUTTON_RESET 65      // reads LOW while pressed

#define NUM_DIGITAL_PINS 66
#define NUM_ANALOG_INPUTS 7

// SPI (J2): chip select pin 5, MOSI pin 11, MISO pin 12, clock pin 15
#define SS    J2_5
#define MOSI  J2_11
#define MISO  J2_12
#define SCK   J2_15

// Serial1 (J1): TX pin 11, RX pin 12 (any other pins: Serial1.setPins(rx, tx))
#define PIN_SERIAL1_TX J1_11
#define PIN_SERIAL1_RX J1_12

#endif  // the board
// "Analog" inputs: the chip's own XADC sensors (there are no analog pins on the connectors)
#define A0 100   // chip temperature
#define A1 101   // VCCINT  (FPGA core, 1.0 V)
#define A2 102   // VCCAUX  (1.8 V)
#define A3 103   // VCCBRAM (1.0 V)
#define A4 104   // VCCPINT (ARM core, 1.0 V)
#define A5 105   // VCCPAUX (1.8 V)
#define A6 106   // VCC_DDR (1.5 V)

#define digitalPinToInterrupt(p) (p)
#define digitalPinHasPWM(p) ((p) < 41 || (p) == FAN_PWM)
#define analogInputToDigitalPin(p) (-1)

// ---- "fast pin" API of the classic cores, used by many libraries (Adafruit and others).
// Port 0 = connector pins D0..D31, port 1 = D32..D48. The output register reads back the
// pins, so  *port |= mask  and  *port &= ~mask  work. Other pins have no port.
#include <stdint.h>
#define NOT_A_PIN 0
#define NOT_A_PORT 255
#ifdef __cplusplus
extern "C" {
#endif
volatile uint32_t *ardzy_port_out(uint8_t port);
volatile uint32_t *ardzy_port_mode(uint8_t port);
#ifdef __cplusplus
}
#endif
#define digitalPinToPort(p) ((p) < 32 ? 0 : (p) < 49 ? 1 : NOT_A_PORT)
#define digitalPinToBitMask(p) ((p) < 32 ? (1UL << (p)) : (p) < 49 ? (1UL << ((p) - 32)) : 0UL)
#define portOutputRegister(port) (ardzy_port_out(port))
#define portInputRegister(port) (ardzy_port_out(port))
#define portModeRegister(port) (ardzy_port_mode(port))
#define digitalPinToTimer(p) (0)
#define NOT_ON_TIMER 0

// ---- timing macros of the classic cores (F_CPU = the ARM clock)
#ifndef F_CPU
#define F_CPU 666666666UL
#endif
#define clockCyclesPerMicrosecond() (F_CPU / 1000000L)
#define clockCyclesToMicroseconds(a) ((a) / clockCyclesPerMicrosecond())
#define microsecondsToClockCycles(a) ((a) * clockCyclesPerMicrosecond())

#endif
