#include <string.h>
#include <Arduino.h>
#include "PinDefinitionsAndMore.h" // Define macros for input and output pin etc.
#include <IRremote.hpp>

#define LIGHT_PIN 2
#define MOTOR_PIN 3
#define MIC_PIN A0
String command;
int DELAY = 100;
char deviceCode = '_';
bool lights_on = false;

void setup() {
  Serial.begin(9600);
  IrSender.begin(); // Start with IR_SEND_PIN as send pin and enable feedback LED at default feedback LED pin
  IrSender.enableIROut(38); // Call it with 38 kHz to initialize the values printed below
  pinMode(LIGHT_PIN, OUTPUT);
  pinMode(MOTOR_PIN, OUTPUT);
  Serial.println("loop_init");
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

void sendSamsung(String c){
  Serial.println("TV command: " + c);
 for (int i = 0; i < 6; i++) {
    IrSender.sendSAMSUNG(comTv(c), 32);
    delay(40);
  }
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

void turn_motor(){
  digitalWrite(MOTOR_PIN, HIGH); 
  delay(1000);
  digitalWrite(MOTOR_PIN, LOW);
}

void change_lights(){
  if (lights_on){
    turn_off_lights();
  }
  else{
    turn_on_lights();
  }
}

int iteration = 0;
int claps = 0;
int threshold = 600;
int t_claps = 2;
int min_iter = 20;
int max_iter = 300;
void loop() {
  /*
  int value_mic = analogRead(MIC_PIN);
  if (claps > 0) iteration += 1;
  if (value_mic < threshold && claps == 0) { claps += 1; }
  if (iteration > min_iter) {
    if (value_mic < threshold && claps < t_claps) { claps += 1; }
    if (claps == t_claps){
      change_lights();
      claps = 0;
      iteration = 0;
      delay(1000);
    } 
  }
  if (iteration > max_iter) {
    claps = 0;
    iteration = 0;
  }
  */

    //digitalWrite(MOTOR_PIN, HIGH); 
    //delay(5000);
    
  if (Serial.available()) {
    command = Serial.readStringUntil('\n');
    command.trim();
    
    if (command.equals("LIGHTSON")) { turn_on_lights(); }
    else if (command.equals("LIGHTSOFF")) { turn_off_lights(); }
    else if (command.equals("H")) { turn_motor(); }
    else if (command.substring(0, 2) == "TV") sendSamsung(command.substring(2, command.length()));
    else if (command.substring(0, 5) == "AUDIO") sendAudio(command.substring(5, command.length()));
    else { Serial.println("bad command"); }
  }
}
