from datetime import datetime, timedelta
from utils import HOSTNAME
import announcements
import serial
import time
import sequences


serialPort: serial.Serial
lights = False
auto_time = None
initialized = False
active_times = [('9:00', '19:59')]
signal = None


# class Command:
#     class_name = ""
#     cmd_type = ""
#     types = []

#     def __init__(self, cmd_type):
#         assert cmd_type.lower() in [x.lower() for x in self.types]
#         self.cmd_type = cmd_type.lower()

#     def arduino_cmd(self):
#         cmd = (self.class_name + self.cmd_type).upper()
#         print(cmd)
#         return cmd
    
#     def send(self):
#         write(self.arduino_cmd())


# class LightCommand(Command):
#     class_name = "lights"
#     types = [
#         "on",
#         "off",
#         "auto"
#     ]


def initialize(signal_):
    global serialPort, initialized, lights, auto_time, signal
    signal = signal_
    serialPort = None
    lights = False
    auto_time = None
    initialized = False
    while not signal['kill']:
        if serialPort is None:
            try:
                serialPort = serial.Serial(
                    port=HOSTNAME['arduino_device'], baudrate=9600, bytesize=8, timeout=1, stopbits=serial.STOPBITS_ONE
                )
            except Exception:
                print(f"Cannot open port {HOSTNAME['arduino_device']}")
                serialPort = None
        else:
            break
        time.sleep(1)

    loop_init = False
    print('Contacting Arduino..')
    while not loop_init and not signal['kill']:
        time.sleep(0.05)
        if serialPort.in_waiting > 0:
            serial_string = serialPort.readline()
            # noinspection PyBroadException
            try:
                if serial_string.decode("Ascii") == "loop_init\r\n":
                    loop_init = True
                    initialized = False
            except Exception:
                pass

    print('Arduino found!')


# noinspection PyBroadException
def write(text, tries=0):
    if tries > 2:
        return
    if HOSTNAME['arduino_device'] is None:
        return
    global signal
    try:
        if serialPort is None:
            raise Exception()
        else:
            print(f'To Arduino: {text}')
            serialPort.write(f"{text}\r\n".encode("Ascii"))
    except Exception:
        print('Trying to initiate connection to COM..')
        time.sleep(1)
        initialize(signal)
        write(text, tries+1)


def lights_cb(data):
    command = data.get("command", None)
    if command in ["on", "off", "auto"]:
        write(data["endpoint"] + command)
        return {"msg": f'Lights [value={command}] sent to arduino.'}
    return {"error": f'Command {command} not recognized.'}


def tob_cb(data):
    command = data.get("command", None)
    if command in ["w", "rgb"]:
        write(data["endpoint"] + command)
        return {"msg": f'TopLights [value={command}] sent to arduino.'}
    return {"error": f'Command {command} not recognized.'}


def tv_cb(data):
    command = data.get("command", None)
    if command in ["power", "ok"]:
        write(data["endpoint"] + command)
        return {"msg": f'TV [value={command}] sent to arduino.'}
    return {"error": f'Command {command} not recognized.'}


def audio_cb(data):
    command = data.get("command", None)
    if command in ["on/off"]:
        write(data["endpoint"] + command)
        return {"msg": f'AudioSystem [value={command}] sent to arduino.'}
    return {"error": f'Command {command} not recognized.'}


def announce_cb(data):
    command = data.get("command", None)
    if command == "announce":
        last_announcement, id_last_announcement = announcements.get_last_announcement()
        last_announcement, id_last_announcement = announcements.update(last_announcement, id_last_announcement, forced=True)
        return {"msg": 'Announcements now.'}
    return {"error": f'Command {command} not recognized.'}


endpoints = {
    'lights': lights_cb,
    'top': tob_cb,
    'tv': tv_cb,
    'audio': audio_cb,
    'announce': announce_cb
}


# noinspection PyBroadException
def actuator(signal):
    print('Actuator running.')
    global auto_time
    while not signal['kill']:
        try:
            cur_time = datetime.now()
            # ---------------------------- Independent processing

            time_list = [cur_time.hour, cur_time.minute]
            if auto_time is not None and time_list[0] == auto_time[0] and time_list[1] == auto_time[1]:
                # signal['data']['commands'].append('LIGHTSAUTO')
                auto_time = None

            # ----------------------------

            if len(signal['data']['commands']) > 0:
                print(len(signal['data']['commands']))
                reply = None
                data = signal['data']['commands'].pop(0)
                ep = data.get("endpoint", None)
                req_id = data.get("req_id", None)
                if not req_id or not ep or ep not in endpoints:
                    continue
                try:
                    reply = endpoints[ep](data)
                    if not reply:
                        reply = {"error": f'Unknown issue while processing:\n{data}.'}
                except Exception:
                    reply = {"error": traceback.format_exc()}
                reply["req_id"] = req_id
                signal['data']['replies'].append(reply)

            time.sleep(0.2)
        except Exception:
            import traceback
            print(traceback.format_exc())

    print('Actuators killed.')


def launch_actuator(signal):
    if HOSTNAME['arduino_device'] is not None:
        initialize(signal)
    else:
        print("Arduino not enabled.")
    actuator(signal)

if __name__ == "__main__":
    commands = []
    replies = []
    signal = {'kill': False, 'restart_server': False, 'restart_websocket': False, 'termination': False,
              'data': {'commands': commands, 'replies': replies}, 'log_file_name': None}
    launch_actuator(signal)