import json
from functions.audio import *
from functions.monitors import *
from utils import KeyEventHolder, Application, ERR_FLAG, PREFERENCES_PATH, DEFAULT_PREFERENCES


class HandleFunction:
    def __init__(self, function_):
        self.function_ = function_
    
    def add_signal(self, signal):
        self.signal = signal
    
    def _run(self, verbose):
        result = ERR_FLAG
        try:
            result = self.function_(self.signal, verbose)
        except:
            import traceback
            text = "\n-----------------\n"
            text += traceback.format_exc()
            text += "-----------------\n"
            print(text)
        return result
    
    def run(self):
        return self._run(False)
    
    def run_verbose(self):
        return self._run(True)


class RegisteredFunctions:
    SWITCH_TO_HEADPHONES=HandleFunction(switch_to_headphones)
    SWITCH_TO_SPEAKERS=HandleFunction(switch_to_speakers)
    VOLUME_UP=HandleFunction(volume_up)
    VOLUME_DOWN=HandleFunction(volume_down)
    FIND_WINDOWS=HandleFunction(find_windows)
    GET_SCREENS=HandleFunction(get_screens)
    ORDER=HandleFunction(order)

    def __init__(self, signal):
        for attr_value in self.__class__.__dict__.values():
            if isinstance(attr_value, HandleFunction):
                attr_value.add_signal(signal)


class Signal:
    kill_flag = False
    preferences: dict
    applications: list[Application]
    reg_functions: RegisteredFunctions

    def __init__(self):
        self.load_preferences()
        self.kill_flag = False
    
    def load_preferences(self):
        if os.path.exists(PREFERENCES_PATH):
            with open(PREFERENCES_PATH, "r") as file:
                self.preferences = json.load(file)
        else:
            self.preferences = DEFAULT_PREFERENCES
    
    def save_preferences(self):
        with open(PREFERENCES_PATH, "w") as file:
            json.dump(self.preferences, file)

    def set_applications(self, applications):
        self.applications = applications
    
    def set_reg_functions(self, reg_functions):
        self.reg_functions = reg_functions
    
    def kill(self):
        self.kill_flag = True
    
    def is_alive(self):
        return not self.kill_flag


def register_functions_and_hotkeys(signal: Signal):
    reg_functions = RegisteredFunctions(signal)
    hotkeys = {
        (79, ): reg_functions.SWITCH_TO_HEADPHONES.run_verbose,
        (81, ): reg_functions.SWITCH_TO_SPEAKERS.run_verbose,
    }
    blocking_hotkeys = {
        (-175, ): reg_functions.VOLUME_UP.run_verbose,
        (-174, ): reg_functions.VOLUME_DOWN.run_verbose,
        (82, ): reg_functions.ORDER.run_verbose,

        # DEBUG PURPOSE
        # ('a', ): reg_functions.FIND_WINDOWS.run_verbose,
        # ('b', ): reg_functions.GET_SCREENS.run_verbose,
    }
    KeyEventHolder(signal, hotkeys, blocking_hotkeys, verbose=False)
    signal.set_reg_functions(reg_functions)
