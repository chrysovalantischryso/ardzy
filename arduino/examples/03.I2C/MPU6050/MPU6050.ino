/*
  MPU6050: a motion sensor (accelerometer + gyroscope) on I2C. No library needed.

  What it does:
    Reads the acceleration (in g) and the turn rate (in degrees per second) 20 times a second and puts
    them on the Plotter. Tilt the sensor and watch ax / ay / az change; turn it and gx / gy / gz move.
    Also prints the tilt angles (roll and pitch) worked out from gravity.

  You need:
    an MPU6050 module (GY-521) and 4 wires.

  Wiring (every connector J1..J8 has the same I2C bus on pins 3 and 4; the board has pull-up resistors):
    MPU6050 VCC  ----  J1 pin 16 (3.3 V out)
    MPU6050 GND  ----  J1 pin 1 (GND)
    MPU6050 SDA  ----  J1 pin 3 (SDA)
    MPU6050 SCL  ----  J1 pin 4 (SCL)
    AD0 open or to GND: address 0x68 (AD0 to 3.3 V: 0x69)

    Connector pins (the same on J1..J9): I/O 5, 11, 12, 15; I2C 3 = SDA, 4 = SCL; 3.3 V out 16;
    GND 1, 2, 9, 10, 13, 14. Where each pin is: the app's Map view, or Examples, How to connect.

  Try:
    Open the Plotter. Lay the sensor flat: az is about 1 g (gravity), ax and ay about 0.
*/
#include <Wire.h>

const int MPU = 0x68;

void writeReg(int reg, int value) {
  Wire.beginTransmission(MPU);
  Wire.write(reg);
  Wire.write(value);
  Wire.endTransmission();
}

int16_t word16() {                         // two bytes, high byte first, signed
  int16_t hi = Wire.read(), lo = Wire.read();
  return (int16_t)((hi << 8) | (lo & 0xFF));
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  Wire.beginTransmission(MPU);
  if (Wire.endTransmission() != 0) {
    Serial.println("No MPU6050 at 0x68: check the 4 wires (SDA = J1 pin 3, SCL = J1 pin 4), or run the I2CScanner example.");
    while (true) delay(1000);
  }
  writeReg(0x6B, 0x00);                     // wake up (it starts asleep)
  writeReg(0x1C, 0x00);                     // accelerometer +-2 g
  writeReg(0x1B, 0x00);                     // gyroscope +-250 degrees/s
  Serial.println("MPU6050 found. Open the Plotter.");
}

void loop() {
  Wire.beginTransmission(MPU);
  Wire.write(0x3B);                         // first data register: ACCEL_XOUT_H
  Wire.endTransmission(false);
  if (Wire.requestFrom((uint8_t)MPU, (size_t)14) != 14) { Serial.println("read failed"); delay(500); return; }
  float ax = word16() / 16384.0, ay = word16() / 16384.0, az = word16() / 16384.0;
  float temp = word16() / 340.0 + 36.53;
  float gx = word16() / 131.0, gy = word16() / 131.0, gz = word16() / 131.0;
  float roll = atan2(ay, az) * 180 / PI;
  float pitch = atan2(-ax, sqrt(ay * ay + az * az)) * 180 / PI;

  Serial.print("ax:"); Serial.print(ax, 3); Serial.print(" ay:"); Serial.print(ay, 3); Serial.print(" az:"); Serial.print(az, 3);
  Serial.print(" gx:"); Serial.print(gx, 1); Serial.print(" gy:"); Serial.print(gy, 1); Serial.print(" gz:"); Serial.println(gz, 1);
  Ardzy.watch("roll_deg", roll);
  Ardzy.watch("pitch_deg", pitch);
  Ardzy.watch("sensor_temp_C", temp);
  delay(50);
}
