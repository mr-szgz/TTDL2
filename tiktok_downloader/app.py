from dataclasses import asdict
import codecs
import json
from pathlib import Path
import sys

from PySide6.QtCore import QByteArray, QProcess, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from .core import Job, filename_component, profile_name, read_links
from . import __version__
from .progress import DownloadProgress
from .settings import AppConfig, AppState, CONFIG_DIR, Settings


class SettingsDialog(QDialog):
    def __init__(self, settings, parent):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)
        self.values = settings
        layout = QFormLayout(self)
        self.config_path = QLineEdit(str(parent.preferences.config_path))
        self.config_path.setReadOnly(True)
        layout.addRow("User config path", self.config_path)
        self.state_path = QLineEdit(str(parent.preferences.state_path))
        self.state_path.setReadOnly(True)
        layout.addRow("Saved state path", self.state_path)
        open_config = QPushButton("Open config &folder")
        open_config.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(parent.preferences.config_path.parent))))
        layout.addRow(open_config)
        self.browser = QComboBox()
        self.browser.addItems(["system", "chromium", "chrome", "msedge", "firefox"])
        self.browser.setCurrentText(settings.browser)
        layout.addRow("&Browser", self.browser)
        self.executable = QLineEdit(settings.executable)
        self.executable.setPlaceholderText("Optional custom browser executable, e.g. Brave")
        layout.addRow("&Executable", self.executable)
        self.checks = {}
        for key, title in [("images_only", "Images only"), ("json_logs", "Save API JSON"),
                           ("download_logs", "Save download log"), ("notifications", "Alert on completion")]:
            check = QCheckBox(title)
            check.setChecked(getattr(settings, key))
            self.checks[key] = check
            layout.addRow(check)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def settings(self):
        return AppConfig.model_validate(self.values.model_dump() | {
            "browser": self.browser.currentText(), "executable": self.executable.text(),
            **{name: check.isChecked() for name, check in self.checks.items()},
        })


class MainWindow(QMainWindow):
    def __init__(self, config_dir=None):
        super().__init__()
        self.preferences = Settings(config_dir if config_dir is not None else CONFIG_DIR)
        self.settings = self.preferences.values
        self.process = QProcess(self)
        self.stderr_decoder = codecs.getincrementaldecoder("utf-8")()
        self.process.readyReadStandardOutput.connect(self.read_events)
        self.process.readyReadStandardError.connect(self.read_errors)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(lambda _: self.log.appendPlainText(self.process.errorString()))
        self.paused = False
        self.stopping = False
        self.completed = False
        self.work_status = "Ready"
        self.download_progress = None
        self.scanned_links = None
        self.scanned_job = None
        self.scanning = False
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(1000)
        self.status_timer.timeout.connect(self.show_work_status)
        self.setWindowTitle("TikTok Downloader 2")
        self.resize(840, 660)
        self.setMinimumSize(500, 480)
        if self.settings.window_geometry:
            self.restoreGeometry(QByteArray.fromHex(self.settings.window_geometry.encode("ascii")))
        body = QWidget()
        self.setCentralWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        title = QLabel("TikTok Downloader 2")
        title_font = title.font()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        instructions = QLabel("Set up the browser session and click Scan Profile.\n"
                             "When scanning finishes, click Download Videos for HD media.")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self.inputs = QWidget()
        form = QFormLayout(self.inputs)
        form.setContentsMargins(0, 8, 0, 8)
        source_row = QHBoxLayout()
        self.source = QLineEdit(self.settings.source)
        self.source.setObjectName("source")
        self.source.setAccessibleName("TikTok username or profile URL")
        self.source.setPlaceholderText("@username or TikTok profile URL")
        source_row.addWidget(self.source, 1)
        self.restore_scan_button = QPushButton("&Restore Scan")
        self.restore_scan_button.clicked.connect(self.restore_scan)
        source_row.addWidget(self.restore_scan_button)
        source_label = QLabel("&Profile")
        source_label.setBuddy(self.source)
        form.addRow(source_label, source_row)
        destination_row = QHBoxLayout()
        self.destination = QLineEdit(self.settings.folder)
        self.destination.setObjectName("destination")
        self.destination.setAccessibleName("Download folder")
        change = QPushButton("&Choose…")
        change.clicked.connect(self.choose_folder)
        destination_row.addWidget(self.destination, 1)
        destination_row.addWidget(change)
        destination_label = QLabel("&Save to")
        destination_label.setBuddy(self.destination)
        form.addRow(destination_label, destination_row)
        layout.addWidget(self.inputs)
        actions = QHBoxLayout()
        self.download = QPushButton("Open &browser")
        self.download.setObjectName("downloadButton")
        self.download.clicked.connect(self.start_download)
        self.start_indexing = QPushButton("&Scan Profile")
        self.start_indexing.setObjectName("startIndexingButton")
        self.start_indexing.setEnabled(False)
        self.start_indexing.clicked.connect(self.begin_indexing)
        self.download_videos = QPushButton("&Download Videos")
        self.download_videos.setEnabled(False)
        self.download_videos.clicked.connect(lambda: self.start_job(self.scanned_job, self.scanned_links))
        self.source.textChanged.connect(self.clear_scan)
        self.destination.textChanged.connect(self.clear_scan)
        self.pause = QPushButton("&Pause")
        self.pause.clicked.connect(self.toggle_pause)
        self.stop = QPushButton("&Stop")
        self.stop.clicked.connect(self.stop_download)
        self.pause.setEnabled(False)
        self.stop.setEnabled(False)
        actions.addWidget(self.download)
        actions.addWidget(self.start_indexing)
        actions.addWidget(self.download_videos)
        actions.addWidget(self.pause)
        actions.addWidget(self.stop)
        actions.addStretch()
        open_folder = QPushButton("Open &folder")
        open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.destination.text())))
        actions.addWidget(open_folder)
        layout.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setObjectName("activityLog")
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)
        self.statusBar().showMessage("Ready")
        menu = self.menuBar().addMenu("&File")
        self.settings_action = menu.addAction("&Settings…", self.edit_settings)
        self.save_config_action = menu.addAction("&Save config", self.save_config)
        self.reset_action = menu.addAction("Restore &Defaults", self.reset_defaults)
        self.import_action = menu.addAction("&Import settings…", self.import_settings)
        menu.addAction("&Export settings…", self.export_settings)
        menu.addSeparator()
        menu.addAction("E&xit", self.close)
        self.menuBar().addMenu("&Help").addAction("&About", self.about)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Download folder", self.destination.text())
        if path:
            self.destination.setText(path)

    def edit_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings = dialog.settings()
            self.preferences.save_config(**self.settings.model_dump(exclude=set(AppState.model_fields)))
            self.settings = self.preferences.values

    def current_state(self):
        return AppState(source=self.source.text(), folder=self.destination.text(),
                        window_geometry=bytes(self.saveGeometry().toHex()).decode("ascii"))

    def save_config(self):
        self.preferences.save_config(**self.settings.model_dump(exclude=set(AppState.model_fields)))
        self.preferences.save_state(self.current_state())
        self.settings = self.preferences.values
        self.statusBar().showMessage("Configuration saved.")

    def apply_settings(self):
        self.source.setText(self.settings.source)
        self.destination.setText(self.settings.folder)
        if self.settings.window_geometry:
            self.restoreGeometry(QByteArray.fromHex(self.settings.window_geometry.encode("ascii")))
        else:
            self.showNormal()
            self.resize(840, 660)
        self.clear_scan()

    def reset_defaults(self):
        self.preferences.reset_state()
        self.settings = self.preferences.values
        self.apply_settings()
        self.statusBar().showMessage("Defaults restored. Click Save config to keep these values.")

    def import_settings(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import settings", "", "JSON (*.json)")
        if path:
            self.settings = AppConfig.model_validate_json(Path(path).read_text(encoding="utf-8"))
            self.apply_settings()
            self.save_config()

    def export_settings(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export settings", "settings.json", "JSON (*.json)")
        if path:
            AppConfig.model_validate(self.settings.model_dump() | self.current_state().model_dump()).save(Path(path))

    def about(self):
        QMessageBox.about(self, "About TikTok Downloader 2", f"TikTok Downloader {__version__}\nPython · PySide6 · Playwright\n\nBased on TikTok Downloader\n© 2024 Jettcodey · MIT License")

    def start_download(self):
        settings = self.settings.model_dump(exclude={"source", "folder", "window_geometry", "notifications"})
        self.start_job(Job(source=self.source.text(), folder=self.destination.text(), **settings))

    def clear_scan(self):
        self.scanned_links = None
        self.download_videos.setEnabled(False)

    def restore_scan(self):
        self.clear_scan()
        username = filename_component(profile_name(self.source.text()))
        path = Path(self.destination.text()) / f"{username}_combined_links.txt"
        if path.exists():
            self.scanned_links = read_links(path)
            settings = self.settings.model_dump(exclude={"source", "folder", "window_geometry", "notifications"})
            self.scanned_job = Job(source=self.source.text(), folder=self.destination.text(), **settings)
            self.download_progress = None
            self.paused = self.stopping = False
            self.progress.setRange(0, max(len(self.scanned_links), 1))
            self.progress.setValue(0)
            self.progress.setFormat(f"{len(self.scanned_links)} scanned posts")
            self.work_status = f"Scan restored — {len(self.scanned_links)} total results."
            self.log.appendPlainText(f"{self.work_status} Loaded {path}")
            self.statusBar().showMessage(self.work_status)
            self.download_videos.setEnabled(bool(self.scanned_links))
        else:
            self.statusBar().showMessage(f"No saved scan found: {path}")

    def start_job(self, job, links=None):
        self.status_timer.stop()
        self.download_progress = None
        self.scanning = links is None
        if self.scanning:
            self.scanned_links = None
            self.scanned_job = job
        self.download_videos.setEnabled(False)
        self.stderr_decoder.reset()
        self.start_indexing.setEnabled(False)
        self.completed = self.stopping = self.paused = False
        self.work_status = "Opening browser" if self.scanning else "Starting downloads"
        self.pause.setText("&Pause")
        self.log.clear()
        self.progress.setRange(0, 0)
        self.set_busy(True)
        self.pause.setEnabled(not self.scanning)
        self.statusBar().showMessage(self.work_status)
        self.process.setProgram(str(Path(sys.executable).with_name("python.exe")))
        self.process.setArguments(["-u", "-m", "tiktok_downloader.worker"])
        self.process.start()
        self.process.write((json.dumps({"job": asdict(job), "links": links}) + "\n").encode())

    def set_busy(self, busy):
        self.inputs.setEnabled(not busy)
        self.download.setEnabled(not busy)
        self.settings_action.setEnabled(not busy)
        self.import_action.setEnabled(not busy)
        self.reset_action.setEnabled(not busy)
        self.pause.setEnabled(busy)
        self.stop.setEnabled(busy)

    def toggle_pause(self):
        self.paused = not self.paused
        if self.download_progress is not None:
            if self.paused:
                self.download_progress.pause()
            else:
                self.download_progress.resume()
        self.process.write(b"pause\n" if self.paused else b"resume\n")
        self.pause.setText("&Resume" if self.paused else "&Pause")
        self.show_work_status()

    def begin_indexing(self):
        self.start_indexing.setEnabled(False)
        self.paused = False
        self.process.write(b"resume\n")
        self.pause.setText("&Pause")
        self.pause.setEnabled(True)
        self.work_status = "Indexing profile — 0 total results"
        self.show_work_status()

    def stop_download(self):
        self.stopping = True
        self.start_indexing.setEnabled(False)
        self.process.write(b"stop\n")
        self.pause.setEnabled(False)
        self.stop.setEnabled(False)
        self.show_work_status()

    def show_work_status(self):
        prefix = "Stopping — " if self.stopping else "Paused — " if self.paused else ""
        metrics = "" if self.download_progress is None else " — " + self.download_progress.summary()
        self.statusBar().showMessage(prefix + self.work_status + metrics)

    def read_events(self):
        while self.process.canReadLine():
            event = json.loads(bytes(self.process.readLine()).decode())
            if event["type"] in ("log", "manual"):
                self.log.appendPlainText(event["message"])
            if event["type"] == "manual":
                self.paused = True
                self.pause.setEnabled(False)
                self.start_indexing.setEnabled(True)
                self.statusBar().showMessage("Waiting for you to click Scan Profile")
            elif event["type"] == "scanned":
                self.scanned_links = event["links"]
            elif event["type"] == "indexing":
                self.work_status = f"Indexing page {event['page']} — {event['total']} total results"
                self.log.appendPlainText(self.work_status)
                self.show_work_status()
            elif event["type"] == "downloading":
                self.work_status = f"Downloading ({event['current']}/{event['total']})"
                self.show_work_status()
            elif event["type"] == "progress":
                if event["current"] == 0:
                    self.download_progress = DownloadProgress(event["total"])
                    if self.paused:
                        self.download_progress.pause()
                    self.status_timer.start()
                self.download_progress.completed = event["current"]
                if event["current"] > 0:
                    self.show_work_status()
                self.progress.setRange(0, max(event["total"], 1))
                self.progress.setValue(event["current"])
                self.progress.setFormat(f"{event['current']} / {event['total']} posts")
            elif event["type"] == "done":
                self.status_timer.stop()
                self.completed = True
                self.stopping = event["stopped"]

    def read_errors(self):
        text = self.stderr_decoder.decode(bytes(self.process.readAllStandardError()))
        if text:
            self.log.appendPlainText(text)

    def process_finished(self, code, status):
        self.read_events()
        self.read_errors()
        self.status_timer.stop()
        self.set_busy(False)
        self.start_indexing.setEnabled(False)
        if code != 0 or status == QProcess.ExitStatus.CrashExit:
            self.statusBar().showMessage(f"Process exited with code {code}; see traceback above")
        elif self.completed:
            if self.stopping:
                self.statusBar().showMessage("Stopped")
            elif self.scanning:
                self.statusBar().showMessage(f"Scan complete — {len(self.scanned_links)} total results. Click Download Videos.")
            else:
                self.statusBar().showMessage("Completed")
            if self.settings.notifications and not self.stopping:
                QApplication.alert(self)
        self.download_videos.setEnabled(bool(self.scanned_links))

    def closeEvent(self, event):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.stop_download()
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName("TikTokDownloader2")
    app.setApplicationName("TikTok Downloader 2")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
