/*
  UsbUartAdapter: talk to your sketch from the PC through a USB-UART adapter (CP2102, CH340, FT232 ...).

  What it does:
    The adapter is a second serial port between the PC and your sketch (not the board's console).
    The sketch greets you and answers simple commands you type in a terminal program on the PC:
      help      the list of commands
      led on    LED0 on      led off   LED0 off
      temp      the chip temperature
      count     how many lines it got

  You need:
    a 3.3 V USB-UART adapter and 3 wires. A terminal program on the PC: PuTTY (Serial, COM port,
    115200), the Arduino IDE Serial Monitor, or the Ardzy app's "USB serial" tab.

  Wiring (3.3 V levels: if the adapter has a 5V / 3V3 jumper, set it to 3V3):
    adapter TX   --->  J1 pin 12 (Ardzy RX)
    adapter RX   <---  J1 pin 11 (Ardzy TX)
    adapter GND  ----  J1 pin 9 (GND)
    adapter 5V / 3V3 pin: not connected (the board has its own power)

    Connector pins (the same on J1..J9): I/O 5, 11, 12, 15; I2C 3 = SDA, 4 = SCL; 3.3 V out 16;
    GND 1, 2, 9, 10, 13, 14. Where each pin is: the app's Map view, or Examples, How to connect.

  Note: this uses the FPGA pins of J1, not the console header J12. An adapter on J12 is the
  board's Linux console (and the Ardzy app's cable link); on J1 it talks to your sketch.

  Try:
    Open the COM port at 115200 in PuTTY, press Enter, type "help".
*/

String line;
int lines = 0;

void reply(const String &s) {
  Serial1.print(s);
  Serial1.print("\r\n");
  Serial.println("answered: " + s);            // (also in the Ardzy Monitor)
}

void command(String c) {
  c.trim();
  c.toLowerCase();
  lines++;
  if (c == "help" || c == "") reply("commands: help, led on, led off, temp, count");
  else if (c == "led on") { digitalWrite(LED0, HIGH); reply("LED0 is on"); }
  else if (c == "led off") { digitalWrite(LED0, LOW); reply("LED0 is off"); }
  else if (c == "temp") reply("chip temperature: " + String(Ardzy.temperature(), 1) + " C");
  else if (c == "count") reply("lines so far: " + String(lines));
  else reply("I do not know \"" + c + "\": type help");
}

void setup() {
  Serial.begin(115200);
  pinMode(LED0, OUTPUT);
  Serial1.begin(115200);
  Serial1.print("\r\nHello from Ardzy! Type help and press Enter.\r\n> ");
  Serial.println("waiting for the USB-UART adapter on J1 pins 11 / 12 (115200 baud)");
}

void loop() {
  while (Serial1.available()) {
    char ch = Serial1.read();
    if (ch == '\r' || ch == '\n') {
      if (line.length() || ch == '\r') { Serial1.print("\r\n"); command(line); Serial1.print("> "); }
      line = "";
    } else if (ch == 8 || ch == 127) {          // backspace
      if (line.length()) { line.remove(line.length() - 1); Serial1.print("\b \b"); }
    } else if (line.length() < 80) {
      line += ch;
      Serial1.write(ch);                         // echo, so you see what you type
    }
  }
}
