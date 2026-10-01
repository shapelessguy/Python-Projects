import keyring
import threading
import service_deps
from utils import Thread
from functools import partial
from PyQt5.QtCore import QTime, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTimeEdit, QCheckBox, QComboBox,
    QLineEdit, QFormLayout, QGroupBox, QPushButton, QLabel, QSizePolicy
)
suspend_change = True


class FunctionItemWidget(QWidget):
    def __init__(self, ui_manager, display_name, function, parent=None):
        super().__init__(parent)

        self.function = function
        self.ui_manager = ui_manager
        self.display_text = display_name

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(2)

        self.label = QLabel(self.display_text, self)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.button = QPushButton("Run", self)
        self.button.setFixedWidth(80)
        self.button.setToolTip(f"Execute: {self.display_text}")

        layout.addWidget(self.label)
        layout.addWidget(self.button)
        self.button.clicked.connect(self._on_run_clicked)
        self.setMinimumHeight(26)
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)

    def _on_run_clicked(self):
        getattr(self.ui_manager.signal.reg_functions, self.display_text).run_shortcut()


class ServiceItemWidget(QWidget):
    # From the install thread to the GUI thread: (ok, error)
    install_done = pyqtSignal(bool, str)

    def __init__(self, thread_manager, threads: list[Thread], parent=None):
        super().__init__(parent)
        
        ui_manager = thread_manager.signal.ui_manager
        self.thread_manager = thread_manager
        self.installing = False
        self.setObjectName(f"service_{thread_manager.name.replace(' ', '_')}")
        
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)
        
        group = QGroupBox(thread_manager.name.replace("&", "&&"))  # a lone & would be a shortcut marker
        group_layout = QVBoxLayout()
        group.setLayout(group_layout)
        main_layout.addWidget(group)
        
        header_layout = QHBoxLayout()
        self.status_lbl = QLabel("Unkwnown")
        self.set_status(False)
        
        # A service whose requirements are not installed (service_deps.py) can
        # only be installed: it is saved as disabled, and enabled once installed.
        installed = thread_manager.installed()
        self.enabled_checkbox = QCheckBox("Enabled")
        enabled = [x.enabled for x in threads if x.name == thread_manager.name]
        self.enabled_checkbox.setChecked(installed and (enabled[0] if len(enabled) > 0 else True))
        self.enabled_checkbox.setEnabled(installed)
        def isEnabled():
            return self.enabled_checkbox.isChecked()
        self.enabled_widget = isEnabled
        def onEnabling():
            saveThreads(ui_manager)
            if self.enabled_checkbox.isChecked() and not thread_manager.is_alive():
                thread_manager.start()
            elif not self.enabled_checkbox.isChecked() and thread_manager.is_alive():
                thread_manager.kill()
                thread_manager.join()
        self.enabled_checkbox.toggled.connect(onEnabling)

        header_layout.addWidget(self.enabled_checkbox)
        if not installed:
            self.install_button = QPushButton("Install dependencies")
            self.install_button.setToolTip(f"pip install -r services/{thread_manager.module}/requirements.txt")
            self.install_button.clicked.connect(partial(self._on_install_clicked, ui_manager))
            self.install_done.connect(partial(self._on_install_done, ui_manager))
            header_layout.addWidget(self.install_button)
        header_layout.addStretch()
        header_layout.addWidget(self.status_lbl)
        
        group_layout.addLayout(header_layout)
        
        params_layout = QFormLayout()
        params_layout.setLabelAlignment(Qt.AlignRight)
        params_layout.setFormAlignment(Qt.AlignLeft)
        params_layout.setSpacing(8)
        
        self.param_widgets = {}
        if not installed:
            # Its PARAMETERS are unknown until it is imported: keep what the profile has.
            saved = [x.parameters for x in threads if x.name == thread_manager.name]
            for k, v in (saved[0] if saved else {}).items():
                self.param_widgets[k] = lambda v=v: v
        for k, param in thread_manager.parameters.items():
            param_values = [p_value for x in threads if x.name == thread_manager.name for p_name, p_value in x.parameters.items() if p_name == k]
            value = param_values[0] if len(param_values) > 0 else param.default

            if param.type == QLineEdit:
                edit = QLineEdit(value)
                params_layout.addRow(k.capitalize() + ":", edit)
                self.param_widgets[k] = lambda edit=edit: edit.text()
                edit.textChanged.connect(lambda _, ui_manager=ui_manager: saveThreads(ui_manager))

            elif param.type == QTimeEdit:
                edit = QTimeEdit()
                if value:
                    edit.setTime(QTime.fromString(value, "HH:mm"))
                edit.setDisplayFormat("HH:mm")
                params_layout.addRow(k.capitalize() + ":", edit)
                self.param_widgets[k] = lambda edit=edit: edit.time().toString("HH:mm")
                edit.timeChanged.connect(lambda _, ui_manager=ui_manager: saveThreads(ui_manager))
            
            elif param.type == QCheckBox:
                checkbox = QCheckBox(k.capitalize())
                checkbox.setChecked(value)
                params_layout.addRow(checkbox)
                self.param_widgets[k] = lambda cb=checkbox: cb.isChecked()
                checkbox.stateChanged.connect(lambda _, ui_manager=ui_manager: saveThreads(ui_manager))
            
            elif param.type == QComboBox:
                combo = QComboBox()
                combo.addItems(param.categ)
                if value in param.categ:
                    combo.setCurrentText(value)
                params_layout.addRow(k.capitalize() + ":", combo)
                self.param_widgets[k] = lambda cb=combo: cb.currentText()
                combo.currentTextChanged.connect(lambda _, ui_manager=ui_manager: saveThreads(ui_manager))
        
        group_layout.addLayout(params_layout)
    
    def _on_install_clicked(self, ui_manager):
        self.installing = True
        self.install_button.setEnabled(False)
        self.install_button.setText("Installing...")
        self.status_lbl.setText("Installing")
        self.status_lbl.setStyleSheet("color: orange")
        signal, module = ui_manager.signal, self.thread_manager.module

        def run():
            try:
                ok, error = service_deps.install(module)
                if ok:
                    service_deps.load(signal, module)
            except Exception as e:
                ok, error = False, f"{e.__class__.__name__}: {e}"
            try:
                self.install_done.emit(ok, error)
            except RuntimeError:
                pass  # the widget went with a profile change; the next layout shows the outcome

        threading.Thread(target=run, name=f"install {module}", daemon=True).start()

    def _on_install_done(self, ui_manager, ok, error):
        self.installing = False
        if ok:
            print(f"Installed the dependencies of {self.thread_manager.name}")
            saveThreads(ui_manager)  # still the disabled placeholder: enabling is left to the user
            generate_thread_layout(ui_manager)
            return
        print(f"Installing the dependencies of {self.thread_manager.name} failed: {error}")
        self.install_button.setEnabled(True)
        self.install_button.setText("Install dependencies")
        self.install_button.setToolTip(f"Failed, see logs/dependencies.log: {error}")
        self.status_lbl.setText("Install failed")
        self.status_lbl.setStyleSheet("color: red")

    def set_status(self, active=False):
        if self.installing:
            return
        if not self.thread_manager.installed():
            self.status_lbl.setText("Not installed")
            self.status_lbl.setStyleSheet("color: gray")
        elif active:
            self.status_lbl.setText("Running")
            self.status_lbl.setStyleSheet("color: green")
        else:
            self.status_lbl.setText("Down")
            self.status_lbl.setStyleSheet("color: red")


def on_profile_change(ui_manager):
    ui_manager.signal.set_profile(ui_manager.ui.profile.currentText())
    ui_manager.signal.restart_thread_managers()
    generate_thread_layout(ui_manager)


def on_change_password(ui_manager):
    keyring.set_password("CyanManager", ui_manager.signal.profile, ui_manager.ui.password.text())


def saveThreads(ui_manager):
    try:
        new_threads = []
        for t_name, service_attr in ui_manager.ui.serviceItems.items():
            new_threads.append(Thread(t_name, enabled=service_attr.enabled_widget(),
                                      parameters={k: get_value() for k, get_value in service_attr.param_widgets.items()}))
        ui_manager.signal.set_threads(new_threads)
    except:
        import traceback
        print(traceback.format_exc())


def clear_layout(layout):
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        if widget := item.widget():
            widget.deleteLater()
        elif sub_layout := item.layout():
            clear_layout(sub_layout)
            del sub_layout
        elif item.spacerItem():
            pass


def add_in_columns(layout, widgets, count):
    """Independent columns, each box at its own height, added to the shorter
    column: rows would stretch a box to its neighbour's height."""
    columns_layout = QHBoxLayout()
    columns_layout.setSpacing(16)
    columns = [QVBoxLayout() for _ in range(count)]
    heights = [0] * count
    for column in columns:
        column.setSpacing(12)
        columns_layout.addLayout(column, 1)
    layout.addLayout(columns_layout)
    for widget in widgets:
        shortest = heights.index(min(heights))
        columns[shortest].addWidget(widget)
        heights[shortest] += widget.sizeHint().height()
    for column in columns:
        column.addStretch()


def generate_thread_layout(ui_manager):
    layout_threads = ui_manager.ui.thread_layout
    layout_functions = ui_manager.ui.functions_layout
    clear_layout(layout_threads)
    clear_layout(layout_functions)
    try:
        modules = {}
        for f_name, function in ui_manager.signal.reg_functions.get_functions().items():
            if function.module_name not in modules:
                modules[function.module_name] = []
            modules[function.module_name].append((f_name, function))
        
        groups = []
        for module, function_list in modules.items():
            group = QGroupBox(module.title())
            group_layout = QVBoxLayout()
            group.setLayout(group_layout)
            for (f_name, f) in function_list:
                function_widget = FunctionItemWidget(ui_manager, f_name, f)
                group_layout.addWidget(function_widget)
            groups.append(group)
        add_in_columns(layout_functions, groups, 3)  # the Functions tab

        threads = ui_manager.signal.get_threads()
        ui_manager.ui.serviceItems = {}
        managers = list(ui_manager.signal.thread_managers.values())
        managers.sort(key=lambda tm: len(tm.parameters))
        ui_manager.ui.password.setText(keyring.get_password("CyanManager", ui_manager.signal.profile))

        for thread_manager in managers:
            ui_manager.ui.serviceItems[thread_manager.name] = ServiceItemWidget(thread_manager, threads)
        add_in_columns(layout_threads, ui_manager.ui.serviceItems.values(), 3)
    except:
        import traceback
        print(traceback.format_exc())
    
    layout_threads.addStretch()


def set_gen_layout(ui_manager):
    global suspend_change
    suspend_change = True
    cur_profile = ui_manager.signal.profile
    all_profiles = ui_manager.signal.get_all_profiles()
    ui_manager.ui.profile.addItems(all_profiles)
    ui_manager.ui.profile.setCurrentText(cur_profile)
    ui_manager.ui.profile.currentTextChanged.connect(lambda _: on_profile_change(ui_manager))
    ui_manager.ui.password.setEchoMode(QLineEdit.Password)
    ui_manager.ui.password.textChanged.connect(partial(on_change_password, ui_manager))
    
    generate_thread_layout(ui_manager)
    suspend_change = False
