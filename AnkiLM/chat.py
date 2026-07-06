from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, QEvent, QSize
from PyQt5.QtGui import QFontMetrics
from backend import History, LLMOpeningWorker, LLMReplyWorker, add_tokens


# Module-level so it survives across Chat re-instantiation (a new exercise creates
# a brand new Chat instance/widget each time, but the user's chosen zoom level
# should persist across that).
_DEFAULT_CHAT_FONT_SIZE = 13
_MIN_CHAT_FONT_SIZE = 8
_MAX_CHAT_FONT_SIZE = 28
_saved_chat_font_size = _DEFAULT_CHAT_FONT_SIZE


class BubbleLabel(QLabel):
    """A word-wrapping QLabel whose size is always computed live (via the widget's
    *current* fontMetrics/heightForWidth) rather than baked in once at creation time.
    This keeps it correctly sized across window resizes, DPI changes, and moving the
    window between screens with different scaling — none of which a one-time pixel
    calculation can track, since the numbers go stale the moment the environment changes."""

    MIN_WIDTH = 60

    def __init__(self, text, max_width_fn, parent=None):
        super().__init__(text, parent)
        self._max_width_fn = max_width_fn  # callable -> int, current cap in px
        self.setWordWrap(True)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.setCursor(Qt.CursorShape.IBeamCursor)

    def _desired_width(self):
        max_width = max(self._max_width_fn(), self.MIN_WIDTH)
        margins = self.contentsMargins()
        pad = margins.left() + margins.right()
        natural = self.fontMetrics().horizontalAdvance(self.text()) + pad
        return max(min(natural, max_width), self.MIN_WIDTH)

    def sizeHint(self):
        width = self._desired_width()
        height = self.heightForWidth(width)
        return QSize(width, height)

    def minimumSizeHint(self):
        return self.sizeHint()


class Chat(QWidget):
    BUBBLE_MAX_WIDTH_RATIO = 0.8   # bubbles cap at 80% of chat area width
    BUBBLE_FALLBACK_WIDTH = 800    # used if chat area isn't laid out yet
    BUBBLE_PADDING = 12

    def __init__(self, data, deck_id, model_name, exercise_name,
                 reviewed_today_notes, top_known_due_notes, parent=None):
        super().__init__(parent)
        uic.loadUi('ui_forms/chat.ui', self)
        self.data = data
        self.deck_id = deck_id
        self.model_name = model_name
        self.exercise_name = exercise_name
        self.reviewed_today_notes = reviewed_today_notes
        self.top_known_due_notes = top_known_due_notes
        self.history = History(self.data.config_llm)
        self.token_consumption = {}

        self.current_note = self.data.get_next_note(
            deck_id, model_name, exercise_name, reviewed_today_notes
        )

        self.ok_btn.setVisible(False)
        self.not_ok_btn.setVisible(False)

        if self.current_note is None:
            self._show_done_state()
            return

        self.ok_btn.clicked.connect(lambda: self._on_answer("ok", self.token_consumption))
        self.not_ok_btn.clicked.connect(lambda: self._on_answer("not_ok", self.token_consumption))
        self.user_prompt.installEventFilter(self)
        self._waiting_for_llm = True

        # restore the last font size the user zoomed to, so it persists across
        # this Chat instance being torn down and recreated for a new exercise
        global _saved_chat_font_size
        self._chat_font_size = _saved_chat_font_size
        self._apply_font_size_to_user_prompt()

        self._setup_card()

        self._pending_scroll_to_bottom = False
        self.chat_area.verticalScrollBar().rangeChanged.connect(self._on_scroll_range_changed)
        self.chat_area.viewport().installEventFilter(self)

        self._start_opening()
        self.user_prompt.setFocus()

    def eventFilter(self, obj, event):
        if obj is self.user_prompt and event.type() == QEvent.Type.KeyPress:
            is_return = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            is_shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if is_return and not is_shift:
                self._on_user_send()
                return True  # consume the event, prevent newline insertion

        if obj is self.chat_area.viewport() and event.type() == QEvent.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                step = 1 if event.angleDelta().y() > 0 else -1
                self._change_font_size(step)
                return True  # consume, don't also scroll while zooming

        return super().eventFilter(obj, event)

    def _change_font_size(self, step):
        global _saved_chat_font_size
        new_size = max(_MIN_CHAT_FONT_SIZE, min(_MAX_CHAT_FONT_SIZE, self._chat_font_size + step))
        if new_size == self._chat_font_size:
            return
        self._chat_font_size = new_size
        _saved_chat_font_size = new_size  # persist for the next Chat instance
        self._apply_font_size_to_bubbles()
        self._apply_font_size_to_user_prompt()

    def _apply_font_size_to_bubbles(self):
        for i in range(self._chat_layout.count()):
            row = self._chat_layout.itemAt(i).widget()
            if row is None:
                continue
            for bubble in row.findChildren(BubbleLabel):
                font = bubble.font()
                font.setPointSize(self._chat_font_size)
                bubble.setFont(font)
                bubble.updateGeometry()  # forces sizeHint recalculation -> relayout

    def _apply_font_size_to_user_prompt(self):
        font = self.user_prompt.font()
        font.setPointSize(self._chat_font_size)
        self.user_prompt.setFont(font)

    def _show_done_state(self):
        self.ok_btn.setVisible(False)
        self.not_ok_btn.setVisible(False)
        self.user_prompt.setVisible(False)

        container = QWidget()
        layout = QVBoxLayout(container)
        label = QLabel("Nothing to do here")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #888888; font-size: 16px;")
        layout.addWidget(label)
        self.chat_area.setWidget(container)
        self.chat_area.setWidgetResizable(True)

    def _setup_card(self):
        container = QWidget()
        self._chat_layout = QVBoxLayout(container)
        self._chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._chat_layout.setSpacing(10)
        self._chat_layout.setContentsMargins(10, 10, 10, 10)
        self.chat_area.setWidget(container)
        self.chat_area.setWidgetResizable(True)

    def _start_opening(self):
        exercise_config = self.data.config.get(self.deck_id, {}).get(self.model_name, {}).get(self.exercise_name, {})
        system_prompt = exercise_config.get("system_prompt", "")
        vocabulary = exercise_config.get("vocabulary", [])
        resolved_prompt = self.history.resolve_system_prompt(system_prompt, self.current_note)

        self._add_message("Thinking…", sender="system")
        self._scroll_chat_to_bottom(force=True)

        self.opening_worker = LLMOpeningWorker(self.history, resolved_prompt, vocabulary, self.top_known_due_notes)
        self.opening_worker.finished.connect(self._on_opening_ready)
        self.opening_worker.error.connect(self._on_llm_error)
        self.opening_worker.start()

    def _on_opening_ready(self, answer, token_info):
        self.token_consumption = add_tokens(self.token_consumption, token_info)
        self._remove_last_message()  # drop "Thinking…"
        self._add_message(answer, sender="llm")
        self._scroll_chat_to_bottom()
        self._waiting_for_llm = False
        self._refresh_button_visibility()

    def _on_user_send(self):
        if self._waiting_for_llm:
            return
        text = self.user_prompt.toPlainText().strip()
        if not text:
            return
        self.user_prompt.clear()
        self._waiting_for_llm = True
        self._waiting_for_llm = False
        self._add_message(text, sender="user")
        self._scroll_chat_to_bottom(force=True)
        self._add_message("Thinking…", sender="system")
        self._scroll_chat_to_bottom(force=True)
        self.reply_worker = LLMReplyWorker(self.history, text)
        self.reply_worker.finished.connect(self._on_reply_ready)
        self.reply_worker.error.connect(self._on_llm_error)
        self.reply_worker.start()

    def _on_reply_ready(self, answer, token_info):
        if "END_EXERCISE" in answer and len(answer) < 20:
            self.ok_btn.click()
        self.token_consumption = add_tokens(self.token_consumption, token_info)
        self._remove_last_message()
        self._add_message(answer, sender="llm")
        self._scroll_chat_to_bottom()   # only scroll if already at bottom
        self._waiting_for_llm = False
        self._refresh_button_visibility()

    def _scroll_chat_to_bottom(self, force=False):
        scrollbar = self.chat_area.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 4  # small tolerance
        if force or at_bottom:
            self._pending_scroll_to_bottom = True
            # apply immediately in case the range has already settled and
            # rangeChanged won't fire again (e.g. layout doesn't grow)
            scrollbar.setValue(scrollbar.maximum())

    def _on_scroll_range_changed(self, min_val, max_val):
        if self._pending_scroll_to_bottom:
            self.chat_area.verticalScrollBar().setValue(max_val)
            self._pending_scroll_to_bottom = False

    def _on_llm_error(self, message):
        self._remove_last_message()
        self._add_message(f"Error: {message}", sender="system")
        self._waiting_for_llm = False

    def _refresh_button_visibility(self):
        show = self.history.llm_message_count() >= 2
        self.ok_btn.setVisible(show)
        self.not_ok_btn.setVisible(show)

    def _remove_last_message(self):
        if self._chat_layout.count() == 0:
            return
        item = self._chat_layout.takeAt(self._chat_layout.count() - 1)
        if item.widget():
            item.widget().deleteLater()
    
    def _apply_font_size_to_user_prompt(self):
        font = self.user_prompt.font()
        font.setPointSize(self._chat_font_size)
        self.user_prompt.setFont(font)

        # size the input box in terms of lines of text, so it scales with the font
        # instead of staying pinned to whatever fixed pixel height the .ui file set
        metrics = QFontMetrics(font)
        line_height = metrics.lineSpacing()
        margins = self.user_prompt.contentsMargins()
        frame = 2 * self.user_prompt.frameWidth()
        vertical_padding = margins.top() + margins.bottom() + frame + 8  # a little breathing room

        min_lines = 1
        max_lines = 3

        self.user_prompt.setMinimumHeight(line_height * min_lines + vertical_padding)
        self.user_prompt.setMaximumHeight(line_height * max_lines + vertical_padding)

    def _current_bubble_max_width(self):
        # called live by BubbleLabel every time it needs its sizeHint, so this always
        # reflects the chat area's *current* width — never a stale snapshot.
        width = self.chat_area.viewport().width()
        if width < 200:  # not laid out yet, or absurdly small — use a sane fallback
            width = self.width() if self.width() > 200 else self.BUBBLE_FALLBACK_WIDTH
        return int(width * self.BUBBLE_MAX_WIDTH_RATIO)

    def _add_message(self, text, sender="system"):
        """sender: 'llm' -> left-aligned bubble, 'user' -> right-aligned bubble,
        'system' -> centered plain text (e.g. status/error lines)."""
        bubble = BubbleLabel(text, self._current_bubble_max_width)
        bubble.setContentsMargins(
            self.BUBBLE_PADDING, self.BUBBLE_PADDING, self.BUBBLE_PADDING, self.BUBBLE_PADDING
        )
        font = bubble.font()
        font.setPointSize(self._chat_font_size)
        bubble.setFont(font)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        if sender == "user":
            bubble.setStyleSheet(
                "background-color: #2a3f5f; color: #bad4ed; border-radius: 8px;"
            )
            row_layout.addStretch()
            row_layout.addWidget(bubble)
        elif sender == "llm":
            bubble.setStyleSheet(
                "background-color: #1e1e1e; color: #e8e8e8; border-radius: 8px;"
            )
            row_layout.addWidget(bubble)
            row_layout.addStretch()
        else:  # system messages: centered, no bubble background
            bubble.setStyleSheet("color: #888888;")
            bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_layout.addStretch()
            row_layout.addWidget(bubble)
            row_layout.addStretch()

        self._chat_layout.addWidget(row)

    def _on_answer(self, status, token_consumption):
        self.data.set_note_status(self.deck_id, self.model_name, self.exercise_name,
                                   self.current_note['noteId'], status, token_consumption)
        self._replace_with_fresh()

    def _replace_with_fresh(self):
        main_window = self.window()  # top-level window, regardless of nesting depth
        main_window._clear_central()
        new_chat = Chat(self.data, self.deck_id, self.model_name, self.exercise_name,
                         self.reviewed_today_notes, self.top_known_due_notes,
                         main_window.centralwidget)
        main_window.centralwidget.layout().addWidget(new_chat)
        main_window.chat_widget = new_chat