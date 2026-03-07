#include <IRremote.hpp>

const int IR_RECEIVE_PIN      = 2;
const int GREEN_LED_PIN       = 4;
const int RED_LED_PIN         = 5;
const int BLUE_LED_PIN        = 6;
const int IR_PIN              = 7;
uint16_t currentAddress       = 0;
uint8_t  currentHeldCommand   = 0;
unsigned long lastActionTime  = 0;
const unsigned long REPEAT_INTERVAL = 50;


void setup() {
  Serial.begin(115200);
  Serial.println(F("IR Receiver ready - pin 2"));
  IrReceiver.begin(IR_RECEIVE_PIN, ENABLE_LED_FEEDBACK);

  IrSender.begin(IR_PIN);
  IrSender.enableIROut(38);

  pinMode(BLUE_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
}


void sendStrip(String c){
  Serial.println("Strip command: " + c);
  uint16_t address = 0x0;
  
  if (c.equals("on")) IrSender.sendNEC(address, 0x40, 2);
  else if (c.equals("off")) IrSender.sendNEC(address, 0x41, 2);
  else if (c.equals("intensity+")) IrSender.sendNEC(address, 0x04, 2);
  else if (c.equals("intensity-")) IrSender.sendNEC(address, 0x05, 2);
  else if (c.equals("col_loop")) IrSender.sendNEC(address, 0x0B, 2);
  else if (c.equals("col_loop_intensity")) IrSender.sendNEC(address, 0x0D, 2);
  else if (c.equals("cyan")) IrSender.sendNEC(address, 0x11, 2);
  else if (c.equals("violet")) IrSender.sendNEC(address, 0x1A, 2);
  else if (c.equals("lilac")) IrSender.sendNEC(address, 0x1B, 2);
  else if (c.equals("orange")) IrSender.sendNEC(address, 0x1B, 2);
  else if (c.equals("aqua")) IrSender.sendNEC(address, 0x1D, 2);
  else if (c.equals("blue")) IrSender.sendNEC(address, 0x1E, 2);
  else if (c.equals("white")) IrSender.sendNEC(address, 0x1F, 2);
  else { Serial.println("bad command"); }
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
      Serial.println("→ GREEN pressed");
      break;

    case 0xF4:
      Serial.println("→ RED pressed");
      break;

    case 0xB4:
      Serial.println("→ BLUE pressed");
      break;

    default:
      Serial.print("Unknown NEC command: 0x");
      Serial.println(IrReceiver.decodedIRData.command, HEX);
      break;
  }
}


void loop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();

    if (command.equals("BLUE_ON")) { digitalWrite(BLUE_LED_PIN, HIGH); }
    else if (command.equals("BLUE_OFF")) { digitalWrite(BLUE_LED_PIN, LOW); }
    else if (command.equals("RED_ON")) { digitalWrite(RED_LED_PIN, HIGH); }
    else if (command.equals("RED_OFF")) { digitalWrite(RED_LED_PIN, LOW); }
    else if (command.equals("GREEN_ON")) { digitalWrite(GREEN_LED_PIN, HIGH); }
    else if (command.equals("GREEN_OFF")) { digitalWrite(GREEN_LED_PIN, LOW); }
    else if (command.substring(0, 5) == "strip") { sendStrip(command.substring(5, command.length())); }
  }
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
        }
      }
    } 
    else {
      if (cmd != 0) {
        currentAddress      = addr;
        currentHeldCommand  = cmd;
        lastActionTime      = millis();
        executeAction(cmd);
      }
    }
    IrReceiver.resume();
  }
  if (currentHeldCommand != 0 && millis() - lastActionTime > 2000) {
    currentHeldCommand = 0;
    currentAddress = 0;
    // Serial.println("Held command timed out");
  }
}
