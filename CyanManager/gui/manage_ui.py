import os
import sys
import threading
import json
import random
import time
from screeninfo import get_monitors
from gui.theme import dark_stylesheet
from gui.tab_general import set_gen_layout
from gui.tab_applications import set_apps_layout
from PyQt5.QtCore import QObject, pyqtSignal, Qt, QSize
from PyQt5.QtWidgets import QMainWindow, QApplication, QSystemTrayIcon, QMenu, QWidget, QTextEdit, QVBoxLayout, QPushButton, QGraphicsScene
from PyQt5.QtGui import QIcon, QPixmap
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
                wait(signal, 500)
            else:
                visibility_change = prev_visible
                prev_visible = False
                wait(signal, 100)
        except:
            wait(signal, 800)


previous_t_state = ""
def get_thread_status(signal):
    global previous_t_state
    while signal.is_alive():
        status = {k: v.is_alive() for k, v in signal.thread_managers.items()}
        if json.dumps(status) != previous_t_state:
            previous_t_state = json.dumps(status)
            signal.ui_manager.execute("set_thread_status", status)
        wait(signal, 500)


def terminal_loop(signal):
    while signal.is_alive():
        while signal.is_alive() and not signal.log_queue.empty():
            signal.ui_manager.execute("push_to_terminal", signal.log_queue.get().rstrip())
        wait(signal, 50)


def create_notification_form():
    from gui import notifications
    Form = QWidget()
    
    Form.setWindowFlags(
        Qt.FramelessWindowHint |
        Qt.WindowStaysOnTopHint |
        Qt.Tool
    )
    Form.setAttribute(Qt.WA_TranslucentBackground)
    Form.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    
    ui = notifications.Ui_Form()
    ui.form = Form
    ui.setupUi(Form)
    Form.setStyleSheet("""
        background: rgba(0, 0, 0, 180);
        border-radius: 20px;
    """)
    lbl_stylesheet = """
        background: transparent;
        color: white;
        text-align: center;
    """
    ui.title.setStyleSheet(lbl_stylesheet + "padding: 0 20px 0 20px;")
    ui.message.setStyleSheet(lbl_stylesheet + "padding: 0 20px 0 20px;")
    ui.icon_path = None

    scene = QGraphicsScene()
    ui.graphicsView.setStyleSheet("background: transparent;")
    ui.graphicsView.setScene(scene)
    ui.graphicsView.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    ui.graphicsView.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def set_data(title, message, icon_path):
        ui.title.setText(f"{title}")
        ui.message.setText(f"{message}")
        if icon_path and ui.icon_path != icon_path:
            ui.icon_path = icon_path
            pixmap = QPixmap(icon_path)
            scene.clear()
            item = scene.addPixmap(pixmap)
            scene.setSceneRect(item.boundingRect())
            ui.graphicsView.resetTransform()
            ui.graphicsView.fitInView(scene.sceneRect(), Qt.KeepAspectRatio)
            ui.graphicsView.centerOn(scene.sceneRect().center())

    ui.set_data = set_data
    return ui


class UIThreadBridge(QObject):
    show_window = pyqtSignal()
    hide_window = pyqtSignal()
    restart_app = pyqtSignal()
    quit_app = pyqtSignal()
    wait_for_close = pyqtSignal()
    set_general = pyqtSignal(object)
    push_to_terminal = pyqtSignal(str)
    set_thread_status = pyqtSignal(object)
    show_notification = pyqtSignal(str, str, str, int)
    hide_notification = pyqtSignal()
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


class TerminalWindow(QWidget):
    def __init__(self, parent=None, title="Terminal"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setGeometry(200, 200, 600, 400)

        icon = QIcon()
        icon.addPixmap(QPixmap(os.path.join(ICONS_FOLDER_PATH, "cyan_system_manager.ico")), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        self.text_edit = QTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.document().setMaximumBlockCount(200)
        layout = QVBoxLayout()
        layout.addWidget(self.text_edit)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.text_edit.clear)
        layout.addWidget(clear_btn)

        self.setLayout(layout)

    def append_text(self, text: str):
        """Public method to add text from anywhere"""
        self.text_edit.append(text)
        self.text_edit.ensureCursorVisible()

    def set_text(self, text: str):
        self.text_edit.setPlainText(text)
        
    def closeEvent(self, event):
        event.ignore()
        self.hide()
        return


class UI:
    def __init__(self, signal):
        self.signal = signal
        ui_files = ['main_interface', 'notifications']
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
        ui.size_to_reduce = 0
        icon = QIcon()
        icon.addPixmap(QPixmap(os.path.join(ICONS_FOLDER_PATH, "cyan_system_manager.ico")), QIcon.Normal, QIcon.Off)
        MainWindow.setWindowIcon(icon)

        self.bridge = UIThreadBridge()
        self.bridge.show_window.connect(self._show_window)
        self.bridge.hide_window.connect(self._hide_window)
        self.bridge.restart_app.connect(self._restart_app)
        self.bridge.quit_app.connect(self._quit_app)
        self.bridge.wait_for_close.connect(self._wait_for_close)
        self.bridge.set_general.connect(set_gen_layout)
        self.bridge.set_apps.connect(set_apps_layout)
        self.bridge.set_thread_status.connect(self._set_thread_status)
        self.bridge.push_to_terminal.connect(self._push_to_terminal)
        self.bridge.show_notification.connect(self._show_notification)
        self.bridge.hide_notification.connect(self._hide_notification)
        self.ui = ui

        self.tray = QSystemTrayIcon(QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons", "cyan_system_manager.ico")), app)
        menu = QMenu()
        menu.addAction("Show", self._show_window)
        menu.addAction("Quit", self._quit_app)
        MainWindow.closeEvent = self._close_event
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.setToolTip("CyanManager")
        self.tray.show()
        self.setup_ui()
        self.notification_pool = []
        self.uwp_map = self.signal.reg_functions.SHOW_UWP_APP_NAMES.run()
    
    def execute(self, function_, *args, **kwargs):
        f = getattr(self.bridge, function_)
        return f.emit(*args, **kwargs)
    
    def open_terminal(self):
        if not self.terminal_window.isVisible():
            self.terminal_window.setVisible(True)
            self.terminal_window.activateWindow()

    def exit_sync(self, signal):
        signal.kill()
        self.ui.app.quit()

    def setup_ui(self):
        self.ui.setupUi(self.ui.main_window)
        
        for btn_info in [
            {"name": "showTerminal", "icon": "terminal.png", "tooltip": "Open terminal"},
            {"name": "x_plus", "icon": "right.png", "tooltip": "Move right"},
            {"name": "x_minus", "icon": "left.png", "tooltip": "Move left"},
            {"name": "y_plus", "icon": "down.png", "tooltip": "Move down"},
            {"name": "y_minus", "icon": "up.png", "tooltip": "Move up"},
            {"name": "width_plus", "icon": "big.png", "tooltip": "Increase width"},
            {"name": "width_minus", "icon": "small.png", "tooltip": "Decrease width"},
            {"name": "height_plus", "icon": "big.png", "tooltip": "Increase height"},
            {"name": "height_minus", "icon": "small.png", "tooltip": "Decrease height"},
            ]:
            btn = getattr(self.ui, btn_info["name"])
            btn.setIcon(QIcon(os.path.join(ICONS_FOLDER_PATH, btn_info["icon"])))
            btn.setIconSize(QSize(20, 20))
            btn.setToolTip(btn_info["tooltip"])

        self.terminal_window = TerminalWindow()
        self.terminal_window.setVisible(False)
        self.ui.showTerminal.clicked.connect(self.open_terminal)
        self.ui.main_window.hide()

    def _close_event(self, event):
        event.ignore()
        self.ui.main_window.hide()
    
    def _push_to_terminal(self, line):
        if line == "":
            return
        self.terminal_window.text_edit.insertPlainText(f"{line}\n")
    
    def notif_timout(self, timeout, notification_id):
        time.sleep(timeout)
        if self.ui.follow_notif_id == notification_id:
            self.execute("hide_notification")
    
    def _show_notification(self, title, message, icon_path, timeout):
        random_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=10))
        monitors = get_monitors()

        if len(monitors) > len(self.notification_pool):
            for _ in range(len(monitors) - len(self.notification_pool)):
                self.notification_pool.append(create_notification_form())

        for notif in self.notification_pool:
            notif.set_data(title, message, icon_path)

        for i, notif in enumerate(self.notification_pool):
            screen = monitors[i % len(monitors)]
            notif.form.move(screen.x + 10, screen.y + 10)
            notif.form.show()
        self.ui.follow_notif_id = random_id
        threading.Thread(target=self.notif_timout, args=(timeout, random_id)).start()
    
    def _hide_notification(self):
        for notif in self.notification_pool:
            notif.form.hide()
    
    def _set_thread_status(self, status):
        if hasattr(self.ui, "serviceItems"):
            for t_name, service_attr in self.ui.serviceItems.items():
                if t_name in status:
                    service_attr.set_status(status[t_name])

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
        threading.Thread(target=terminal_loop, args=(self.signal, )).start()
        threading.Thread(target=gui_loop, args=(self.signal, )).start()
        threading.Thread(target=get_thread_status, args=(self.signal, )).start()

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