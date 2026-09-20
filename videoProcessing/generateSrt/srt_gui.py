import json
import subprocess
import sys
import time
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QMainWindow, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from videoProcessing.generateSrt.extract_audio import extract_audio
from videoProcessing.generateSrt.transcribe_client import transcribe_movie
from videoProcessing.generateSrt.languages import FULL_LANGUAGE_CODES, detect_language_name, short_code

UNKNOWN_LANGUAGE = "(unknown)"
LANGUAGE_CHOICES = [UNKNOWN_LANGUAGE] + sorted(FULL_LANGUAGE_CODES.keys())
DEFAULT_TARGET_LANGUAGE = "German"

SUPPORTED_VIDEO_EXT = {"mp4", "m4v", "mkv", "avi"}
POLL_INTERVAL_MS = 5000
MAX_TRACKS = 2  # only the first 2 audio tracks are considered (dub + original is the common case)
VLC_PATH = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
ICON_PATH = Path(__file__).parent / "srt.ico"

GENERATED_COLOR = QColor("#A5D6A7")    # green -- already has a .gen-*.srt
IN_PROGRESS_COLOR = QColor("#FFD700")  # gold -- currently being generated (at most one row)

# Under pythonw (no console attached), spawning a console app like ffprobe
# briefly flashes a new console window unless this flag is set.
SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class NoScrollComboBox(QComboBox):
    """A QComboBox that ignores the mouse wheel, so scrolling the table
    doesn't accidentally change whichever combo the cursor happens to be
    over."""
    def wheelEvent(self, event):
        event.ignore()


def find_videos(folder: Path) -> list[Path]:
    return sorted(
        (p for p in folder.rglob("*") if p.is_file() and p.suffix.lower().lstrip(".") in SUPPORTED_VIDEO_EXT),
        key=lambda p: p.name.lower(),
    )


def has_generated_subs(video: Path) -> bool:
    return any(video.parent.glob(f"{video.stem}.gen-*.srt"))


def probe_audio_streams(video: Path) -> list[dict]:
    """Returns a list of {"label": str, "language_name": str|None} per audio
    stream, in stream order. language_name is only set when the stream's tag
    matches one of our known codes (see languages.py) -- otherwise the
    track's actual language is genuinely uncertain and needs a manual pick."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", "-select_streams", "a", str(video)],
            capture_output=True, text=True, check=True, creationflags=SUBPROCESS_FLAGS,
        )
        streams = json.loads(result.stdout).get("streams", [])
    except Exception:
        return [{"label": "?", "language_name": None}]

    if not streams:
        return []

    out = []
    for s in streams:
        tags = s.get("tags", {})
        language_name = detect_language_name(tags.get("language")) or detect_language_name(tags.get("title"))
        label = tags.get("title") or tags.get("language") or s.get("codec_name", "?")
        out.append({"label": label, "language_name": language_name})
    return out


def open_video(path: Path):
    subprocess.Popen([VLC_PATH, str(path)], encoding="utf-8")


def format_eta(seconds: float) -> str:
    total_minutes = int(seconds) // 60
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


class GenerationWorker(QThread):
    file_started = pyqtSignal(object)                  # video: Path
    file_progress = pyqtSignal(float, object)          # percent, eta seconds (or None)
    file_finished = pyqtSignal(object, bool, str)      # video: Path, success, error message
    overall_progress = pyqtSignal(int, int, object)    # completed, total, eta seconds (or None)

    def __init__(self, jobs, host, language=None):
        super().__init__()
        self.jobs = jobs  # list of (video: Path, track_index: int)
        self.host = host
        self.language = language

    def run(self):
        total = len(self.jobs)
        start_time = time.time()

        for i, (video, track_index) in enumerate(self.jobs):
            self.file_started.emit(video)
            audio_path = None
            try:
                audio_path = extract_audio(video, audio_stream_index=track_index)
                result = transcribe_movie(
                    self.host, str(audio_path), language=self.language,
                    on_progress=lambda p, e: self.file_progress.emit(p, e),
                )
                if result.get("status") == "done":
                    lang_code = result.get("language", "xx")
                    srt_path = video.with_name(f"{video.stem}.gen-{lang_code}.srt")
                    srt_path.write_text(result["srt"], encoding="utf-8")
                    self.file_finished.emit(video, True, "")
                else:
                    self.file_finished.emit(video, False, str(result.get("error", result)))
            except Exception as e:
                self.file_finished.emit(video, False, str(e))
            finally:
                if audio_path and Path(audio_path).exists():
                    Path(audio_path).unlink()

            completed = i + 1
            elapsed = time.time() - start_time
            remaining = total - completed
            eta = (elapsed / completed) * remaining if remaining > 0 else None
            self.overall_progress.emit(completed, total, eta)


class MainWindow(QMainWindow):
    def __init__(self, folder: Path, host="localhost:10000"):
        super().__init__()
        self.folder = folder
        self.host = host
        self.audio_cache = {}
        self.language_selection = {}  # video path -> list of language names, one per shown track
        self.currently_generating = None  # video path currently being processed, or None
        self.worker = None

        self.setWindowTitle(f"Generate SRT - {folder}")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1100, 600)

        central = QWidget()
        layout = QVBoxLayout(central)

        track_headers = [f"Track {i + 1} language" for i in range(MAX_TRACKS)]
        self.table = QTableWidget(0, 1 + MAX_TRACKS)
        self.table.setHorizontalHeaderLabels(["File", *track_headers])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 1 + MAX_TRACKS):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.on_row_double_clicked)
        layout.addWidget(self.table)

        bar_font = QFont()
        bar_font.setPointSize(8)
        bar_font.setBold(True)

        bottom = QHBoxLayout()
        bottom.setAlignment(Qt.AlignVCenter)

        target_box = QVBoxLayout()
        target_box.addWidget(QLabel("Target language"))
        self.target_language_combo = NoScrollComboBox()
        self.target_language_combo.addItems(sorted(FULL_LANGUAGE_CODES.keys()))
        self.target_language_combo.setCurrentText(DEFAULT_TARGET_LANGUAGE)
        target_box.addWidget(self.target_language_combo)
        bottom.addLayout(target_box)
        bottom.setAlignment(target_box, Qt.AlignVCenter)

        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setMinimumHeight(56)
        self.generate_btn.setStyleSheet("font-size: 18px; font-weight: bold; padding: 0 32px;")
        self.generate_btn.clicked.connect(self.start_generation)
        bottom.addWidget(self.generate_btn)
        bottom.setAlignment(self.generate_btn, Qt.AlignVCenter)

        bars_box = QVBoxLayout()
        self.current_bar = QProgressBar()
        self.current_bar.setFormat("Idle")
        self.current_bar.setAlignment(Qt.AlignCenter)
        self.current_bar.setFont(bar_font)
        bars_box.addWidget(self.current_bar)

        self.overall_bar = QProgressBar()
        self.overall_bar.setFormat("0/0")
        self.overall_bar.setAlignment(Qt.AlignCenter)
        self.overall_bar.setFont(bar_font)
        bars_box.addWidget(self.overall_bar)
        bottom.addLayout(bars_box, stretch=1)
        bottom.setAlignment(bars_box, Qt.AlignVCenter)

        layout.addLayout(bottom)
        self.setCentralWidget(central)

        self._current_name = ""
        self.current_videos = []
        self.refresh_table()
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.refresh_table)
        self.poll_timer.start(POLL_INTERVAL_MS)

    def refresh_table(self):
        videos = find_videos(self.folder)
        self.current_videos = videos
        self.table.setRowCount(len(videos))
        for row, video in enumerate(videos):
            if video == self.currently_generating:
                color = IN_PROGRESS_COLOR
            elif has_generated_subs(video):
                color = GENERATED_COLOR
            else:
                color = None

            file_item = QTableWidgetItem(video.name)
            if color:
                file_item.setBackground(color)
            self.table.setItem(row, 0, file_item)

            if video not in self.audio_cache:
                self.audio_cache[video] = probe_audio_streams(video)
            streams = self.audio_cache[video]
            track_slots = streams[:MAX_TRACKS]

            # First time we see this file, seed each shown track's language
            # from ffprobe; after that, only the user's own picks (via the
            # combos below) are kept, even across later polls.
            if video not in self.language_selection:
                self.language_selection[video] = [s["language_name"] or UNKNOWN_LANGUAGE for s in track_slots]

            for slot in range(MAX_TRACKS):
                col = 1 + slot
                if slot < len(track_slots):
                    combo = NoScrollComboBox()
                    combo.addItems(LANGUAGE_CHOICES)
                    combo.setCurrentText(self.language_selection[video][slot])
                    combo.currentTextChanged.connect(
                        lambda text, v=video, i=slot: self.on_language_changed(v, i, text)
                    )
                    if color:
                        combo.setStyleSheet(f"background-color: {color.name()};")
                    self.table.setCellWidget(row, col, combo)
                else:
                    self.table.setCellWidget(row, col, None)
                    placeholder = QTableWidgetItem("-")
                    if color:
                        placeholder.setBackground(color)
                    self.table.setItem(row, col, placeholder)

    def on_language_changed(self, video, slot, text):
        self.language_selection[video][slot] = text

    def on_row_double_clicked(self, row, column):
        if row < len(self.current_videos):
            open_video(self.current_videos[row])

    def start_generation(self):
        if self.worker and self.worker.isRunning():
            return

        target_name = self.target_language_combo.currentText()
        jobs = []
        for v in find_videos(self.folder):
            if has_generated_subs(v):
                continue
            langs = self.language_selection.get(v, [])
            if target_name in langs:
                jobs.append((v, langs.index(target_name)))
        if not jobs:
            return

        self.generate_btn.setEnabled(False)
        self.current_bar.setValue(0)
        self.current_bar.setFormat("Idle")
        self.overall_bar.setMaximum(len(jobs))
        self.overall_bar.setValue(0)
        self.overall_bar.setFormat(f"0/{len(jobs)}")

        self.worker = GenerationWorker(jobs, self.host, short_code(target_name))
        self.worker.file_started.connect(self.on_file_started)
        self.worker.file_progress.connect(self.on_file_progress)
        self.worker.file_finished.connect(self.on_file_finished)
        self.worker.overall_progress.connect(self.on_overall_progress)
        self.worker.finished.connect(self.on_all_done)
        self.worker.start()

    def on_file_started(self, video):
        self._current_name = video.name
        self.currently_generating = video
        self.current_bar.setValue(0)
        self.current_bar.setFormat(f"{self._current_name}: %p%")
        self.refresh_table()

    def on_file_progress(self, percent, eta):
        eta_str = f", ETA {format_eta(eta)}" if eta is not None else ""
        self.current_bar.setValue(int(percent))
        self.current_bar.setFormat(f"{self._current_name}: %p%{eta_str}")

    def on_file_finished(self, video, success, message):
        if not success:
            print(f"Failed on {video.name}: {message}")
        else:
            self.refresh_table()

    def on_overall_progress(self, completed, total, eta):
        eta_str = f", ETA {format_eta(eta)}" if eta else ""
        self.overall_bar.setValue(completed)
        self.overall_bar.setFormat(f"{completed}/{total} - {self._current_name}{eta_str}")

    def on_all_done(self):
        self.generate_btn.setEnabled(True)
        self.current_bar.setFormat("Idle")
        self.currently_generating = None
        self.refresh_table()


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(ICON_PATH)))

    if len(sys.argv) > 1:
        folder = Path(sys.argv[1])
    else:
        picked = QFileDialog.getExistingDirectory(None, "Select folder")
        if not picked:
            sys.exit(0)
        folder = Path(picked)

    if not folder.exists():
        sys.exit(1)

    window = MainWindow(folder)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
