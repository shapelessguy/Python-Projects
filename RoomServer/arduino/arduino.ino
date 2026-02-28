#include <string.h>
#include <Arduino.h>
#include "PinDefinitionsAndMore.h" // Define macros for input and output pin etc.
#include <IRremote.hpp>

#define LIGHT_PIN 2
// IR_PIN = 3 from PinDefinitions

// To compile on Roomserver:
// arduino-cli compile --fqbn arduino:avr:uno --upload --port /dev/ttyUSB0 /home/claudio/Python-Projects/RoomServer/arduino

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

long comAudio(String c){
  if (c == "on/off") return 0x80;
  else if (c.substring(0, 4) == "vol+") return 0xAA;
  else if (c.substring(0, 4) == "vol-") return 0x6A;
  else if (c.equals("mute")) return 0xEA;
  else if (c.equals("level")) return 0xA;
  else if (c.equals("effect")) return 0xE;
  else if (c.equals("input")) return 0x8;
  return 0;
}

long comTop(String c){
  if (c.equals("w")) return 0x02;
  else if (c.equals("rgb")) return 0x03;
  else if (c.equals("bright+")) return 0x09;
  else if (c.equals("bright-")) return 0x11;
  else if (c.equals("cold+")) return 0xE;
  else if (c.equals("cold-")) return 0xC;
  else if (c.equals("col_loop")) return 0xB;
  else if (c.equals("col_change")) return 0x7;
  else if (c.equals("heart")) return 0x14;
  return 0;
}

int repeatAudio(String c){
  if (c.substring(0, 3) == "vol") {
    String repeat = c.substring(4, c.length());
    int_fast8_t repeat_int = repeat.toInt();
    return repeat_int;
  }
  return 0;
}

void sendPlantLights(String c) {
  Serial.println("Sending Plant lights...");
  if (c.equals("on")) turn_on_lights();
  else if (c.equals("off")) turn_off_lights();
}

void sendHisense(String c) {
  Serial.println("Sending Hisense...");
  uint16_t address = 0xBF00;
  uint8_t  command;
  int      repetitions = 1;

  if (c.substring(0, 2) == "ok"){
    command = 0x15;
    repetitions = 1;
  }
  else if (c.substring(0, 5) == "power"){
    command = 0x0D;
    repetitions = 6;
  }

  for (int i = 0; i < repetitions; i++) {
    IrSender.sendNEC(address, command, 0);
    delay(40);
  }
}

void sendAudio(String c){
  Serial.println("Audio command: " + c);
  if (c.substring(0, 6) == "setvol"){
    IrSender.sendNEC(0xA002, comAudio("vol-"), 43);
    IrSender.sendNEC(0xA002, comAudio("vol+"), c.substring(6, c.length()).toInt());
  }
  else if (c.substring(0, 7) == "pingvol"){
    IrSender.sendNEC(0xA002, comAudio("vol-"), 1);
    IrSender.sendNEC(0xA002, comAudio("vol+"), 1);
  }
  else{
    IrSender.sendNEC(0xA002, comAudio(c), repeatAudio(c));
  }
}

void sendTop(String c){
  Serial.println("Top command: " + c);
  IrSender.sendNEC(0xEF00, comTop(c), 2);
}

void loop() {
  if (Serial.available()) {
    command = Serial.readStringUntil('\n');
    command.trim();

    if (command.substring(0, 6) == "lights") { sendPlantLights(command.substring(6, command.length())); }
    else if (command.substring(0, 3) == "top") sendTop(command.substring(3, command.length()));
    else if (command.substring(0, 2) == "tv") sendHisense(command.substring(2, command.length()));
    else if (command.substring(0, 5) == "audio") sendAudio(command.substring(5, command.length()));

    else { Serial.println("bad command"); }
  }
}
