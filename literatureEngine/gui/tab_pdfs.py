import os
import json
from utils import pprint, ICONS_FOLDER_PATH
from fetch_papers.fetch import fetch_metadata
from PyQt5.QtWidgets import QWidget, QDialog, QPushButton, QListWidget, QListWidgetItem, QSizePolicy
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QSize
from gui.utils import Operation, OpClass, create_paper_id, normalize_name


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
        args["result"] = fetch_metadata(normalized_filename, "title")
        args["result"]["fill_mode"] = "auto"
        if args["result"].get("doi", None):
            ui_manager.signal.mongo.add_paper(ui_manager.signal.cur_review, args["result"], missing_md["_id"])
    
    def end(self, signal, args):
        pass


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
        result = fetch_metadata(self.value, self.obj)
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
    if ui_manager.paper_selected:
        ui_manager.signal.mongo.remove_paper(ui_manager.signal.cur_review, ui_manager.paper_selected["_id"])
        ui_manager.paper_selected = None
    load_paper_props(ui_manager, widget)


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

    widget.title_box.setText(props.get("title", ""))
    widget.title_box.textChanged.connect(lambda: manual_change(ui_manager, widget))
    widget.doi_box.setText(props.get("doi", ""))
    widget.year_box.setValue(props.get("year", 2025))
    widget.abstract_box.setText(props.get("abstract", ""))
    widget.abstract_box.textChanged.connect(lambda: manual_change(ui_manager, widget))
    widget.notes_box.setText(props.get("notes", ""))
    widget.notes_box.textChanged.connect(lambda: manual_change(ui_manager, widget))

    widget.init_md = json.dumps(get_temp_paper(ui_manager, widget))


def get_temp_paper(ui_manager, widget):
    return {
        "fill_mode": "manual",
        "paperId": create_paper_id(widget.title_box.toPlainText(), widget.doi_box.text(), widget.year_box.value()),
        "title": widget.title_box.toPlainText(),
        "doi": widget.doi_box.text(),
        "year": widget.year_box.value(),
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

def format_authors(authors):
    formatted = []
    for a in authors:
        parts = a.split(" ")
        last = parts[-1]
        initials = [p[0] + "." for p in parts[:-1] if p.lower() != "none"]
        formatted.append(f"{''.join(initials)} {last}")
    return ", ".join(formatted)



map_ = {'USER STORY QUALITY EVALUATION: ANALYZING FRAMEWORKS AND APPLICATION METHODS': '9f20c5e9d20102e91db8c238251586b9db041613', 'Automatic Requirements Engineering: Activities, Methods, Tools, and Domains – A Systematic Literature Review': 'aeedbe8ed96ff0144d8438db1ba574e1bd3399fe', 'Requirements Elicitation in Transition: A Review of Conventional and Contemporary Approaches': 'e9143ccd592f8494f14818ff38db47a45d84dd61', 'Privacy, ethics, transparency, and accountability in AI systems for wearable devices': 'e2f29532d298579799721d82dac20c0567823670', 'Large Language Models in Software Engineering: Automation, Collaboration, and Challenges': '2d41d032763a3251846783b3e2ad120dd33e8218', 'Use of Artificial Intelligence and Large Language Models in Software Development': 'da014138cad4a144abdb73d2d87b149ecb2a63ab', 'Formal Requirements Engineering and Large Language Models A Two‑Way Roadmap': '1a09c6ed57c4', 'Using Large Language Models for Natural Language Processing Tasks in Requirements Engineering A Systematic Guideline copy': 'd8b70e4ddbbd', 'A Systematic Mapping Review: Tracking the Relationships Between Software Artifacts using NLP': '1faffcb5ca36be3cbf889b84179cc8b6fe8e6f75', 'Frontiers article Research directions for using LLM in software requirement engineering': 'fd42366a61b3', 'Leveraging AI-driven requirements for SysML modeling of the IoBT: A comprehensive investigation': '2c9dd3f35df0a97e575155df7f2e0bd918673d3b', 'AI-Driven Prioritization Techniques of Requirements in Agile Methodologies: A Systematic Literature Review': '028f01e1b01330353294c4ef713132ec2a4f8ea5', 'Large Language Model Is Not a Good Few-shot Information Extractor, but a Good Reranker for Hard Samples!': '0100785773b8217c44606ab260e3212f93b0a4fd', 'Large Language Models for Software Engineering Survey and Open Problems': '13853f73b428', 'Research directions for using LLM in software requirement engineering a systematic review': 'e20d2510ec99', 'A Bird’s Eye View of Natural Language Processing and Requirements Engineering': '8fc3cee973e8dc522eb65e1cf6a5830aeff1da99', 'Role of Generative AI in Software Development': 'f8e2b38e0221717122ca23b17c9773376b249e90', 'Use of LLM assistants as support in the Project’s Formulation process: A Systematic Mapping': '168ea16d5e51097c0adb353e57b7caeaed87d3fc', 'Large Language Models (LLMs) for Requirements Engineering (RE) A Systematic Literature Review': 'd31788fb9f03', 'Innovation and Challenges in Product Design Paradigms Based on Artificial Intelligence-Generated Content (AIGC): A Review': '59d02a1aad71f7a3a426d1e1688e07825c9fc304', 'Large language models in software engineering': '0a0f0a4a57c8ddaeb4c5ba91fbf77343232dd158', 'Prompt Engineering Guidelines for Using Large Language Models in Requirements Engineering': '9ad8a800d09e'}
map_ = {**map_,
  "Requirements Management Model (RMM): A Proposed Model for Successful Delivery of Software Projects": "535fb33b4d614ebe417dd37e10907045601d4d5c",
  "Requirement Analysis on Network Teaching Management System": "4a426e709bee574a1679a9ce875e0f075ca9c7b4",
  "On Satisfying the Android OS Community: User Feedback Still Central to Developers' Portfolios": "b08892d4207a0babd835358712c66aebbf64b3ce",
  "Which Requirements Artifact Quality Defects are Automatically Detectable? A Case Study": "240590f7b140393d80995a25b6995432dba5bae6",
  "Advances in Requirements Engineering for Well-Being, Aging, and Health: A Systematic Mapping Study": "e1d794ada96824a7341a33fde4d620c794c0959b",
  "Challenges of requirements engineering in the (XP) methodology: a systematic review": "35dea4e931e9486118b76f8915ff7432c2702ea6",
  "Advances in automated support for requirements engineering: a systematic literature review": "c1860303ee4421980a79a53f94e85390bddb7d57",
  "REQUIREMENTS CHANGE MANAGEMENT (RCM) TOOL FOR PAKISTAN SOFTWARE INDUSTRY": "98567555988875c45db8cf37330231838a448d28",
  "Requirements document relations": "0434754f5e20d4f70e5f00ef77af4d76a3d4263e",
  "Non-functional requirements for machine learning: understanding current use and challenges among practitioners": "5fcb403f08050a20a591aa3ddc35efa48611ccdb",
  "Investigating requirements change requests": "cef1d0fa2320f5c62d990aa2f73cd96b6f252fff",
  "Integraci\u00f3n de pruebas remotas de usabilidad en Programaci\u00f3n Extrema: revisi\u00f3n de literatura": "bdc4e2d32ace2e46536c4151225965aac0d4771b",
  "Modelling the quantification of requirements technical debt": "2de4507c41b5d2b025ea746f8231d72cf8e22f56",
  "Designing Internet of Things Systems for Circular Economy and Digital Product Passports \u2013 A Requirements Engineering Perspective": "31027700d2a79d5139a613d88187c41b36267bc5"  
}

def char_safe_modifier(key: str) -> str:
    return key.replace("_", "\\_")


def generate_bibitem(paper):
    authors = format_authors(paper["authors"])
    container = paper.get('container_title') or paper.get('venue') or "arXiv.org"
    first_author_last = authors[0].split()[-1].lower() if authors else "unknown"
    short_title = ''.join(filter(str.isalnum, paper['title'].split()[0].lower()))
    year = paper.get('year', 'n.d.')
    if paper['title'] in map_:
        cite_key = f"ref:{map_[paper['title']]}"
    else:
        cite_key = f"ref:{first_author_last}_{short_title}_{year}"

    # Build LaTeX bibitem string
    bibitem = f"\\bibitem{{{cite_key}}} {authors}: {paper['title']}. {container} ({year})."
    
    # Add DOI if available
    if paper.get('doi'):
        bibitem += f" https://doi.org/{paper['doi']}"

    return char_safe_modifier(bibitem)


def save_references(ui_manager):
    paper_file_mds, all_user_paper_mds = get_all_user_paper_mds(ui_manager)
    for paper in all_user_paper_mds:
        try:
            reference = generate_bibitem(paper)
            print(reference)
        except:
            import traceback
            print(paper)


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

    return True


def load_user_pdfs(ui_manager):
    clear_user_papers(ui_manager)
    user_pdfs_md = ui_manager.signal.mongo.fetch_user_pdf_mds(ui_manager.signal.cur_review, ui_manager.signal.cur_library)
    list_widget = QListWidget(ui_manager.ui.tab_pdfs)
    list_widget.setMaximumHeight(16777215)
    list_widget.setSortingEnabled(True)
    list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    list_widget.setWordWrap(True)
    list_widget.setTextElideMode(Qt.ElideNone)
    for user_pdf_md in user_pdfs_md:
        item = QListWidgetItem(user_pdf_md["filename"])
        item.setData(Qt.UserRole, user_pdf_md)
        list_widget.addItem(item)
    list_widget.currentItemChanged.connect(lambda current, _: load_paper(ui_manager, current))
    ui_manager.ui.list_user_pdfs = list_widget
    ui_manager.ui.user_papers_layout.addWidget(list_widget)
    save_references(ui_manager)


def clear_user_papers(ui_manager):
    layout = ui_manager.ui.user_papers_layout
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.setParent(None)
            widget.deleteLater()
    clear_paper(ui_manager)


def load_container(ui_manager, container):
    ui_manager.signal.set_current_library(container)
    ui_manager.ui.delete_container.setVisible(True)
    ui_manager.ui.user_paper_lbl.setVisible(True)
    ui_manager.ui.search_by_filename.setVisible(True)
    ui_manager.ui.user_papers.setVisible(True)
    ui_manager.ui.auto_paper_lbl.setVisible(True)
    ui_manager.ui.auto_papers.setVisible(True)
    load_user_pdfs(ui_manager)
    layout = ui_manager.ui.container_area_layout
    
    for i in range(layout.count()):
        item = layout.itemAt(i)
        widget = item.widget()
        if widget:
            widget.setProperty("activeContainer", widget.name == container)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    ui_manager.ui.container_name_lbl.setText(f"Library: {container}")


def get_all_user_paper_mds(ui_manager):
    layout = ui_manager.ui.user_papers_layout
    list_widget_item = layout.itemAt(0)
    list_widget = list_widget_item.widget()
    paper_file_mds = [list_widget.item(index).data(Qt.UserRole) for index in range(list_widget.count())]
    all_user_paper_mds = ui_manager.signal.mongo.get_papers_by_fs_ids(ui_manager.signal.cur_review, [x["_id"] for x in paper_file_mds])
    return paper_file_mds, all_user_paper_mds


def find_missing_md_user_papers(ui_manager):
    paper_file_mds, all_user_paper_mds = get_all_user_paper_mds(ui_manager)
    missing_md_for_paper_filenames = [p for p in paper_file_mds if p["_id"] not in [x["file_id"] for x in all_user_paper_mds]]
    for missing_md in missing_md_for_paper_filenames:
        ui_manager.send_operation(Operation(ui_manager.signal, SearchMD, {"missing_md": missing_md, "ui_manager": ui_manager}))


def clear_layout(ui_manager):
    ui_manager.signal.set_current_library("")
    ui_manager.ui.container_name_lbl.setText("")
    ui_manager.ui.delete_container.setVisible(False)
    ui_manager.ui.user_paper_lbl.setVisible(False)
    ui_manager.ui.search_by_filename.setVisible(False)
    ui_manager.ui.user_papers.setVisible(False)
    ui_manager.ui.auto_paper_lbl.setVisible(False)
    ui_manager.ui.auto_papers.setVisible(False)
    clear_user_papers(ui_manager)

    layout = ui_manager.ui.container_area_layout
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.setParent(None)
            widget.deleteLater()


def load_containers(ui_manager):
    clear_layout(ui_manager)
    layout = ui_manager.ui.container_area_layout
    all_containers = ui_manager.signal.fetch_containers()
    for container in all_containers:
        btn = QPushButton(container, ui_manager.ui.tab_pdfs)
        btn.setMinimumHeight(30)
        font = QFont()
        font.setPointSize(14)
        btn.setFont(font)
        layout.addWidget(btn)
        btn.name = container
        btn.clicked.connect(lambda _, c=container: load_container(ui_manager, c))
    return all_containers


def setup_tab_pdfs(ui_manager):
    ui_manager.ui.user_papers.setAcceptDrops(True)

    def dragEnterEvent(event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(event):
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if filepath.lower().endswith(".pdf"):
                print("Dropped PDF:", filepath)
                ui_manager.send_operation(Operation(ui_manager.signal, SavePDF, {"filepath": filepath}))

    ui_manager.ui.user_papers.dragEnterEvent = dragEnterEvent
    ui_manager.ui.user_papers.dropEvent = dropEvent

    def add_container_():
        from gui import new_review_dialog as reviewDialog
        new_library_dialog = QDialog(ui_manager.ui.main_window)
        new_library_dialog.setWindowIcon(ui_manager.icon)
        ui = reviewDialog.Ui_new_review_dialog()
        ui.setupUi(new_library_dialog)
        ui.requestTitle.setText("Library's name:")
        ui.new_name.setPlaceholderText("Enter a name for the new library here...")
        new_library_dialog.setWindowTitle("New Library")
        ui.error_lbl.setText("")
        ui.error_lbl.setStyleSheet("color: red")

        def on_ok():
            new_name = ui.new_name.text().strip()
            already_used = load_containers(ui_manager)
            if not new_name:
                ui.error_lbl.setText("Empty name")
                return
            if new_name in already_used:
                ui.error_lbl.setText("Name already in use")
                return
            new_library_dialog.accept()
            ui_manager.signal.mongo.create_container(ui_manager.signal.cur_review, new_name)
            clear_layout(ui_manager)
            load_containers(ui_manager)

        ui.buttonBox.accepted.disconnect()
        ui.buttonBox.accepted.connect(on_ok)
        new_library_dialog.exec()

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

        ui.buttonBox.accepted.disconnect()
        ui.buttonBox.accepted.connect(on_ok)
        delete_library_dialog.exec()


    for btn_info in [
        {"name": "search_by_filename", "icon": "search.png", "tooltip": "Search by filename", "on_clicked": lambda _: find_missing_md_user_papers(ui_manager)},
        {"name": "delete_container", "icon": "trash.png", "tooltip": "Delete library", "on_clicked": rm_container},
        ]:
        btn = getattr(ui_manager.ui, btn_info["name"])
        btn.setIcon(QIcon(os.path.join(ICONS_FOLDER_PATH, btn_info["icon"])))
        btn.setIconSize(QSize(18, 18))
        btn.clicked.connect(btn_info["on_clicked"])
        btn.setToolTip(btn_info["tooltip"])

    ui_manager.ui.container_name_lbl.setText("")
    ui_manager.ui.add_container.clicked.connect(add_container_)
