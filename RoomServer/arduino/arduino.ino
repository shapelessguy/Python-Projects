#include <string.h>
#include <Arduino.h>
#include "PinDefinitionsAndMore.h" // Define macros for input and output pin etc.
#include <IRremote.hpp>

#define LIGHT_PIN 2
// IR_PIN = 3 from PinDefinitions

String command;
int DELAY = 100;
char deviceCode = '_';
bool lights_on = false;


void setup() {
  Serial.begin(9600);
  IrSender.begin();
  IrSender.enableIROut(38);
  pinMode(LIGHT_PIN, OUTPUT);
  Serial.println("loop_init");
}

void turn_on_lights(){
  digitalWrite(LIGHT_PIN, HIGH); 
  Serial.println("lights_on");
  lights_on = true;
}

void turn_off_lights(){
  digitalWrite(LIGHT_PIN, LOW); 
  Serial.println("lights_off");
  lights_on = false;
}

void change_lights(){
  if (lights_on){
    turn_off_lights();
  }
  else{
    turn_on_lights();
  }
}



long comTv(String c){
  if (c == "ON") return 0xE0E09966;
  else if (c == "OFF") return 0xE0E019E6;
  else if (c == "PC") return 0xE0E09768;
  return 0;
}

long comAudio(String c){
  if (c == "ON/OFF") return 0x80;
  else if (c.substring(0, 4) == "VOL+") return 0xAA;
  else if (c.substring(0, 4) == "VOL-") return 0x6A;
  else if (c == "MUTE") return 0xEA;
  else if (c == "LEVEL") return 0xA;
  else if (c == "EFFECT") return 0xE;
  else if (c == "INPUT") return 0x8;
  return 0;
}

int repeatAudio(String c){
  if (c.substring(0, 3) == "VOL") {
    String repeat = c.substring(4, c.length());
    int_fast8_t repeat_int = repeat.toInt();
    return repeat_int;
  }
  return 0;
}

void sendHisense(String c) {
  Serial.println("Sending Hisense POWER TOGGLE (address 0xBF00, cmd 0x0D)...");
  uint16_t address = 0xBF00;
  uint8_t  command = 0x0D;

  for (int i = 0; i < 6; i++) {
    IrSender.sendNEC(address, command, 0);
    delay(40);
  }

  Serial.println("Toggle sent 6 times — check TV!");
}

void sendAudio(String c){
  Serial.println("Audio command: " + c);
  if (c.substring(0, 6) == "SETVOL"){
    IrSender.sendNEC(0xA002, comAudio("VOL-"), 43);
    IrSender.sendNEC(0xA002, comAudio("VOL+"), c.substring(6, c.length()).toInt());
  }
  else if (c.substring(0, 7) == "PINGVOL"){
    IrSender.sendNEC(0xA002, comAudio("VOL-"), 1);
    IrSender.sendNEC(0xA002, comAudio("VOL+"), 1);
  }
  else{
    IrSender.sendNEC(0xA002, comAudio(c), repeatAudio(c));
  }
}

void loop() {
  if (Serial.available()) {
    command = Serial.readStringUntil('\n');
    command.trim();
    
    if (command.equals("LIGHTSON")) { turn_on_lights(); }
    else if (command.equals("LIGHTSOFF")) { turn_off_lights(); }

    else if (command.substring(0, 2) == "TV") sendHisense(command.substring(2, command.length()));
    else if (command.substring(0, 5) == "AUDIO") sendAudio(command.substring(5, command.length()));

    else { Serial.println("bad command"); }
  }
}
