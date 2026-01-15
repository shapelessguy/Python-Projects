import os
import sys
from gui.theme import dark_stylesheet
from PyQt5.QtCore import QObject, Qt
from PyQt5.QtWidgets import QMainWindow, QApplication, QSystemTrayIcon, QMenu
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QIcon


class UIThreadBridge(QObject):
    show_window = pyqtSignal()
    hide_window = pyqtSignal()
    restart_app = pyqtSignal()
    quit_app = pyqtSignal()


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


class UI:
    def __init__(self):
        ui_files = ['main_interface']
        ui_paths = [os.path.join(os.path.dirname(os.path.realpath(__file__)), x + '.ui') for x in ui_files]
        py_paths = [os.path.join(os.path.dirname(os.path.realpath(__file__)), x + '.py') for x in ui_files]
        for i in range(len(ui_paths)):
            ui_path = ui_paths[i]
            py_path = py_paths[i]
            if os.path.exists(ui_path):
                os.system(f'pyuic5 -x {ui_path} -o {py_path}')

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
        
        drag_filter = WindowDragFilter(MainWindow)
        MainWindow.installEventFilter(drag_filter)

        self.bridge = UIThreadBridge()
        self.bridge.show_window.connect(self._show_window)
        self.bridge.hide_window.connect(self._hide_window)
        self.bridge.restart_app.connect(self._restart_app)
        self.bridge.quit_app.connect(self._quit_app)
        self.ui = ui

        self.tray = QSystemTrayIcon(QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons", "cyan_system_manager.ico")), app)
        menu = QMenu()
        menu.addAction("Show", self._show_window)
        menu.addAction("Restart", self._restart_app)
        menu.addAction("Quit", self._quit_app)
        MainWindow.closeEvent = self._close_event
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.setToolTip("CyanManager")
        self.tray.show()
    
    def execute(self, function_, *args, **kwargs):
        f = getattr(self.bridge, function_)
        return f.emit(*args, **kwargs)

    def exit_sync(self, signal):
        signal.kill()
        self.ui.app.quit()

    def setup_ui(self, signal):
        self.ui.setupUi(self.ui.main_window)
        # self.ui.exit.clicked.connect(lambda _=False: self.exit_sync(signal))

    def _close_event(self, event):
        event.ignore()
        self.ui.main_window.hide()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.ui.main_window.show()
            self.ui.main_window.activateWindow()

    def resize_window(self):
        width = 468
        height = 210
        
        # self.ui.main_window.resize(width, height)
        # screen_geometry = self.ui.app.primaryScreen().availableGeometry()
        # x = screen_geometry.width() - width - 4
        # y = screen_geometry.height() - height - 1
        # self.ui.main_window.move(x, y)
        self.ui.main_window.hide()

    def wait_for_close(self, _=None):
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

    def _restart_app(self):
        self.restart = True
        self.tray.deleteLater()
        self._quit_app()


if __name__ == "__main__":
    pass