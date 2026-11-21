/*
  BMP280: temperature and air pressure (and the height from it) on I2C. No library needed.

  What it does:
    Reads the sensor's calibration once, then every second the temperature (C) and pressure (hPa),
    corrected with the formulas of the Bosch datasheet, and a height estimate. Watch them on the Plotter.
    Works with a BME280 too (same addresses and registers for temperature and pressure).

  You need:
    a BMP280 (or BME280) module and 4 wires.

  Wiring (the I2C bus is on pins 3 and 4 of every connector J1..J8; pull-ups are on the board):
    BMP280 VCC  ----  J1 pin 16 (3.3 V out)
    BMP280 GND  ----  J1 pin 1 (GND)
    BMP280 SDA  ----  J1 pin 3 (SDA)
    BMP280 SCL  ----  J1 pin 4 (SCL)
    SDO to GND: address 0x76 (most modules); SDO to 3.3 V: 0x77. CSB to 3.3 V (I2C mode) if the module has it.

  Try:
    Breathe on the sensor: the temperature goes up. Lift it 1 m: the height goes up about 1 m
    (the pressure drops about 0.12 hPa).
*/
#include <Wire.h>

int addr = 0x76;
uint16_t T1, P1;
int16_t T2, T3, P2, P3, P4, P5, P6, P7, P8, P9;
const float SEA_LEVEL_HPA = 1013.25;        // put today's sea-level pressure of your weather report here

uint8_t read8(int reg) {
  Wire.beginTransmission(addr); Wire.write(reg); Wire.endTransmission(false);
  Wire.requestFrom((uint8_t)addr, (size_t)1);
  return Wire.read();
}
uint16_t read16le(int reg) { return read8(reg) | (read8(reg + 1) << 8); }

bool found(int a) { Wire.beginTransmission(a); return Wire.endTransmission() == 0; }

void setup() {
  Serial.begin(115200);
  Wire.begin();
  if (!found(0x76)) addr = 0x77;
  if (!found(addr)) {
    Serial.println("No BMP280 at 0x76 or 0x77: check the wires (SDA = J1 pin 3, SCL = J1 pin 4), or run I2CScanner.");
    while (true) delay(1000);
  }
  uint8_t id = read8(0xD0);
  Serial.print("Sensor at 0x"); Serial.print(addr, HEX);
  Serial.println(id == 0x58 ? ": BMP280" : id == 0x60 ? ": BME280" : ": unknown chip id (trying anyway)");
  T1 = read16le(0x88); T2 = read16le(0x8A); T3 = read16le(0x8C);
  P1 = read16le(0x8E); P2 = read16le(0x90); P3 = read16le(0x92); P4 = read16le(0x94); P5 = read16le(0x96);
  P6 = read16le(0x98); P7 = read16le(0x9A); P8 = read16le(0x9C); P9 = read16le(0x9E);
  Wire.beginTransmission(addr); Wire.write(0xF4); Wire.write(0x57); Wire.endTransmission();   // x2 temp, x16 pressure, normal mode
  Wire.beginTransmission(addr); Wire.write(0xF5); Wire.write(0x90); Wire.endTransmission();   // 500 ms standby, filter 16
}

void loop() {
  Wire.beginTransmission(addr); Wire.write(0xF7); Wire.endTransmission(false);
  Wire.requestFrom((uint8_t)addr, (size_t)6);
  uint8_t b[6];
  for (int i = 0; i < 6; i++) b[i] = Wire.read();          // (one by one, in order: pressure then temperature)
  int32_t adcP = ((int32_t)b[0] << 12) | ((int32_t)b[1] << 4) | (b[2] >> 4);
  int32_t adcT = ((int32_t)b[3] << 12) | ((int32_t)b[4] << 4) | (b[5] >> 4);

  // temperature (datasheet: compensate_T, double version)
  double v1 = (adcT / 16384.0 - T1 / 1024.0) * T2;
  double v2 = (adcT / 131072.0 - T1 / 8192.0) * (adcT / 131072.0 - T1 / 8192.0) * T3;
  double tFine = v1 + v2, celsius = tFine / 5120.0;
  // pressure (datasheet: compensate_P, double version)
  v1 = tFine / 2.0 - 64000.0;
  v2 = v1 * v1 * P6 / 32768.0 + v1 * P5 * 2.0;
  v2 = v2 / 4.0 + P4 * 65536.0;
  v1 = (P3 * v1 * v1 / 524288.0 + P2 * v1) / 524288.0;
  v1 = (1.0 + v1 / 32768.0) * P1;
  double pa = 0;
  if (v1 != 0) {
    pa = 1048576.0 - adcP;
    pa = (pa - v2 / 4096.0) * 6250.0 / v1;
    v1 = P9 * pa * pa / 2147483648.0;
    v2 = pa * P8 / 32768.0;
    pa += (v1 + v2 + P7) / 16.0;
  }
  double hpa = pa / 100.0;
  double meters = 44330.0 * (1.0 - pow(hpa / SEA_LEVEL_HPA, 0.1903));

  Serial.print(celsius, 2); Serial.print(" C   "); Serial.print(hpa, 2); Serial.print(" hPa   about ");
  Serial.print(meters, 1); Serial.println(" m above the sea");
  Ardzy.watch("temperature_C", celsius);
  Ardzy.watch("pressure_hPa", hpa);
  Ardzy.watch("height_m", meters);
  delay(1000);
}
