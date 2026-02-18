import os
import json
from bson import json_util
from utils import ICONS_FOLDER_PATH
from fetch_papers.fetch import fetch_metadata, expand_dois
from PyQt5.QtWidgets import QApplication, QShortcut, QDialog, QPushButton, QListWidget, QListWidgetItem, QTableView, QWidget, QAbstractItemView, QHBoxLayout, QVBoxLayout
from PyQt5.QtGui import QFont, QIcon, QColor, QBrush, QStandardItemModel, QStandardItem, QKeySequence
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QSize
from gui.utils import pprint
from gui.paper_tools import are_valid_formulas


def new_filter(ui_manager):
    process_info = {"type": "Filter", "name": "", "formula": ""}
    ui_manager.signal.mongo.add_process(ui_manager.signal.cur_review, ui_manager.signal.cur_context, process_info)
    reload_processes(ui_manager)


def show_filter(ui_manager):
    from gui.shapes.py_files import new_filter as newFilter
    container = QWidget()
    ui = newFilter.Ui_new_filter()
    ui.setupUi(container)
    ui.instruction_lbl.setWordWrap(True)
    text = """
    <b>Filter Formula</b> Enter a Python-style condition to filter papers.<br>
    Use <code>paper</code> to refer to each item (Ex: <code>paper.year() >= 2020</code>)
    """
    ui.saved_filter = json_util.dumps(ui_manager.signal.cur_process)
    ui.save_btn.setVisible(False)
    ui.instruction_lbl.setText(text)
    ui.process_name.setText(ui_manager.signal.cur_process.get("name", ""))
    ui.filter_edit.setPlainText(ui_manager.signal.cur_process.get("formula", ""))
    ui.error_lbl.setText("")
    ui.error_lbl.setStyleSheet("color: red")

    def on_remove():
        try:
            ui_manager.signal.mongo.remove_process(ui_manager.signal.cur_review, ui_manager.signal.cur_context, ui_manager.signal.cur_process["_id"])
            processes = ui_manager.signal.mongo.fetch_processes(ui_manager.signal.cur_review, ui_manager.signal.cur_context)
            reload_proc_layout(ui_manager, processes)
        except:
            import traceback
            print(traceback.format_exc())

    for btn_info in [{"name": "delete_btn", "icon": "trash.png", "on_clicked": on_remove}]:
        btn = getattr(ui, btn_info["name"])
        btn.setIcon(QIcon(os.path.join(ICONS_FOLDER_PATH, btn_info["icon"])))
        btn.setIconSize(QSize(18, 18))
        btn.clicked.connect(btn_info["on_clicked"])
    

    def get_process_info():
        process_info = {"_id": ui_manager.signal.cur_process["_id"]} if ui_manager.signal.cur_process.get("_id", None) else {}
        return {**process_info, "type": "Filter", "name": ui.process_name.text(), "formula": ui.filter_edit.toPlainText()}

    def on_change():
        ui.error_lbl.setText("")
        ui.save_btn.setVisible(json_util.dumps(get_process_info()) != ui.saved_filter)
    
    ui.process_name.textChanged.connect(on_change)
    ui.filter_edit.textChanged.connect(on_change)

    def on_save():
        if are_valid_formulas([ui.filter_edit.toPlainText()]):
            new_process = ui_manager.signal.mongo.add_process(ui_manager.signal.cur_review, ui_manager.signal.cur_context, get_process_info())
            processes = ui_manager.signal.mongo.fetch_processes(ui_manager.signal.cur_review, ui_manager.signal.cur_context)
            reload_proc_layout(ui_manager, processes)
            load_process(ui_manager, processes, new_process)
        else:
            ui.error_lbl.setText("Bad formula")

    ui.save_btn.clicked.connect(on_save)
    ui_manager.ui.context_info.addWidget(container, stretch=1)


def clear_processes_layout(ui_manager):
    layout = ui_manager.ui.process_buttons_layout
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.setParent(None)
            widget.deleteLater()
    clear_process(ui_manager)


def clear_process(ui_manager):
    layout = ui_manager.ui.context_info
    while layout.count() > 0:
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.setParent(None)
            widget.deleteLater()


def load_process(ui_manager, processes, process):
    print("Loading process:", process.get("_id"))
    process_list_1 = []
    process_list_2 = []
    process_list = process_list_1
    for p in processes:
        process_list.append(p)
        if p["_id"] == process["_id"]:
            process_list = process_list_2

    ui_manager.signal.set_current_process(process)
    highlight_btns(ui_manager)
    ui_manager.signal.ref_holder.apply_processes(process_list_1, process_list_2)
    ui_manager._reload_table(ui_manager)
    
    clear_process(ui_manager)
    if process["type"] == "Filter":
        show_filter(ui_manager)


def highlight_btns(ui_manager):
    layout = ui_manager.ui.process_buttons_layout
    for i in range(layout.count()):
        item = layout.itemAt(i)
        widget = item.widget()
        if widget and hasattr(widget, "btn"):
            button = widget.btn
            process = widget.process
            button.setProperty("activeContainer", process["_id"] == ui_manager.signal.cur_process.get("_id", ""))
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
    ui_manager.ui.base_btn.setProperty("activeContainer", ui_manager.signal.cur_process == {})
    ui_manager.ui.base_btn.style().unpolish(ui_manager.ui.base_btn)
    ui_manager.ui.base_btn.style().polish(ui_manager.ui.base_btn)
    ui_manager.ui.base_btn.update()


def move_process_up(ui_manager, processes, process):
    print(f"Move UP requested for process")
    idx = processes.index(process)
    if idx == 0:
        return
    processes[idx], processes[idx-1] = processes[idx-1], processes[idx]
    ui_manager.signal.mongo.save_process_order(ui_manager.signal.cur_review, ui_manager.signal.cur_context, processes)
    reload_processes(ui_manager)
    if ui_manager.signal.cur_process != {}:
        load_process(ui_manager, processes, ui_manager.signal.cur_process)


def move_process_down(ui_manager, processes, process):
    print(f"Move DOWN requested for process")
    idx = processes.index(process)
    if idx == len(processes) - 1:
        return
    processes[idx], processes[idx+1] = processes[idx+1], processes[idx]
    ui_manager.signal.mongo.save_process_order(ui_manager.signal.cur_review, ui_manager.signal.cur_context, processes)
    reload_processes(ui_manager)
    if ui_manager.signal.cur_process != {}:
        load_process(ui_manager, processes, ui_manager.signal.cur_process)


def reload_proc_layout(ui_manager, processes):
    main_layout = ui_manager.ui.process_buttons_layout
    clear_processes_layout(ui_manager)

    for i, process in enumerate(processes):
        btn_main = QPushButton(process.get("type", "Unknown"))
        btn_main.setProperty("activeContainer", process["_id"] == ui_manager.signal.cur_process.get("_id", ""))
        btn_main.setMinimumHeight(23)
        btn_main.setMaximumHeight(23)
        font = QFont()
        font.setPointSize(13)
        btn_main.setFont(font)
        btn_main.clicked.connect(lambda _, p=process: load_process(ui_manager, processes, p))
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(4, 4, 4, 4)
        row_layout.setSpacing(2)
        row_layout.addWidget(btn_main, stretch=1)
        btn_up_, btn_down_ = i != 0, i != len(processes) - 1
        if btn_up_:
            btn_up = QPushButton("↑")
            btn_up.setFixedSize(23, 23)
            btn_up.clicked.connect(lambda _, p=process: move_process_up(ui_manager, processes, p))
            row_layout.addWidget(btn_up)
        if btn_down_:
            btn_down = QPushButton("↓")
            btn_down.setFixedSize(23, 23)
            btn_down.clicked.connect(lambda _, p=process: move_process_down(ui_manager, processes, p))
            row_layout.addWidget(btn_down)

        for existing in (btn_down_, btn_up_):
            if not existing:
                spacer = QWidget()
                spacer.setFixedWidth(23)
                row_layout.addWidget(spacer)

        row_container = QWidget()
        row_container.setLayout(row_layout)
        
        row_container.btn = btn_main
        row_container.process = process
        main_layout.addWidget(row_container)
    main_layout.addStretch()


def reload_processes(ui_manager):
    pprint("Reloading Processes")
    processes = ui_manager.signal.mongo.fetch_processes(ui_manager.signal.cur_review, ui_manager.signal.cur_context)
    reload_proc_layout(ui_manager, processes)


def setup_processes(ui_manager):
    ui_manager.ui.new_filter.clicked.connect(lambda: new_filter(ui_manager))

    def base(ui_manager):
        ui_manager.signal.set_current_process({})
        highlight_btns(ui_manager)
        try:
            ui_manager.signal.ref_holder.process_list([])
            ui_manager._reload_table(ui_manager)
        except:
            import traceback
            print(traceback.format_exc())

    ui_manager.ui.base_btn.clicked.connect(lambda: base(ui_manager))