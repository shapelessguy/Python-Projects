import ctypes
import ctypes.wintypes
from PyQt5.QtCore import QAbstractNativeEventFilter
from functions import session_lights


WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016


class SessionEndFilter(QAbstractNativeEventFilter):
    """
    Windows asks every app "may I shut down?" (WM_QUERYENDSESSION) before it starts closing any of them,
    so OpenRGB and the network are still up at that point. The lights go off there, and come back on
    if the shutdown is cancelled (WM_ENDSESSION with wParam=0).
    """
    def __init__(self, signal):
        super().__init__()
        self.signal = signal
        self.lights_are_off = False

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_QUERYENDSESSION:
                self.turn_off()
            elif msg.message == WM_ENDSESSION and not msg.wParam and self.lights_are_off:
                self.lights_are_off = False
                session_lights.lights_on(self.signal)
        return False, 0

    def turn_off(self):
        # The message reaches every top-level window of the app
        if not self.lights_are_off:
            self.lights_are_off = True
            session_lights.lights_off(self.signal)
