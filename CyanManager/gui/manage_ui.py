"""What CyanManager keeps of Qt: the tray icon, the notifications drawn on every
screen and the shutdown hook (session_end.py). Its window is a web page now
(gui/web.py, web_ui/): the tray icon opens it in the browser.
"""
import os
import sys
import threading
import random
import time
import webbrowser
from screeninfo import get_monitors
from gui import web
from gui.app_icons import icon_png, _start_menu_ids
from gui.session_end import SessionEndFilter
from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QWidget, QGraphicsScene
from PyQt5.QtGui import QIcon, QPixmap
from utils import ICONS_FOLDER_PATH



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


TRAY_MENU_STYLE = """
QMenu {
    background: #151a20;
    color: #e7ebf0;
    border: 1px solid #333d4a;
    border-radius: 10px;
    padding: 6px;
    font-family: "Segoe UI Variable Text", "Segoe UI";
    font-size: 10pt;
}
QMenu::item {
    padding: 7px 28px 7px 14px;
    border-radius: 6px;
    background: transparent;
}
QMenu::item:selected {
    background: rgba(46, 196, 214, 0.16);
    color: #5fdcea;
}
QMenu::separator {
    height: 1px;
    background: #262e39;
    margin: 5px 8px;
}
"""


class UIThreadBridge(QObject):
    show_window = pyqtSignal()
    restart_app = pyqtSignal()
    quit_app = pyqtSignal()
    wait_for_close = pyqtSignal()
    show_notification = pyqtSignal(str, str, str, int)
    hide_notification = pyqtSignal()
    render_icon = pyqtSignal(object)  # {"application", "exe"} -> fills "png", on the GUI thread


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
        ui_files = ['notifications']
        for name in ui_files:
            ui_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), name + '.ui')
            py_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), name + '.py')
            if os.path.exists(ui_path):
                os.system(f'pyuic5 -x {ui_path} -o {py_path}')
                remove_pyuic_header(py_path)

        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)  # no window: the tray's Quit ends it
        self.restart = False
        self.follow_notif_id = None
        self.notification_pool = []
        self.icon_lock = threading.Lock()

        self.bridge = UIThreadBridge()
        self.bridge.show_window.connect(self._show_window)
        self.bridge.restart_app.connect(self._restart_app)
        self.bridge.quit_app.connect(self._quit_app)
        self.bridge.wait_for_close.connect(self._wait_for_close)
        self.bridge.show_notification.connect(self._show_notification)
        self.bridge.hide_notification.connect(self._hide_notification)
        self.bridge.render_icon.connect(self._render_icon, Qt.BlockingQueuedConnection)

        # Windows only sends the session-end messages to windows that exist natively, even hidden ones
        self.native_window = QWidget()
        self.native_window.winId()
        self.session_end_filter = SessionEndFilter(self.signal)
        self.app.installNativeEventFilter(self.session_end_filter)
        self.app.aboutToQuit.connect(self.session_end_filter.turn_off)

        self.tray = QSystemTrayIcon(QIcon(os.path.join(ICONS_FOLDER_PATH, "cyan_system_manager.ico")), self.app)
        # The page's colours (web_ui/src/styles.css). Frameless and translucent so the corners can be round.
        self.tray_menu = QMenu()
        self.tray_menu.setWindowFlags(self.tray_menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.tray_menu.setAttribute(Qt.WA_TranslucentBackground)
        self.tray_menu.setStyleSheet(TRAY_MENU_STYLE)
        self.tray_menu.addAction("Show", self._show_window)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction("Quit", self._quit_app)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.setToolTip("CyanManager")
        self.tray.show()

    def execute(self, function_, *args, **kwargs):
        f = getattr(self.bridge, function_)
        return f.emit(*args, **kwargs)

    def app_icon_png(self, application, mapped_exe):
        """An application's icon as PNG bytes; from any thread but the GUI's."""
        _start_menu_ids()  # PowerShell, up to seconds: not on the GUI thread
        job = {"application": application, "exe": mapped_exe, "png": None}
        with self.icon_lock:
            self.execute("render_icon", job)
        return job["png"]

    def _render_icon(self, job):
        try:
            job["png"] = icon_png(job["application"], job["exe"])
        except Exception as e:
            print(f"Icon of {job['application'].name} not drawn: {e.__class__.__name__} - {e}")

    def notif_timout(self, timeout, notification_id):
        time.sleep(timeout)
        if self.follow_notif_id == notification_id:
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
        self.follow_notif_id = random_id
        threading.Thread(target=self.notif_timout, args=(timeout, random_id)).start()

    def _hide_notification(self):
        for notif in self.notification_pool:
            notif.form.hide()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._show_window()

    def _wait_for_close(self):
        return self.app.exec_()

    def _show_window(self):
        webbrowser.open(web.url())

    def start_gui_tasks(self):
        web.start(self.signal, self)

    def _quit_app(self):
        if self.tray:
            self.tray.hide()
            self.tray.deleteLater()
            self.tray = None
        self.app.quit()
        print("App quit")

    def _restart_app(self):
        self.restart = True
        self._quit_app()


if __name__ == "__main__":
    pass