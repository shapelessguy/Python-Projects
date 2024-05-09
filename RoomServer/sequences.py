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

def top_off(write: callable, delay):
    write('STRIPTOPDEF')
    time.sleep(delay)
    write('STRIPTOPCOLSWITCH')

def handle_strip_com(command, write: callable):
    delay_top_col_change = 0.100
    delay_top_default = 0.400
    if command == 'TOPLIGHT':
        write('STRIPOFF')
        time.sleep(0.50)
        write('STRIPTOPDEF')
        time.sleep(delay_top_default)
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
        time.sleep(delay_top_default)
        for _ in range(1):
            write('STRIPTOPCHANGECOL')
            time.sleep(delay_top_col_change)
        write('STRIPON')
        time.sleep(0.100)
        write('STRIPB3')
    elif command == 'TOPR0':
        write('STRIPOFF')
        time.sleep(0.50)
        write('STRIPTOPDEF')
        time.sleep(delay_top_default)
        for _ in range(2):
            write('STRIPTOPCHANGECOL')
            time.sleep(delay_top_col_change)
        write('STRIPON')
        time.sleep(0.100)
        write('STRIPR0')
    elif command == 'TOPG0':
        write('STRIPOFF')
        time.sleep(0.50)
        write('STRIPTOPDEF')
        time.sleep(delay_top_default)
        for _ in range(3):
            write('STRIPTOPCHANGECOL')
            time.sleep(delay_top_col_change)
        write('STRIPON')
        time.sleep(0.100)
        write('STRIPG0')
    elif command == 'TOPB0':
        write('STRIPOFF')
        time.sleep(0.50)
        write('STRIPTOPDEF')
        time.sleep(delay_top_default)
        for _ in range(4):
            write('STRIPTOPCHANGECOL')
            time.sleep(delay_top_col_change)
        write('STRIPON')
        time.sleep(0.100)
        write('STRIPB0')
    elif command == 'TOPR4':
        write('STRIPOFF')
        time.sleep(0.50)
        write('STRIPTOPDEF')
        time.sleep(delay_top_default)
        for _ in range(5):
            write('STRIPTOPCHANGECOL')
            time.sleep(delay_top_col_change)
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
        top_off(write, delay_top_default)
    elif command == 'I0':
        write('STRIPOFF')
        time.sleep(0.50)
        top_off(write, delay_top_default)
        time.sleep(0.50)
        write('STRIPON')
        time.sleep(0.50)
        write('STRIPI1')
    elif command == 'I1':
        write('STRIPI1')
    elif command == 'I2':
        write('STRIPI2')
    elif command == 'I3':
        write('STRIPI3')
    elif command == 'I4':
        write('STRIPI4')
