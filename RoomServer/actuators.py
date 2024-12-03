import threading
from datetime import datetime, timedelta
from utils import HOSTNAME
import announcements
import serial
import time
import asyncio
import sequences


serialPort: serial.Serial
lights = False
auto_time = None
initialized = False
active_times = [('7:30', '21:59')]
signal = None


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
def write(text):
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
        write(text)


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
async def actuator(signal):
    print('Actuator running.')
    commands = signal['data']['commands']
    mode = 'LIGHTSAUTO'
    act_times_func = [list(int(y.split(':')[0]) * 60 + int(y.split(':')[1]) for y in x) for x in active_times]
    global auto_time
    if signal['state'].get_param('audio') == True:
        audio_on = True
    else:
        audio_on = False
        sequences.audio_off(write)
    last_audio_ping = datetime.now()
    audio_ping_index = 0
    ping_period = 10  # audio ping received every 10 seconds
    tollerance = 180  # audio turns off after 180 seconds
    ping_sent = 60 * 60  # audio ping sent to HW every <-- seconds
    threading.Thread(target=announcements.spawn_monitoring, args=(signal, )).start()
    last_announcement, id_last_announcement = announcements.get_last_announcement()
    while not signal['kill']:
        try:
            cur_time = datetime.now()
            last_announcement, id_last_announcement = await announcements.update(last_announcement, id_last_announcement)
            if 'AUDIOON' in commands or 'AUDIOOFF' in commands:
                pass
            elif cur_time - last_audio_ping > timedelta(seconds=tollerance) and audio_on:
                print('Audio set off automatically')
                commands.append('AUDIOOFF')
                audio_on = False
                signal['state'].set_param('audio', False)
                signal['state'].save()
            elif cur_time - last_audio_ping < timedelta(seconds=tollerance) and not audio_on:
                print('Audio set on automatically')
                commands.append('AUDIOON')
                audio_on = True
                signal['state'].set_param('audio', True)
                signal['state'].save()

            time_list = [cur_time.hour, cur_time.minute]
            if auto_time is not None and time_list[0] == auto_time[0] and time_list[1] == auto_time[1]:
                commands.append('LIGHTSAUTO')
                auto_time = None
            if len(commands) > 0:
                reply = None
                command = commands.pop(0)
                if command == 'ANNOUNCEPERFORMING':
                    last_announcement, id_last_announcement = await announcements.update(last_announcement, id_last_announcement, forced=True)
                    reply = f'Command {command} sent'
                elif command[:2] == 'TV':
                    write(command)
                    reply = f'Command {command} sent'
                elif command[:5] == 'STRIP':
                    reply = f'Command {command} sent'
                    sequences.handle_strip_com(command[5:], write)
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
                        signal['state'].set_param('audio', True)
                        signal['state'].save()
                        sequences.audio_on(write)
                    elif command == 'AUDIOOFF':
                        reply = f'Command {command} sent'
                        audio_on = False
                        signal['state'].set_param('audio', False)
                        signal['state'].save()
                        sequences.audio_off(write)
                    else:
                        write(command)
                        reply = f'Command {command} sent'
                    for i in range(len(commands) - 1, -1, -1):
                        if commands[i] in ['AUDIOON', 'AUDIOOFF', 'AUDIOON/OFF']:
                            commands.pop(i)
                elif command == 'LIGHTSAUTO':
                    mode = 'LIGHTSAUTO'
                    reply = f'Mode set to: {mode}'
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
                elif command == 'LIGHTSON':
                    mode = 'LIGHTSON'
                    reply = f'Mode set to: {mode}'
                elif command == 'LIGHTSOFF':
                    mode = 'LIGHTSOFF'
                    reply = f'Mode set to: {mode}'
                if reply is not None:
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
        except Exception:
            import traceback
            print(traceback.format_exc())

    print('Actuators killed.')


def launch_actuator(signal):
    initialize(signal)
    asyncio.run(actuator(signal))
