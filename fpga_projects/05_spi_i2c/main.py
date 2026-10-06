# 05 SPI and I2C demo: scans the I2C bus and reads what it knows (BME280 / BMP280 id, DS3231 time,
# SSD1306 present), and reads the JEDEC id of an SPI flash chip on J2 (W25Qxx).
import time
from blocks import Bus, SPI, I2C, require

bus = Bus()
require(bus, 'SPIC')
i2c = I2C(bus, slot=2, hz=400000)
spi = SPI(bus, slot=1)
spi.setup(hz=10e6, mode=0, bits=8)

KNOWN = {0x3C: 'SSD1306 OLED display', 0x3D: 'SSD1306 OLED display', 0x68: 'DS3231 / DS1307 clock or MPU6050',
         0x76: 'BME280 / BMP280', 0x77: 'BME280 / BMP280 / BMP180', 0x27: 'PCF8574 LCD backpack',
         0x3F: 'PCF8574 LCD backpack', 0x48: 'ADS1115 / PCF8591 ADC', 0x50: 'AT24C EEPROM', 0x57: 'AT24C EEPROM'}
print('I2C bus scan (400 kHz):')
found = i2c.scan()
for a in found:
    print('  0x%02X  %s' % (a, KNOWN.get(a, '')))
if not found:
    print('  nothing found (connect a device to pin 3 SDA / pin 4 SCL of J1..J8)')
for a in (0x76, 0x77):
    if a in found:
        cid = i2c.read(a, 1, reg=0xD0)
        print('  0x%02X chip id 0x%02X (%s)' % (a, cid[0], {0x60: 'BME280', 0x58: 'BMP280', 0x55: 'BMP180'}.get(cid[0], '?')))
if 0x68 in found:
    t = i2c.read(0x68, 3, reg=0x00)
    if t:
        bcd = lambda b: (b >> 4) * 10 + (b & 15)
        print('  clock time %02d:%02d:%02d' % (bcd(t[2] & 0x3F), bcd(t[1]), bcd(t[0] & 0x7F)))

print('SPI flash JEDEC id on J2 (10 MHz):')
r = spi.transfer([0x9F, 0, 0, 0])
if r[1:] in ([0xFF] * 3, [0] * 3):
    print('  no SPI flash answered (MISO reads %02X)' % r[1])
else:
    print('  manufacturer 0x%02X, type 0x%02X, size 2^%d bytes' % (r[1], r[2], r[3]))
