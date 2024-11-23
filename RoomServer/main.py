import threading
from datetime import datetime, timedelta
import announcements
import serial
import time
import os
import sys
import socket
import asyncio
import sequences
import multiprocessing
import serial.tools.list_ports as port_list
from simple_http_server import route, server
from simple_http_server import ModelDict
from firebase_admin import credentials, initialize_app, storage
from requests import get
import logging
logging.getLogger("simple_http_server").setLevel(logging.CRITICAL)

class TeeOutput:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, message):
        self.streams[0].write(message)
        self.streams[0].flush()
        message = '\n'.join([f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] - {m}\n" for m in message.split('\n') if m.strip() != ''])
        try:
            self.streams[1].write(message)
            self.streams[1].flush()
        except UnicodeEncodeError:
            encoded_message = message.encode('utf-8', 'replace').decode('utf-8')
            self.streams[1].write(encoded_message)
            self.streams[1].flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()

log_file_path = os.path.join(os.path.dirname(__file__), "output.log")
log_file = open(log_file_path, "a", encoding='utf-8')
sys.stdout = TeeOutput(sys.__stdout__, log_file)
sys.stderr = TeeOutput(sys.__stderr__, log_file)

SERVER_PORT = 10000
initialized_firebase = False
terminate = False
commands = None
replies = None


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
    while not terminate:
        for _ in range(10):
            if not terminate:
                time.sleep(0.5)
        try:
            prev_ip = None
            if not initialized_firebase:
                init_firebase()
            while not terminate:
                ip = get('https://api.ipify.org').content.decode('utf8')
                if prev_ip != ip:
                    try:
                        upload_ip(ip)
                        prev_ip = ip
                    except Exception:
                        print('Issue while trying to upload IP')
                        break
                for _ in range(120):
                    if not terminate:
                        time.sleep(0.5)
        except Exception as e:
            print('Issue while trying to upload IP (initialization)')
            print(e)
            pass


ports = list(port_list.comports())

serialPort: serial.Serial
lights = False
auto_time = None


def initialize():
    global serialPort, initialized
    serialPort = serial.Serial(
        port="COM6", baudrate=9600, bytesize=8, timeout=1, stopbits=serial.STOPBITS_ONE
    )

    loop_init = False
    print('Contacting Arduino..')
    while not loop_init and not terminate:
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
        print(f'To Arduino: {text}')
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
        write('LIGHTSON')
    elif not on and (lights or not initialized):
        lights = False
        write('LIGHTSOFF')
    initialized = True


# noinspection PyBroadException
def actuator(active_times, commands):
    print('Actuator running.')
    mode = 'LIGHTSAUTO'
    act_times_func = [list(int(y.split(':')[0]) * 60 + int(y.split(':')[1]) for y in x) for x in active_times]
    global auto_time
    audio_on = False
    last_audio_ping = datetime.now() - timedelta(hours=24)
    audio_ping_index = 0
    ping_period = 10  # audio ping received every 10 seconds
    tollerance = 180  # audio turns off after 180 seconds
    ping_sent = 60 * 60  # audio ping sent to HW every <-- seconds
    last_announcement, id_last_announcement = announcements.get_last_announcement()
    while not terminate:
        try:
            cur_time = datetime.now()
            last_announcement, id_last_announcement = announcements.update(cur_time, last_announcement, id_last_announcement)
            # print(cur_time - last_audio_ping, audio_on, 'pass='+ str('AUDIOON' in commands or 'AUDIOOFF' in commands))
            if 'AUDIOON' in commands or 'AUDIOOFF' in commands:
                pass
            elif cur_time - last_audio_ping > timedelta(seconds=tollerance) and audio_on:
                print('Audio set off automatically')
                commands.append('AUDIOOFF')
            # elif cur_time - last_audio_ping < timedelta(seconds=tollerance) and not audio_on:
            #     commands.append('AUDIOON')
            #     print('Audio set on automatically')

            time_list = [cur_time.hour, cur_time.minute]
            if auto_time is not None and time_list[0] == auto_time[0] and time_list[1] == auto_time[1]:
                commands.append('LIGHTSAUTO')
                auto_time = None
            if len(commands) > 0:
                reply = None
                command = commands.pop(0)
                if command == 'ANNOUNCE':
                    last_announcement, id_last_announcement = announcements.update(cur_time, last_announcement, id_last_announcement, forced=True)
                    reply = f'Command {command} sent'
                    print(reply)
                elif command[:2] == 'TV':
                    write(command)
                    reply = f'Command {command} sent'
                    print(reply)
                elif command[:5] == 'STRIP':
                    reply = f'Command {command} sent'
                    sequences.handle_strip_com(command[5:], write)
                    print(reply)
                elif command[:5] == 'AUDIO':
                    if command == 'AUDIOPINGVOL':
                        audio_ping_index += 1
                        last_audio_ping = cur_time
                        if audio_ping_index % (ping_sent / ping_period) == 0:
                            write(command)
                    elif command == 'AUDIOON':
                        reply = f'Command {command} sent'
                        last_audio_ping = cur_time
                        audio_on = True
                        sequences.audio_on(write)
                        print(reply)
                    elif command == 'AUDIOOFF':
                        reply = f'Command {command} sent'
                        audio_on = False
                        sequences.audio_off(write)
                        print(reply)
                    else:
                        write(command)
                        reply = f'Command {command} sent'
                        print(reply)
                    for i in range(len(commands) - 1, -1, -1):
                        if commands[i] in ['AUDIOON', 'AUDIOOFF', 'AUDIOON/OFF']:
                            commands.pop(i)
                elif command == 'LIGHTSAUTO':
                    mode = 'LIGHTSAUTO'
                    reply = f'Mode set to: {mode}'
                    print(reply)
                elif 'LIGHTSAUTO+' in command:
                    try:
                        time_ = command.split('+')[1]
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
                if reply is not None:
                    replies.append(reply)
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
        except Exception:
            import traceback
            print(traceback.format_exc())


def functions():
    global terminate
    try:
        initialize()
        active_times = [('7:30', '21:59')]
        worker = threading.Thread(target=actuator, args=(active_times, commands))
        worker.start()
        while not terminate:
            command = input('').upper().strip()
            if command == 'EXIT':
                terminate = True
                break
            commands.append(command)
    except:
        pass
    terminate = True
    global server_proc
    server_proc.terminate()
    print('Application gracefully terminated')


def start_server(serv_commands, serv_replies):
    global commands, replies
    commands = serv_commands
    replies = serv_replies
    try:
        server.start('0.0.0.0', SERVER_PORT)
    except socket.timeout:
        print("Socket timeout occurred - this might be due to a lost client connection.")
    except asyncio.TimeoutError:
        print("Asyncio timeout occurred - operation took too long.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    
def formulate_reply(topic):
    global replies
    time.sleep(0.1)
    for _ in range(20):
        try:
            if len(replies) > 0:
                return {topic: replies.pop(0)}
        except:
            pass
        time.sleep(0.05)
    return {topic: 'no answer :('}


@route("/")
def ping_callback():
    return {'/': '200'}

@route("/lights")
def lights_callback(model=ModelDict()):
    command = "LIGHTS" + model['lights'].upper()
    commands.append(command)
    return formulate_reply('lights')

@route("/strip")
def strip_callback(model=ModelDict()):
    command = "STRIP" + model['strip'].upper()
    commands.append(command)
    return formulate_reply('strip')

@route("/tv")
def tv_callback(model=ModelDict()):
    command = "TV" + model['tv'].upper()
    commands.append(command)
    return formulate_reply('tv')

@route("/audio")
def audio_callback(model=ModelDict()):
    command = "AUDIO" + model['audio'].upper()
    commands.append(command)
    return formulate_reply('audio')

@route("/announce")
def announcing_callback(model=ModelDict()):
    commands.append('ANNOUNCE')
    return {'announce': 'performing'}


if __name__ == '__main__':
    print('_')
    print('*************************')
    print('      NEW SESSION')
    print('*************************')
    commands = multiprocessing.Manager().list()
    replies = multiprocessing.Manager().list()
    threading.Thread(target=firebase_).start()
    server_proc = multiprocessing.Process(target=start_server, args=(commands, replies))
    server_proc.start()
    functions()
