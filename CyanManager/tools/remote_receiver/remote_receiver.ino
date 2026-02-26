#include <IRremote.hpp>

const int IR_RECEIVE_PIN      = 2;
uint16_t currentAddress       = 0;
uint8_t  currentHeldCommand   = 0;
unsigned long lastActionTime  = 0;
const unsigned long REPEAT_INTERVAL = 150;


void setup() {
  Serial.begin(115200);
  Serial.println(F("IR Receiver ready - pin 2"));
  IrReceiver.begin(IR_RECEIVE_PIN, ENABLE_LED_FEEDBACK);
}


bool shouldRepeat(uint8_t cmd) {
  if (cmd == 0x07 || cmd == 0x0B) return true;
  return false;
}


void executeAction(uint8_t cmd) {
  Serial.print("Pressed cmd_8: ");
  Serial.println(cmd, HEX);

  switch (cmd) {  

    case 0xE6:
      Serial.println("→ POWER pressed");
      break;

    case 0xD2:
      Serial.println("→ MONOFF pressed");
      break;

    case 0xCE:
      Serial.println("→ MONON pressed");
      break;

    case 0x60:
      Serial.println("→ DIR_UP pressed");
      break;

    case 0x62:
      Serial.println("→ DIR_RIGHT pressed");
      break;

    case 0x61:
      Serial.println("→ DIR_DOWN pressed");
      break;

    case 0x65:
      Serial.println("→ DIR_LEFT pressed");
      break;

    case 0x68:
      Serial.println("→ DIR_CENTER pressed");
      break;

    case 0x58:
      Serial.println("→ BACK pressed");
      break;

    case 0x79:
      Serial.println("→ HOME pressed");
      break;

    case 0xB9:
      Serial.println("→ PLAY pressed");
      break;

    case 0x07:
      Serial.println("→ + pressed");
      break;

    case 0x0B:
      Serial.println("→ - pressed");
      break;

    case 0x12:
      Serial.println("→ UP pressed");
      break;

    case 0x10:
      Serial.println("→ DOWN pressed");
      break;

    case 0xF3:
      Serial.println("→ Netflix pressed");
      break;

    case 0xF4:
      Serial.println("→ PrimeVideo pressed");
      break;

    case 0xB4:
      Serial.println("→ SamsungTv pressed");
      break;

    default:
      Serial.print("Unknown NEC command: 0x");
      Serial.println(IrReceiver.decodedIRData.command, HEX);
      break;
  }
}


void loop() {
  if (IrReceiver.decode()) {

    uint16_t addr = IrReceiver.decodedIRData.address;
    uint8_t  cmd  = IrReceiver.decodedIRData.command;
    bool isRepeatLike = (cmd == 0xFF) || (addr == 0 && cmd == 0);

    if (isRepeatLike) {
      if (currentHeldCommand != 0 && currentAddress != 0) {
        unsigned long now = millis();
        if (now - lastActionTime >= REPEAT_INTERVAL && shouldRepeat(currentHeldCommand)) {
          lastActionTime = now;
          executeAction(currentHeldCommand);
          // Serial.print(" → REPEATED action: ");
          // Serial.print(currentAddress, HEX);
          // Serial.print(", ");
          // Serial.println(currentHeldCommand, HEX);
        } else {
          // Serial.println(" → too soon or not repeatable");
        }
      } else {
        // Serial.println(" → ignored (no valid prior command)");
      }
    } 
    else {
      if (cmd != 0) {
        Serial.print(" → NEW/VALID");
        currentAddress      = addr;
        currentHeldCommand  = cmd;
        lastActionTime      = millis();
        executeAction(cmd);
        // Serial.print(" → executed: ");
        // Serial.print(currentAddress, HEX);
        // Serial.print(", ");
        // Serial.println(currentHeldCommand, HEX);
      } else {
        // Serial.println(" → ignored (cmd=0)");
      }
    }
    Serial.println();
    IrReceiver.resume();
  }
  if (currentHeldCommand != 0 && millis() - lastActionTime > 2000) {
    currentHeldCommand = 0;
    currentAddress = 0;
    // Serial.println("Held command timed out");
  }
}
