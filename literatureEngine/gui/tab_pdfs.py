import os
import json
from utils import ICONS_FOLDER_PATH
from fetch_papers.fetch import fetch_metadata
from PyQt5.QtWidgets import QWidget, QDialog, QPushButton, QListWidget, QListWidgetItem, QSizePolicy, QStyledItemDelegate, QStyleOptionViewItem, QStyle
from PyQt5.QtGui import QFont, QIcon, QColor, QBrush, QPainter
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QSize
from gui.tab_contexts import reload_context
from gui.utils import pprint, Operation, OpClass, VENUE_TYPES


class SavePDF(OpClass):

    def start(self, signal, args):
        filepath = args["filepath"]
        args["saved_pdf"] = signal.mongo.save_user_pdf(signal.cur_review, signal.cur_library, filepath)
    
    def end(self, signal, args):
        md = signal.mongo.fetch_user_pdf_md(args["saved_pdf"]["_id"])
        add_user_paper(signal.ui_manager, md)


class SearchMD(OpClass):

    def start(self, signal, args):
        ui_manager = args["ui_manager"]
        missing_md = args["missing_md"]
        normalized_filename = missing_md["filename"].replace(".pdf", "").replace("_", " ")
        args["result"] = fetch_metadata(signal, normalized_filename, "title")
        if args["result"].get("doi", None):
            args["result"]["fill_mode"] = "auto"
            ui_manager.signal.mongo.add_paper(ui_manager.signal.cur_review, args["result"], missing_md["_id"])
    
    def end(self, signal, args):
        list_widget = args["ui_manager"].ui.list_user_pdfs
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            existing_md = item.data(Qt.UserRole)
            if existing_md["_id"] == args["missing_md"]["_id"]:
                set_item_background_by_md(args["ui_manager"], item)
                if hasattr(args["ui_manager"], "pdf_selected_btn") and args["ui_manager"].pdf_selected_btn == item:
                    load_paper(args["ui_manager"], item)


def clear_paper(ui_manager):
    layout = ui_manager.ui.paper_layout
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.setParent(None)
            widget.deleteLater()


class SearchWorker(QThread):
    finished = pyqtSignal(object)

    def __init__(self, ui_manager, obj):
        super().__init__()
        self.ui_manager = ui_manager
        self.obj = obj
    
    def set_value(self, value):
        self.value = value

    def run(self):
        result = fetch_metadata(self.ui_manager.signal, self.value, self.obj)
        self.finished.emit(result)


def view_paper(ui_manager, widget):
    paper_fs_id = ui_manager.pdf_selected_btn.data(Qt.UserRole)["_id"]
    ui_manager.signal.mongo.open_pdf(paper_fs_id)


def search_by(ui_manager, default_query, widget=None, obj="title"):
    from gui import new_review_dialog as reviewDialog
    search_name_dialog = QDialog(ui_manager.ui.main_window)
    search_name_dialog.setWindowIcon(ui_manager.icon)
    ui = reviewDialog.Ui_new_review_dialog()
    ui.setupUi(search_name_dialog)
    ui.requestTitle.setText(f"Paper's {obj}:")
    ui.new_name.setPlaceholderText(f"Enter the paper's {obj} here...")
    if obj == "title":
        ui.new_name.setText(default_query)
    search_name_dialog.setWindowTitle(f"Search by {obj}")
    ui.error_lbl.setText("")
    ui.error_lbl.setStyleSheet("color: red")

    def on_ok():
        value = ui.new_name.text().strip()
        if not value:
            ui.error_lbl.setText(f"Empty {obj}")
            return
        
        ui.error_lbl.setText("Searching... Please wait.")
        ui.buttonBox.setEnabled(False)
        ui_manager.search_worker = SearchWorker(ui_manager, obj)
        ui_manager.search_worker.set_value(value)
        ui_manager.search_worker.finished.connect(lambda result: on_search_complete(result))
        ui_manager.search_worker.start()

    def on_search_complete(result):
        if not result:
            ui.buttonBox.setEnabled(True)
            ui.error_lbl.setText("Paper not found.")
            return
        
        result["fill_mode"] = "auto"
        
        if result.get("doi", None):
            ui_manager.signal.mongo.add_paper(ui_manager.signal.cur_review, result, ui_manager.pdf_selected_btn.data(Qt.UserRole)["_id"])    
            set_item_background_by_md(ui_manager, ui_manager.pdf_selected_btn)
            if widget:
                load_paper_props(ui_manager, widget, result)
        search_name_dialog.accept()

    ui.buttonBox.accepted.disconnect()
    ui.buttonBox.accepted.connect(on_ok)
    search_name_dialog.exec()


def remove_paper(ui_manager):
    from gui import generalDialog as deleteReviewDialog
    paper_fs_id = ui_manager.pdf_selected_btn.data(Qt.UserRole)["_id"]
    delete_paper_dialog = QDialog(ui_manager.ui.main_window)
    delete_paper_dialog.setWindowIcon(ui_manager.icon)
    ui = deleteReviewDialog.Ui_Dialog()
    ui.setupUi(delete_paper_dialog)
    ui.dialog_msg.setText(f"Are you sure you want to delete the selected paper from this library?")

    def on_ok():
        ui_manager.signal.mongo.delete_user_pdf_ref(ui_manager.signal.cur_review, ui_manager.signal.cur_library, paper_fs_id)
        delete_paper_dialog.accept()
        load_user_pdfs(ui_manager)

    ui.buttonBox.accepted.disconnect()
    ui.buttonBox.accepted.connect(on_ok)
    delete_paper_dialog.exec()


def clear_paper_md(ui_manager, widget):
    try:
        if ui_manager.paper_selected:
            ui_manager.signal.mongo.remove_paper(ui_manager.signal.cur_review, ui_manager.paper_selected["_id"])
            ui_manager.paper_selected = None
        load_paper_props(ui_manager, widget)
        set_item_background_by_md(ui_manager, ui_manager.pdf_selected_btn)
    except:
        import traceback
        print(traceback.format_exc())


def manual_change(ui_manager, widget):
    temp_paper = get_temp_paper(ui_manager, widget)
    valid_change = temp_paper["title"].strip() != "" and widget.init_md != json.dumps(temp_paper)
    widget.save_btn.setVisible(valid_change)


def load_paper_props(ui_manager, widget, temp_paper=None):
    props = ui_manager.paper_selected if ui_manager.paper_selected else {}
    props = temp_paper if temp_paper else props
    widget_state = props.get("fill_mode", "")  # "maual" / "auto" / ""

    widget.search_by_title.setVisible(widget_state == "")
    widget.search_by_doi.setVisible(widget_state == "")
    widget.save_btn.setVisible(False)

    widget.title_box.setReadOnly(widget_state != "")
    widget.doi_box.setReadOnly(widget_state != "")
    widget.year_box.setReadOnly(widget_state != "")
    widget.venue_box.setReadOnly(widget_state != "" and props.get("venue", "") != "")
    widget.venue_type_box.setDisabled(widget_state != "" and props.get("venue_type", "") != "")
    widget.citation_box.setReadOnly(widget_state != "" and props.get("citation_count", "") != "")

    widget.title_box.setText(props.get("title", ""))
    widget.title_box.textChanged.connect(lambda: manual_change(ui_manager, widget))
    widget.doi_box.setText(props.get("doi", ""))
    widget.year_box.setValue(props.get("year", 2025))
    widget.venue_box.setText(props.get("venue", ""))
    widget.venue_box.textChanged.connect(lambda: manual_change(ui_manager, widget))
    widget.venue_type_box.setCurrentText(props.get("venue_type", ""))
    widget.venue_type_box.currentTextChanged.connect(lambda: manual_change(ui_manager, widget))
    widget.citation_box.setValue(props.get("citation_count", 0))
    widget.abstract_box.setText(props.get("abstract", ""))
    widget.abstract_box.textChanged.connect(lambda: manual_change(ui_manager, widget))
    widget.notes_box.setText(props.get("notes", ""))
    widget.notes_box.textChanged.connect(lambda: manual_change(ui_manager, widget))

    widget.init_md = json.dumps(get_temp_paper(ui_manager, widget))


def get_temp_paper(ui_manager, widget):
    return {
        "fill_mode": "manual",
        "title": widget.title_box.toPlainText(),
        "doi": widget.doi_box.text(),
        "year": widget.year_box.value(),
        "venue": widget.venue_box.toPlainText(),
        "venue_type": widget.venue_type_box.currentText(),
        "citation_count": widget.citation_box.value(),
        "abstract": widget.abstract_box.toPlainText(),
        "notes": widget.notes_box.toPlainText(),
    }


def save_paper(ui_manager, widget):
    temp_paper = get_temp_paper(ui_manager, widget)
    str_md = json.dumps(temp_paper)
    widget.init_md = str_md
    widget.save_btn.setVisible(False)
    load_paper_props(ui_manager, widget, temp_paper)
    ui_manager.signal.mongo.add_paper(ui_manager.signal.cur_review, temp_paper, ui_manager.pdf_selected_btn.data(Qt.UserRole)["_id"])
    set_item_background_by_md(ui_manager, ui_manager.pdf_selected_btn)


def format_authors(authors):
    formatted = []
    for a in authors:
        parts = a.split(" ")
        last = parts[-1]
        initials = [p[0] + "." for p in parts[:-1] if p.lower() != "none"]
        formatted.append(f"{''.join(initials)} {last}")
    return ", ".join(formatted)


# def char_safe_modifier(key: str) -> str:
#     return key.replace("_", "\\_")


# def generate_bibitem(paper):
#     authors = format_authors(paper["authors"])
#     container = paper.get('container_title') or paper.get('venue') or "arXiv.org"
#     first_author_last = authors[0].split()[-1].lower() if authors else "unknown"
#     short_title = ''.join(filter(str.isalnum, paper['title'].split()[0].lower()))
#     year = paper.get('year', 'n.d.')
#     if paper['title'] in map_:
#         cite_key = f"ref:{map_[paper['title']]}"
#     else:
#         cite_key = f"ref:{first_author_last}_{short_title}_{year}"

#     # Build LaTeX bibitem string
#     bibitem = f"\\bibitem{{{cite_key}}} {authors}: {paper['title']}. {container} ({year})."
    
#     # Add DOI if available
#     if paper.get('doi'):
#         bibitem += f" https://doi.org/{paper['doi']}"

#     return char_safe_modifier(bibitem)


def load_paper(ui_manager, paper_item):
    from gui import paper_widget
    clear_paper(ui_manager)
    ui_manager.pdf_selected_btn = paper_item
    
    paper_file_id = paper_item.data(Qt.UserRole)["_id"]
    ui_manager.paper_selected = ui_manager.signal.mongo.get_paper_by_fs_id(ui_manager.signal.cur_review, paper_file_id)

    container = QWidget()
    widget = paper_widget.Ui_paper_widget()
    widget.setupUi(container)
    default_query = ui_manager.pdf_selected_btn.data(Qt.UserRole)["filename"].replace(".pdf", "")

    for btn_info in [
        {"name": "rm_paper", "icon": "trash.png", "on_clicked": lambda _: remove_paper(ui_manager)},
        {"name": "save_btn", "icon": "save.png", "on_clicked": lambda _, widget=widget: save_paper(ui_manager, widget)},
        {"name": "clear_btn", "icon": "clear.png", "on_clicked": lambda _: clear_paper_md(ui_manager, widget)},
        {"name": "view_pdf", "icon": "pdf.png", "on_clicked": lambda _: view_paper(ui_manager, widget)},
        {"name": "search_by_title", "icon": "search.png", "on_clicked": lambda _, widget=widget: search_by(ui_manager, default_query, widget, "title")},
        {"name": "search_by_doi", "icon": "search.png", "on_clicked": lambda _, widget=widget: search_by(ui_manager, default_query, widget, "doi")},
        ]:

        btn = getattr(widget, btn_info["name"])
        btn.setIcon(QIcon(os.path.join(ICONS_FOLDER_PATH, btn_info["icon"])))
        btn.setIconSize(QSize(18, 18))
        btn.clicked.connect(btn_info["on_clicked"])

    ui_manager.ui.paper_layout.addWidget(container, stretch=1)
    widget.venue_type_box.addItems(VENUE_TYPES)
    load_paper_props(ui_manager, widget)


def add_user_paper(ui_manager, user_pdf_md):
    list_widget = ui_manager.ui.list_user_pdfs
    new_id = user_pdf_md["_id"]

    for i in range(list_widget.count()):
        item = list_widget.item(i)
        existing_md = item.data(Qt.UserRole)

        if existing_md and existing_md["_id"] == new_id:
            return False

    item = QListWidgetItem(user_pdf_md["filename"])
    item.setData(Qt.UserRole, user_pdf_md)
    list_widget.addItem(item)
    set_item_background_by_md(ui_manager, item)
    ui_manager.ui.user_paper_lbl.setText(f"Your papers ({list_widget.count()})")
    return True


def set_items_background(ui_manager):
    list_widget = ui_manager.ui.list_user_pdfs
    ui_manager.ui.abstract_papers = []
    _, p_mds = get_all_user_paper_mds(ui_manager)
    map_ = {x["file_id"]: x for x in p_mds if "file_id" in x}
    ui_manager.ui.user_paper_lbl.setText(f"Your papers ({list_widget.count()})")

    for i in range(list_widget.count()):
        item = list_widget.item(i)
        existing_md = item.data(Qt.UserRole)
        paper_md = map_.get(existing_md["_id"], None)
        if set_item_state(item, paper_md):
            ui_manager.ui.abstract_papers += [item]


def set_item_background_by_md(ui_manager, item):
    p_mds = get_user_paper_md(ui_manager, item)
    has_abstract = set_item_state(item, p_mds)
    _load_contexts = False
    if item in ui_manager.ui.abstract_papers and not has_abstract:
        _load_contexts = True
        ui_manager.ui.abstract_papers = [x for x in ui_manager.ui.abstract_papers if x != item]
    elif item not in ui_manager.ui.abstract_papers and has_abstract:
        _load_contexts = True
        ui_manager.ui.abstract_papers += [item]
    if _load_contexts:
        reload_context(ui_manager)


class TransparentSelectionDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        opt = QStyleOptionViewItem(option)
        opt.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, opt, index)

        if option.state & QStyle.StateFlag.State_MouseOver:
            painter.save()
            hover_color = QColor(0, 0, 0, 15)
            painter.setBrush(hover_color)
            painter.setPen(Qt.NoPen)
            painter.drawRect(option.rect)
            painter.restore()

        if option.state & QStyle.StateFlag.State_Selected:
            painter.save()
            overlay_color = QColor(0, 0, 0, 25)
            painter.setBrush(overlay_color)
            painter.setPen(Qt.NoPen)
            painter.drawRect(option.rect)
            painter.restore()


def set_item_state(item, paper_md):
    if paper_md:
        if paper_md.get("abstract", "") != "":
            item.setBackground(QColor("#55fc63"))
            item.setForeground(QBrush(QColor("black")))
            return True
        else:
            item.setBackground(QColor("#ffea72"))
            item.setForeground(QBrush(QColor("black")))
    else:
        item.setBackground(QColor("transparent"))
        item.setForeground(QBrush(QColor("black")))


def load_user_pdfs(ui_manager):
    clear_user_papers(ui_manager)
    user_pdfs_md = ui_manager.signal.mongo.fetch_user_pdf_mds(ui_manager.signal.cur_review, ui_manager.signal.cur_library)
    list_widget = QListWidget(ui_manager.ui.tab_pdfs)
    list_widget.setMaximumHeight(16777215)
    list_widget.setMouseTracking(True)
    list_widget.setSortingEnabled(True)
    list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    list_widget.setWordWrap(True)
    list_widget.setTextElideMode(Qt.ElideNone)
    ui_manager.ui.list_user_pdfs = list_widget
    for user_pdf_md in user_pdfs_md:
        item = QListWidgetItem(user_pdf_md["filename"])
        item.setData(Qt.UserRole, user_pdf_md)
        list_widget.addItem(item)
    list_widget.setItemDelegate(TransparentSelectionDelegate(list_widget))
    list_widget.currentItemChanged.connect(lambda current, _: load_paper(ui_manager, current))
    ui_manager.ui.user_papers_layout.addWidget(list_widget)
    set_items_background(ui_manager)


def clear_user_papers(ui_manager):
    layout = ui_manager.ui.user_papers_layout
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.setParent(None)
            widget.deleteLater()
    clear_paper(ui_manager)


def load_container(ui_manager, container_name):
    ui_manager.signal.set_current_library(container_name)
    ui_manager.ui.delete_container.setVisible(True)
    ui_manager.ui.edit_container.setVisible(True)
    ui_manager.ui.search_by_filename.setVisible(True)
    ui_manager.ui.user_papers.setVisible(True)
    load_user_pdfs(ui_manager)
    layout = ui_manager.ui.container_area_layout
    
    for i in range(layout.count()):
        item = layout.itemAt(i)
        widget = item.widget()
        if widget:
            widget.setProperty("activeContainer", widget.name == container_name)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    ui_manager.ui.container_name_lbl.setText(f"Library: {container_name}")


def get_all_user_paper_mds(ui_manager):
    layout = ui_manager.ui.user_papers_layout
    list_widget_item = layout.itemAt(0)
    list_widget = list_widget_item.widget()
    paper_file_mds = [list_widget.item(index).data(Qt.UserRole) for index in range(list_widget.count())]
    all_user_paper_mds = ui_manager.signal.mongo.get_papers_by_fs_ids(ui_manager.signal.cur_review, [x["_id"] for x in paper_file_mds])
    return paper_file_mds, all_user_paper_mds


def get_user_paper_md(ui_manager, item_):
    list_widget = ui_manager.ui.list_user_pdfs
    for i in range(list_widget.count()):
        item = list_widget.item(i)
        if item == item_:
            existing_md = item.data(Qt.UserRole)
            user_paper_md = ui_manager.signal.mongo.get_papers_by_fs_ids(ui_manager.signal.cur_review, [existing_md["_id"]])
            if len(user_paper_md):
                return user_paper_md[0]
            else:
                return None


def find_missing_md_user_papers(ui_manager):
    paper_file_mds, all_user_paper_mds = get_all_user_paper_mds(ui_manager)
    missing_md_for_paper_filenames = [p for p in paper_file_mds if p["_id"] not in [x["file_id"] for x in all_user_paper_mds]]
    for missing_md in missing_md_for_paper_filenames:
        ui_manager.send_operation(Operation(ui_manager.signal, SearchMD, missing_md["filename"], {"missing_md": missing_md, "ui_manager": ui_manager}))


def clear_layout(ui_manager):
    ui_manager.signal.set_current_library("")
    ui_manager.ui.container_name_lbl.setText("")
    ui_manager.ui.delete_container.setVisible(False)
    ui_manager.ui.edit_container.setVisible(False)
    ui_manager.ui.user_paper_lbl.setText("")
    ui_manager.ui.search_by_filename.setVisible(False)
    ui_manager.ui.user_papers.setVisible(False)
    clear_user_papers(ui_manager)

    layout = ui_manager.ui.container_area_layout
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.setParent(None)
            widget.deleteLater()


def load_containers(ui_manager, cur_container_name=""):
    clear_layout(ui_manager)
    layout = ui_manager.ui.container_area_layout
    all_containers = ui_manager.signal.mongo.fetch_containers(ui_manager.signal.cur_review)
    for container in all_containers:
        btn = QPushButton(container["name"], ui_manager.ui.tab_pdfs)
        btn.setMinimumHeight(30)
        font = QFont()
        font.setPointSize(14)
        btn.setFont(font)
        layout.addWidget(btn)
        btn.name = container["name"]
        btn.clicked.connect(lambda _, c=container["name"]: load_container(ui_manager, c))
        if cur_container_name == container["name"]:
            load_container(ui_manager, cur_container_name)


def setup_tab_pdfs(ui_manager):
    ui_manager.ui.user_papers.setAcceptDrops(True)

    def dragEnterEvent(event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(event):
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if filepath.lower().endswith(".pdf"):
                pprint("Dropped PDF:", filepath)
                ui_manager.send_operation(Operation(ui_manager.signal, SavePDF, filepath, {"filepath": filepath}))

    ui_manager.ui.user_papers.dragEnterEvent = dragEnterEvent
    ui_manager.ui.user_papers.dropEvent = dropEvent

    def add_container_(edit=False):
        from gui import new_review_dialog as reviewDialog
        new_library_dialog = QDialog(ui_manager.ui.main_window)
        new_library_dialog.setWindowIcon(ui_manager.icon)
        ui = reviewDialog.Ui_new_review_dialog()
        ui.setupUi(new_library_dialog)
        ui.requestTitle.setText("Library's name:")
        ui.new_name.setPlaceholderText("Enter a name for the library here...")
        new_library_dialog.setWindowTitle("New Library" if not edit else "Edit Library")
        ui.error_lbl.setText("")
        ui.error_lbl.setStyleSheet("color: red")
        old_name = ui_manager.signal.cur_library if edit else ""
        ui.new_name.setText(old_name)

        def on_ok():
            new_name = ui.new_name.text().strip()
            if not new_name:
                ui.error_lbl.setText("Empty name")
                return
            if new_name != old_name and new_name in [x["name"] for x in ui_manager.signal.mongo.fetch_containers(ui_manager.signal.cur_review)]:
                ui.error_lbl.setText("Name already in use")
                return
            new_library_dialog.accept()
            if edit:
                ui_manager.signal.mongo.edit_container(ui_manager.signal.cur_review, old_name, new_name)
                load_containers(ui_manager, new_name)
            else:
                ui_manager.signal.mongo.create_container(ui_manager.signal.cur_review, new_name)
                load_containers(ui_manager)

        ui.buttonBox.accepted.disconnect()
        ui.buttonBox.accepted.connect(on_ok)
        new_library_dialog.exec()

    def edit_container():
        add_container_(edit=True)

    def rm_container():
        from gui import generalDialog as deleteReviewDialog
        delete_library_dialog = QDialog(ui_manager.ui.main_window)
        delete_library_dialog.setWindowIcon(ui_manager.icon)
        ui = deleteReviewDialog.Ui_Dialog()
        ui.setupUi(delete_library_dialog)
        ui.dialog_msg.setText(f"Are you sure you want to delete the library \"{ui_manager.signal.cur_library}\" with all of its data?")

        def on_ok():
            ui_manager.signal.mongo.delete_container(ui_manager.signal.cur_review, ui_manager.signal.cur_library)
            delete_library_dialog.accept()
            load_containers(ui_manager)
            reload_context(ui_manager)

        ui.buttonBox.accepted.disconnect()
        ui.buttonBox.accepted.connect(on_ok)
        delete_library_dialog.exec()


    for btn_info in [
        {"name": "search_by_filename", "icon": "search.png", "tooltip": "Search by filename", "on_clicked": lambda _: find_missing_md_user_papers(ui_manager)},
        {"name": "delete_container", "icon": "trash.png", "tooltip": "Delete library", "on_clicked": rm_container},
        {"name": "edit_container", "icon": "edit.png", "tooltip": "Edit library", "on_clicked": edit_container},
        ]:
        btn = getattr(ui_manager.ui, btn_info["name"])
        btn.setIcon(QIcon(os.path.join(ICONS_FOLDER_PATH, btn_info["icon"])))
        btn.setIconSize(QSize(18, 18))
        btn.clicked.connect(btn_info["on_clicked"])
        btn.setToolTip(btn_info["tooltip"])

    ui_manager.ui.container_name_lbl.setText("")
    ui_manager.ui.add_container.clicked.connect(add_container_)
