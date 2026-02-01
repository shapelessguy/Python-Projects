light_stylesheet = """

QWidget {
    background-color: #ffffff;
    color: #000000;
    font-family: Segoe UI;
}

QLineEdit, QPlainTextEdit, QTextEdit {
    background-color: #f7f7f7;
    color: #000000;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 4px 6px;
    selection-background-color: #cce6ff;
    selection-color: #000000;
}

QComboBox {
    background-color: #f7f7f7;
    color: #000000;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 2px 6px;
}

QComboBox:hover {
    border: 1px solid #888;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 0px;
    border-left: 1px solid #ccc;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #000000;
    border: 1px solid #ccc;
    selection-background-color: #cce6ff;
    selection-color: #000000;
}

QMenuBar, QMenu, QToolBar {
    background-color: #ffffff;
    color: #000000;
}

QMenu::item:selected {
    background-color: #e6f2ff;
}

QTabWidget::pane {
    border: 1px solid #ccc;
    background-color: #ffffff;
}

QTabBar::tab {
    background: #f7f7f7;
    color: #000000;
    padding: 6px 12px;
    border: 1px solid #ccc;
    border-bottom: none;
}

QTabBar::tab:selected {
    background: #ffffff;
    color: #000000;
}

QTabBar::tab:hover {
    background: #e6f2ff;
}

QTabBar::tab:!selected {
    margin-top: 2px;
}

QPushButton {
    background-color: #f0f4f8;
    color: #000000;
    border: 1px solid #50a0ff;
    border-radius: 6px;
    padding: 4px 8px;
}

QPushButton[activeContainer="true"] {
    background-color: #cce6ff;
    color: #000000;
    border: 1px solid #50a0ff;
    border-radius: 6px;
    padding: 4px 8px;
}

QPushButton:hover {
    background-color: #e6f2ff;
    border: 1px solid #50a0ff;
}

QPushButton:hover[activeContainer="true"] {
    background-color: #cce6ff;
    border: 1px solid #50a0ff;
}

QPushButton:pressed {
    background-color: #cce6ff;
}

QCheckBox, QRadioButton {
    color: #000000;
    qproperty-layoutDirection: RightToLeft;
    spacing: 5px;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
}

QCheckBox::indicator:unchecked, QRadioButton::indicator:unchecked {
    border: 1px solid #ccc;
    background-color: #f7f7f7;
    border-radius: 3px; /* use 8px for radio */
}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    border: 1px solid #ccc;
    background-color: #50a0ff;
}

QScrollBar:vertical, QScrollBar:horizontal {
    background: #f7f7f7;
    width: 12px;
    height: 12px;
    margin: 0px;
}

QScrollBar::handle {
    background: #ccc;
    border-radius: 4px;
}

QScrollBar::handle:hover {
    background: #b3b3b3;
}

QScrollBar::add-line, QScrollBar::sub-line {
    background: none;
}

QDateTimeEdit {
    background-color: #f7f7f7;
    color: #000000;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 2px 6px;
    selection-background-color: #cce6ff;
    selection-color: #000000;
}

QDateTimeEdit:hover {
    background-color: #e6e6e6;
    border: 1px solid #888;
}

QDateTimeEdit:focus {
    border: 1px solid #50a0ff;
}

#app_divider {
    border-right: 1px solid #ccc;
}

#tab1 {
    font-size: 16px;
}

#tab1 QLabel {
    font-size: 16px;
}

#tab1 QCheckBox {
    font-size: 16px;
}

"""
