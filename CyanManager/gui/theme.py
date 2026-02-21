dark_stylesheet = """

QWidget {
    background-color: #2b2b2b;
    color: #f0f0f0;
    font-family: Segoe UI;
}

QLineEdit, QPlainTextEdit, QTextEdit {
    background-color: #3c3c3c;
    color: #f0f0f0;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px 6px;
    selection-background-color: #555;
    selection-color: #fff;
}

QComboBox {
    background-color: #3c3c3c;
    color: #f0f0f0;
    border: 1px solid #555;
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
    border-left: 1px solid #555;
}

QComboBox QAbstractItemView {
    background-color: #3c3c3c;
    color: #f0f0f0;
    border: 1px solid #555;
    selection-background-color: #555;
    selection-color: #fff;
}

QMenuBar, QMenu, QToolBar {
    background-color: #2b2b2b;
    color: #f0f0f0;
}

QMenu::item:selected {
    background-color: #505050;
}

QTabWidget::pane {
    border: 1px solid #555;
    background-color: #2b2b2b;
}

QTabBar::tab {
    background: #3c3c3c;
    color: #f0f0f0;
    padding: 6px 12px;
    border: 1px solid #555;
    border-bottom: none;
}

QTabBar::tab:selected {
    background: #2b2b2b;
    color: #ffffff;
}

QTabBar::tab:hover {
    background: #505050;
}

QTabBar::tab:!selected {
    margin-top: 2px;
}

QPushButton {
    background-color: #3c3c3c;
    color: #f0f0f0;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px 8px;
}

QPushButton:hover {
    border: 1px solid #888;
    background-color: #444;
}

QPushButton:pressed {
    background-color: #555;
}

QCheckBox, QRadioButton {
    color: #e0e0e0;
    spacing: 8px;
    font-weight: 500;
    qproperty-layoutDirection: RightToLeft;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #606060;
    border-radius: 4px;
    background-color: #2a2a2a;
}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #80b0ff;
    background-color: #333;
}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    border: 2px solid #70a0ff;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #70a0ff, stop:1 #5080e0);
}

QCheckBox::indicator:indeterminate {   /* for tristate checkbox */
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #606060, stop:1 #808080);
    border: 2px solid #70a0ff;
}

QScrollBar:vertical, QScrollBar:horizontal {
    background: #3c3c3c;
    width: 12px;
    height: 12px;
    margin: 0px;
}

QScrollBar::handle {
    background: #555;
    border-radius: 4px;
}

QScrollBar::handle:hover {
    background: #666;
}

QScrollBar::add-line, QScrollBar::sub-line {
    background: none;
}

QDateTimeEdit {
    background-color: #3c3c3c;       /* matches QPushButton background */
    color: #f0f0f0;                  /* text color */
    border: 1px solid #555;          /* same border as QTabWidget */
    border-radius: 4px;
    padding: 2px 6px;
    selection-background-color: #50a0ff; /* selection highlight */
    selection-color: #ffffff;
}

QDateTimeEdit:hover {
    background-color: #444;
    border: 1px solid #888;
}

QDateTimeEdit:focus {
    border: 1px solid #50a0ff;
}



#app_divider {
    border-right: 1px solid #555;
}

#line {
    border-right: 1px solid #555;
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