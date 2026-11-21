/*
  UartLoopback: the first UART test. One wire, no other parts.

  What it does:
    Serial1 (the board's hardware UART in the FPGA) sends a line, the wire brings it straight back,
    and the sketch checks that every byte came back right. Then it tries faster and faster speeds,
    so you also learn how fast the UART can go.

  You need:
    1 jumper wire (female-female for the 2.54 mm pins of the connector).

  Wiring:
    J1 pin 11 (TX)  --->  J1 pin 12 (RX)        one wire between the two pins

    Connector pins (the same on J1..J9): I/O 5, 11, 12, 15; I2C 3 = SDA, 4 = SCL; 3.3 V out 16;
    GND 1, 2, 9, 10, 13, 14. Where each pin is: the app's Map view, or Examples, How to connect.

  Try:
    Upload and open the Monitor. Every line should say OK. Pull the wire out: the next line says
    "nothing came back". Put it back: OK again.
*/

const long SPEEDS[] = {9600, 115200, 460800, 1000000};

bool testAt(long baud) {
  Serial1.begin(baud);
  while (Serial1.available()) Serial1.read();       // old bytes out
  const char *msg = "Hello UART 0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  int n = strlen(msg);
  Serial1.print(msg);
  Serial1.flush();
  int got = 0, wrong = 0;
  unsigned long t0 = millis();
  while (got < n && millis() - t0 < 500) {
    if (Serial1.available()) {
      if (Serial1.read() != msg[got]) wrong++;
      got++;
    }
  }
  Serial.print(baud);
  Serial.print(" baud: ");
  if (got == 0) Serial.println("nothing came back (is the wire on J1 pin 11 and pin 12?)");
  else if (got < n || wrong) { Serial.print(got); Serial.print(" of "); Serial.print(n); Serial.print(" bytes, "); Serial.print(wrong); Serial.println(" wrong"); }
  else Serial.println("OK, every byte came back");
  Serial1.end();
  return got == n && !wrong;
}

void setup() {
  Serial.begin(115200);
  Serial.println("UART loopback: J1 pin 11 (TX) wired to J1 pin 12 (RX)");
}

void loop() {
  int ok = 0;
  for (long b : SPEEDS) ok += testAt(b);
  Ardzy.watch("loopback_ok", ok);
  Serial.println();
  delay(3000);
}
