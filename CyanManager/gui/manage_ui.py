import os
import sys
import threading
import time
from gui.theme import dark_stylesheet
from gui.tab_general import set_gen_layout
from gui.tab_applications import set_apps_layout
from PyQt5.QtCore import QObject, Qt
from PyQt5.QtWidgets import QMainWindow, QApplication, QSystemTrayIcon, QMenu, QLabel
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap, QMovie
from utils import ICONS_FOLDER_PATH, wait


def gui_loop(signal):
    signal.ui_manager.execute("set_general", signal.ui_manager)
    prev_visible = False
    visibility_change = False
    while signal.is_alive():
        try:
            win_visible = signal.ui_manager.ui.main_window.isVisible() and int(signal.ui_manager.ui.main_window.windowState()) == 0
            if win_visible:
                visibility_change = not prev_visible
                prev_visible = True

                apps = signal.reg_functions.GET_APPS_STATUS.run()
                monitors = signal.reg_functions.GET_SCREENS.run()

                exe_map = {}
                for a in apps:
                    if a.process:
                        exe_map[a.name] = a.process.ExecutablePath
                signal.update_exe_table(exe_map)
                signal.ui_manager.execute("set_apps", signal.ui_manager, visibility_change, apps, monitors)
                wait(signal, 800)
            else:
                visibility_change = prev_visible
                prev_visible = False
                wait(signal, 100)
        except:
            wait(signal, 800)


class UIThreadBridge(QObject):
    show_window = pyqtSignal()
    hide_window = pyqtSignal()
    restart_app = pyqtSignal()
    quit_app = pyqtSignal()
    wait_for_close = pyqtSignal()
    set_general = pyqtSignal(object)
    set_apps = pyqtSignal(object, bool, list, list)


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


def remove_pyuic_header(py_path):
    with open(py_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    lines = [
        line for line in lines
        if not line.startswith("# Form implementation generated from reading ui file")
    ]

    with open(py_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


class UI:
    def __init__(self, signal):
        self.signal = signal
        ui_files = ['main_interface']
        ui_paths = [os.path.join(os.path.dirname(os.path.realpath(__file__)), x + '.ui') for x in ui_files]
        py_paths = [os.path.join(os.path.dirname(os.path.realpath(__file__)), x + '.py') for x in ui_files]
        for i in range(len(ui_paths)):
            ui_path = ui_paths[i]
            py_path = py_paths[i]
            if os.path.exists(ui_path):
                os.system(f'pyuic5 -x {ui_path} -o {py_path}')
                remove_pyuic_header(py_path)

        from gui import main_interface

        app = QApplication(sys.argv)
        app.setStyleSheet(dark_stylesheet)
        MainWindow = QMainWindow()
        ui = main_interface.Ui_MainWindow()
        
        ui.app = app
        self.restart = False
        ui.main_window = MainWindow
        ui.main_window.setWindowFlags(Qt.WindowStaysOnTopHint)
        ui.size_to_reduce = 0
        icon = QIcon()
        icon.addPixmap(QPixmap(os.path.join(ICONS_FOLDER_PATH, "cyan_system_manager.ico")), QIcon.Normal, QIcon.Off)
        MainWindow.setWindowIcon(icon)
        
        drag_filter = WindowDragFilter(MainWindow)
        MainWindow.installEventFilter(drag_filter)

        self.bridge = UIThreadBridge()
        self.bridge.show_window.connect(self._show_window)
        self.bridge.hide_window.connect(self._hide_window)
        self.bridge.restart_app.connect(self._restart_app)
        self.bridge.quit_app.connect(self._quit_app)
        self.bridge.wait_for_close.connect(self._wait_for_close)
        self.bridge.set_general.connect(set_gen_layout)
        self.bridge.set_apps.connect(set_apps_layout)
        self.ui = ui

        self.tray = QSystemTrayIcon(QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons", "cyan_system_manager.ico")), app)
        menu = QMenu()
        menu.addAction("Show", self._show_window)
        # menu.addAction("Restart", self._restart_app)
        menu.addAction("Quit", self._quit_app)
        MainWindow.closeEvent = self._close_event
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.setToolTip("CyanManager")
        self.tray.show()
        self.setup_ui()
        self.uwp_map = self.signal.reg_functions.SHOW_UWP_APP_NAMES.run()
    
    def execute(self, function_, *args, **kwargs):
        f = getattr(self.bridge, function_)
        return f.emit(*args, **kwargs)

    def exit_sync(self, signal):
        signal.kill()
        self.ui.app.quit()

    def setup_ui(self):
        self.ui.setupUi(self.ui.main_window)
        
        # self.ui.loadingBar = QLabel()
        # movie = QMovie(os.path.join(ICONS_FOLDER_PATH, "spinner.gif"))  # Load a GIF of a spinner
        # self.ui.loadingBar.setMovie(movie)
        # movie.start()
        # self.ui.loadingBar.setVisible(False)
        # self.ui.application_view_layout.insertWidget(self.ui.application_view_layout.count() - 2, self.ui.loadingBar, alignment=Qt.AlignHCenter)
        # self.ui.exit.clicked.connect(lambda _=False: self.exit_sync(signal))
        self.ui.main_window.hide()

    def _close_event(self, event):
        event.ignore()
        self.ui.main_window.hide()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.ui.main_window.show()
            self.ui.main_window.activateWindow()

    def _wait_for_close(self):
        app = self.ui.app
        form_closed = app.exec_()
        return form_closed

    def _show_window(self):
        self.ui.main_window.show()

    def _hide_window(self):
        self.ui.main_window.hide()

    def start_gui_tasks(self):
        threading.Thread(target=gui_loop, args=(self.signal, )).start()

    def _quit_app(self):
        self.ui.main_window.closeEvent = None
        if self.tray:
            self.tray.hide()
            self.tray.deleteLater()
            self.tray = None
        self.ui.main_window.close()
        self.ui.main_window.deleteLater()
        self.ui.main_window = None
        self.ui.app.quit()
        print("App quit")

    def _restart_app(self):
        self.restart = True
        self._quit_app()


if __name__ == "__main__":
    pass