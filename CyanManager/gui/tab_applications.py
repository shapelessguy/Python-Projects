import ctypes
import os
import sys
import threading
import json
from functools import partial
from utils import pprint, Application
from PyQt5.QtWidgets import QWidget, QLabel, QPushButton, QHBoxLayout, QLineEdit, QComboBox, QCheckBox, QSizePolicy
from PyQt5.QtGui import QColor, QPainter, QIcon, QIntValidator
from PyQt5.QtCore import Qt, pyqtSignal
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


def set_applications(ui_manager, applications):
    ui_manager.signal.set_applications(applications)


def save_app_settings(ui_manager):
    global cur_application, new_application
    applications = ui_manager.signal.get_applications()
    handling_obj = cur_application if cur_application else new_application

    if cur_application:
        applications = [x for x in applications if x.loaded_name != handling_obj.loaded_name]
    else:
        if handling_obj.name == "" or handling_obj.name in [x.name for x in applications]:
            return
        applications = [x for x in applications if x.name != handling_obj.name]
    applications.append(handling_obj)
    set_applications(ui_manager, applications)


def remove_application(ui_manager):
    global cur_application
    applications = ui_manager.signal.get_applications()

    if cur_application:
        applications = [x for x in applications if x.loaded_name != cur_application.loaded_name]
        set_applications(ui_manager, applications)


cur_application = None
new_application = None
suspend_change_cb = False
previous_object_state = None
def on_change_controls(ui_manager, size_cmd):
    global cur_application
    this_prop, direction = size_cmd.split("_")
    if cur_application:
        for i in range(ui_manager.ui.application_area_layout.count()):
            item = ui_manager.ui.application_area_layout.itemAt(i)
            widget = item.widget()
            if isinstance(widget, ApplicationRow) and widget.application.name == cur_application.name:
                for w, prop in zip([widget.x_textbox, widget.y_textbox, widget.width_textbox, widget.height_textbox], ["x", "y", "width", "height"]):
                    if prop == this_prop:
                        app_num = widget.application.window_props[prop]
                        app_num += (1 if direction == "plus" else -1)
                        if size_cmd in ["width_minus", "height_minus"] and app_num == 0:
                            app_num += 1
                        w.setText(str(app_num))
        ui_manager.signal.reg_functions.ORDER.run_shortcut([cur_application.name])


def on_change_dynamical(ui_manager):
    try:
        global cur_application, new_application
        handling_obj = cur_application if cur_application else new_application
        ui_manager.ui.appproc_lbl.setText("ID:")
        ui_manager.ui.appproc.setVisible(True)
        ui_manager.ui.spacer.setVisible(False)
        if handling_obj.proc_type == "python":
            ui_manager.ui.appproc_lbl.setText("Script:")
        elif handling_obj.proc_type == "chrome":
            ui_manager.ui.appproc_lbl.setText("")
            ui_manager.ui.appproc.setVisible(False)
            ui_manager.ui.spacer.setVisible(True)
    except:
        import traceback
        print(traceback.format_exc())


def on_change(ui_manager):
    global cur_application, new_application, suspend_change_cb, previous_object_state
    if suspend_change_cb:
        return
    
    handling_obj = cur_application if cur_application else new_application
    handling_obj.name = ui_manager.ui.appname.text()
    handling_obj.window_kw = [x.strip() for x in ui_manager.ui.appinclude.toPlainText().split(",") if x.strip() != ""]
    handling_obj.excluded_kw = [x.strip() for x in ui_manager.ui.appexclude.toPlainText().split(",") if x.strip() != ""]
    handling_obj.proc_name = ui_manager.ui.appproc.text()
    handling_obj.proc_type = ui_manager.ui.proc_type.currentText()
    on_change_dynamical(ui_manager)
    handling_obj.path = ui_manager.ui.apppath.toPlainText()
    handling_obj.arguments = ui_manager.ui.appargs.text()
    handling_obj.runas = ui_manager.ui.runas.isChecked()
    handling_obj.startup = ui_manager.ui.startup.isChecked()
    
    cur_state = json.dumps(handling_obj.to_dict())
    if cur_state == previous_object_state:
        return
    previous_object_state = cur_state
    if cur_application is not None:
        save_app_settings(ui_manager)


def view_application(ui_manager, application=None):
    global cur_application, new_application, suspend_change_cb

    suspend_change_cb = True
    cur_application = application
    if cur_application:
        ui_manager.ui.app_name_lbl.setText(f"{cur_application.name}")
        ui_manager.ui.create_app_btn.setVisible(True)
        ui_manager.ui.remove_app_btn.setVisible(True)
        ui_manager.ui.add_app_btn.setVisible(False)
        handling_obj = cur_application
    else:
        ui_manager.ui.app_name_lbl.setText(f"Create application")
        ui_manager.ui.create_app_btn.setVisible(False)
        ui_manager.ui.remove_app_btn.setVisible(False)
        ui_manager.ui.add_app_btn.setVisible(True)
        new_application = Application("", [], [], "", "exe", "")
        handling_obj = new_application

    ui_manager.ui.appname.setText(handling_obj.name)
    ui_manager.ui.appinclude.setPlainText(", ".join(handling_obj.window_kw))
    ui_manager.ui.appexclude.setPlainText(", ".join(handling_obj.excluded_kw))
    ui_manager.ui.appproc.setText(handling_obj.proc_name)
    ui_manager.ui.proc_type.setCurrentText(handling_obj.proc_type)
    on_change_dynamical(ui_manager)
    ui_manager.ui.apppath.setPlainText(handling_obj.path)
    ui_manager.ui.appargs.setText(handling_obj.arguments)
    ui_manager.ui.runas.setChecked(handling_obj.runas)
    ui_manager.ui.startup.setChecked(handling_obj.startup)

    suspend_change_cb = False
    highlight(ui_manager, cur_application)


def on_win_pos_value_committed(app_row, application):
    global suspend_change_cb
    if not suspend_change_cb:
        ui_manager = app_row.ui_manager
        pos_widgets = [app_row.x_textbox, app_row.y_textbox, app_row.width_textbox, app_row.height_textbox]
        applications = ui_manager.signal.get_applications()
        cur_application = [x for x in applications if x.name == application.name][0]
        order = app_row.order_checkbox.isChecked()
        app_row.application = cur_application
        cur_application.window_props["order"] = order
        cur_application.window_props["monitor_id"] = app_row.screen_combobox.currentText()
        cur_application.window_props["win_state"] = app_row.win_state_combobox.currentText()
        app_row.screen_combobox.setEnabled(order)
        app_row.win_state_combobox.setEnabled(order)
        for w, prop in zip(pos_widgets, ["x", "y", "width", "height"]):
            w.setEnabled(order)
            if w.hasAcceptableInput():
                cur_application.window_props[prop] = int(w.text())
        set_applications(ui_manager, applications)
        return cur_application



class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ApplicationRow(QWidget):
    def __init__(self, ui_manager, application, parent=None):
        super().__init__(parent)
        self.ui_manager = ui_manager
        self.application = application
        self.dot = StatusDot("green" if (application.process or application.window) else "red")
        self.label = ClickableLabel(application.name)
        self.label.setMinimumWidth(150)
        self.label.setMaximumWidth(150)
        self.start_btn = QPushButton("Start")
        self.start_btn.setMinimumWidth(40)
        self.kill_btn = QPushButton("Kill")
        self.kill_btn.setMinimumWidth(40)

        self.order_checkbox = QCheckBox("ON")
        self.screen_combobox = QComboBox()
        self.x_textbox = QLineEdit()
        self.y_textbox = QLineEdit()
        self.width_textbox = QLineEdit()
        self.height_textbox = QLineEdit()
        self.win_state_combobox = QComboBox()

        def on_value_committed(highlight_=False):
            cur_app = on_win_pos_value_committed(self, application)
            if cur_app and highlight_:
                highlight(ui_manager, cur_app)

        ui_manager.ui.appname.textChanged.connect(partial(on_change, ui_manager))
        ui_manager.ui.appinclude.textChanged.connect(partial(on_change, ui_manager))
        ui_manager.ui.appexclude.textChanged.connect(partial(on_change, ui_manager))
        ui_manager.ui.appproc.textChanged.connect(partial(on_change, ui_manager))
        ui_manager.ui.proc_type.currentTextChanged.connect(partial(on_change, ui_manager))
        ui_manager.ui.apppath.textChanged.connect(partial(on_change, ui_manager))
        ui_manager.ui.appargs.textChanged.connect(partial(on_change, ui_manager))
        ui_manager.ui.runas.toggled.connect(partial(on_change, ui_manager))
        ui_manager.ui.startup.toggled.connect(partial(on_change, ui_manager))

        self.set_monitors()
        self.set_values()
        self.win_state_combobox.addItems(["normal", "minimized", "maximized", "hidden"])
        self.order_checkbox.setChecked(application.window_props["order"])

        self.win_state_combobox.setCurrentText(self.application.window_props["win_state"])
        for w, size in zip([self.screen_combobox, self.win_state_combobox], [90, 70]):
            w.setMinimumWidth(size)
            w.setMaximumWidth(size)
        
        for w, prop in zip([self.x_textbox, self.y_textbox, self.width_textbox, self.height_textbox], ["x", "y", "width", "height"]):
            w.setEnabled(application.window_props["order"])
            w.setMinimumWidth(40)
            w.setPlaceholderText(f"{prop}...")
            w.setAlignment(Qt.AlignCenter)
            w.setValidator(QIntValidator(-10_000, 10_000))
            w.textChanged.connect(on_value_committed)

        self.order_checkbox.toggled.connect(lambda _: on_value_committed(True))
        self.screen_combobox.setEnabled(application.window_props["order"])
        self.screen_combobox.currentTextChanged.connect(on_value_committed)
        self.win_state_combobox.setEnabled(application.window_props["order"])
        self.win_state_combobox.currentTextChanged.connect(on_value_committed)

        def start_app():
            threading.Thread(target=ui_manager.signal.reg_functions.STARTUP.run_shortcut, args=([application.name], )).start()
        self.start_btn.clicked.connect(start_app)

        def kill_app():
            threading.Thread(target=ui_manager.signal.reg_functions.KILL_APP.run_shortcut, args=(application, )).start()
        self.kill_btn.clicked.connect(kill_app)

        def view_app():
            view_application(ui_manager, self.application)
        self.label.clicked.connect(view_app)

        self.icon_label = QLabel()
        exe_path = self.ui_manager.signal.exe_map.get(application.name, application.path)
        icon = icon_from_exe(exe_path)

        if icon:
            self.icon_label.setPixmap(icon.pixmap(16, 16))
            self.icon_label.setMinimumWidth(16)
            self.icon_label.setMaximumWidth(16)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        layout.addWidget(self.dot)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.kill_btn)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.label)
        layout.addStretch()
        layout.addWidget(self.order_checkbox)
        layout.addWidget(self.screen_combobox)
        for w in [self.x_textbox, self.y_textbox, self.width_textbox, self.height_textbox]:
            layout.addWidget(w)
        layout.addWidget(self.win_state_combobox)
        layout.addStretch()
        self.setMaximumHeight(24)
    
    def set_background(self, color):
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet(f"background: {color};")
    
    def set_values(self):
        global suspend_change_cb
        suspend_change_cb = True
        for w, prop in zip([self.screen_combobox, self.win_state_combobox], ["monitor_id", "win_state"]):
            w.setCurrentText(self.application.window_props[prop])
        for w, prop in zip([self.x_textbox, self.y_textbox, self.width_textbox, self.height_textbox], ["x", "y", "width", "height"]):
            app_num = self.application.window_props[prop]
            w.setText(str(app_num))
        suspend_change_cb = False
    
    def set_monitors(self, monitors: list=[]):
        combo = self.screen_combobox

        monitor_ids = {m._id for m in monitors}
        monitor_ids.add(self.application.window_props["monitor_id"])
        ordered = sorted(monitor_ids, key=str)

        combo.blockSignals(True)
        combo.clear()
        combo.addItems(ordered)
        combo.setCurrentText(self.application.window_props["monitor_id"])
        combo.blockSignals(False)


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def save_app_position(ui_manager):
    global cur_application
    applications: list[Application] = ui_manager.signal.get_applications()
    positions = ui_manager.signal.reg_functions.GET_WIN_POSITIONS.run_shortcut()
    for app in applications:
        if cur_application and app.name == cur_application.name:
            cur_application = app
        if app.window_props["order"] and app.name in positions:
            app_props = positions[app.name]
            app.window_props = {**app.window_props, **app_props}
    set_values(ui_manager, applications)
    set_applications(ui_manager, applications)


def build_layout(ui_manager, apps):
    global cur_application
    pprint("building app layout...")
    clear_layout(ui_manager.ui.application_area_layout)
    def create_app():
        view_application(ui_manager)
    def add_app():
        save_app_settings(ui_manager)
    def remove_app():
        remove_application(ui_manager)
    ui_manager.ui.create_app_btn.clicked.connect(create_app)
    ui_manager.ui.add_app_btn.clicked.connect(add_app)
    ui_manager.ui.remove_app_btn.clicked.connect(remove_app)

    ui_manager.ui.x_plus.clicked.connect(partial(on_change_controls, ui_manager, "x_plus"))
    ui_manager.ui.x_minus.clicked.connect(partial(on_change_controls, ui_manager, "x_minus"))
    ui_manager.ui.y_plus.clicked.connect(partial(on_change_controls, ui_manager, "y_plus"))
    ui_manager.ui.y_minus.clicked.connect(partial(on_change_controls, ui_manager, "y_minus"))
    ui_manager.ui.width_plus.clicked.connect(partial(on_change_controls, ui_manager, "width_plus"))
    ui_manager.ui.width_minus.clicked.connect(partial(on_change_controls, ui_manager, "width_minus"))
    ui_manager.ui.height_plus.clicked.connect(partial(on_change_controls, ui_manager, "height_plus"))
    ui_manager.ui.height_minus.clicked.connect(partial(on_change_controls, ui_manager, "height_minus"))

    def save_app_pos():
        save_app_position(ui_manager)
    ui_manager.ui.save_current_positions.clicked.connect(save_app_pos)

    for application in apps:
        if application.equals(cur_application):
            view_application(ui_manager, application)
        row = ApplicationRow(ui_manager, application)
        ui_manager.ui.application_area_layout.addWidget(row)
    ui_manager.ui.application_area_layout.addStretch()
    for application in apps:
        highlight(ui_manager, application)


def set_values(ui_manager, apps):
    for i in range(ui_manager.ui.application_area_layout.count()):
        item = ui_manager.ui.application_area_layout.itemAt(i)
        widget = item.widget()

        if isinstance(widget, ApplicationRow):
            for app in apps:
                if widget.application.name == app.name:
                    widget.application = app
                    widget.set_values()


def change_states(ui_manager, apps, monitors):
    for i in range(ui_manager.ui.application_area_layout.count()):
        item = ui_manager.ui.application_area_layout.itemAt(i)
        widget = item.widget()

        if isinstance(widget, ApplicationRow):
            for app in apps:
                if widget.application.name == app.name:
                    widget.application = app
                    widget.set_monitors(monitors)
                    widget.dot.setColor("green" if (app.process or app.window) else "red")
                    break


def set_dark_background_recursive(w, color):
    if isinstance(w, (QLineEdit, QComboBox)):
        w.setStyleSheet(f"background-color: {color};")
    for child in w.findChildren(QWidget):
        set_dark_background_recursive(child, color)


def highlight(ui_manager, app):
    global cur_application
    for i in range(ui_manager.ui.application_area_layout.count()):
        item = ui_manager.ui.application_area_layout.itemAt(i)
        widget = item.widget()

        if isinstance(widget, ApplicationRow):
            if app and cur_application and widget.application.name == cur_application.name:
                widget.set_background("#1b696e")
            else:
                widget.set_background("transparent")
                if not widget.application.window_props["order"]:
                    set_dark_background_recursive(widget, "#1d1d1d")
                else:
                    set_dark_background_recursive(widget, "transparent")

prev_app_names = []
def set_apps_layout(ui_manager, force_layout_build, apps, monitors):
    global prev_app_names

    app_names = [x.name for x in apps]
    if force_layout_build or len(app_names) != len(prev_app_names) or any([x not in prev_app_names for x in app_names]):
        prev_app_names = app_names
        build_layout(ui_manager, apps)
    change_states(ui_manager, apps, monitors)
