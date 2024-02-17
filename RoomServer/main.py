import threading
from datetime import datetime
import serial
import time
import os
import sys
import subprocess
import serial.tools.list_ports as port_list
from simple_http_server import route, server
from simple_http_server import request_map
from simple_http_server import Response
from simple_http_server import MultipartFile
from simple_http_server import Parameter
from simple_http_server import Parameters
from simple_http_server import Header
from simple_http_server import JSONBody
from simple_http_server import HttpError
from simple_http_server import StaticFile
from simple_http_server import Headers
from simple_http_server import Cookies
from simple_http_server import Cookie
from simple_http_server import Redirect
from simple_http_server import ModelDict
from firebase_admin import credentials, initialize_app, storage
from requests import get
SERVER_PORT = 10001
initialized_firebase = False


def init_firebase():
    global initialized_firebase
    cred_json = os.path.join(os.path.dirname(sys.argv[0]), "ip-manager42.json")
    cred = credentials.Certificate(cred_json)
    initialize_app(cred, {'storageBucket': 'ip-manager42.appspot.com'})
    initialized_firebase = True


def upload_ip(ip):
    file_path = os.path.join(os.path.dirname(sys.argv[0]), "ip_server.txt")
    file_name = "ip_server.txt"
    with open(file_path, 'w+') as file:
        file.write(ip)
    bucket = storage.bucket()
    blob = bucket.blob('RaspberryPi-Cyan/' + file_name)
    blob.upload_from_filename(file_path)
    blob.make_public()
    print("IP uploaded to:", blob.public_url)


# noinspection PyBroadException
def firebase_():
    global initialized_firebase
    while 1:
        try:
            prev_ip = None
            if not initialized_firebase:
                init_firebase()
            while 1:
                ip = get('https://api.ipify.org').content.decode('utf8')
                if prev_ip != ip:
                    try:
                        upload_ip(ip)
                        prev_ip = ip
                    except Exception as ex:
                        print('Issue while trying to upload IP')
                        break
                time.sleep(60)
        except Exception as e:
            print('Issue while trying to upload IP (initialization)')
            print(e)
            pass
        time.sleep(5)


ports = list(port_list.comports())

serialPort: serial.Serial
lights = False
auto_time = None
commands = []
reply = ''


def initialize():
    global serialPort, initialized
    
    print('Trying to compile Arduino.ino ...')
    cmd = "source ~/.bashrcd df; arduino-cli compile --fqbn arduino:avr:uno ~/Documents/Python-Projects/RoomServer/arduino/" + \
          "arduino.ino; arduino-cli upload -p /dev/ttyUSB0 --fqbn arduino:avr:uno ~/Documents/Python-Projects/RoomServer/arduino/arduino.ino"
    a = subprocess.run(['bash', '-c', cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print(a.stdout.decode('utf-8'))

    # returned_value = subprocess.call(cmd, shell=True)
    # if returned_value != 0:
    #     raise Exception('Error while compiling or uploading the .ino script on arduino :(')
    print('Arduino.ino compiled and uploaded!')
    serialPort = serial.Serial(
        port="/dev/ttyUSB0", baudrate=9600, bytesize=8, timeout=1, stopbits=serial.STOPBITS_ONE
    )

    loop_init = False
    print('Contacting Arduino..')
    while not loop_init:
        time.sleep(0.05)
        # Wait until there is data waiting in the serial buffer
        if serialPort.in_waiting > 0:

            # Read data out of the buffer until a carriage return / new line is found
            serial_string = serialPort.readline()

            # Print the contents of the serial data
            # noinspection PyBroadException
            try:
                if serial_string.decode("Ascii") == "loop_init\r\n":
                    loop_init = True
                    initialized = False
            except Exception:
                pass

    if serialPort is None:
        raise Exception("Issue while initializing Arduino.")
    else:
        print('Arduino found!')


# noinspection PyBroadException
def write(text):
    try:
        serialPort.write(f"{text}\r\n".encode("Ascii"))
    except Exception:
        print('Trying to initiate connection to COM..')
        time.sleep(1)
        initialize()
        write(text)


initialized = False
def change_lights(on):
    global lights, initialized
    if on and (not lights or not initialized):
        lights = True
        print('lights on.')
        write('lights_on')
    elif not on and (lights or not initialized):
        lights = False
        print('lights off.')
        write('lights_off')
    initialized = True


# noinspection PyBroadException
def actuator(active_times, commands):
    print('Actuator running.')
    mode = 'LIGHTSAUTO'
    act_times_func = [list(int(y.split(':')[0]) * 60 + int(y.split(':')[1]) for y in x) for x in active_times]
    now_active = False
    global auto_time, reply
    while 1:
        cur_time = datetime.now()
        cur_time = [cur_time.hour, cur_time.minute]
        if auto_time is not None and cur_time[0] == auto_time[0] and cur_time[1] == auto_time[1]:
            commands.append('LIGHTSAUTO')
            auto_time = None
        if len(commands) > 0:
            command = commands.pop(0).replace('+', ' ')
            if command == 'LIGHTSAUTO':
                mode = 'LIGHTSAUTO'
                reply = f'Mode set to: {mode}'
                print(reply)
            elif 'LIGHTSAUTO ' in command:
                try:
                    time_ = command.split(' ')[1]
                    hour = int(time_.split(':')[0])
                    minute = int(time_.split(':')[1])
                    hour_str = "0" + str(hour) if len(str(hour)) == 1 else str(hour)
                    minute_str = "0" + str(minute) if len(str(minute)) == 1 else str(minute)
                    auto_time = [hour, minute]
                    reply = f'Mode is: {mode} but will switch to auto at {hour_str}:{minute_str}'
                except Exception as e:
                    reply = 'Command not recognized'
                print(reply)
            elif command == 'LIGHTSON':
                mode = 'LIGHTSON'
                reply = f'Mode set to: {mode}'
                print(reply)
            elif command == 'LIGHTSOFF':
                mode = 'LIGHTSOFF'
                reply = f'Mode set to: {mode}'
                print(reply)
            elif command == 'TVON' or command == 'TVOFF':
                write(command)
                reply = f'Command {command} sent'
                print(reply)
        if mode == 'LIGHTSAUTO':
            now = int(time.localtime().tm_hour * 60 + time.localtime().tm_min)
            turn_lights = False
            for interval in act_times_func:
                if interval[0] <= now < interval[1]:
                    turn_lights = True
            change_lights(turn_lights)
        elif mode == 'LIGHTSON':
            change_lights(True)
        elif mode == 'LIGHTSOFF':
            change_lights(False)
        time.sleep(0.2)


def functions():
    initialize()
    active_times = [('7:30', '22:00')]
    worker = threading.Thread(target=actuator, args=(active_times, commands))
    worker.start()
    while 1:
        command = input('')
        commands.append(command)


def start_server():
    server.start(port=SERVER_PORT)
    
def formulate_reply(topic):
    global reply
    time.sleep(0.5)
    for i in range(20):
        if reply != '':
            return {topic: reply}
        time.sleep(0.05)
    reply = ''
    return {topic: 'no answer :('}


@route("/")
def ping(model=ModelDict()):
    return {'/': '200'}


@route("/lights")
def lights(model=ModelDict()):
    command = "LIGHTS" + model['lights'].upper()
    commands.append(command)
    return formulate_reply('lights')


@route("/tv")
def lights(model=ModelDict()):
    command = "TV" + model['tv'].upper()
    commands.append(command)
    return {'tv': command}


if __name__ == '__main__':
    threading.Thread(target=firebase_).start()
    threading.Thread(target=start_server).start()
    functions()
