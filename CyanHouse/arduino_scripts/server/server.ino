#include <IRremote.hpp>
#include "../libraries/CyanDevice/CyanDevice.h"

const int IP_LAST_OCTET = 254;
const int IR_PIN = 17;

WebServer server(80);
CyanDevice device(WIFI_SSID, WIFI_PASSWORD, IP_LAST_OCTET);

#define COUNT_OF(a) (sizeof(a) / sizeof((a)[0]))

static const uint16_t ADDR_TV    = 0xBF00;
static const uint16_t ADDR_AUDIO = 0xA002;
static const uint16_t ADDR_TOP   = 0xEF00;
static const uint16_t ADDR_FAN   = 0x0000;

struct IRCommand { const char* name; uint8_t code; uint8_t repeats; };

struct IRDevice {
  const char*      name;
  uint16_t         address;
  const IRCommand* cmds;
  size_t           count;
  bool (*special)(const String&);   // multi-frame commands; nullptr if none
};

bool audioSpecial(const String& c);

static const IRCommand TV_COMMANDS[] = {
  { "ok",    0x15, 1 },
  { "power", 0x0D, 6 },
};

// "+" and "/" are unsafe in a query string, so each has a plain alias.
static const IRCommand AUDIO_COMMANDS[] = {
  { "onoff",   0x80, 2 }, { "on/off", 0x80, 2 },
  { "volup",   0xAA, 1 }, { "vol+",   0xAA, 1 },
  { "voldown", 0x6A, 1 }, { "vol-",   0x6A, 1 },
  { "mute",    0xEA, 2 },
  { "level",   0x0A, 2 },
  { "effect",  0x0E, 2 },
  { "input",   0x08, 2 },
};

static const IRCommand TOP_COMMANDS[] = {
  { "w",          0x02, 2 },
  { "rgb",        0x03, 1 },
  { "brightup",   0x09, 1 }, { "bright+", 0x09, 1 },
  { "brightdown", 0x11, 1 }, { "bright-", 0x11, 1 },
  { "coldup",     0x0E, 1 }, { "cold+",   0x0E, 1 },
  { "colddown",   0x0C, 1 }, { "cold-",   0x0C, 1 },
  { "col_loop",   0x0B, 1 },
  { "col_change", 0x07, 1 },
  { "heart",      0x14, 2 },
};

static const IRCommand FAN_COMMANDS[] = {
  { "on",    0x44, 2 },
  { "off",   0x46, 2 },
  { "mode",  0x15, 2 },
  { "timer", 0x16, 2 },
  { "swing", 0x08, 2 },
};

static const IRDevice IR_DEVICES[] = {
  { "tv",    ADDR_TV,    TV_COMMANDS,    COUNT_OF(TV_COMMANDS),    nullptr      },
  { "audio", ADDR_AUDIO, AUDIO_COMMANDS, COUNT_OF(AUDIO_COMMANDS), audioSpecial },
  { "top",   ADDR_TOP,   TOP_COMMANDS,   COUNT_OF(TOP_COMMANDS),   nullptr      },
  { "fan",   ADDR_FAN,   FAN_COMMANDS,   COUNT_OF(FAN_COMMANDS),   nullptr      },
};

bool audioSpecial(const String& c) {
  if (c.startsWith("setvol")) {
    const int level = c.substring(6).toInt();
    IrSender.sendNEC(ADDR_AUDIO, 0x6A, 43);                    // floor the volume
    if (level > 0) IrSender.sendNEC(ADDR_AUDIO, 0xAA, level);  // then climb to level
    return true;
  }
  if (c.equals("pingvol")) {
    IrSender.sendNEC(ADDR_AUDIO, 0x6A, 1);
    IrSender.sendNEC(ADDR_AUDIO, 0xAA, 1);
    return true;
  }
  return false;
}

bool sendIR(const IRDevice& dev, const String& c) {
  if (dev.special && dev.special(c)) {
    Serial.printf("%s <- %s\n", dev.name, c.c_str());
    return true;
  }
  for (size_t i = 0; i < dev.count; i++) {
    if (c.equals(dev.cmds[i].name)) {
      IrSender.sendNEC(dev.address, dev.cmds[i].code, dev.cmds[i].repeats);
      Serial.printf("%s <- %s (0x%02X)\n", dev.name, dev.cmds[i].name, dev.cmds[i].code);
      return true;
    }
  }
  Serial.printf("%s: bad command '%s'\n", dev.name, c.c_str());
  return false;
}

// ---- required interface ----

void deviceSetup() {
  IrSender.begin(IR_PIN);
  IrSender.enableIROut(38);
}

void deviceLoop() {
  if (!Serial.available()) return;

  String command = Serial.readStringUntil('\n');
  command.trim();
  if (command.length() == 0) return;

  for (const auto& d : IR_DEVICES) {
    if (command.startsWith(d.name)) {
      sendIR(d, command.substring(strlen(d.name)));
      return;
    }
  }
  Serial.println(F("bad command"));
}

void registerRoutes() {
  for (const auto& d : IR_DEVICES) {
    const IRDevice* dev = &d;
    server.on(String("/") + d.name, [dev]() {
      if (!server.hasArg("cmd")) {
        server.send(400, F("text/plain"), F("missing cmd param"));
        return;
      }
      const String cmd = server.arg("cmd");
      const bool ok = sendIR(*dev, cmd);
      server.send(ok ? 200 : 400, F("text/plain"), (ok ? "OK: " : "bad command: ") + cmd);
    });
  }
}

// ----------------------------

void setup() { device.begin(); }
void loop()  { device.loop();  }