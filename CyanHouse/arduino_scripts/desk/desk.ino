#include <IRremote.hpp>
#include "../libraries/CyanDevice/CyanDevice.h"

const int IP_LAST_OCTET = 253;
const int IR_PIN = 17;

WebServer server(80);
CyanDevice device(WIFI_SSID, WIFI_PASSWORD, IP_LAST_OCTET);

struct IRCommand { const char* name; uint8_t code; };
static const IRCommand IR_COMMANDS[] = {
  { "on",                 0x40 },
  { "off",                0x41 },
  { "intensity+",         0x04 },
  { "intensity-",         0x05 },
  { "col_loop",           0x0B },
  { "col_loop_intensity", 0x0D },
  { "cyan",               0x11 },
  { "violet",             0x1A },
  { "lilac",              0x1B },
  { "orange",             0x1B },
  { "aqua",               0x1D },
  { "blue",               0x1E },
  { "white",              0x1F },
};

void sendStrip(const String& c) {
  for (const auto& cmd : IR_COMMANDS) {
    if (c.equals(cmd.name)) { IrSender.sendNEC(0x0, cmd.code, 2); return; }
  }
  Serial.println(F("bad command"));
}

// ---- required interface ----

void deviceSetup() {
  IrSender.begin(IR_PIN);
  IrSender.enableIROut(38);
}

void deviceLoop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    if (command.startsWith("strip")) sendStrip(command.substring(5));
  }
}

void registerRoutes() {
  server.on("/strip", []() {
    if (!server.hasArg("cmd")) {
      server.send(400, F("text/plain"), F("missing cmd param"));
      return;
    }
    const String cmd = server.arg("cmd");
    sendStrip(cmd);
    server.send(200, F("text/plain"), "OK: " + cmd);
  });
}

// ----------------------------

void setup() { device.begin(); }
void loop()  { device.loop();  }