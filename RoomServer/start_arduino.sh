#!/bin/bash

if [ "$1" == "--upload" ]; then
    cd ~/Documents/Python-Projects
    git pull
    bash -i -c "arduino-cli compile --upload --fqbn arduino:avr:uno ~/Documents/Python-Projects/RoomServer/arduino/arduino.ino --port /dev/ttyUSB0";
else
    sudo fuser -k 10001/tcp
    cd ~/Documents/Python-Projects
    git pull
    python ~/Documents/Python-Projects/RoomServer/main.py
fi
