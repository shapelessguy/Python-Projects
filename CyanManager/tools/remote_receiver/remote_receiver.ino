#include <IRremote.hpp>

const int IR_RECEIVE_PIN = 2;

void setup() {
  Serial.begin(9600);
  Serial.println(F("IR Receiver ready - pin 2"));
  IrReceiver.begin(IR_RECEIVE_PIN, ENABLE_LED_FEEDBACK);
}

unsigned long lastActionTime = 0;
uint8_t currentHeldCommand = 0xFF;
const unsigned long REPEAT_INTERVAL = 100;

void loop() {
  if (IrReceiver.decode()) {

    if (IrReceiver.decodedIRData.protocol == NEC) {

      uint8_t cmd = IrReceiver.decodedIRData.command;
      bool isRepeat = (IrReceiver.decodedIRData.flags & IRDATA_FLAGS_IS_REPEAT);

      unsigned long now = millis();

      if (!isRepeat) {
        currentHeldCommand = cmd;
        lastActionTime = now;
        executeAction(cmd);
      }
      else if (isRepeat && cmd == currentHeldCommand) {
        if (now - lastActionTime >= REPEAT_INTERVAL && shouldRepeat(cmd)) {
          lastActionTime = now;
          executeAction(cmd);
        }
      }
      else if (isRepeat) {
        currentHeldCommand = cmd;
        lastActionTime = now;
        executeAction(cmd);
      }
    }

    IrReceiver.resume();
  }

  if (currentHeldCommand != 0xFF && millis() - lastActionTime > 1500) {
    currentHeldCommand = 0xFF;
  }
}

const uint8_t REPEATING_COMMANDS[] = {0x18, 0x52};
const int NUM_REPEATING = sizeof(REPEATING_COMMANDS) / sizeof(REPEATING_COMMANDS[0]);
bool shouldRepeat(uint8_t cmd) {
  for (int i = 0; i < NUM_REPEATING; i++) {
    if (cmd == REPEATING_COMMANDS[i]) {
      return true;
    }
  }
  return false;
}

void executeAction(uint8_t cmd) {
  switch (cmd) {
          
    case 0x45:
      Serial.println("→ 1 pressed");
      break;
      
    case 0x46:
      Serial.println("→ 2 pressed");
      break;
      
    case 0x47:
      Serial.println("→ 3 pressed");
      break;

    case 0x44:
      Serial.println("→ 4 pressed");
      break;

    case 0x40:
      Serial.println("→ 5 pressed");
      break;

    case 0x43:
      Serial.println("→ 6 pressed");
      break;

    case 0x07:
      Serial.println("→ 7 pressed");
      break;

    case 0x15:
      Serial.println("→ 8 pressed");
      break;

    case 0x09:
      Serial.println("→ 9 pressed");
      break;

    case 0x19:
      Serial.println("→ 0 pressed");
      break;

    case 0x1C:
      Serial.println("→ OK pressed");
      break;

    case 0x08:
      Serial.println("→ LEFT pressed");
      break;
      
    case 0x5A:
      Serial.println("→ RIGHT pressed");
      break;

    case 0x18:
      Serial.println("→ UP pressed");
      break;

    case 0x52:
      Serial.println("→ DOWN pressed");
      break;
      
    case 0x16:
      Serial.println("→ * pressed");
      break;

    case 0xD:
      Serial.println("→ # pressed");
      break;

    default:
      Serial.print("Unknown NEC command: 0x");
      Serial.println(IrReceiver.decodedIRData.command, HEX);
      break;
  }
}