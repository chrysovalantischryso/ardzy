/*
  ESP32Link: Ardzy and an ESP32 (or ESP8266, Raspberry Pi Pico) talk over UART.

  What it does:
    Ardzy sends its chip temperature every second as "temp:47.5"; the ESP32 can show it, put it on
    Wi-Fi, send it to your phone ... The ESP32 sends back any line; Ardzy prints it in the Monitor.
    A simple way to give Ardzy Wi-Fi or Bluetooth.

  You need:
    an ESP32 board (3.3 V logic: no resistors needed) and 3 wires.

  Wiring (both boards are 3.3 V: connect directly):
    ESP32 RX2 (GPIO16)  <---  J1 pin 11 (Ardzy TX)
    ESP32 TX2 (GPIO17)  --->  J1 pin 12 (Ardzy RX)
    ESP32 GND           ----  J1 pin 9 (GND)
    No wire between the 3V3 / 5V pins: each board keeps its own power (USB for the ESP32).

  The ESP32's sketch (Arduino IDE, board "ESP32 Dev Module"):

    void setup() {
      Serial.begin(115200);                        // the ESP32's USB, to see what happens
      Serial2.begin(115200, SERIAL_8N1, 16, 17);   // RX = 16, TX = 17: the wires to Ardzy
    }
    void loop() {
      while (Serial2.available()) Serial.write(Serial2.read());     // from Ardzy to the ESP32's USB
      static unsigned long t = 0;
      if (millis() - t > 2000) { t = millis(); Serial2.println("hello from the ESP32"); }
    }

  Try:
    The Ardzy Monitor shows "ESP32 says: hello from the ESP32" every 2 s; the ESP32's serial monitor
    shows the temperature lines.
*/

String line;
unsigned long lastSend = 0;

void setup() {
  Serial.begin(115200);
  Serial1.begin(115200);
  Serial.println("ESP32 link on J1 pins 11 (TX) / 12 (RX), 115200 baud");
}

void loop() {
  if (millis() - lastSend >= 1000) {
    lastSend = millis();
    Serial1.print("temp:");
    Serial1.println(Ardzy.temperature(), 1);
  }
  while (Serial1.available()) {
    char c = Serial1.read();
    if (c == '\n') {
      line.trim();
      if (line.length()) Serial.println("ESP32 says: " + line);
      line = "";
    } else if (c != '\r' && line.length() < 200) {
      line += c;
    }
  }
}
