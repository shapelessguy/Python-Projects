import ctypes
import os
import sys
from PyQt5.QtWidgets import QWidget, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtGui import QColor, QPainter, QIcon, QPixmap
from PyQt5.QtCore import Qt
from PyQt5.QtWinExtras import QtWin


class StatusDot(QWidget):
    def __init__(self, color="red", parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(12, 12)

    def setColor(self, color):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, self.width(), self.height())


def icon_from_exe(exe_path):
    DEFAULT_ICON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons", "app.ico")
    if not exe_path or not os.path.exists(exe_path):
        return QIcon(DEFAULT_ICON_PATH)
    
    large, small = ctypes.c_void_p(), ctypes.c_void_p()
    num_icons = ctypes.windll.shell32.ExtractIconExW(
        exe_path, 0,
        ctypes.byref(large),
        ctypes.byref(small),
        1
    )

    if num_icons == 0 or (large.value is None and small.value is None):
        return QIcon(DEFAULT_ICON_PATH)

    hicon = large.value or small.value
    try:
        pixmap = QtWin.fromHICON(hicon)
        return QIcon(pixmap)
    finally:
        ctypes.windll.user32.DestroyIcon(hicon)


class ApplicationRow(QWidget):
    def __init__(self, ui_manager, application, parent=None):
        super().__init__(parent)
        self.ui_manager = ui_manager
        self.application = application
        self.dot = StatusDot("green" if application.process else "red")
        self.label = QLabel(application.name)
        self.start_btn = QPushButton("Start")
        self.start_btn.setMinimumWidth(60)
        self.kill_btn = QPushButton("Kill")
        self.kill_btn.setMinimumWidth(60)
        self.kill_btn2 = QPushButton("Kill")
        self.kill_btn2.setMinimumWidth(200)

        def start_app():
            ui_manager.signal.reg_functions.STARTUP.run(application)
        self.start_btn.clicked.connect(start_app)

        def kill_app():
            ui_manager.signal.reg_functions.KILL_APP.run(application)
        self.kill_btn.clicked.connect(kill_app)

        self.icon_label = QLabel()
        icon = icon_from_exe(sys.executable if application.proc_name.startswith("python:") else application.path)

        if icon:
            self.icon_label.setPixmap(icon.pixmap(16, 16))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        layout.addWidget(self.dot)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.kill_btn)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.label)
        layout.addStretch()
        layout.addWidget(self.kill_btn2)
        self.setMaximumHeight(24)


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def build_layout(ui_manager, apps):
    clear_layout(ui_manager.ui.application_area_layout)
    for application in apps:
        row = ApplicationRow(ui_manager, application)
        ui_manager.ui.application_area_layout.addWidget(row)
    ui_manager.ui.application_area_layout.addStretch()


def change_states(ui_manager, apps):
    for i in range(ui_manager.ui.application_area_layout.count()):
        item = ui_manager.ui.application_area_layout.itemAt(i)
        widget = item.widget()

        if isinstance(widget, ApplicationRow):
            for app in apps:
                if widget.application.name == app.name:
                    widget.application = app
                    widget.dot.setColor("green" if app.process else "red")
                    break


prev_app_names = []
def set_apps_layout(ui_manager, apps):
    global prev_app_names
    app_names = [x.name for x in apps]
    if len(app_names) != prev_app_names or any([x not in prev_app_names for x in app_names]):
        prev_app_names = app_names
        build_layout(ui_manager, apps)
    else:
        change_states(ui_manager, apps)
