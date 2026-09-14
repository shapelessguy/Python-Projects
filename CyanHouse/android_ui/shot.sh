#!/bin/bash
ADB="C:/Users/shape/AppData/Local/Android/Sdk/platform-tools/adb.exe -s adb-R52Y708M99Z-1OXA2J._adb-tls-connect._tcp"
NAME=$1
MSYS_NO_PATHCONV=1 $ADB shell screencap -p /sdcard/$NAME.png
MSYS_NO_PATHCONV=1 $ADB pull /sdcard/$NAME.png ./$NAME.png
