from dataclasses import asdict
import codecs
import json
import os
from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import QByteArray, QProcess, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPlainTextEdit, QProgressBar, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)
from playwright.sync_api import sync_playwright

from .core import Job, profile_name, read_links, system_browser
from . import __version__
from .progress import DownloadProgress
from .settings import AppState, CONFIG_DIR, Settings


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
        self.process.started.connect(self.cancel_started_process)
        self.process.errorOccurred.connect(self.process_error)
        self.browser_install_process = QProcess(self)
        self.browser_install_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.browser_install_decoder = codecs.getincrementaldecoder("utf-8")()
        self.browser_install_process.readyReadStandardOutput.connect(self.read_browser_install_output)
        self.browser_install_process.finished.connect(self.browser_install_finished)
        self.closing = False
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
        self.setWindowTitle(f"ttdl2 - v{__version__}")
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parent.parent / "assets" / "purple" / "ttdl2-icon-purple.ico")))
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
        self.tabs = QTabWidget()
        self.download_tab = QWidget()
        self.settings_tab = QWidget()
        self.tabs.addTab(self.download_tab, "Download")
        self.tabs.addTab(self.settings_tab, "Settings")
        layout.addWidget(self.tabs, 1)
        layout = QVBoxLayout(self.download_tab)
        layout.setSpacing(12)
        self.inputs = QWidget()
        form = QFormLayout(self.inputs)
        form.setContentsMargins(0, 8, 0, 8)
        self.profiles = []
        self.profile_index = 0
        self.profile_list = QLineEdit(str(Path(self.settings.folder) / "ttdl2.txt"))
        self.profile_list.setObjectName("profileList")
        self.profile_list.setAccessibleName("Profile List")
        profile_list_label = QLabel("Profile &List")
        profile_list_label.setBuddy(self.profile_list)
        form.addRow(profile_list_label, self.profile_list)
        profile_actions = QHBoxLayout()
        self.open_profile_list_button = QPushButton("Open Profile List")
        self.open_profile_list_button.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(self.profile_list.text())))
        self.load_profile_list_button = QPushButton("&Load Profile List")
        self.load_profile_list_button.clicked.connect(self.load_profile_list)
        self.next_profile_button = QPushButton("&Next Profile")
        self.next_profile_button.clicked.connect(lambda: self.select_profile(self.profile_index + 1))
        self.prev_profile_button = QPushButton("Pre&v Profile")
        self.prev_profile_button.clicked.connect(lambda: self.select_profile(self.profile_index - 1))
        self.next_profile_button.setEnabled(False)
        self.prev_profile_button.setEnabled(False)
        profile_actions.addWidget(self.open_profile_list_button)
        profile_actions.addWidget(self.load_profile_list_button)
        profile_actions.addWidget(self.next_profile_button)
        profile_actions.addWidget(self.prev_profile_button)
        profile_actions.addStretch()
        form.addRow("", profile_actions)
        source_row = QHBoxLayout()
        self.source = QLineEdit(self.settings.source)
        self.source.setObjectName("source")
        self.source.setAccessibleName("TikTok username or profile URL")
        self.source.setPlaceholderText("@username or TikTok profile URL")
        source_row.addWidget(self.source, 1)
        self.check_profile_button = QPushButton("Check Profile")
        self.check_profile_button.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl(f"https://www.tiktok.com/@{profile_name(self.source.text())}")))
        source_row.addWidget(self.check_profile_button)
        source_label = QLabel("&Profile")
        source_label.setBuddy(self.source)
        form.addRow(source_label, source_row)
        scans_row = QHBoxLayout()
        self.profile_scans = QComboBox()
        self.profile_scans.setObjectName("profileScans")
        self.profile_scans.setAccessibleName("Profile Scans")
        scans_row.addWidget(self.profile_scans, 1)
        self.restore_scan_button = QPushButton("&Restore Scan")
        self.restore_scan_button.clicked.connect(self.restore_scan)
        scans_row.addWidget(self.restore_scan_button)
        scans_label = QLabel("Profile S&cans")
        scans_label.setBuddy(self.profile_scans)
        form.addRow(scans_label, scans_row)
        self.refresh_profile_scans()
        destination_row = QHBoxLayout()
        self.destination = QLineEdit(self.settings.folder)
        self.destination.setObjectName("destination")
        self.destination.setAccessibleName("Download folder")
        self.destination.textChanged.connect(
            lambda folder: self.profile_list.setText(str(Path(folder) / "ttdl2.txt")))
        change = QPushButton("&Choose…")
        change.clicked.connect(self.choose_folder)
        destination_row.addWidget(self.destination, 1)
        destination_row.addWidget(change)
        destination_label = QLabel("Downloads")
        destination_label.setBuddy(self.destination)
        form.addRow(destination_label, destination_row)
        options = QHBoxLayout()
        self.checks = {}
        for key, title in [("images_only", "Images only"), ("json_logs", "Save API JSON"),
                           ("download_logs", "Save download log"), ("notifications", "Alert on completion")]:
            check = QCheckBox(title)
            check.setChecked(getattr(self.settings, key))
            check.toggled.connect(lambda checked, name=key: self.update_option(name, checked))
            self.checks[key] = check
            options.addWidget(check)
        options.addStretch()
        open_folder = QPushButton("Open &Downloads")
        open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.destination.text())))
        form.addRow(options)
        layout.addWidget(self.inputs)
        actions = QHBoxLayout()
        self.check_session_button = QPushButton("Chec&k Session")
        self.check_session_button.setObjectName("checkSessionButton")
        self.check_session_button.setToolTip("Load the saved session or open a new one, then check for CAPTCHA")
        self.check_session_button.clicked.connect(lambda: self.start_download(check_session=True))
        self.download = QPushButton("Create &Session")
        self.download.setObjectName("downloadButton")
        self.download.clicked.connect(self.start_download)
        self.save_session_button = QPushButton("Sa&ve Session")
        self.save_session_button.setObjectName("saveSessionButton")
        self.save_session_button.setToolTip("Save browser cookies, local storage, and IndexedDB after logging in")
        self.save_session_button.setEnabled(False)
        self.save_session_button.clicked.connect(self.save_browser_session)
        self.restore_session_button = QPushButton("Res&tore Session")
        self.restore_session_button.setObjectName("restoreSessionButton")
        self.restore_session_button.setToolTip("Open a browser using the saved session")
        self.restore_session_button.setEnabled(self.preferences.session_path.is_file())
        self.restore_session_button.clicked.connect(lambda: self.start_download(restore_session=True))
        self.start_indexing = QPushButton("&Scan Profile")
        self.start_indexing.setObjectName("startIndexingButton")
        self.start_indexing.setEnabled(False)
        self.start_indexing.clicked.connect(self.begin_indexing)
        self.reset_session_button = QPushButton("&Reset session")
        self.reset_session_button.setObjectName("resetSessionButton")
        self.reset_session_button.setToolTip("Clear the current scan, progress, and log after work has stopped")
        self.reset_session_button.clicked.connect(self.reset_session)
        self.download_videos = QPushButton("&Download Profile")
        self.download_videos.setEnabled(False)
        self.download_videos.clicked.connect(lambda: self.start_job(self.scanned_job, self.scanned_links))
        self.source.textChanged.connect(self.clear_scan)
        self.destination.textChanged.connect(self.clear_scan)
        self.pause = QPushButton("&Pause")
        self.pause.clicked.connect(self.toggle_pause)
        self.stop = QPushButton("&Stop")
        self.stop.setToolTip("Stop the current operation and close its browser")
        self.stop.clicked.connect(self.stop_download)
        self.pause.setEnabled(False)
        self.stop.setEnabled(False)
        actions.addWidget(self.check_session_button)
        actions.addWidget(self.download)
        actions.addWidget(self.save_session_button)
        actions.addWidget(self.restore_session_button)
        actions.addWidget(self.reset_session_button)
        actions.addStretch()
        layout.addLayout(actions)
        actions = QHBoxLayout()
        actions.addWidget(self.start_indexing)
        actions.addWidget(self.download_videos)
        actions.addWidget(self.pause)
        actions.addWidget(self.stop)
        actions.addWidget(open_folder)
        actions.addStretch()
        layout.addLayout(actions)
        self.auto_download = QCheckBox("&Automatically download videos")
        self.auto_download.setChecked(True)
        layout.addWidget(self.auto_download)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setObjectName("activityLog")
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)
        log_actions = QHBoxLayout()
        log_actions.addStretch()
        self.select_all_logs_button = QPushButton("Select all")
        self.select_all_logs_button.clicked.connect(self.log.selectAll)
        log_actions.addWidget(self.select_all_logs_button)
        self.copy_logs_button = QPushButton("Copy")
        self.copy_logs_button.clicked.connect(self.log.selectAll)
        self.copy_logs_button.clicked.connect(self.log.copy)
        log_actions.addWidget(self.copy_logs_button)
        layout.addLayout(log_actions)
        self.statusBar().showMessage("Ready")
        settings_layout = QVBoxLayout(self.settings_tab)
        settings_form = QFormLayout()
        self.browser = QComboBox()
        self.browser.addItems(["system", "chromium", "chrome", "msedge", "firefox"])
        self.browser.setCurrentText(self.settings.browser)
        self.browser.currentTextChanged.connect(lambda value: self.update_option("browser", value))
        settings_form.addRow("&Browser", self.browser)
        browser_actions = QHBoxLayout()
        self.download_browser_button = QPushButton("&Download Browser")
        self.download_browser_button.clicked.connect(lambda: self.install_browser(False))
        self.check_browser_button = QPushButton("&Check Browser")
        self.check_browser_button.clicked.connect(self.check_browser)
        self.reinstall_browser_button = QPushButton("&Reinstall Browser")
        self.reinstall_browser_button.setToolTip("Force a fresh installation of the selected browser")
        self.reinstall_browser_button.clicked.connect(lambda: self.install_browser(True))
        browser_actions.addWidget(self.download_browser_button)
        browser_actions.addWidget(self.check_browser_button)
        browser_actions.addWidget(self.reinstall_browser_button)
        browser_actions.addStretch()
        settings_form.addRow("", browser_actions)
        self.browser_status = QLabel()
        self.browser_status.setObjectName("browserStatus")
        self.browser_status.setWordWrap(True)
        settings_form.addRow("", self.browser_status)
        self.executable = QLineEdit(self.settings.executable)
        self.executable.setPlaceholderText("Optional custom browser executable, e.g. Brave")
        self.executable.textChanged.connect(lambda value: self.update_option("executable", value))
        settings_form.addRow("&Executable", self.executable)
        self.config_path = QLineEdit(str(self.preferences.config_path))
        self.config_path.setReadOnly(True)
        settings_form.addRow("User config path", self.config_path)
        self.state_path = QLineEdit(str(self.preferences.state_path))
        self.state_path.setReadOnly(True)
        settings_form.addRow("Saved state path", self.state_path)
        self.scan_path = QLineEdit(str(self.preferences.scan_dir))
        self.scan_path.setReadOnly(True)
        settings_form.addRow("Saved scans folder", self.scan_path)
        self.open_scans_button = QPushButton("Open saved scans folder")
        self.open_scans_button.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.preferences.scan_dir))))
        settings_form.addRow("", self.open_scans_button)
        open_config = QPushButton("Open config &folder")
        open_config.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.preferences.config_path.parent))))
        settings_form.addRow("", open_config)
        settings_layout.addLayout(settings_form)
        settings_actions = QHBoxLayout()
        self.save_settings_button = QPushButton("&Save Settings")
        self.save_settings_button.clicked.connect(self.save_config)
        self.restore_defaults_button = QPushButton("Restore &Defaults")
        self.restore_defaults_button.clicked.connect(self.reset_defaults)
        settings_actions.addWidget(self.save_settings_button)
        settings_actions.addWidget(self.restore_defaults_button)
        settings_actions.addStretch()
        settings_layout.addLayout(settings_actions)
        settings_layout.addStretch()
        self.browser.currentTextChanged.connect(self.check_browser)
        self.executable.textChanged.connect(self.check_browser)
        self.check_browser()

    def check_browser(self):
        browser = self.browser.currentText()
        executable = self.executable.text()
        managed = browser != "system" and not executable
        self.download_browser_button.setEnabled(managed)
        self.reinstall_browser_button.setEnabled(managed)
        if browser == "system" and not executable:
            executable = system_browser()
        if "firefox" in executable.lower() or (not executable and browser in ("chromium", "firefox")):
            with sync_playwright() as playwright:
                engine = playwright.firefox if browser == "firefox" or "firefox" in executable.lower() else playwright.chromium
                paths = [Path(engine.executable_path)]
        elif executable:
            paths = [Path(executable)]
        else:
            relative = {"chrome": "Google/Chrome/Application/chrome.exe",
                        "msedge": "Microsoft/Edge/Application/msedge.exe"}[browser]
            paths = [Path(os.environ[root]) / relative
                     for root in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)")]
        installed = any(path.is_file() for path in paths)
        self.browser_status.setText("Browser installed" if installed else "Browser not installed")
        self.browser_status.setToolTip("\n".join(str(path) for path in paths))
        if not managed:
            self.browser_status.setText(self.browser_status.text() + " — system/custom browser managed externally")

    def install_browser(self, force):
        arguments = ["-m", "playwright", "install", self.browser.currentText()]
        if force:
            arguments.append("--force")
        self.browser_install_decoder.reset()
        self.browser_status.setText("Reinstalling browser…" if force else "Downloading browser…")
        self.set_busy(True)
        self.pause.setEnabled(False)
        self.stop.setEnabled(False)
        self.reset_session_button.setEnabled(False)
        self.start_indexing.setEnabled(False)
        self.download_videos.setEnabled(False)
        self.browser_install_process.setProgram(sys.executable)
        self.browser_install_process.setArguments(arguments)
        self.browser_install_process.start()

    def read_browser_install_output(self):
        self.log.appendPlainText(self.browser_install_decoder.decode(
            bytes(self.browser_install_process.readAllStandardOutput())))

    def browser_install_finished(self, code, status):
        self.read_browser_install_output()
        self.set_busy(False)
        self.reset_session_button.setEnabled(True)
        self.download_videos.setEnabled(bool(self.scanned_links))
        self.check_browser()
        self.statusBar().showMessage(f"Browser installer exited with code {code}")
        if self.closing:
            self.close()

    def load_profile_list(self):
        self.profiles = read_links(self.profile_list.text())
        self.select_profile(0)

    def select_profile(self, index):
        self.source.setText(self.profiles[index])
        self.profile_index = index
        self.prev_profile_button.setEnabled(index > 0)
        self.next_profile_button.setEnabled(index < len(self.profiles) - 1)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Download folder", self.destination.text())
        if path:
            self.destination.setText(path)

    def current_state(self):
        return AppState(source=self.source.text(), folder=self.destination.text(),
                        window_geometry=bytes(self.saveGeometry().toHex()).decode("ascii"))

    def update_option(self, name, checked):
        setattr(self.settings, name, checked)
        if self.scanned_job is not None and name != "notifications":
            setattr(self.scanned_job, name, checked)

    def save_config(self):
        self.preferences.save_config(**self.settings.model_dump(exclude=set(AppState.model_fields)))
        self.preferences.save_state(self.current_state())
        self.settings = self.preferences.values
        self.statusBar().showMessage("Configuration saved.")

    def apply_settings(self):
        self.source.setText(self.settings.source)
        self.destination.setText(self.settings.folder)
        self.browser.setCurrentText(self.settings.browser)
        self.executable.setText(self.settings.executable)
        for name, check in self.checks.items():
            check.setChecked(getattr(self.settings, name))
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
        self.statusBar().showMessage("Defaults restored. Click Save Settings to keep these values.")

    def start_download(self, checked=False, *, restore_session=False, check_session=False):
        if self.process.state() != QProcess.ProcessState.NotRunning and self.scanned_job.check_session:
            self.session_setup_requested = True
            self.download.setEnabled(False)
            self.save_session_button.setEnabled(self.paused)
            self.start_indexing.setEnabled(self.paused)
            self.statusBar().showMessage("Solve the CAPTCHA in the open browser, then Save Session or Scan Profile.")
            return
        settings = self.settings.model_dump(exclude={"source", "folder", "window_geometry", "notifications"})
        self.start_job(Job(source=self.source.text(), folder=self.destination.text(),
                           restore_session=restore_session, check_session=check_session, **settings))

    def save_browser_session(self):
        self.save_session_button.setEnabled(False)
        self.start_indexing.setEnabled(False)
        self.process.write(b"save_session\n")
        self.statusBar().showMessage("Saving browser session…")

    def clear_scan(self):
        self.scanned_links = None
        self.scanned_job = None
        self.download_videos.setEnabled(False)

    def refresh_profile_scans(self):
        selected = self.profile_scans.currentText()
        self.profile_scans.clear()
        self.profile_scans.addItems(sorted(
            path.name.removesuffix("_combined_links.txt")
            for path in self.preferences.scan_dir.glob("*_combined_links.txt")))
        if selected:
            self.profile_scans.setCurrentText(selected)
        self.restore_scan_button.setEnabled(self.profile_scans.count() > 0)

    def restore_scan(self):
        self.clear_scan()
        username = self.profile_scans.currentText()
        path = self.preferences.scan_dir / f"{username}_combined_links.txt"
        if path.exists():
            self.source.setText(f"https://www.tiktok.com/@{username.lstrip('@')}")
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
        self.session_setup_requested = False
        job.session_path = str(self.preferences.session_path)
        job.scan_dir = str(self.preferences.scan_dir)
        self.save_config()
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
        self.download.setEnabled(self.scanning and job.check_session)
        self.pause.setEnabled(not self.scanning)
        self.statusBar().showMessage(self.work_status)
        self.process.setProgram(str(Path(sys.executable).with_name("python.exe")))
        self.process.setArguments(["-u", "-m", "tiktok_downloader.worker"])
        self.process.start()
        self.process.write((json.dumps({"job": asdict(job), "links": links}) + "\n").encode())

    def set_busy(self, busy):
        self.reset_session_button.setEnabled(not busy)
        self.inputs.setEnabled(not busy)
        self.download_videos.setEnabled(not busy and bool(self.scanned_links))
        self.download.setEnabled(not busy)
        self.check_session_button.setEnabled(not busy)
        self.save_session_button.setEnabled(False)
        self.restore_session_button.setEnabled(not busy and self.preferences.session_path.is_file())
        self.settings_tab.setEnabled(not busy)
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
        self.save_config()
        self.save_session_button.setEnabled(False)
        self.start_indexing.setEnabled(False)
        self.paused = False
        self.process.write(b"resume\n")
        self.pause.setText("&Pause")
        self.pause.setEnabled(True)
        self.work_status = "Indexing profile — 0 total results"
        self.show_work_status()

    def stop_download(self):
        self.stopping = True
        self.status_timer.stop()
        self.download.setEnabled(False)
        self.save_session_button.setEnabled(False)
        self.start_indexing.setEnabled(False)
        self.pause.setEnabled(False)
        self.stop.setEnabled(False)
        self.statusBar().showMessage("Stopping…")
        if self.process.state() == QProcess.ProcessState.Running:
            self.cancel_started_process()

    def cancel_started_process(self):
        if self.stopping:
            subprocess.run(["taskkill", "/PID", str(self.process.processId()), "/T", "/F"],
                           check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def reset_session(self):
        self.status_timer.stop()
        self.clear_scan()
        self.download_progress = None
        self.paused = self.stopping = self.completed = self.scanning = False
        self.stderr_decoder.reset()
        self.set_busy(False)
        self.reset_session_button.setEnabled(True)
        self.start_indexing.setEnabled(False)
        self.pause.setText("&Pause")
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.resetFormat()
        self.log.clear()
        self.work_status = "Ready"
        self.statusBar().showMessage(self.work_status)
        self.download.setFocus()

    def process_error(self, _):
        if not self.stopping:
            self.log.appendPlainText(self.process.errorString())

    def show_work_status(self):
        prefix = "Stopping — " if self.stopping else "Paused — " if self.paused else ""
        metrics = "" if self.download_progress is None else " — " + self.download_progress.summary()
        self.statusBar().showMessage(prefix + self.work_status + metrics)

    def read_events(self):
        while self.process.canReadLine():
            event = json.loads(bytes(self.process.readLine()).decode())
            if self.stopping:
                continue
            if event["type"] in ("log", "manual"):
                self.log.appendPlainText(event["message"])
            if event["type"] == "manual":
                self.paused = True
                self.save_session_button.setEnabled(True)
                self.pause.setEnabled(False)
                self.start_indexing.setEnabled(True)
                self.statusBar().showMessage("Waiting for you to click Scan Profile")
            elif event["type"] == "session_checked":
                self.paused = True
                self.pause.setEnabled(False)
                if not event["challenge"]:
                    self.download.setEnabled(False)
                self.save_session_button.setEnabled(self.session_setup_requested and not self.stopping)
                self.start_indexing.setEnabled((self.session_setup_requested or not event["challenge"]) and not self.stopping)
                self.work_status = ("CAPTCHA detected. Click Create Session to complete setup in the open browser."
                                    if event["challenge"] else "Session ready. Click Scan Profile.")
                if self.session_setup_requested:
                    self.work_status = "Solve the CAPTCHA in the open browser, then Save Session or Scan Profile."
                self.log.appendPlainText(self.work_status)
                self.statusBar().showMessage(self.work_status)
            elif event["type"] == "session_saved":
                self.save_session_button.setEnabled(not self.stopping)
                self.start_indexing.setEnabled(not self.stopping)
                self.log.appendPlainText(f"Browser session saved: {event['path']}")
                self.statusBar().showMessage("Browser session saved. Click Scan Profile when ready.")
            elif event["type"] == "scanned":
                self.scanned_links = event["links"]
                self.refresh_profile_scans()
            elif event["type"] == "indexing":
                self.work_status = (f"Indexed {event['total']} unique posts | {event['added']} new posts found"
                                    f" | Scan {event['scan_ms']:.0f} ms | Delay {event['delay_ms']:.0f} ms"
                                    f" | Total {event['round_ms']:.0f} ms")
                self.log.appendPlainText(self.work_status)
                self.show_work_status()
            elif event["type"] == "downloading":
                self.work_status = f"Downloading ({event['current']}/{event['total']})"
                self.show_work_status()
            elif event["type"] == "transfer":
                self.download_progress.downloaded_bytes += event["bytes"]
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
        if self.stopping:
            self.paused = False
            self.pause.setText("&Pause")
            if self.progress.maximum() == 0:
                self.progress.setRange(0, 1)
                self.progress.setValue(0)
            self.statusBar().showMessage("Stopped")
        elif code != 0 or status == QProcess.ExitStatus.CrashExit:
            self.statusBar().showMessage(f"Process exited with code {code}; see traceback above")
        elif self.completed:
            if self.scanning:
                if self.auto_download.isChecked():
                    self.start_job(self.scanned_job, self.scanned_links)
                    return
                self.statusBar().showMessage(f"Scan complete — {len(self.scanned_links)} total results. Click Download Profile.")
            else:
                self.statusBar().showMessage("Completed")
            if self.settings.notifications and not self.stopping:
                QApplication.alert(self)
        self.download_videos.setEnabled(bool(self.scanned_links))
        if self.closing:
            self.close()

    def closeEvent(self, event):
        if self.browser_install_process.state() != QProcess.ProcessState.NotRunning:
            self.closing = True
            event.ignore()
        elif self.process.state() != QProcess.ProcessState.NotRunning:
            self.closing = True
            if not self.stopping:
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
