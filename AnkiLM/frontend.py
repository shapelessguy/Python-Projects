import warnings
import sys
from PyQt5 import uic
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QApplication, QStyleFactory, QVBoxLayout, QPushButton,
    QHBoxLayout, QMessageBox, QCheckBox, QToolButton, QMenu, QWidgetAction, QProgressBar, QScrollArea,
    QSizePolicy, QLabel, QInputDialog, QDialog, QLineEdit, QFormLayout, QDialogButtonBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QPalette, QColor, QFontMetrics, QStandardItemModel, QStandardItem
from backend import Data, get_first_notes_info, get_notes_info
warnings.filterwarnings("ignore", category=DeprecationWarning)
from PyQt5.QtWidgets import QProgressBar, QScrollArea
from chat import Chat

from backend import Data, get_first_notes_info, get_notes_info, test_llm_connection, get_vocabulary_entries


class LoadingOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 160);")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel("Loading…")
        label.setStyleSheet("color: #e8e8e8; font-size: 14px; background-color: transparent;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        progress = QProgressBar()
        progress.setRange(0, 0)  # indeterminate spinner-style bar
        progress.setFixedWidth(200)
        layout.addWidget(progress, alignment=Qt.AlignmentFlag.AlignCenter)

        if parent is not None:
            self.setGeometry(parent.rect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.parent():
            self.setGeometry(self.parent().rect())


class LLMConnectionCheckWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config

    def run(self):
        success, message = test_llm_connection(self.config, timeout=2.0)
        self.finished.emit(success, message)


class LLMConfigDialog(QDialog):
    def __init__(self, current_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM Config")
        self.setMinimumWidth(700)

        current_config = current_config or {}

        form = QFormLayout(self)

        self.endpoint_input = QLineEdit(current_config.get("api_endpoint", ""))
        self.token_input = QLineEdit(current_config.get("api_token", ""))
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.model_input = QLineEdit(current_config.get("model_name", ""))

        form.addRow("API Endpoint:", self.endpoint_input)
        form.addRow("API Token (optional):", self.token_input)
        form.addRow("Model:", self.model_input)

        self.test_connection_btn = QPushButton("Test Connection")
        self.test_connection_btn.clicked.connect(self._on_test_connection_clicked)
        form.addRow(self.test_connection_btn)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(60)
        self.status_label.setStyleSheet("color: #888888;")
        form.addRow("Status:", self.status_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.connection_worker = None

    def _on_test_connection_clicked(self):
        self.test_connection_btn.setEnabled(False)
        self.status_label.setText("Checking…")
        self.status_label.setStyleSheet("color: #888888;")

        self.connection_worker = LLMConnectionCheckWorker(self.get_config())
        self.connection_worker.finished.connect(self._on_check_finished)
        self.connection_worker.start()

    def _on_check_finished(self, success: bool, message: str):
        if success:
            self.status_label.setText(f"● {message}")
            self.status_label.setStyleSheet("color: #5cb85c;")
        else:
            self.status_label.setText(f"● {message}")
            self.status_label.setStyleSheet("color: #d9534f;")
        self.test_connection_btn.setEnabled(True)

    def get_config(self) -> dict:
        return {
            "api_endpoint": self.endpoint_input.text().strip(),
            "pricing": None,
            "api_token": self.token_input.text().strip(),
            "model_name": self.model_input.text().strip(),
        }

    def closeEvent(self, event):
        if self.connection_worker is not None and self.connection_worker.isRunning():
            self.connection_worker.wait(2500)
        super().closeEvent(event)

    def done(self, result):
        if self.connection_worker is not None and self.connection_worker.isRunning():
            self.connection_worker.wait(2500)
        super().done(result)


class VocabularyFetchWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, note_ids, vocabulary, parent=None):
        super().__init__(parent)
        self.note_ids = note_ids
        self.vocabulary = vocabulary

    def run(self):
        try:
            notes = get_notes_info(self.note_ids) if self.note_ids else []
            entries = get_vocabulary_entries(self.vocabulary, notes)
            self.finished.emit(entries)
        except Exception as e:
            self.error.emit(str(e))


class VocabularyExamplesDialog(QDialog):
    def __init__(self, note_ids, vocabulary, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vocabulary Examples")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        layout.addWidget(self.progress)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVisible(False)
        layout.addWidget(self.scroll_area)

        self.empty_label = QLabel("No vocabulary examples available.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #888888;")
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

        self.worker = VocabularyFetchWorker(note_ids, vocabulary)
        self.worker.finished.connect(self._on_entries_ready)
        self.worker.error.connect(self._on_fetch_error)
        self.worker.start()

    def _on_entries_ready(self, entries):
        self.progress.setVisible(False)

        if not entries:
            self.empty_label.setVisible(True)
            return

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        for entry in entries:
            label = QLabel(entry)
            label.setWordWrap(True)
            label.setStyleSheet("padding: 6px; border-bottom: 1px solid #444444;")
            container_layout.addWidget(label)

        self.scroll_area.setWidget(container)
        self.scroll_area.setVisible(True)

    def _on_fetch_error(self, message):
        self.progress.setVisible(False)
        self.empty_label.setText(f"Error: {message}")
        self.empty_label.setVisible(True)

    def closeEvent(self, event):
        if self.worker.isRunning():
            self.worker.wait(2000)
        super().closeEvent(event)


def apply_anki_style(app: QApplication):
    app.setStyle(QStyleFactory.create("fusion"))
    
    palette = QPalette()
    
    canvas = QColor("#2b2b2b")
    canvas_light = QColor("#353535")
    text = QColor("#e8e8e8")
    highlight = QColor("#3d6a99")
    border = QColor("#444444")
    
    palette.setColor(QPalette.ColorRole.Window, canvas)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Button, canvas_light)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.Base, canvas_light)
    palette.setColor(QPalette.ColorRole.AlternateBase, canvas)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, canvas_light)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#888888"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#666666"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#666666"))
    
    app.setPalette(palette)
    
    with open('ui_forms/style.qss', 'r') as f:
        app.setStyleSheet(f.read())


class MultiCheckCombo(QToolButton):
    selectionChanged = pyqtSignal()
    
    def __init__(self, placeholder="Select keywords...", parent=None):
        super().__init__(parent)
        self.placeholder = placeholder
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(150)
        self.menu = QMenu(self)
        self.setMenu(self.menu)
        self.checkboxes = {}
        self._update_text()

    def populate(self, keywords, checked=None):
        checked = set(checked or [])
        self.menu.clear()
        self.checkboxes = {}
        for keyword in keywords:
            checkbox = QCheckBox(keyword, self.menu)
            checkbox.setChecked(keyword in checked)
            checkbox.stateChanged.connect(self._update_text)
            checkbox.stateChanged.connect(self.selectionChanged.emit)
            action = QWidgetAction(self.menu)
            action.setDefaultWidget(checkbox)
            self.menu.addAction(action)
            self.checkboxes[keyword] = checkbox
        self._update_text()

    def selected_keywords(self) -> list[str]:
        return [kw for kw, box in self.checkboxes.items() if box.isChecked()]

    def _update_text(self):
        selected = self.selected_keywords()
        full_text = ", ".join(selected) if selected else self.placeholder
        self.setToolTip(full_text)

        metrics = QFontMetrics(self.font())
        available_width = max(self.width() - 30, 50)
        elided = metrics.elidedText(full_text, Qt.TextElideMode.ElideRight, available_width)
        self.setText(elided)

        self.updateGeometry()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_text()


class DeckRow(QWidget):
    def __init__(self, display_text: str, on_click, parent=None, focusable=True,
                 value=None, red_count=None, blue_count=None):
        super().__init__(parent)
        uic.loadUi('ui_forms/row_element.ui', self)
        self._full_text = display_text
        self.text.setText(display_text)
        self.text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.text.setContentsMargins(0, 0, 0, 0)
        self.text.setIndent(0)
        self.value = value if value is not None else display_text
        self.on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._selected = False
        self.set_selected(False)
        if not focusable:
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            for child in self.findChildren(QWidget):
                child.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        if red_count is not None:
            self.n1.setText(str(red_count))
            self.n1.setStyleSheet("color: #d9534f; font-weight: bold;")
            self.n1.setVisible(True)
        else:
            self.n1.setVisible(False)

        if blue_count is not None:
            self.n2.setText(str(blue_count))
            self.n2.setStyleSheet("color: #4a90d9; font-weight: bold;")
            self.n2.setVisible(True)
        else:
            self.n2.setVisible(False)

    def set_selected(self, selected: bool):
        self._selected = selected
        if selected:
            self.setStyleSheet("""
                QWidget {
                    background-color: #2a3f5f;
                    border-radius: 6px;
                    padding: 4px;
                    color: #bad4ed;
                }
            """)
        else:
            self.setStyleSheet("""
                QWidget {
                    background-color: #1e1e1e;
                    border-radius: 6px;
                    padding: 4px;
                    color: #e8e8e8;
                }
            """)

    def enterEvent(self, event):
        if not self._selected:
            self.text.setStyleSheet("color: #bad4ed;")

    def leaveEvent(self, event):
        if not self._selected:
            self.text.setStyleSheet("color: #e8e8e8;")

    def mousePressEvent(self, event):
        self.on_click(self.value)
        event.accept()


class FirstMenu(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi('ui_forms/first_menu.ui', self)

        container = QWidget()
        container.setStyleSheet("background-color: #353535;")
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        for deck_id, deck_info in self.parent().parent().parent().data.decks.items():
            review_count = sum(
                len(model_info.get("reviewed_today_note_ids", []))
                for model_info in deck_info["models"].values()
            )
            row = DeckRow(
                deck_info["name"],
                self.on_deck_clicked,
                value=deck_id,
                blue_count=review_count
            )
            layout.addWidget(row)

        layout.addStretch()

        self.deck_scroll_area.setWidget(container)
        self.deck_scroll_area.setWidgetResizable(True)

    def on_deck_clicked(self, deck_id):
        self.parent().parent().parent().load_deck_menu(deck_id)


class PromptConfig(QWidget):
    configChanged = pyqtSignal(str, list)
    deleteRequested = pyqtSignal()
    startRequested = pyqtSignal()
    vocabularyExampleRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi('ui_forms/prompt_config.ui', self)
        self.exercise_title.setText("")

        layout = QHBoxLayout(self.vocabulary_frame)
        layout.setContentsMargins(0, 0, 0, 0)

        self.vocabulary_label = QLabel("Vocabulary")
        self.vocabulary_label.setMinimumWidth(100)
        self.vocabulary_label.setMinimumHeight(30)
        layout.addWidget(self.vocabulary_label)

        self.vocabulary_combo = MultiCheckCombo()
        self.vocabulary_combo.setMinimumHeight(30)
        layout.addWidget(self.vocabulary_combo)

        self.vocabulary_example_btn = QPushButton("View Examples")
        self.vocabulary_example_btn.setMinimumHeight(30)
        self.vocabulary_example_btn.setMinimumWidth(150)
        layout.addWidget(self.vocabulary_example_btn)

        self.system_prompt.textChanged.connect(self._emit_config_changed)
        self.vocabulary_combo.selectionChanged.connect(self._emit_config_changed)
        self.delete_btn.clicked.connect(self.deleteRequested.emit)
        self.start_btn.clicked.connect(self.startRequested.emit)
        self.vocabulary_example_btn.clicked.connect(self.vocabularyExampleRequested.emit)

    def _emit_config_changed(self):
        self.configChanged.emit(self.system_prompt.toPlainText(), self.selected_keywords())

    def refresh(self, model_name: str, exercise_name: str, keywords=None, system_prompt="", vocabulary=None):
        if model_name and exercise_name:
            self.exercise_title.setText(f"Exercise: {exercise_name}")
            self.delete_btn.setVisible(True)
            self.config_area.setVisible(True)
            self.vocabulary_combo.populate(keywords or [], checked=vocabulary or [])

            self.system_prompt.blockSignals(True)
            self.system_prompt.setPlainText(system_prompt or "")
            self.system_prompt.blockSignals(False)
        else:
            self.exercise_title.setText("")
            self.delete_btn.setVisible(False)
            self.config_area.setVisible(False)

    def selected_keywords(self) -> list[str]:
        return self.vocabulary_combo.selected_keywords()

    def insert_keyword(self, keyword: str):
        # if not self.system_prompt.hasFocus():
        #     return
        self.system_prompt.insertPlainText(f"{{{{{keyword}}}}}")


class NotesFetchWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, deck_name, model_name, limit, parent=None):
        super().__init__(parent)
        self.deck_name = deck_name
        self.model_name = model_name
        self.limit = limit

    def run(self):
        try:
            notes = get_first_notes_info(self.deck_name, self.model_name, self.limit)
            self.finished.emit(notes)
        except Exception as e:
            self.error.emit(str(e))


class ChatPrepWorker(QThread):
    finished = pyqtSignal(object)  # emits (reviewed_today_notes, top_known_due_notes)
    error = pyqtSignal(str)

    def __init__(self, reviewed_today_ids, top_known_due_ids, parent=None):
        super().__init__(parent)
        self.reviewed_today_ids = reviewed_today_ids
        self.top_known_due_ids = top_known_due_ids

    def run(self):
        try:
            reviewed_today_notes = get_notes_info(self.reviewed_today_ids) if self.reviewed_today_ids else []
            top_known_due_notes = get_notes_info(self.top_known_due_ids) if self.top_known_due_ids else []
            self.finished.emit((reviewed_today_notes, top_known_due_notes))
        except Exception as e:
            self.error.emit(str(e))


class Examples(QWidget):
    nExamples = 10

    def __init__(self, deck_name: str, model_name: str, fields: list, parent=None):
        super().__init__(parent)
        uic.loadUi('ui_forms/examples.ui', self)
        self.setWindowTitle("Examples")
        self.fields = fields

        self.worker = NotesFetchWorker(deck_name, model_name, self.nExamples)
        self.worker.finished.connect(self.on_notes_fetched)
        self.worker.error.connect(self.on_fetch_error)
        self.worker.start()

    def on_notes_fetched(self, notes: list):
        example_notes = notes[:self.nExamples]
        model = QStandardItemModel(len(self.fields), len(example_notes))
        model.setVerticalHeaderLabels(self.fields)
        model.setHorizontalHeaderLabels([f"Example {i + 1}" for i in range(len(example_notes))])

        for col, note in enumerate(example_notes):
            note_fields = note.get('fields', {})
            for row, field_name in enumerate(self.fields):
                value = note_fields.get(field_name, {}).get('value', '')
                model.setItem(row, col, QStandardItem(value))

        self.tableView.setModel(model)

    def on_fetch_error(self, message: str):
        QMessageBox.warning(self, "Connection Error", f"Could not fetch examples:\n{message}")


class DeckMenu(QWidget):
    def __init__(self, deck_id, parent=None):
        super().__init__(parent)
        uic.loadUi('ui_forms/deck_menu.ui', self)
        self.deck_id = deck_id
        self.model_rows = {}
        self.exercise_rows = {}

        data = self.parent().parent().parent().data
        deck_info = data.decks[deck_id]
        self.deck_name_label.setText(deck_info["name"])

        self.prompt_config_widget = PromptConfig(self.prompt_config)
        self.prompt_config_widget.vocabularyExampleRequested.connect(self.on_vocabulary_example_clicked)
        self.prompt_config_widget.configChanged.connect(self.on_prompt_config_changed)
        self.prompt_config_widget.deleteRequested.connect(self.on_delete_exercise_clicked)
        self.prompt_config_widget.startRequested.connect(self.on_start_clicked)
        self.view_examples_btn.clicked.connect(self.on_view_examples_clicked)
        layout = QVBoxLayout(self.prompt_config)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.prompt_config_widget)

        models = deck_info["models"]
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        for model_name, model_info in models.items():
            review_count = len(model_info.get("reviewed_today_note_ids", []))
            row = DeckRow(
                model_name,
                self.on_model_clicked,
                blue_count=review_count
            )
            self.model_rows[model_name] = row
            layout.addWidget(row)
        
        self.new_exercise_btn.setEnabled(False)
        self.new_exercise_btn.clicked.connect(self.on_new_exercise_clicked)

        layout.addStretch()
        self.model_area.setWidget(container)
        self.model_area.setWidgetResizable(True)

        if data.current_model:
            self.on_model_clicked(data.current_model)
    
    def on_vocabulary_example_clicked(self):
        data = self.parent().parent().parent().data
        if data.current_model is None:
            return

        model_info = data.decks[self.deck_id]["models"][data.current_model]
        top_known_due_ids = model_info.get("top_known_due_note_ids", [])
        vocabulary = self.prompt_config_widget.selected_keywords()
        
        dialog = VocabularyExamplesDialog(top_known_due_ids, vocabulary, self)
        dialog.exec_()
    
    def on_start_clicked(self):
        data = self.parent().parent().parent().data
        if data.current_model is None or data.current_exercise is None:
            return

        model_info = data.decks[self.deck_id]["models"][data.current_model]
        reviewed_today_ids = model_info.get("reviewed_today_note_ids", [])
        top_known_due_ids = model_info.get("top_known_due_note_ids", [])

        self.loading_overlay = LoadingOverlay(self)
        self.loading_overlay.setGeometry(self.rect())
        self.loading_overlay.show()
        self.loading_overlay.raise_()

        self.chat_worker = ChatPrepWorker(reviewed_today_ids, top_known_due_ids)
        self.chat_worker.finished.connect(self.on_chat_ready)
        self.chat_worker.error.connect(self.on_chat_fetch_error)
        self.chat_worker.start()

    def on_chat_ready(self, payload):
        self.loading_overlay.hide()
        self.loading_overlay.deleteLater()

        data = self.parent().parent().parent().data
        reviewed_today_notes, top_known_due_notes = payload

        main_window = self.parent().parent().parent()
        main_window._clear_central()
        chat_widget = Chat(data, self.deck_id, data.current_model, data.current_exercise,
                            reviewed_today_notes, top_known_due_notes, main_window.centralwidget)
        main_window.centralwidget.layout().addWidget(chat_widget)
        main_window.chat_widget = chat_widget

    def on_chat_fetch_error(self, message: str):
        self.loading_overlay.hide()
        self.loading_overlay.deleteLater()
        QMessageBox.warning(self, "Connection Error", f"Could not start chat:\n{message}")
        # stays on DeckMenu — nothing else to do

    def _refresh_prompt_config(self):
        data = self.parent().parent().parent().data
        keywords = data.decks[self.deck_id]["models"].get(data.current_model, {}).get("fields", [])
        exercise_config = data.config.get(self.deck_id, {}).get(data.current_model, {}).get(data.current_exercise, {})
        self.prompt_config_widget.refresh(
            data.current_model,
            data.current_exercise,
            keywords,
            exercise_config.get("system_prompt", ""),
            exercise_config.get("vocabulary", [])
        )
    
    def on_view_examples_clicked(self):
        data = self.parent().parent().parent().data
        if data.current_model is None:
            return

        deck_name = data.decks[self.deck_id]["name"]
        fields = data.decks[self.deck_id]["models"][data.current_model]["fields"]

        self.examples_window = Examples(deck_name, data.current_model, fields)
        self.examples_window.setWindowFlags(Qt.WindowType.Window)
        self.examples_window.show()

    def on_prompt_config_changed(self, prompt_text: str, keywords: list):
        data = self.parent().parent().parent().data
        if data.current_model is None or data.current_exercise is None:
            return
        data.update_exercise(prompt_text, keywords)
    
    def on_new_exercise_clicked(self):
        data = self.parent().parent().parent().data
        if data.current_model is None:
            return  # guarded by disabled state, but safe regardless

        existing_exercises = set(
            data.config.get(self.deck_id, {}).get(data.current_model, {}).keys()
        )

        dialog = QInputDialog(self)
        dialog.setWindowTitle("New Exercise")
        dialog.setLabelText("Exercise name:")
        dialog.setMinimumWidth(400)
        dialog.resize(400, dialog.sizeHint().height())

        ok = dialog.exec_()
        name = dialog.textValue()

        if not ok:
            return

        name = name.strip()
        if not name:
            QMessageBox.warning(self, "Invalid name", "Exercise name cannot be empty.")
            return
        if name in existing_exercises:
            QMessageBox.warning(self, "Duplicate name", "An exercise with that name already exists.")
            return

        data.add_exercise(name)
        self.on_model_clicked(data.current_model)
        self.on_exercise_clicked(name)
    
    def on_delete_exercise_clicked(self):
        data = self.parent().parent().parent().data
        if data.current_model is None or data.current_exercise is None:
            return

        reply = QMessageBox.question(
            self,
            "Delete Exercise",
            f"Delete exercise \"{data.current_exercise}\"? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        data.remove_cur_exercise()
        data.setCurrentExercise(None)
        self.on_model_clicked(data.current_model)  # refresh exercise list + hide prompt panel

    def on_model_clicked(self, model_name: str):
        data = self.parent().parent().parent().data
        data.setCurrentModel(model_name)
        self.new_exercise_btn.setEnabled(True)

        for name, row in self.model_rows.items():
            row.set_selected(name == model_name)

        # keywords
        keywords = data.decks[self.deck_id]["models"][model_name]["fields"]
        container = QWidget()
        container.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        for keyword in keywords:
            row = DeckRow(keyword, self.on_keyword_clicked, focusable=False)
            layout.addWidget(row)
        layout.addStretch()
        self.keyword_area.setWidget(container)
        self.keyword_area.setWidgetResizable(True)
        self.keyword_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        exercises = data.config.get(self.deck_id, {}).get(model_name, {})
        reviewed_today_ids = data.decks[self.deck_id]["models"][model_name].get("reviewed_today_note_ids", [])

        self.exercise_rows = {}
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        for exercise_name in exercises:
            not_ok_count, unreviewed_count = data.get_exercise_review_counts(
                self.deck_id, model_name, exercise_name, reviewed_today_ids
            )
            row = DeckRow(
                exercise_name,
                self.on_exercise_clicked,
                red_count=not_ok_count,
                blue_count=unreviewed_count
            )
            self.exercise_rows[exercise_name] = row
            layout.addWidget(row)
        layout.addStretch()
        self.exercise_area.setWidget(container)
        self.exercise_area.setWidgetResizable(True)

        if data.current_exercise and data.current_exercise in self.exercise_rows:
            self.exercise_rows[data.current_exercise].set_selected(True)

        self._refresh_prompt_config()

    def on_keyword_clicked(self, keyword: str):
        self.prompt_config_widget.insert_keyword(keyword)

    def on_exercise_clicked(self, exercise_name: str):
        data = self.parent().parent().parent().data
        data.setCurrentExercise(exercise_name)
        for name, row in self.exercise_rows.items():
            row.set_selected(name == exercise_name)
        self._refresh_prompt_config()


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        uic.loadUi('ui_forms/main.ui', self)
        self.data = None

        layout = QVBoxLayout(self.centralwidget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.decks_btn.clicked.connect(self.load_first_menu)
        self.update_btn.clicked.connect(self.load_data)
        self.llm_btn.clicked.connect(self.on_llm_config_clicked)

        self.load_data()

    def _clear_central(self):
        layout = self.centralwidget.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def load_first_menu(self):
        self._clear_central()
        self.data.setDeck(None)
        self.first_menu = FirstMenu(self.centralwidget)
        self.centralwidget.layout().addWidget(self.first_menu)

    def load_data(self):
        config, config_llm, history = None, None, None
        if self.data:
            self.data.stop_autosave()
            config = self.data.config
            config_llm = self.data.config_llm
            history = self.data.history

        self.data = Data()

        if config:
            self.data.config = config
        if config_llm:
            self.data.config_llm = config_llm
        if history:
            self.data.history = history

        if self.data.pending_connection_err:
            self.data.pending_connection_err = False
            self.show_connection_error_popup()
        else:
            self.data.start_autosave()

        self.load_first_menu()

    def show_connection_error_popup(self):
        msg = QMessageBox(self)
        msg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Connection Error")
        msg.setText("Could not connect to Anki. Is Anki running with AnkiConnect installed?")
        msg.setWindowModality(Qt.WindowModality.NonModal)
        msg.show()
        self._connection_error_popup = msg

    def load_deck_menu(self, deck_id):
        self.data.setDeck(deck_id)
        self._clear_central()
        self.deck_menu = DeckMenu(deck_id, self.centralwidget)
        self.centralwidget.layout().addWidget(self.deck_menu)
    
    def on_llm_config_clicked(self):
        dialog = LLMConfigDialog(self.data.config_llm, self)
        if dialog.exec_() == QDialog.DialogCode.Accepted:
            self.data.set_llm_config(dialog.get_config())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_anki_style(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())