import time


def audio_on(write: callable):
    write('AUDIOON/OFF')
    time.sleep(1)
    write('AUDIOON/OFF')
    time.sleep(0.5)
    write('STRIPTOPG4')

def audio_off(write: callable):
    write('AUDIOON/OFF')
    time.sleep(1)
    write('AUDIOON/OFF')
    time.sleep(3)
    write('AUDIOON/OFF')
    time.sleep(0.5)
    write('STRIPTOPOFF')

def handle_strip_com(command, write: callable):
    if command == 'TOPLIGHT':
        write('STRIPOFF')
        time.sleep(0.50)
        write('STRIPTOPDEF')
        time.sleep(0.250)
        write('STRIPTOPCOLSWITCH')
        time.sleep(0.100)
        write('STRIPTOPLIGHTSWITCH')
        time.sleep(0.100)
        write('STRIPON')
        time.sleep(0.100)
        write('STRIPW0')
    elif command == 'TOPB3':
        write('STRIPOFF')
        time.sleep(0.50)
        write('STRIPTOPDEF')
        time.sleep(0.250)
        for _ in range(1):
            write('STRIPTOPCHANGECOL')
            time.sleep(0.100)
        write('STRIPON')
        time.sleep(0.100)
        write('STRIPB3')
    elif command == 'TOPR0':
        write('STRIPOFF')
        time.sleep(0.50)
        write('STRIPTOPDEF')
        time.sleep(0.250)
        for _ in range(2):
            write('STRIPTOPCHANGECOL')
            time.sleep(0.100)
        write('STRIPON')
        time.sleep(0.100)
        write('STRIPR0')
    elif command == 'TOPG0':
        write('STRIPOFF')
        time.sleep(0.50)
        write('STRIPTOPDEF')
        time.sleep(0.250)
        for _ in range(3):
            write('STRIPTOPCHANGECOL')
            time.sleep(0.100)
        write('STRIPON')
        time.sleep(0.100)
        write('STRIPG0')
    elif command == 'TOPB0':
        write('STRIPOFF')
        time.sleep(0.50)
        write('STRIPTOPDEF')
        time.sleep(0.250)
        for _ in range(4):
            write('STRIPTOPCHANGECOL')
            time.sleep(0.100)
        write('STRIPON')
        time.sleep(0.100)
        write('STRIPB0')
    elif command == 'TOPR4':
        write('STRIPOFF')
        time.sleep(0.50)
        write('STRIPTOPDEF')
        time.sleep(0.250)
        for _ in range(5):
            write('STRIPTOPCHANGECOL')
            time.sleep(0.100)
        write('STRIPON')
        time.sleep(0.100)
        write('STRIPR4')
    elif command == 'TOPG4':
        write('STRIPOFF')
        time.sleep(0.50)
        write('STRIPTOPDEF')
        time.sleep(0.100)
        write('STRIPON')
        time.sleep(0.100)
        write('STRIPG4')
    elif command == 'TOPOFF':
        write('STRIPOFF')
        time.sleep(0.50)
        write('STRIPTOPDEF')
        time.sleep(0.250)
        write('STRIPTOPCOLSWITCH')