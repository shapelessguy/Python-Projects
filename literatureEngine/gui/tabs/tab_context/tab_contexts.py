import os
import json
from bson import json_util
from utils import ICONS_FOLDER_PATH
from fetch_papers.fetch import fetch_metadata, expand_dois
from PyQt5.QtWidgets import QApplication, QShortcut, QDialog, QPushButton, QListWidget, QListWidgetItem, QTableView, QWidget, QAbstractItemView
from PyQt5.QtGui import QFont, QIcon, QColor, QBrush, QStandardItemModel, QStandardItem, QKeySequence
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QSize
from gui.utils import pprint, Operation, OpClass, StopOp, VENUE_TYPES, READONLY_TYPES, objectid_decoder
from gui.tabs.tab_context.processes_handler import setup_processes, reload_processes
from gui.paper_tools import References


TABLE_HEADERS = {
    "Title": { "attribute": "title", "type": str, "size": 500 },
    "Year": { "attribute": "year", "type": int, "size": 40 },
    "DOI": { "attribute": "doi", "type": str, "size": 100 },
    "Cit.": { "attribute": "citation_count", "type": int, "size": 40 },
    "Venue": { "attribute": "venue", "type": str, "size": 200 }
}


class SearchBulk(OpClass):

    def start(self, signal, args):
        CHUNK_SIZE = 5
        stage = args.get("stage", -2)
        args["stage"] = stage
        args['update_ui'] = False
        if stage == -2:
            pass
        elif stage == -1:
            dois = expand_dois(signal, args["query"])
            args['n_found'] = 0
            args['n_found_ids'] = len(dois)
            args["doi_list"] = [dois[i:i + CHUNK_SIZE] for i in range(0, len(dois), CHUNK_SIZE)]
        else:
            doi_list = args["doi_list"][stage]
            missing_dois = signal.mongo.get_missing_dois_from_context(signal.cur_review, signal.cur_context, doi_list)
            args['n_found'] += (len(doi_list) - len(missing_dois))
            results = fetch_metadata(signal, missing_dois, "paper_ids")
            stored_ids = []
            for paper in results:
                stored_ids.append(signal.mongo.add_paper(signal.cur_review, paper))
            signal.mongo.add_paperIds_to_context(signal.cur_review, signal.cur_context, stored_ids)
            args['n_found'] += len(results)
            args['update_ui'] = len(results) > 0
    
    def end(self, signal, args):
        args["stage"] += 1
        stage = args["stage"]
        query = args["query"]
        widget = args["ui_manager"].expansion_widget

        if stage > -1 and stage >= len(args.get("doi_list", [])) - 1:
            try:
                for i in range(widget.queryList.count()):
                    item = widget.queryList.item(i)
                    item_data = item.data(Qt.UserRole)
                    if item_data["query"] == query:
                        item.setText(f"{query} (found: {args['n_found']})")
                        item.setBackground(QColor("#5BFF4C"))
                        item.setData(Qt.UserRole, {"query": query, "search_complete": True, "n_found": args["n_found"]})
            
                if args["end"]:
                    activate_expansion_widget(widget)
            except:
                pass
            update_query_results(signal, args, search_complete=True)
        else:
            try:
                for i in range(widget.queryList.count()):
                    item = widget.queryList.item(i)
                    item_data = item.data(Qt.UserRole)
                    if item_data["query"] == query:
                        if stage > 0:
                            item.setText(f"{query} (found: {args['n_found']})")
                            item.setBackground(QColor("#FCFF4C"))
                        else:
                            item.setText(f"{query} (working...)")
                            item.setBackground(QColor("#E66BFF"))
            except:
                pass
            if args['update_ui']:
                update_query_results(signal, args, search_complete=False)
            return True


def update_query_results(signal, args, search_complete):
    signal.mongo.add_query(signal.cur_review, signal.cur_context, {"query": args["query"], "search_complete": search_complete, "n_found": args['n_found']})
    try:
        args["ui_manager"].expansion_widget.queryList.item(0)
    except:
        reload_context(args["ui_manager"])


def activate_expansion_widget(widget, text="Search complete!", color="green"):
    current_index = widget.tabWidget.currentIndex()
    widget.tabWidget.setTabEnabled(current_index, True)
    for i in range(widget.tabWidget.count()):
        if i != current_index:
            widget.tabWidget.setTabEnabled(i, True)
    widget.queryList.setSelectionMode(QAbstractItemView.SingleSelection)
    widget.queryList.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
    widget.queryList.setFocusPolicy(Qt.StrongFocus)

    widget.queryEditBlock.setVisible(True)
    widget.aiBlock.setVisible(False)
    widget.askAi.setVisible(True)
    widget.instruction_lbl.setVisible(True)
    widget.executeQuery.setEnabled(True)
    widget.error_lbl.setStyleSheet(f"color: {color}")
    widget.error_lbl.setText(text)
    widget.stop_btn.setVisible(False)


def clear_layout(ui_manager):
    ui_manager.signal.set_current_context("")
    ui_manager.ui.table_widget.setVisible(False)
    ui_manager.ui.delete_context.setVisible(False)
    ui_manager.ui.context_info_area.setVisible(False)
    ui_manager.ui.context_title.setVisible(False)
    ui_manager.ui.references_lbl.setText("")

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


def load_data(ui_manager):
    if ui_manager.signal.ref_holder:
        ui_manager.signal.ref_holder.apply_filters()
    else:
        ui_manager.signal.ref_holder = References(ui_manager.signal)
    reload_table(ui_manager)
    reload_processes(ui_manager)


def reload_context(ui_manager):
    if not hasattr(ui_manager.signal, "cur_context"):
        return
    if not ui_manager.signal.ref_holder:
        model = QStandardItemModel()
        ui_manager.ui.referenceView.setModel(model)
        model.removeRows(0, model.rowCount())
        ui_manager.ui.table_widget.setVisible(False)

    pprint(f"Reloading context: {ui_manager.signal.cur_context}")
    if ui_manager.ui.tab_widget.tabText(ui_manager.ui.tab_widget.currentIndex()) != "Contexts":
        ui_manager.reload_table_delayed = True
    else:
        load_data(ui_manager)



def reload_table(ui_manager):
    ui_manager.ui.table_widget.setVisible(True)
    ui_manager.ui.references_lbl.setText(f"References ({len(ui_manager.signal.ref_holder.view)})")
    populate_references_table(ui_manager)


def load_context(ui_manager, context_name, force=False):
    if ui_manager.signal.cur_context == context_name and not force:
        return
    print("Loading context")
    ui_manager.signal.set_current_context(context_name)
    ui_manager.ui.context_name_lbl.setText(f"Context: {context_name}")
    ui_manager.ui.delete_context.setVisible(True)
    ui_manager.ui.context_info_area.setVisible(True)
    ui_manager.ui.context_title.setVisible(True)
    ui_manager.signal.ref_holder = None
    reload_context(ui_manager)

    layout = ui_manager.ui.context_area_layout
    for i in range(layout.count()):
        item = layout.itemAt(i)
        widget = item.widget()
        if widget:
            widget.setProperty("activeContainer", widget.name == context_name)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()


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


def populate_references_table(ui_manager):
    table = ui_manager.ui.referenceView
    shortcut = QShortcut(QKeySequence("Ctrl+C"), table)
    shortcut.activated.connect(lambda: copy_selected(table))
    
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels(list(TABLE_HEADERS.keys()))

    table.setModel(model)
    model.removeRows(0, model.rowCount())
    for ref in ui_manager.signal.ref_holder.get_attributes([x["attribute"] for x in TABLE_HEADERS.values()]):
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
            item.setData(ref, Qt.UserRole)
            row.append(item)
        model.appendRow(row)

    ui_manager.ui.referenceView.resizeColumnsToContents()
    for i, header in enumerate(TABLE_HEADERS.values()):
        table.setColumnWidth(i, header["size"])


def execute_by_queries(ui_manager, widget):
    widget.queryList.clearSelection()
    widget.deleteQuery.setVisible(False)
    widget.newQuery.setVisible(False)
    widget.queryEditBlock.setVisible(False)
    widget.aiBlock.setVisible(False)
    widget.askAi.setVisible(False)
    widget.instruction_lbl.setVisible(False)
    widget.executeQuery.setEnabled(False)
    current_index = widget.tabWidget.currentIndex()
    all_items = [widget.queryList.item(i).data(Qt.UserRole) for i in range(widget.queryList.count())]
    all_queries = [x for x in all_items if not x["search_complete"]]
    if len(all_queries) == 0 and ui_manager.signal.cur_operation == "":
        widget.error_lbl.setStyleSheet("color: red")
        widget.error_lbl.setText("No queries defined")
        widget.executeQuery.setEnabled(True)
        widget.newQuery.setVisible(True)
        return
    for i in range(widget.tabWidget.count()):
        if i != current_index:
            widget.tabWidget.setTabEnabled(i, False)

    widget.queryList.setSelectionMode(QAbstractItemView.NoSelection)
    widget.queryList.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.queryList.setFocusPolicy(Qt.NoFocus)
    widget.error_lbl.setText("Searching by Semantic queries...")
    widget.stop_btn.setVisible(True)

    if ui_manager.signal.cur_operation != "":
        return

    for i, query in enumerate(all_queries, start=1):
        if not query["search_complete"] and query["n_found"] == 0:
            ui_manager.signal.mongo.add_query(ui_manager.signal.cur_review, ui_manager.signal.cur_context,
                                                        {"query": query["query"], "search_complete": False, "n_found": 0})
    for i, query in enumerate(all_queries, start=1):
        ui_manager.send_operation(Operation(ui_manager.signal, SearchBulk, query["query"],
                                            {"query": query["query"], "ui_manager": ui_manager, "end": i == len(all_queries)}))


def execute_by_refs(ui_manager, widget):
    widget.error_lbl.setText("Searching by papers'references...")

    
def showExpandWidget(ui_manager):
    from gui.shapes.py_files import contextExpansion
    expansionWin = QDialog()
    expansionWin.setWindowIcon(ui_manager.icon)
    ui = contextExpansion.Ui_expansionWin()
    ui.setupUi(expansionWin)
    ui_manager.expansion_widget = ui
    ui.tabWidget.setStyleSheet("""QTabBar::tab {width: 242px;}""")
    ui.deleteQuery.setVisible(False)
    ui.newQuery.setVisible(False)
    ui.queryEditBlock.setVisible(True)
    ui.aiBlock.setVisible(False)
    ui.askAi.setVisible(True)
    ui.instruction_lbl.setVisible(True)
    label = ui.instruction_lbl
    link = '<a href="https://api.semanticscholar.org/api-docs/#tag/Paper-Data/operation/get_graph_paper_bulk_search">Semantic Scholar API</a>'
    label.setText(f"For more information, see the {link} documentation under query parameters.")
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(Qt.TextBrowserInteraction)
    
    queries = ui_manager.signal.mongo.fetch_performed_queries(ui_manager.signal.cur_review, ui_manager.signal.cur_context)
    for q_info in queries:
        item = QListWidgetItem(q_info["query"])
        post_text = f" (found: {q_info['n_found']})" if (q_info["search_complete"] or (not q_info["search_complete"] and q_info['n_found'] > 0)) else ""
        item.setText(f"{item.text()}{post_text}")
        if q_info["search_complete"]:
            item.setBackground(QColor("#5BFF4C"))
        item.setData(Qt.UserRole, q_info)
        ui.queryList.addItem(item)

    def on_selection_changed():
        item = ui.queryList.currentItem() is not None
        ui.newQuery.setVisible(item)
        ui.queryEditBlock.setVisible(not item)
        ui.aiBlock.setVisible(False)
        ui.askAi.setVisible(not item)
        ui.deleteQuery.setVisible(item and not ui.queryList.currentItem().data(Qt.UserRole)["search_complete"])
    
    ui.queryList.itemSelectionChanged.connect(on_selection_changed)

    def create_query():
        ui.queryList.clearSelection()
        ui.newQuery.setVisible(False)
        ui.queryEditBlock.setVisible(True)
        ui.aiBlock.setVisible(False)
        ui.askAi.setVisible(True)
        ui.deleteQuery.setVisible(False)
        
    ui.newQuery.clicked.connect(create_query)

    def delete_query():
        for item in ui.queryList.selectedItems():
            row = ui.queryList.row(item)
            ui_manager.signal.mongo.remove_query(ui_manager.signal.cur_review, ui_manager.signal.cur_context, item.data(Qt.UserRole)["query"])
            ui.queryList.takeItem(row)
        create_query()
        
    ui.deleteQuery.clicked.connect(delete_query)

    def add_query():
        queries = ui.queryEdit.toPlainText().split("\n")
        queries = [x.strip() for x in queries]
        for q in queries:
            all_q_items = [ui.queryList.item(i).data(Qt.UserRole) for i in range(ui.queryList.count())]
            q_stored = [x for x in all_q_items if x["query"] == q]
            existing = len(q_stored) != 0
            if not existing and q != "":
                item = QListWidgetItem(q)
                item.setData(Qt.UserRole, {"query": q, "search_complete": False, "n_found": 0})
                ui.queryList.addItem(item)
                ui.queryEdit.clear()
    ui.addQuery.clicked.connect(add_query)

    def execute_search(index=None):
        current_index = ui.tabWidget.currentIndex() if index is None else index
        ui.tabWidget.setCurrentIndex(current_index)
        ui.error_lbl.setStyleSheet("color: blue")
        if current_index == 0:
            try:
                execute_by_queries(ui_manager, ui)
            except:
                import traceback
                print(traceback.format_exc())
        elif current_index == 1:
            execute_by_refs(ui_manager, ui)
    
    def askAi():
        ui.queryEditBlock.setVisible(False)
        ui.askAi.setVisible(False)
        ui.aiBlock.setVisible(True)
    
    def manualQueries():
        ui.queryEditBlock.setVisible(True)
        ui.askAi.setVisible(True)
        ui.aiBlock.setVisible(False)

    ui.askAi.clicked.connect(askAi)
    ui.manual_queries.clicked.connect(manualQueries)
    
    def stop_op():
        ui_manager.send_operation(Operation(ui_manager.signal, StopOp))
        activate_expansion_widget(ui, "Search interrupted", "orange")
    
    ui.executeQuery.clicked.connect(execute_search)
    ui.stop_btn.clicked.connect(stop_op)
    ui.stop_btn.setVisible(False)
    ui_manager.ui.make_btn_transparent(ui.stop_btn, icon="stop.png", normal_dim=QSize(15, 15), hovered_dim=QSize(18, 18))
    for i, n in enumerate([SearchBulk.__name__]):
        if ui_manager.signal.cur_operation == n:
            execute_search(i)

    expansionWin.exec()
    reload_context(ui_manager)


def show_paper(ui_manager, paper_item):
    from gui.shapes.py_files import paper_widget
    container = QWidget()
    container.setWindowIcon(ui_manager.icon)
    widget = paper_widget.Ui_paper_widget()
    widget.setupUi(container)
    widget.paper_data = json.loads(json_util.dumps(ui_manager.signal.mongo.fetch_ref_by_id(ui_manager.signal.cur_review, paper_item.data(Qt.UserRole)["_id"])),
                                   object_hook=objectid_decoder)
    widget.cur_review = ui_manager.signal.cur_review

    ui_manager._open_paper_windows.append(container)

    container.setWindowTitle(f"Paper View")
    container.resize(600, 400)
    container.show()
    container.activateWindow()

    widget_state = widget.paper_data.get("fill_mode", "")  # "maual" / "auto" / ""

    widget.search_by_title.setVisible(widget_state == "")
    widget.search_by_doi.setVisible(widget_state == "")
    widget.save_btn.setVisible(False)
    
    widget.venue_type_box.addItems(VENUE_TYPES)
    for child in widget.op_widget.findChildren(READONLY_TYPES):
        if hasattr(child, "setReadOnly"):
            child.setReadOnly(True)
        elif hasattr(child, "setEnabled"):
            child.setEnabled(False)

    widget.view_pdf.setVisible(widget.paper_data.get("file_id", "") != "")
    widget.clear_btn.setVisible(False)
    widget.rm_paper.setVisible(False)
    widget.search_by_title.setVisible(False)
    widget.search_by_doi.setVisible(False)
    widget.abstract_box.setReadOnly(False)
    widget.notes_box.setReadOnly(False)

    def get_temp_paper():
        temp_paper = json.loads(json_util.dumps(widget.paper_data), object_hook=objectid_decoder)
        temp_paper["abstract"] = widget.abstract_box.toPlainText()
        temp_paper["notes"] = widget.notes_box.toPlainText()
        return temp_paper

    def on_change(ui_manager_, widget_):
        temp_paper = get_temp_paper()
        valid_change = json_util.dumps(widget.paper_data) != json_util.dumps(temp_paper)
        widget.save_btn.setVisible(valid_change)
    set_paper_props(ui_manager, widget, widget.paper_data, on_change)

    def save_paper():
        temp_paper = get_temp_paper()
        widget.save_btn.setVisible(False)
        ui_manager.signal.mongo.add_paper(widget.cur_review, temp_paper, overwrite=True)
        cur_index = ui_manager.ui.tab_widget.currentIndex()
        if cur_index == 0:
            ui_manager.load_user_pdfs(ui_manager)
        elif cur_index == 1:
            reload_context(ui_manager)
        widget.paper_data = json.loads(json_util.dumps(temp_paper), object_hook=objectid_decoder)

    def view_paper():
        ui_manager.signal.mongo.open_pdf(widget.paper_data.get("file_id", ""))

    for btn_info in [
        {"name": "save_btn", "icon": "save.png", "on_clicked": save_paper},
        {"name": "view_pdf", "icon": "pdf.png", "on_clicked": view_paper},
        ]:

        btn = getattr(widget, btn_info["name"])
        btn.setIcon(QIcon(os.path.join(ICONS_FOLDER_PATH, btn_info["icon"])))
        btn.setIconSize(QSize(18, 18))
        btn.clicked.connect(btn_info["on_clicked"])


    # widget.init_md = json.dumps(get_temp_paper(ui_manager, widget))

def disable_boxes(widget, props):
    widget_state = props.get("fill_mode", "")

    widget.venue_box.setReadOnly(widget_state != "" and props.get("venue", "") != "")
    widget.venue_type_box.setDisabled(widget_state != "" and props.get("venue_type", "") != "")
    widget.citation_box.setReadOnly(widget_state != "" and props.get("citation_count", "") != "")

def set_paper_props(ui_manager, widget, props, on_change):
    widget.title_box.setText(props.get("title", ""))
    widget.title_box.textChanged.connect(lambda: on_change(ui_manager, widget))
    widget.doi_box.setText(props.get("doi", ""))
    widget.doi_box.textChanged.connect(lambda: on_change(ui_manager, widget))
    widget.year_box.setValue(props.get("year", 2025))
    widget.year_box.valueChanged.connect(lambda: on_change(ui_manager, widget))

    widget.venue_box.setText(props.get("venue", ""))
    widget.venue_box.textChanged.connect(lambda: on_change(ui_manager, widget))

    widget.venue_type_box.setCurrentText(props.get("venue_type", ""))
    widget.venue_type_box.currentTextChanged.connect(lambda: on_change(ui_manager, widget))

    widget.citation_box.setValue(props.get("citation_count", 0))
    widget.citation_box.valueChanged.connect(lambda: on_change(ui_manager, widget))

    widget.abstract_box.setText(props.get("abstract", ""))
    widget.abstract_box.textChanged.connect(lambda: on_change(ui_manager, widget))

    widget.notes_box.setText(props.get("notes", ""))
    widget.notes_box.textChanged.connect(lambda: on_change(ui_manager, widget))


def setup_tab_contexts(ui_manager):

    def on_import_change(widget):
        import_from = widget.import_from.currentText()
        if import_from == "Libraries":
            widget.library_list.setVisible(True)
            widget.context_list.setVisible(False)
        elif import_from == "Contexts":
            widget.library_list.setVisible(False)
            widget.context_list.setVisible(True)

    def add_context_(edit=False):
        from gui.shapes.py_files import new_context_dialog as contextDialog
        new_context_dialog = QDialog(ui_manager.ui.main_window)
        new_context_dialog.setWindowIcon(ui_manager.icon)
        ui = contextDialog.Ui_new_context_dialog()
        ui.setupUi(new_context_dialog)
        new_context_dialog.setMinimumHeight(250)
        new_context_dialog.setMaximumHeight(250)
        new_context_dialog.setWindowTitle("New Context" if not edit else "Edit Context")
        ui.error_lbl.setText("")
        ui.error_lbl.setStyleSheet("color: red")
        ui.context_list.setVisible(False)
        ui.import_from.currentTextChanged.connect(lambda: on_import_change(ui))
        ui.library_list.setSelectionMode(QListWidget.NoSelection)
        ui.library_list.setStyleSheet("""QListWidget {padding-top: 3px;}""")
        
        libraries = ui_manager.signal.mongo.fetch_containers(ui_manager.signal.cur_review)
        contexts = ui_manager.signal.mongo.fetch_contexts(ui_manager.signal.cur_review)
        target_libraries, target_contexts = [], []
        cur_context = [x for x in ui_manager.signal.mongo.fetch_contexts(ui_manager.signal.cur_review) if x["name"] == ui_manager.signal.cur_context]
        cur_context_name = cur_context[0]["name"] if len(cur_context) else ""
        if edit:
            if len(cur_context):
                ui.new_name.setText(cur_context_name)
                target_libraries = cur_context[0]['target_libraries']
                target_contexts = cur_context[0]['target_contexts']
                if len(target_libraries):
                    ui.import_from.setCurrentText("Libraries")
                elif len(target_contexts):
                    ui.import_from.setCurrentText("Contexts")
            else:
                edit = False
    
        for lib in libraries:
            item = QListWidgetItem(lib["name"])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked if lib["_id"] not in target_libraries else Qt.Checked)
            ui.library_list.addItem(item)

        for context in contexts:
            if context["name"] != cur_context_name:
                item = QListWidgetItem(context["name"])
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked if context["_id"] not in target_contexts else Qt.Checked)
                ui.context_list.addItem(item)

        def on_ok():
            new_name = ui.new_name.text().strip()
            if not new_name:
                ui.error_lbl.setText("Empty name")
                return
            if new_name != cur_context_name and new_name in [x["name"] for x in ui_manager.signal.mongo.fetch_contexts(ui_manager.signal.cur_review)]:
                ui.error_lbl.setText("Name already in use")
                return
            
            lib_ids, contexts_ids = [], []
            if ui.import_from.currentText() == "Libraries":
                checked_items = []
                for i in range(ui.library_list.count()):
                    item = ui.library_list.item(i)
                    if item.checkState() == Qt.Checked:
                        checked_items.append(item.text())
                if not len(checked_items):
                    ui.error_lbl.setText("Select libraries")
                    return
                lib_ids = [x["_id"] for x in ui_manager.signal.mongo.fetch_containers(ui_manager.signal.cur_review) if x["name"] in checked_items]
            elif ui.import_from.currentText() == "Contexts":
                checked_items = []
                for i in range(ui.context_list.count()):
                    item = ui.context_list.item(i)
                    if item.checkState() == Qt.Checked:
                        checked_items.append(item.text())
                if not len(checked_items):
                    ui.error_lbl.setText("Select contexts")
                    return
                contexts_ids = [x["_id"] for x in ui_manager.signal.mongo.fetch_contexts(ui_manager.signal.cur_review) if x["name"] in checked_items]
            
            new_context_dialog.accept()
            if edit:
                ui_manager.signal.mongo.edit_context(ui_manager.signal.cur_review, cur_context_name, new_name, lib_ids, contexts_ids)
                load_contexts(ui_manager, new_name)
                ui_manager.signal.cur_context = ""
                load_context(ui_manager, cur_context_name)
            else:
                ui_manager.signal.mongo.create_context(ui_manager.signal.cur_review, new_name, lib_ids, contexts_ids)
                load_contexts(ui_manager)

        ui.buttonBox.accepted.disconnect()
        ui.buttonBox.accepted.connect(on_ok)
        new_context_dialog.exec()

    def rm_context():
        from gui.shapes.py_files import generalDialog as deleteReviewDialog
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
    
    table = ui_manager.ui.referenceView
    table.setSortingEnabled(True)
    table.setEditTriggers(QTableView.NoEditTriggers)
    table.doubleClicked.connect(lambda item: show_paper(ui_manager, item))
    shortcut = QShortcut(QKeySequence("Ctrl+C"), table)
    shortcut.activated.connect(lambda: copy_selected(table))
    ui_manager.ui.expand_btn.clicked.connect(lambda: showExpandWidget(ui_manager))
    ui_manager.ui.context_name_lbl.setText("")
    ui_manager.ui.add_context.clicked.connect(add_context_)
    ui_manager._open_paper_windows = []
    ui_manager._reload_table = reload_table
    ui_manager.reload_table_delayed = False

    def on_tab_changed(index):
        if ui_manager.reload_table_delayed and ui_manager.ui.tab_widget.tabText(index) == "Contexts":
            ui_manager.reload_table_delayed = False
            load_data(ui_manager)
    ui_manager.ui.tab_widget.currentChanged.connect(on_tab_changed)
    setup_processes(ui_manager)
