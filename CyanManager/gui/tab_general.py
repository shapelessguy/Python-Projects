import keyring
from utils import Thread
from functools import partial
from PyQt5.QtCore import QTime, Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTimeEdit, QCheckBox,
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
    def __init__(self, thread_manager, threads: list[Thread], parent=None):
        super().__init__(parent)
        
        ui_manager = thread_manager.signal.ui_manager
        self.setObjectName(f"service_{thread_manager.name.replace(' ', '_')}")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)
        
        group = QGroupBox(thread_manager.name)
        group_layout = QVBoxLayout()
        group.setLayout(group_layout)
        main_layout.addWidget(group)
        
        header_layout = QHBoxLayout()
        self.status_lbl = QLabel("Unkwnown")
        self.set_status(False)
        
        self.enabled_checkbox = QCheckBox("Enabled")
        enabled = [x.enabled for x in threads if x.name == thread_manager.name]
        self.enabled_checkbox.setChecked(enabled[0] if len(enabled) > 0 else True)
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
        header_layout.addStretch()
        header_layout.addWidget(self.status_lbl)
        
        group_layout.addLayout(header_layout)
        
        params_layout = QFormLayout()
        params_layout.setLabelAlignment(Qt.AlignRight)
        params_layout.setFormAlignment(Qt.AlignLeft)
        params_layout.setSpacing(8)
        
        self.param_widgets = {}
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
        
        group_layout.addLayout(params_layout)
    
    def set_status(self, active=False):
        if active:
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
        
        for module, function_list in modules.items():
            group = QGroupBox(module.title())
            group_layout = QVBoxLayout()
            group.setLayout(group_layout)
            layout_functions.addWidget(group)
            for (f_name, f) in function_list:
                function_widget = FunctionItemWidget(ui_manager, f_name, f)
                group_layout.addWidget(function_widget)

        current_row_layout = None
        threads = ui_manager.signal.get_threads()
        ui_manager.ui.serviceItems = {}
        managers = list(ui_manager.signal.thread_managers.values())
        managers.sort(key=lambda tm: len(tm.parameters))
        ui_manager.ui.password.setText(keyring.get_password("CyanManager", ui_manager.signal.profile))

        for thread_manager in managers:
            thread_widget = ServiceItemWidget(thread_manager, threads)
            ui_manager.ui.serviceItems[thread_manager.name] = thread_widget

            if current_row_layout is None or current_row_layout.count() == 2:
                current_row_layout = QHBoxLayout()
                current_row_layout.setSpacing(16)
                layout_threads.addLayout(current_row_layout)

            current_row_layout.addWidget(thread_widget)

        if current_row_layout and current_row_layout.count() == 1:
            current_row_layout.addStretch()
            current_row_layout.addSpacing(16)
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
