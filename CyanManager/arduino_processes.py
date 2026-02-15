import serial
import time
from utils import wait, pprint


ARDUINO_PORT = "COM6"


def initialize(signal):
    global serialPort
    serialPort = None
    while signal.is_alive():
        if serialPort is None:
            try:
                serialPort = serial.Serial(
                    port=ARDUINO_PORT, baudrate=9600, bytesize=8, timeout=1, stopbits=serial.STOPBITS_ONE
                )
            except Exception:
                print(f"Cannot open port {ARDUINO_PORT}")
                serialPort = None
        else:
            break
        time.sleep(1)

    loop_init = False
    print('Contacting Arduino..')
    while not loop_init and signal.is_alive():
        time.sleep(0.05)
        if serialPort.in_waiting > 0:
            serial_string = serialPort.readline().decode("Ascii")
            try:
                if "IR Receiver ready" in serial_string:
                    loop_init = True
            except Exception:
                pass

    print('Arduino found!')


def take_action(signal, verb):
    if verb == "2":
        signal.reg_functions.TURN_ON_MONITORS.run_shortcut()
    elif verb == "8":
        signal.reg_functions.SHUTDOWN_MONITORS.run_shortcut()
    elif verb == "6":
        signal.reg_functions.TV_OK.run_shortcut()
    elif verb == "UP":
        signal.reg_functions.VOLUME_UP.run_shortcut()
    elif verb == "DOWN":
        signal.reg_functions.VOLUME_DOWN.run_shortcut()
    elif verb == "LEFT":
        signal.reg_functions.LIGHTS_ON.run_shortcut()
    elif verb == "RIGHT":
        signal.reg_functions.LIGHTS_OFF.run_shortcut()
    elif verb == "OK":
        signal.reg_functions.PLAY_PAUSE.run_shortcut()


def react_to_commands(thread_manager):
    signal = thread_manager.signal
    initialize(signal)
    while signal.is_alive() and not thread_manager.to_kill:
        time.sleep(0.05)
        if serialPort.in_waiting > 0:
            try:
                serial_string = serialPort.readline().decode("utf8")
                if len(serial_string.split()) == 3 and "pressed" in serial_string.split()[2]:
                    take_action(signal, serial_string.split()[1])
            except:
                pass
    pprint(f"{thread_manager.name} thread down..")


def register_arduino_tasks(signal):
    signal.register_thread(name="Arduino", target=react_to_commands)
