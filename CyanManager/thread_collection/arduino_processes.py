import serial
import time
import threading


class Mode:
    GREEN = "GREEN"
    RED = "RED"
    BLUE = "BLUE"
    mode = ""
    tollerance = 10  # seconds after which any mode except GREEN starts to blink and be irresponsive for ~5seconds.
    set_mode_at = time.time()
    led_states = {}
    is_unstable = False

    def __init__(self):
        self.mode = self.GREEN
        self.led_states = {k: False for k in self.get_all_modes()}

    @classmethod
    def get_all_modes(self):
        return tuple(value for name, value in vars(self).items() if isinstance(value, str) and name.upper() == name)
    
    def set_mode(self, mode):
        all_modes = self.get_all_modes()
        if mode in all_modes:
            for m_ in all_modes:
                if m_ != mode:
                    self.write(f"{m_}_OFF")
            self.write(f"{mode}_ON")
            self.mode = mode
            self.set_mode_at = time.time()
        self.is_unstable = False
        self.led_states = {k: (k == mode) for k in all_modes}
    
    def hide_leds(self):
        all_modes = self.get_all_modes()
        for m_ in all_modes:
            self.write(f"{m_}_OFF")
        if self.mode != Mode.GREEN:
            self.is_unstable = True
            threading.Thread(target=self.blink).start()
        self.led_states = {k: False for k in all_modes}
    
    def blink(self):
        interval = 0.3
        duration = 5
        for _ in range(int(duration * 0.5 / interval)):
            if self.is_unstable:
                self.write(f"{self.mode}_OFF")
                time.sleep(interval)
            if self.is_unstable:
                self.write(f"{self.mode}_ON")
                time.sleep(interval)
        if self.is_unstable and self.mode != Mode.GREEN:
            self.set_mode(Mode.GREEN)

    def write(self, text, tries=0):
        global signal
        if tries > 2:
            return
        try:
            if serialPort is None:
                raise Exception()
            else:
                serialPort.write(f"{text}\r\n".encode("Ascii"))
        except Exception:
            print('Trying to initiate connection to COM..')
            time.sleep(1)
            initialize(signal)
            self.write(text, tries+1)


current_mode = Mode()
signal = None
serialPort = None
NAME = "Arduino"
PARAMETERS = {}
ARDUINO_PORT = "COM6"


def send_to_arduino_receiver(signal, verbose, topic, arg):
    global pending_message
    pending_message = verbose, topic, arg


def initialize(thread_manager):
    global serialPort, mode
    signal = thread_manager.signal
    serialPort = None
    while signal.is_alive() and not thread_manager.to_kill:
        if serialPort is None:
            try:
                serialPort = serial.Serial(
                    port=ARDUINO_PORT, baudrate=115200, bytesize=8, timeout=1, stopbits=serial.STOPBITS_ONE
                )
            except Exception:
                print(f"Cannot open port {ARDUINO_PORT}")
                serialPort = None
        else:
            break
        time.sleep(1)

    loop_init = False
    print('Contacting Arduino..')
    while not loop_init and signal.is_alive() and not thread_manager.to_kill:
        time.sleep(0.05)
        if serialPort.in_waiting > 0:
            serial_string = serialPort.readline().decode("Ascii")
            try:
                if "IR Receiver ready" in serial_string:
                    loop_init = True
            except Exception:
                pass
    current_mode.set_mode(Mode.GREEN)
    print('Arduino found!')


def resolve_green_mode(verb):
    global current_mode
    if verb == "POWER":
        if time.time() - current_mode.set_mode_at > 0.8:
            signal.reg_functions.TV_POWER.run_shortcut()
    elif verb == "MONON":
        signal.reg_functions.TURN_ON_MONITORS.run_shortcut()
    elif verb == "MONOFF":
        signal.reg_functions.SHUTDOWN_MONITORS.run_shortcut()

    if verb == "DIR_RIGHT":
        signal.reg_functions.NEXT.run_shortcut()
    elif verb == "DIR_LEFT":
        signal.reg_functions.PREV.run_shortcut()

    elif verb == "+":
        signal.reg_functions.VOLUME_UP.run_shortcut()
    elif verb == "-":
        signal.reg_functions.VOLUME_DOWN.run_shortcut()
    
    elif verb == "PLAY":
        signal.reg_functions.TV_OK.run_shortcut()


def resolve_red_mode(verb):
    global current_mode
    if verb == "POWER":
        if time.time() - current_mode.set_mode_at > 0.8:
            signal.reg_functions.AUDIO_POWER.run_shortcut()
    elif verb == "DIR_RIGHT":
        signal.reg_functions.SPEAKERS.run_shortcut()
    elif verb == "DIR_LEFT":
        signal.reg_functions.HEADPHONES.run_shortcut()
    elif verb == "DIR_UP":
        signal.reg_functions.AUDIO_LEVEL.run_shortcut()
    elif verb == "DIR_DOWN":
        signal.reg_functions.AUDIO_EFFECT.run_shortcut()
    elif verb == "DIR_CENTER":
        signal.reg_functions.PLAY_PAUSE.run_shortcut()

    elif verb == "+":
        signal.reg_functions.VOLUME_UP.run_shortcut()
    elif verb == "-":
        signal.reg_functions.VOLUME_DOWN.run_shortcut()
    elif verb == "PLAY":
        signal.reg_functions.PLAY_PAUSE.run_shortcut()


def resolve_blue_mode(verb):
    global current_mode
    
    if verb == "POWER":
        if time.time() - current_mode.set_mode_at > 0.8:
            signal.reg_functions.TOP_POWER.run_shortcut()
    elif verb == "MONON":
        signal.reg_functions.TOP_COL_CHANGE.run_shortcut()
    elif verb == "MONOFF":
        signal.reg_functions.TOP_RGB.run_shortcut()
    elif verb == "DIR_RIGHT":
        signal.reg_functions.TOP_COLD_PLUS.run_shortcut()
    elif verb == "DIR_LEFT":
        signal.reg_functions.TOP_COLD_LESS.run_shortcut()
    elif verb == "DIR_UP":
        signal.reg_functions.TOP_BRIGHT_PLUS.run_shortcut()
    elif verb == "DIR_DOWN":
        signal.reg_functions.TOP_BRIGHT_MINUS.run_shortcut()
    elif verb == "DIR_CENTER":
        signal.reg_functions.TOP_HEART.run_shortcut()
    
    elif verb == "HOME":
        signal.reg_functions.LIGHTS_AUTO.run_shortcut()
    elif verb == "PLAY":
        signal.reg_functions.LIGHTS_ON.run_shortcut()
    elif verb == "BACK":
        signal.reg_functions.LIGHTS_OFF.run_shortcut()


def take_action(signal, verb):
    global current_mode

    if verb == "GREEN":
        current_mode.set_mode(Mode.GREEN)
    elif verb == "RED":
        current_mode.set_mode(Mode.RED)
    elif verb == "BLUE":
        current_mode.set_mode(Mode.BLUE)
    
    if current_mode.is_unstable:
        return
    elif current_mode.mode == Mode.GREEN:
        threading.Thread(target=resolve_green_mode, args=(verb,)).start()
    elif current_mode.mode == Mode.RED:
        threading.Thread(target=resolve_red_mode, args=(verb,)).start()
    elif current_mode.mode == Mode.BLUE:
        threading.Thread(target=resolve_blue_mode, args=(verb,)).start()

    current_mode.set_mode_at = time.time()


def entrypoint(thread_manager):
    global signal, current_mode, pending_message, serialPort
    signal = thread_manager.signal
    pending_message = None
    initialize(thread_manager)
    while signal.is_alive() and not thread_manager.to_kill:
        if pending_message:
            verbose, topic, arg = pending_message
            pending_message = None
            serialPort.write(f"{topic}{arg}\r\n".encode("Ascii"))

        time.sleep(0.05)
        if time.time() - current_mode.set_mode_at > Mode.tollerance and any(current_mode.led_states.values()):
            current_mode.hide_leds()
        if serialPort.in_waiting > 0:
            try:
                serial_string = serialPort.readline().decode("utf8")
                if len(serial_string.split()) == 3 and "pressed" in serial_string.split()[2]:
                    take_action(signal, serial_string.split()[1])
            except:
                pass
    print(f"{thread_manager.name} thread down..")
