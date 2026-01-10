import sys
import os
import time
import importlib
from PyQt5 import QtWidgets
from PyQt5 import QtWidgets
from PyQt5.QtCore import QObject, Qt
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject, pyqtSignal
from utils import *


try:
    import frontend
except:
    pass
bar_width = 0


class UIThreadBridge(QObject):
    show_window = pyqtSignal()
    hide_window = pyqtSignal()
    quit_app = pyqtSignal()
    set_text = pyqtSignal(str, str)
    set_statistics = pyqtSignal(dict, object)
    set_operation = pyqtSignal(str, str)


class WindowDragFilter(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._drag_pos = None

    def eventFilter(self, obj, event):
        if obj is self.window:
            if event.type() == event.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_pos = event.globalPos() - self.window.frameGeometry().topLeft()
                return True

            elif event.type() == event.MouseMove and event.buttons() & Qt.LeftButton and self._drag_pos:
                self.window.move(event.globalPos() - self._drag_pos)
                return True

            elif event.type() == event.MouseButtonRelease:
                self._drag_pos = None
                return True

        return False


class UI(EmptyUI):
    def __init__(self):
        ui_files = ['frontend']
        ui_paths = [os.path.join(os.path.dirname(os.path.realpath(__file__)), x + '.ui') for x in ui_files]
        py_paths = [os.path.join(os.path.dirname(os.path.realpath(__file__)), x + '.py') for x in ui_files]
        for i in range(len(ui_paths)):
            ui_path = ui_paths[i]
            py_path = py_paths[i]
            if os.path.exists(ui_path):
                os.system(f'pyuic5 -x {ui_path} -o {py_path}')
        importlib.reload(frontend)

        app = QApplication(sys.argv)
        MainWindow = QtWidgets.QMainWindow()
        ui = frontend.Ui_MainWindow()
        ui.app = app
        ui.main_window = MainWindow
        ui.main_window.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        ui.size_to_reduce = 0
        
        drag_filter = WindowDragFilter(MainWindow)
        MainWindow.installEventFilter(drag_filter)

        self.bridge = UIThreadBridge()
        self.bridge.show_window.connect(self._show_window)
        self.bridge.hide_window.connect(self._hide_window)
        self.bridge.quit_app.connect(self._quit_app)
        self.bridge.set_text.connect(self._set_text)
        self.bridge.set_statistics.connect(self._set_statistics)
        self.bridge.set_operation.connect(self._set_operation)
        self.ui = ui
    
    def execute(self, function_, *args, **kwargs):
        f = getattr(self.bridge, function_)
        return f.emit(*args, **kwargs)

    def exit_sync(self, signal):
        signal["kill"] = True
        self.ui.app.quit()

    def setup_ui(self, signal):
        self.ui.setupUi(self.ui.main_window)
        self.ui.exit.clicked.connect(lambda _=False: self.exit_sync(signal))
        
        for p, p_text in {"sync": "Objects in sync", "partial": "Objects with conflicting metadata",
                    "local": "Objects available only on the current system", "remote": "Objects available only on the remote device"}.items():
            for el_name, el_text in {"icon": "", "n_lbl": ": absolute number", "size_lbl": ": total size"}.items():
                tooltip_text = f"{p_text}{el_text}"
                object_id = f"{p}_{el_name}"
                getattr(self.ui, object_id).setToolTip(tooltip_text)

    def resize_window(self):
        global bar_width
        self.ui.model_text.setText("")
        self.ui.details_lbl.setText("")

        width = 468
        height = 210
        bar_width = self.ui.bar.width()
        
        self.ui.main_window.resize(width, height)
        screen_geometry = self.ui.app.primaryScreen().availableGeometry()
        x = screen_geometry.width() - width - 4
        y = screen_geometry.height() - height - 1
        self.ui.main_window.move(x, y)
        self.ui.main_window.hide()

    def wait_for_close(self, _):
        app = self.ui.app
        form_closed = app.exec_()
        return form_closed

    def _show_window(self):
        self.ui.main_window.show()

    def _hide_window(self):
        self.ui.main_window.hide()

    def _quit_app(self):
        app = self.ui.app
        app.quit()
        print("App quit")

    def _set_text(self, element_name: str, text: str):
        element = getattr(self.ui, element_name)
        element.setText(text)

    def _set_statistics(self, global_stats: dict, size_to_reduce: int=None):
        global bar_width
        if size_to_reduce is not None:
            self.ui.size_to_reduce = size_to_reduce
        self.ui.sync_n_lbl.setText("#" + str(global_stats["in_sync"]["n"]))
        self.ui.sync_size_lbl.setText(scale_bytes(global_stats["in_sync"]["size"]))
        self.ui.partial_n_lbl.setText("#" + str(global_stats["partial"]["n"]))
        self.ui.partial_size_lbl.setText(scale_bytes(global_stats["partial"]["size"]))
        self.ui.local_n_lbl.setText("#" + str(global_stats["only_local"]["n"]))
        self.ui.local_size_lbl.setText(scale_bytes(global_stats["only_local"]["size"]))
        self.ui.remote_n_lbl.setText("#" + str(global_stats["only_remote"]["n"]))
        self.ui.remote_size_lbl.setText(scale_bytes(global_stats["only_remote"]["size"]))

        remaining_width = bar_width
        for element, key in {"partial_bar": "partial", "local_bar": "only_local", "remote_bar": "only_remote"}.items():
            width = int(global_stats[key]["size"] / self.ui.size_to_reduce * bar_width) if self.ui.size_to_reduce > 0 else 0
            remaining_width -= width
            for prop in ["setMinimumWidth", "setMaximumWidth"]:
                getattr(getattr(self.ui, element), prop)(width)
        self.ui.filler_bar.setMinimumWidth(remaining_width)
        self.ui.filler_bar.setMaximumWidth(remaining_width)

    def _set_operation(self, text, color="black"):
        self.ui.operation_lbl.setText(text)
        self.ui.operation_lbl.setStyleSheet(f"color: {color}")


if __name__ == "__main__":
    pass