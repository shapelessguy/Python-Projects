from datetime import datetime
from utils import HOSTNAME
import announcements
import serial
import time


serialPort: serial.Serial
lights = False
auto_active = False
prev_light_state = ""
initialized = False
active_times = [('9:00', '19:59')]
signal = None


def initialize(signal_):
    global serialPort, initialized, lights, signal
    signal = signal_
    serialPort = None
    lights = False
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
    global signal, auto_active, prev_light_state
    command = data.get("command", None)
    set_auto_time = data.get("set_auto_time", None)
    if command in ["on", "off", "auto"]:
        prev_light_state = command
        if command == "auto":
            auto_active = True
        else:
            auto_active = False
            write(data["endpoint"] + command)

        if set_auto_time:
            try:
                from_ = set_auto_time["from"]
                to_ = set_auto_time["to"]
                datetime.strptime(from_, "%H:%M")
                datetime.strptime(to_, "%H:%M")
                signal["state"].set_param("lights_auto", {"Lights from": from_, "Lights to": to_})
                signal["state"].save()
            except:
                return {"error": f'set_auto_time {set_auto_time} improper syntax.'}
        return {"msg": f'Lights [value={command}] sent to arduino.'}
    return {"error": f'Command {command} not recognized.'}


def tob_cb(data):
    command = data.get("command", None)
    if command in ["w", "rgb", "bright+", "bright-", "cold+", "cold-", "col_loop", "col_change", "heart"]:
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
    global auto_active
    lights_auto = signal["state"].get_param("lights_auto")
    lights_from = datetime.strptime(lights_auto.get("Lights from", "9:00"), "%H:%M").time()
    lights_to = datetime.strptime(lights_auto.get("Lights to", "20:00"), "%H:%M").time()
    while not signal['kill']:
        try:
            now = datetime.now()
            # --- Independent processing

            if auto_active:
                if lights_from <= lights_to:
                    lights_active = lights_from <= now <= lights_to
                else:
                    lights_active = now >= lights_from or now <= lights_to
                if lights_active and lights_active != prev_light_state:
                    prev_light_state = "on" if lights_active else "off"
                    write("lights" + prev_light_state)

            # ----------------------------

            if len(signal['data']['commands']) > 0:
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
    from main import State
    commands = []
    replies = []
    signal = {'kill': False, 'restart_server': False, 'restart_websocket': False, 'termination': False,
              'data': {'commands': commands, 'replies': replies}, 'state': State(), 'log_file_name': None}
    launch_actuator(signal)