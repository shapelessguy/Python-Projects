import inspect
from functions.audio import *
from functions.monitors import *
from functions.generic import *
from functions.application import *
from functions.arduino import *
from utils import ERR_FLAG


class HandleFunction:
    def __init__(self, function_, verbose_always_off=False):
        self.function_ = function_
        self.verbose_always_off = verbose_always_off

    @property
    def module_name(self) -> str:
        """Returns the module/package name where the wrapped function was defined."""
        if self.function_ is None:
            return "<no function>"
        
        mod = inspect.getmodule(self.function_)
        if mod is None:
            return "<unknown>"
        
        return mod.__name__.split(".")[-1]
    
    def add_signal(self, signal):
        self.signal = signal
    
    def _run(self, verbose, *args):
        result = ERR_FLAG
        try:
            if verbose:
                print(f"RUN FUNCTION: '{self.function_.__name__}'")
            result = self.function_(self.signal, verbose, *args)
        except:
            import traceback
            text = "\n-----------------\n"
            text += traceback.format_exc()
            text += "-----------------\n"
            print(text)
        return result
    
    def run(self, *args):
        return self._run(False, *args)
    
    def run_shortcut(self, *args):
        self.signal.last_interaction = datetime.now()
        return self._run(not self.verbose_always_off, *args)
    
    def __name__(self):
        return self.function_.__name__


class RegisteredFunctions:
    HEADPHONES=HandleFunction(switch_to_headphones)
    SPEAKERS=HandleFunction(switch_to_speakers)
    VOLUME_UP=HandleFunction(volume_up, verbose_always_off=True)
    VOLUME_DOWN=HandleFunction(volume_down, verbose_always_off=True)
    FIND_WINDOWS=HandleFunction(find_windows)
    GET_SCREENS=HandleFunction(get_screens)
    ORDER=HandleFunction(order)
    SNAPSHOT=HandleFunction(get_snapshot)
    WIN_SNAPSHOT=HandleFunction(get_win_snapshot)
    TURN_ON_MONITORS=HandleFunction(turn_on_monitors)
    SHUTDOWN_MONITORS=HandleFunction(shutdown_monitors)
    GET_MOUSE_POS=HandleFunction(get_mouse_position)
    GET_APPS_STATUS=HandleFunction(get_apps_status)
    GET_WIN_POSITIONS=HandleFunction(get_win_pos)
    DISCOVER_WIN=HandleFunction(discover_windows)
    STARTUP=HandleFunction(startup_applications)
    KILL_APP=HandleFunction(kill_application)
    SHOW_UWP_APP_NAMES=HandleFunction(get_uwp_apps)
    SHOW_ALARM=HandleFunction(show_alarm)
    RING_ALARM=HandleFunction(ring_alarm)
    THREADS_STATUS=HandleFunction(get_threads_status)
    LIGHTS_ON=HandleFunction(lights_on)
    LIGHTS_OFF=HandleFunction(lights_off)
    LIGHTS_AUTO=HandleFunction(lights_auto)
    AUDIO_POWER=HandleFunction(audio_power)
    TV_POWER=HandleFunction(tv_power)
    TV_OK=HandleFunction(tv_ok)
    SPECIAL=HandleFunction(special)
    TYPE_PASSWORD=HandleFunction(type_password)
    PLAY_PAUSE=HandleFunction(play_pause)

    def __init__(self, signal):
        for attr_value in self.__class__.__dict__.values():
            if isinstance(attr_value, HandleFunction):
                attr_value.add_signal(signal)

    def get_functions(self):
        functions = {}
        for f_name, attr_value in self.__class__.__dict__.items():
            if isinstance(attr_value, HandleFunction):
                functions[f_name] = attr_value
        return functions


def register_functions(signal):
    reg_functions = RegisteredFunctions(signal)
    signal.set_reg_functions(reg_functions)
