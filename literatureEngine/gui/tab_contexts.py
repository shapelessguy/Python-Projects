import os
import json
from utils import ICONS_FOLDER_PATH
from fetch_papers.fetch import expand
from PyQt5.QtWidgets import QApplication, QShortcut, QDialog, QPushButton, QListWidget, QListWidgetItem, QSizePolicy, QTableView
from PyQt5.QtGui import QFont, QIcon, QColor, QBrush, QStandardItemModel, QStandardItem, QKeySequence
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QSize
from gui.utils import pprint, Operation, OpClass, VENUE_TYPES


TABLE_HEADERS = {
    "Title": { "attribute": "title", "type": str, "size": 500 },
    "Year": { "attribute": "year", "type": int, "size": 40 },
    "DOI": { "attribute": "doi", "type": str, "size": 100 },
    "Cit.": { "attribute": "citation_count", "type": int, "size": 40 },
    "Venue": { "attribute": "venue", "type": str, "size": 200 }
}


class SearchBulk(OpClass):

    def start(self, signal, args):
        query = args["query"]
        widget = args["widget"]
        end = args["end"]
        n_found = 0
        
        results = expand(signal, args["query"])
        # print(results)



        args["n_found"] = len(results)
        args["result"] = results
        # signal.mongo.add_performed_query(signal.cur_review, signal.cur_context, {"query": args["query"], "n_found": n_found})
    
    def end(self, signal, args):
        query = args["query"]
        widget = args["widget"]

        for i in range(widget.queryList.count()):
            item = widget.queryList.item(i)
            item_data = item.data(Qt.UserRole)
            if item_data["query"] == query:
                item.setText(f"{item.text()} (found: {args['n_found']})")
                item.setBackground(QColor("#5BFF4C"))
                item.setData(Qt.UserRole, {"query": query, "search_complete": True})
    
        if args["end"]:
            current_index = widget.tabWidget.currentIndex()
            widget.tabWidget.setTabEnabled(current_index, True)
            for i in range(widget.tabWidget.count()):
                if i != current_index:
                    widget.tabWidget.setTabEnabled(i, True)
            widget.queryEdit.setVisible(True)
            widget.addQuery.setVisible(True)
            widget.instruction_lbl.setVisible(True)
            widget.executeQuery.setEnabled(True)
            widget.error_lbl.setStyleSheet("color: green")
            widget.error_lbl.setText("Search complete!")


def clear_layout(ui_manager):
    # ui_manager.signal.set_current_library("")
    # ui_manager.ui.container_name_lbl.setText("")
    ui_manager.ui.referenceView.setVisible(False)
    ui_manager.ui.delete_context.setVisible(False)
    ui_manager.ui.expand_btn.setVisible(False)
    ui_manager.ui.references_lbl.setText("")
    # ui_manager.ui.user_papers.setVisible(False)
    # clear_user_papers(ui_manager)

    layout = ui_manager.ui.context_area_layout
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.setParent(None)
            widget.deleteLater()


def copy_selected(table):
    selected = table.selectedIndexes()
    if not selected:
        return
    selected = sorted(selected, key=lambda x: (x.row(), x.column()))
    current_row = selected[0].row()
    text = []
    row_text = []
    for idx in selected:
        if idx.row() != current_row:
            text.append("\t".join(row_text))
            row_text = []
            current_row = idx.row()
        row_text.append(str(idx.data()))
    text.append("\t".join(row_text))
    QApplication.clipboard().setText("\n".join(text))


def populate_references_table(ui_manager, references):
    model = ui_manager.ui.referenceViewModel
    table = ui_manager.ui.referenceView
    model.removeRows(0, model.rowCount())
    for ref in references:
        row = []
        for header in TABLE_HEADERS.values():
            if header["type"] is str:
                value = ref.get(header["attribute"], "")
                item = QStandardItem(value)
            elif header["type"] is int:
                value = ref.get(header["attribute"], 0)
                item = QStandardItem()
                item.setData(value, Qt.DisplayRole)
            else:
                raise
            item.setData(value, Qt.ToolTipRole)
            row.append(item)
        model.appendRow(row)

    ui_manager.ui.referenceView.resizeColumnsToContents()
    for i, header in enumerate(TABLE_HEADERS.values()):
        table.setColumnWidth(i, header["size"])


def reload_context(ui_manager):
    if not hasattr(ui_manager.signal, "cur_context"):
        return
    pprint(f"Reloading context: {ui_manager.signal.cur_context}")
    references = ui_manager.signal.mongo.fetch_refs_by_context(ui_manager.signal.cur_review, ui_manager.signal.cur_context)
    ui_manager.ui.references_lbl.setText(f"References ({len(references)})")
    populate_references_table(ui_manager, references)


def load_context(ui_manager, context_name):
    ui_manager.signal.set_current_context(context_name)
    ui_manager.ui.context_name_lbl.setText(f"Context: {context_name}")
    ui_manager.ui.delete_context.setVisible(True)
    ui_manager.ui.expand_btn.setVisible(True)
    ui_manager.ui.referenceView.setVisible(True)
    reload_context(ui_manager)


def load_contexts(ui_manager, cur_context_name=""):
    clear_layout(ui_manager)
    layout = ui_manager.ui.context_area_layout
    all_contexts = ui_manager.signal.mongo.fetch_contexts(ui_manager.signal.cur_review)
    for context in all_contexts:
        btn = QPushButton(context["name"], ui_manager.ui.tab_context)
        btn.setMinimumHeight(30)
        font = QFont()
        font.setPointSize(14)
        btn.setFont(font)
        layout.addWidget(btn)
        btn.name = context["name"]
        btn.clicked.connect(lambda _, c=context["name"]: load_context(ui_manager, c))
        if cur_context_name == context["name"]:
            load_context(ui_manager, cur_context_name)


def execute_by_queries(ui_manager, widget):
    widget.queryList.clearSelection()
    widget.deleteQuery.setVisible(False)
    widget.newQuery.setVisible(False)
    widget.queryEdit.setVisible(False)
    widget.addQuery.setVisible(False)
    widget.instruction_lbl.setVisible(False)
    widget.executeQuery.setEnabled(False)
    current_index = widget.tabWidget.currentIndex()
    all_items = [widget.queryList.item(i).data(Qt.UserRole) for i in range(widget.queryList.count())]
    all_queries = [x["query"] for x in all_items if not x["search_complete"]]
    if len(all_queries) == 0:
        widget.error_lbl.setStyleSheet("color: red")
        widget.error_lbl.setText("No queries defined")
        return
    for i in range(widget.tabWidget.count()):
        if i != current_index:
            widget.tabWidget.setTabEnabled(i, False)
    widget.tabWidget.setTabEnabled(current_index, False)
    widget.error_lbl.setText("Searching by Semantic queries...")
    for i, query in enumerate(all_queries, start=1):
        ui_manager.send_operation(Operation(ui_manager.signal, SearchBulk, query, {"query": query, "widget": widget, "end": i == len(all_queries)}))


def execute_by_refs(ui_manager, widget):
    widget.error_lbl.setText("Searching by papers'references...")

    
def showExpandWidget(ui_manager):
    from gui import contextExpansion
    expansionWin = QDialog()
    expansionWin.setWindowIcon(ui_manager.icon)
    ui = contextExpansion.Ui_expansionWin()
    ui.setupUi(expansionWin)
    ui.tabWidget.setStyleSheet("""QTabBar::tab {width: 242px;}""")
    ui.deleteQuery.setVisible(False)
    ui.newQuery.setVisible(False)
    ui.queryEdit.setVisible(True)
    ui.addQuery.setVisible(True)
    ui.instruction_lbl.setVisible(True)
    label = ui.instruction_lbl
    link = '<a href="https://api.semanticscholar.org/api-docs/#tag/Paper-Data/operation/get_graph_paper_bulk_search">Semantic Scholar API</a>'
    label.setText(f"For more information, see the {link} documentation under query parameters.")
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(Qt.TextBrowserInteraction)
    
    queries = ui_manager.signal.mongo.fetch_performed_queries(ui_manager.signal.cur_review, ui_manager.signal.cur_context)
    for q_info in queries:
        item = QListWidgetItem(q_info["query"])
        item.setText(f"{item.text()} (found: {q_info['n_found']})")
        item.setBackground(QColor("#5BFF4C"))
        item.setData(Qt.UserRole, {"query": q_info["query"], "search_complete": True})
        ui.queryList.addItem(item)

    def on_selection_changed():
        item = ui.queryList.currentItem() is not None
        ui.newQuery.setVisible(item)
        ui.queryEdit.setVisible(not item)
        ui.addQuery.setVisible(not item)
        ui.deleteQuery.setVisible(item and not ui.queryList.currentItem().data(Qt.UserRole)["search_complete"])
    
    ui.queryList.itemSelectionChanged.connect(on_selection_changed)

    def create_query():
        ui.queryList.clearSelection()
        ui.newQuery.setVisible(False)
        ui.queryEdit.setVisible(True)
        ui.addQuery.setVisible(True)
        ui.deleteQuery.setVisible(False)
        
    ui.newQuery.clicked.connect(create_query)

    def delete_query():
        for item in ui.queryList.selectedItems():
            row = ui.queryList.row(item)
            ui.queryList.takeItem(row)
        create_query()
        
    ui.deleteQuery.clicked.connect(delete_query)

    def add_query():
        queries = ui.queryEdit.toPlainText().split("\n")
        queries = [x.strip() for x in queries]
        for q in queries:
            all_qs = [ui.queryList.item(i).data(Qt.UserRole)["query"] for i in range(ui.queryList.count())]
            existing = any([x == q for x in all_qs])
            if not existing and q != "":
                item = QListWidgetItem(q)
                item.setData(Qt.UserRole, {"query": q, "search_complete": False})
                ui.queryList.addItem(item)
                ui.queryEdit.clear()
    ui.addQuery.clicked.connect(add_query)

    def execute_search():
        current_index = ui.tabWidget.currentIndex()
        ui.error_lbl.setStyleSheet("color: blue")
        if current_index == 0:
            try:
                execute_by_queries(ui_manager, ui)
            except:
                import traceback
                print(traceback.format_exc())
        elif current_index == 1:
            execute_by_refs(ui_manager, ui)
    
    ui.executeQuery.clicked.connect(execute_search)

    expansionWin.exec()


def setup_tab_contexts(ui_manager):

    def add_context_(edit=False):
        from gui import new_review_dialog as reviewDialog
        new_context_dialog = QDialog(ui_manager.ui.main_window)
        new_context_dialog.setWindowIcon(ui_manager.icon)
        ui = reviewDialog.Ui_new_review_dialog()
        ui.setupUi(new_context_dialog)
        new_context_dialog.setMinimumHeight(250)
        new_context_dialog.setMaximumHeight(250)
        ui.requestTitle.setText("Context's name:")
        ui.new_name.setPlaceholderText("Enter a name for the context here...")
        new_context_dialog.setWindowTitle("New Context" if not edit else "Edit Context")
        ui.error_lbl.setText("")
        ui.error_lbl.setStyleSheet("color: red")

        ui.context_list = QListWidget(new_context_dialog)
        ui.context_list.setSelectionMode(QListWidget.NoSelection)
        ui.context_list.setStyleSheet("""QListWidget {padding-top: 3px;}""")
        ui.verticalLayout.insertWidget(1, ui.context_list)
        
        libraries = ui_manager.signal.mongo.fetch_containers(ui_manager.signal.cur_review)
        target_libraries = []
        old_name = ""
        if edit:
            cur_context = [x for x in ui_manager.signal.mongo.fetch_contexts(ui_manager.signal.cur_review) if x["name"] == ui_manager.signal.cur_context]
            if len(cur_context):
                old_name = cur_context[0]["name"]
                ui.new_name.setText(old_name)
                target_libraries = cur_context[0]['target_libraries']
            else:
                edit = False
    
        for lib in libraries:
            item = QListWidgetItem(lib["name"])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked if lib["_id"] not in target_libraries else Qt.Checked)
            ui.context_list.addItem(item)

        def on_ok():
            new_name = ui.new_name.text().strip()
            checked_items = []
            for i in range(ui.context_list.count()):
                item = ui.context_list.item(i)
                if item.checkState() == Qt.Checked:
                    checked_items.append(item.text())
            if not new_name:
                ui.error_lbl.setText("Empty name")
                return
            if not len(checked_items):
                ui.error_lbl.setText("Select libraries")
                return
            if new_name != old_name and new_name in [x["name"] for x in ui_manager.signal.mongo.fetch_contexts(ui_manager.signal.cur_review)]:
                ui.error_lbl.setText("Name already in use")
                return
            lib_ids = [x["_id"] for x in ui_manager.signal.mongo.fetch_containers(ui_manager.signal.cur_review) if x["name"] in checked_items]
            new_context_dialog.accept()
            if edit:
                ui_manager.signal.mongo.edit_context(ui_manager.signal.cur_review, old_name, new_name, lib_ids)
                load_contexts(ui_manager, new_name)
            else:
                ui_manager.signal.mongo.create_context(ui_manager.signal.cur_review, new_name, lib_ids)
                load_contexts(ui_manager)

        ui.buttonBox.accepted.disconnect()
        ui.buttonBox.accepted.connect(on_ok)
        new_context_dialog.exec()

    def rm_context():
        from gui import generalDialog as deleteReviewDialog
        delete_context_dialog = QDialog(ui_manager.ui.main_window)
        delete_context_dialog.setWindowIcon(ui_manager.icon)
        ui = deleteReviewDialog.Ui_Dialog()
        ui.setupUi(delete_context_dialog)
        ui.dialog_msg.setText(f"Are you sure you want to delete the context \"{ui_manager.signal.cur_context}\"?")

        def on_ok():
            ui_manager.signal.mongo.delete_context(ui_manager.signal.cur_review, ui_manager.signal.cur_context)
            delete_context_dialog.accept()
            load_contexts(ui_manager)

        ui.buttonBox.accepted.disconnect()
        ui.buttonBox.accepted.connect(on_ok)
        delete_context_dialog.exec()

    def edit_context():
        add_context_(edit=True)


    for btn_info in [
        {"name": "edit_context", "icon": "edit.png", "tooltip": "Edit context", "on_clicked": edit_context},
        {"name": "delete_context", "icon": "trash.png", "tooltip": "Delete context", "on_clicked": rm_context},
        ]:
        btn = getattr(ui_manager.ui, btn_info["name"])
        btn.setIcon(QIcon(os.path.join(ICONS_FOLDER_PATH, btn_info["icon"])))
        btn.setIconSize(QSize(18, 18))
        btn.clicked.connect(btn_info["on_clicked"])
        btn.setToolTip(btn_info["tooltip"])

    
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels(list(TABLE_HEADERS.keys()))
    ui_manager.ui.referenceViewModel = model
    table = ui_manager.ui.referenceView
    shortcut = QShortcut(QKeySequence("Ctrl+C"), table)
    shortcut.activated.connect(lambda: copy_selected(table))
    table.setModel(model)
    table.setSortingEnabled(True)
    table.setEditTriggers(QTableView.NoEditTriggers)
    ui_manager.ui.expand_btn.clicked.connect(lambda: showExpandWidget(ui_manager))
    ui_manager.ui.context_name_lbl.setText("")
    ui_manager.ui.add_context.clicked.connect(add_context_)
