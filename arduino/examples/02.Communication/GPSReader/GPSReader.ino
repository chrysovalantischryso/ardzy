/*
  GPSReader: position, time and satellites from a GPS module (NEO-6M, NEO-8M, BN-220, ...).

  What it does:
    A GPS module sends NMEA lines over UART once a second ($GPRMC, $GPGGA ...). The sketch checks each
    line's checksum, reads the time, latitude, longitude, speed, the number of satellites and the height,
    prints them in the Monitor and shows them in the Watch tab. No library needed.

  You need:
    a GPS module with UART (most are 9600 baud) and 4 wires. Outdoors or at a window: the first fix
    can take a few minutes.

  Wiring:
    GPS VCC  ----  J1 pin 16 (3.3 V out)     (check the module: most work on 3.3 V; a module that needs
                                               5 V gets its power elsewhere, but its TX must stay 3.3 V)
    GPS GND  ----  J1 pin 9 (GND)
    GPS TX   --->  J1 pin 12 (Ardzy RX)
    GPS RX   <---  J1 pin 11 (Ardzy TX)       (not needed to read; only to change the module's settings)

  Try:
    The Monitor shows "waiting for a fix" lines with the number of satellites; when the module has a fix
    (its LED blinks on most modules) you get the position and a Google Maps link.
*/

String line;
unsigned long lastPrint = 0;
bool fix = false;
double lat = 0, lon = 0, knots = 0, height = 0;
int sats = 0;
String utc = "--:--:--";

// the field number `n` (0 = the sentence name) of a comma-separated NMEA line
String field(const String &s, int n) {
  int start = 0;
  for (int i = 0; i < n; i++) {
    start = s.indexOf(',', start) + 1;
    if (start == 0) return "";
  }
  int end = s.indexOf(',', start);
  int star = s.indexOf('*', start);
  if (end < 0 || (star >= 0 && star < end)) end = star;
  return end < 0 ? s.substring(start) : s.substring(start, end);
}

// "4807.038" + "N"  ->  48.1173 (degrees; south and west are negative)
double nmeaDegrees(const String &v, const String &hemi) {
  if (v.length() < 4) return 0;
  double x = v.toDouble();
  int d = (int)(x / 100);
  double result = d + (x - d * 100) / 60.0;
  return (hemi == "S" || hemi == "W") ? -result : result;
}

// a line is good when its checksum (XOR of the bytes between $ and *) matches the two hex digits after *
bool checksumOk(const String &s) {
  int star = s.indexOf('*');
  if (s.charAt(0) != '$' || star < 0 || star + 3 > (int)s.length()) return false;
  uint8_t x = 0;
  for (int i = 1; i < star; i++) x ^= (uint8_t)s.charAt(i);
  return x == (uint8_t)strtol(s.substring(star + 1, star + 3).c_str(), nullptr, 16);
}

void handle(const String &s) {
  if (!checksumOk(s)) return;
  String type = field(s, 0).substring(3);         // GPRMC, GNRMC ... -> RMC
  if (type == "RMC") {
    String t = field(s, 1);
    if (t.length() >= 6) utc = t.substring(0, 2) + ":" + t.substring(2, 4) + ":" + t.substring(4, 6);
    fix = field(s, 2) == "A";
    if (fix) {
      lat = nmeaDegrees(field(s, 3), field(s, 4));
      lon = nmeaDegrees(field(s, 5), field(s, 6));
      knots = field(s, 7).toDouble();
    }
  } else if (type == "GGA") {
    sats = field(s, 7).toInt();
    height = field(s, 9).toDouble();
  }
}

void setup() {
  Serial.begin(115200);
  Serial1.begin(9600);
  Serial.println("GPS on J1 pin 12 (RX), 9600 baud");
}

void loop() {
  while (Serial1.available()) {
    char c = Serial1.read();
    if (c == '\n') { line.trim(); handle(line); line = ""; }
    else if (c != '\r' && line.length() < 120) line += c;
  }
  if (millis() - lastPrint >= 2000) {
    lastPrint = millis();
    Ardzy.watch("satellites", sats);
    if (!fix) {
      Serial.println("UTC " + utc + "  waiting for a fix, " + String(sats) + " satellites");
      return;
    }
    Serial.println("UTC " + utc + "  " + String(lat, 6) + ", " + String(lon, 6) + "  " + String(knots * 1.852, 1) +
                   " km/h  " + String(height, 0) + " m  " + String(sats) + " satellites");
    Serial.println("  https://maps.google.com/?q=" + String(lat, 6) + "," + String(lon, 6));
    Ardzy.watch("latitude", lat);
    Ardzy.watch("longitude", lon);
    Ardzy.watch("speed_kmh", knots * 1.852);
  }
}
