dark_stylesheet = """

QWidget {
    background-color: #2b2b2b;
    color: #f0f0f0;
    font-family: Segoe UI;
}

QPushButton {
    background-color: #3c3c3c;
    color: #f0f0f0;
    border: 1px solid #555;
    padding: 5px;
}

QPushButton:hover {
    background-color: #505050;
}

QLineEdit, QTextEdit {
    background-color: #3c3c3c;
    color: #f0f0f0;
    border: 1px solid #555;
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

#app_divider {
    border-top: 1px solid #555;
}

"""