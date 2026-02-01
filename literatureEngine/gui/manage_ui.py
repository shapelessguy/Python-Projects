import os
import sys
import threading
from queue import Queue
from gui.theme import light_stylesheet
from gui.tab_pdfs import setup_tab_pdfs, load_containers, Operation
from PyQt5.QtCore import QObject, Qt
from PyQt5.QtWidgets import QMainWindow, QApplication, QSystemTrayIcon, QMenu, QDialog, QPushButton, QProgressBar
from PyQt5.QtCore import QObject, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QPixmap, QFont
from utils import ICONS_FOLDER_PATH, wait


def gui_loop(signal):
    pending_element: Operation = None

    buffer_op_class_name = ""
    buffer: list[Operation] = []

    while signal.is_alive():
        try:
            if not signal.ui_manager.operation_queue.empty() or pending_element:

                if pending_element:
                    buffer.append(pending_element)
                    buffer_op_class_name = pending_element.op_class_name

                while not signal.ui_manager.operation_queue.empty():
                    operation: Operation = signal.ui_manager.operation_queue.get()
                    if buffer_op_class_name != "" and operation.op_class_name != buffer_op_class_name:
                        pending_element = operation
                        break
                    else:
                        buffer_op_class_name = operation.op_class_name
                        buffer.append(operation)
                
                for i, operation in enumerate(buffer, start=1):
                    signal.ui_manager.execute("show_loading", f"({i}/{len(buffer)}) {operation.op_class_name}")
                    operation.start()
                    signal.ui_manager.execute("end_of_operation", operation)
                    signal.ui_manager.execute("show_loading", "")

                buffer = []
                buffer_op_class_name = ""
            wait(signal, 100)
        except:
            wait(signal, 1000)


def terminal_loop(signal):
    while signal.is_alive():
        while signal.is_alive() and not signal.log_queue.empty():
            signal.ui_manager.execute("push_to_terminal", signal.log_queue.get().rstrip())

        signal.ui_manager.execute("increase_loading_value")
        wait(signal, 50)


class UIThreadBridge(QObject):
    show_window = pyqtSignal()
    hide_window = pyqtSignal()
    quit_app = pyqtSignal()
    wait_for_close = pyqtSignal()
    end_of_operation = pyqtSignal(object)
    push_to_terminal = pyqtSignal(str)
    increase_loading_value = pyqtSignal()
    show_loading = pyqtSignal(str)


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


class UI_Manager:
    def __init__(self, signal):
        self.signal = signal
        self.operation_queue = Queue()
        ui_files = ['literatureEngineMainWin', 'new_review_dialog', 'generalDialog', 'paper_widget']
        ui_paths = [os.path.join(os.path.dirname(os.path.realpath(__file__)), x + '.ui') for x in ui_files]
        py_paths = [os.path.join(os.path.dirname(os.path.realpath(__file__)), x + '.py') for x in ui_files]
        for i in range(len(ui_paths)):
            ui_path = ui_paths[i]
            py_path = py_paths[i]
            if os.path.exists(ui_path):
                os.system(f'pyuic5 -x {ui_path} -o {py_path}')
                remove_pyuic_header(py_path)

        from gui import literatureEngineMainWin as main_interface

        app = QApplication(sys.argv)
        app.setStyleSheet(light_stylesheet)
        MainWindow = QMainWindow()
        ui = main_interface.Ui_MainWindow()
        self.signal.set_current_review("")
        
        ui.app = app
        ui.main_window = MainWindow
        # ui.main_window.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.icon = QIcon()
        self.icon.addPixmap(QPixmap(os.path.join(ICONS_FOLDER_PATH, "literature_engine.ico")), QIcon.Normal, QIcon.Off)
        MainWindow.setWindowIcon(self.icon)
        
        # drag_filter = WindowDragFilter(MainWindow)
        # MainWindow.installEventFilter(drag_filter)

        self.bridge = UIThreadBridge()
        self.bridge.show_window.connect(self._show_window)
        self.bridge.hide_window.connect(self._hide_window)
        self.bridge.quit_app.connect(self._quit_app)
        self.bridge.wait_for_close.connect(self._wait_for_close)
        self.bridge.end_of_operation.connect(self._end_of_operation)
        self.bridge.push_to_terminal.connect(self._push_to_terminal)
        self.bridge.increase_loading_value.connect(self._increase_loading_value)
        self.bridge.show_loading.connect(self._show_loading)
        self.ui = ui

        self.tray = QSystemTrayIcon(QIcon(os.path.join(ICONS_FOLDER_PATH, "literature_engine.ico")), app)
        menu = QMenu()
        menu.addAction("Show", self._show_window)
        menu.addAction("Quit", self._quit_app)
        MainWindow.closeEvent = self._close_event
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.setToolTip("Literature Engine")
        self.tray.show()
        self.ui.setupUi(self.ui.main_window)
        self.custom_setup()

    
    def execute(self, function_, *args, **kwargs):
        f = getattr(self.bridge, function_)
        return f.emit(*args, **kwargs)
    
    def send_operation(self, op: Operation):
        self.operation_queue.put(op)

    def custom_setup(self):
        def new_review():
            from gui import new_review_dialog as reviewDialog
            new_review_dialog = QDialog(self.ui.main_window)
            new_review_dialog.setWindowIcon(self.icon)
            ui = reviewDialog.Ui_new_review_dialog()
            ui.setupUi(new_review_dialog)
            ui.requestTitle.setText("Review's name:")
            ui.new_name.setPlaceholderText("Enter a name for the new review here...")
            new_review_dialog.setWindowTitle("New Review")
            ui.error_lbl.setText("")
            ui.error_lbl.setStyleSheet("color: red")

            def on_ok():
                new_name = ui.new_name.text().strip()
                already_used = self.load_reviews()
                if not new_name:
                    ui.error_lbl.setText("Empty name")
                    return
                if new_name in already_used:
                    ui.error_lbl.setText("Name already in use")
                    return
                new_review_dialog.accept()
                self.signal.mongo.create_collection(new_name)
                self.load_reviews()

            ui.buttonBox.accepted.disconnect()
            ui.buttonBox.accepted.connect(on_ok)
            new_review_dialog.exec()
        
        def delete_review():
            from gui import generalDialog as deleteReviewDialog
            delete_review_dialog = QDialog(self.ui.main_window)
            delete_review_dialog.setWindowIcon(self.icon)
            ui = deleteReviewDialog.Ui_Dialog()
            ui.setupUi(delete_review_dialog)
            ui.dialog_msg.setText(f"Are you sure you want to delete the review \"{self.signal.cur_review}\" with all of its data?")

            def on_ok():
                self.signal.mongo.delete_collection(self.signal.cur_review)
                delete_review_dialog.accept()
                self.load_reviews()

            ui.buttonBox.accepted.disconnect()
            ui.buttonBox.accepted.connect(on_ok)
            delete_review_dialog.exec()
            
        self.ui.new_review.clicked.connect(new_review)
        def view_terminal():
            self.ui.terminal.setVisible(not self.ui.terminal.isVisible())
        self.ui.actionView_terminal.triggered.connect(view_terminal)
        self.ui.back_to_reviews.clicked.connect(self.load_reviews)
        self.ui.terminal.setVisible(False)
        self.ui.main_widget.setVisible(False)
        
        self.ui.delete_review.setIcon(QIcon(os.path.join(ICONS_FOLDER_PATH, "trash.png")))
        self.ui.delete_review.setIconSize(QSize(18, 18))
        self.ui.delete_review.clicked.connect(delete_review)

        self.ui.op_lbl.setMinimumWidth(100)
        self.ui.op_lbl.setText("")
        self.ui.op_loading = QProgressBar(None)
        self.ui.op_loading.setMinimum(20)
        self.ui.op_loading.setMaximum(100)
        self.ui.op_loading.setFixedWidth(120)
        self.ui.op_loading.setFixedHeight(10)
        self.ui.op_loading.setTextVisible(False)
        self.ui.op_loading.hide()
        self.ui.bottom_layout.insertWidget(self.ui.bottom_layout.count() - 3, self.ui.op_loading)
        self.load_reviews()
        setup_tab_pdfs(self)

        self.ui.main_window.show()
    
    def load_review(self, review_name):
        self.signal.set_current_review(review_name)
        self.ui.select_review.setVisible(False)
        self.ui.main_widget.setVisible(True)
        self.ui.review_indicator.setText(f"Review: {review_name}")
        load_containers(self)

    def load_reviews(self):
        self.ui.select_review.setVisible(True)
        self.ui.main_widget.setVisible(False)
        all_reviews = self.signal.mongo.fetch_collections()
        layout = self.ui.review_layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

        for review in all_reviews:
            btn = QPushButton(review, self.ui.select_review)
            btn.setMinimumHeight(50)
            font = QFont()
            font.setPointSize(20)
            btn.setFont(font)
            layout.addWidget(btn)
            btn.clicked.connect(lambda _, r=review: self.load_review(r))
        return all_reviews

    def _close_event(self, event):
        pass
        # event.ignore()
        # self.ui.main_window.hide()
    
    def _end_of_operation(self, operation):
        operation.end()
    
    def _push_to_terminal(self, line):
        if line == "":
            return
        self.ui.terminal.insertPlainText(f"{line}\n")
    
    def _increase_loading_value(self):
        cur_value = self.ui.op_loading.value()
        next_value = cur_value + 2
        if next_value > 100:
            next_value = 20
        self.ui.op_loading.setValue(next_value)
    
    def _show_loading(self, show_txt: str):
        self.ui.op_lbl.setText(show_txt)
        if show_txt:
            self.ui.op_loading.show()
        else:
            self.ui.op_loading.hide()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.ui.main_window.show()
            self.ui.main_window.activateWindow()

    def _wait_for_close(self):
        form_closed = self.ui.app.exec_()
        return form_closed

    def _show_window(self):
        self.ui.main_window.show()

    def _hide_window(self):
        self.ui.main_window.hide()

    def start_gui_tasks(self):
        threading.Thread(target=terminal_loop, args=(self.signal, )).start()
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


if __name__ == "__main__":
    pass