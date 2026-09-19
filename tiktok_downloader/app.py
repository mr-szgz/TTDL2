from dataclasses import asdict
import codecs
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from PySide6.QtCore import QByteArray, QProcess, QSize, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)
from playwright.sync_api import sync_playwright

from .core import Job, filename_component, profile_name, read_links, system_browser
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
        title_row = QHBoxLayout()
        title_row.addWidget(title)
        title_row.addStretch()
        self.repository_button = QToolButton()
        self.repository_button.setIcon(QIcon(str(Path(__file__).resolve().parent.parent / "assets" / "purple" / "ttdl2-icon-purple.png")))
        self.repository_button.setIconSize(QSize(40, 40))
        self.repository_button.setAutoRaise(True)
        self.repository_button.setAccessibleName("Open repository")
        self.repository_button.setToolTip("Open the ttdl2 repository on GitHub")
        self.repository_button.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/mr-szgz/ttdl2")))
        title_row.addWidget(self.repository_button)
        layout.addLayout(title_row)
        self.tabs = QTabWidget()
        self.download_tab = QScrollArea()
        self.download_tab.setWidgetResizable(True)
        self.download_tab.setFrameShape(QFrame.Shape.NoFrame)
        download_content = QWidget()
        self.download_tab.setWidget(download_content)
        self.settings_tab = QScrollArea()
        self.settings_tab.setWidgetResizable(True)
        self.settings_tab.setFrameShape(QFrame.Shape.NoFrame)
        settings_content = QWidget()
        self.settings_tab.setWidget(settings_content)
        self.tabs.addTab(self.download_tab, "Download")
        self.tabs.addTab(self.settings_tab, "Settings")
        layout.addWidget(self.tabs, 1)
        layout = QVBoxLayout(download_content)
        layout.setSpacing(12)
        self.inputs = QWidget()
        form = QFormLayout(self.inputs)
        form.setContentsMargins(0, 8, 0, 8)
        profiles_group = QGroupBox("Profiles List")
        profiles_form = QFormLayout(profiles_group)
        form.addRow(profiles_group)
        self.profiles = []
        self.profile_list = QLineEdit(str(Path(self.settings.folder) / "ttdl2.txt"))
        self.profile_list.setObjectName("profileList")
        self.profile_list.setAccessibleName("File")
        profile_list_label = QLabel("&File")
        profile_list_label.setBuddy(self.profile_list)
        profile_list_row = QHBoxLayout()
        profile_list_row.addWidget(self.profile_list, 1)
        self.open_profile_list_button = QPushButton("Open List File")
        self.open_profile_list_button.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(self.profile_list.text())))
        profile_list_row.addWidget(self.open_profile_list_button)
        profiles_form.addRow(profile_list_label, profile_list_row)
        profile_actions = QHBoxLayout()
        self.load_profile_list_button = QPushButton("&Load List File")
        self.load_profile_list_button.clicked.connect(self.load_profile_list)
        self.sort_file_button = QPushButton("Sort file")
        self.sort_file_button.clicked.connect(self.sort_profile_list)
        self.next_profile_button = QPushButton("&Next Profile")
        self.next_profile_button.clicked.connect(lambda: self.profile_usernames.setCurrentIndex(
            self.profile_usernames.currentIndex() + 1))
        self.prev_profile_button = QPushButton("Pre&v Profile")
        self.prev_profile_button.clicked.connect(lambda: self.profile_usernames.setCurrentIndex(
            self.profile_usernames.currentIndex() - 1))
        self.next_profile_button.setEnabled(False)
        self.prev_profile_button.setEnabled(False)
        profile_actions.addWidget(self.load_profile_list_button)
        profile_actions.addWidget(self.sort_file_button)
        profile_actions.addStretch()
        profiles_form.addRow("", profile_actions)
        self.profile_usernames = QComboBox()
        self.profile_usernames.setObjectName("profileUsernames")
        self.profile_usernames.setAccessibleName("Profile list usernames")
        self.profile_usernames.addItem("", None)
        self.profile_usernames.currentIndexChanged.connect(self.select_profile)
        usernames_label = QLabel("Username")
        usernames_label.setBuddy(self.profile_usernames)
        usernames_row = QHBoxLayout()
        usernames_row.addWidget(self.profile_usernames, 1)
        usernames_row.addWidget(self.prev_profile_button)
        usernames_row.addWidget(self.next_profile_button)
        profiles_form.addRow(usernames_label, usernames_row)
        filter_row = QHBoxLayout()
        self.profile_filter = QLineEdit()
        self.profile_filter.setPlaceholderText("Enter text to filter usernames")
        self.profile_filter.setAccessibleName("Filter profile usernames")
        self.filter_profiles_button = QPushButton("Filter")
        self.filter_profiles_button.clicked.connect(self.filter_profiles)
        filter_row.addWidget(self.profile_filter, 1)
        filter_row.addWidget(self.filter_profiles_button)
        profiles_form.addRow("", filter_row)
        scans_row = QHBoxLayout()
        self.profile_scans = QComboBox()
        self.profile_scans.setObjectName("profileScans")
        self.profile_scans.setAccessibleName("Results")
        scans_row.addWidget(self.profile_scans, 1)
        self.restore_scan_button = QPushButton("&Restore")
        self.restore_scan_button.clicked.connect(self.restore_scan)
        self.profile_scans.currentIndexChanged.connect(lambda: self.restore_scan_button.setEnabled(
            self.profile_scans.isEnabled() and self.profile_scans.currentIndex() >= 0
            and not self.profile_scans.currentText().endswith("*")))
        scans_row.addWidget(self.restore_scan_button)
        scans_label = QLabel("Res&ults")
        scans_label.setBuddy(self.profile_scans)
        sync_scans_row = QHBoxLayout()
        self.sync_scans_button = QPushButton("Sync scans to file")
        self.sync_scans_button.setObjectName("syncScans")
        self.sync_scans_button.clicked.connect(self.sync_scanned_profiles)
        sync_scans_row.addWidget(self.sync_scans_button)
        self.refresh_scans_button = QPushButton("Refresh Scans")
        self.refresh_scans_button.setObjectName("refreshScans")
        self.refresh_scans_button.clicked.connect(self.refresh_profile_scans)
        sync_scans_row.addWidget(self.refresh_scans_button)
        sync_scans_row.addStretch()
        self.refresh_profile_scans()
        profile_group = QGroupBox("Scan Profiles")
        profile_form = QFormLayout(profile_group)
        form.addRow(profile_group)
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
        source_label = QLabel("&URL or Username")
        source_label.setBuddy(self.source)
        profile_form.addRow(source_label, source_row)
        profile_form.addRow(scans_label, scans_row)
        profile_form.addRow("", sync_scans_row)
        download_group = QGroupBox("Downloads")
        download_form = QFormLayout(download_group)
        form.addRow(download_group)
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
        destination_label = QLabel("Folder")
        destination_label.setBuddy(self.destination)
        download_form.addRow(destination_label, destination_row)
        options = QHBoxLayout()
        self.checks = {}
        for key, title in [("images_only", "Images only"), ("notifications", "Alert on completion")]:
            check = QCheckBox(title)
            check.setChecked(getattr(self.settings, key))
            check.toggled.connect(lambda checked, name=key: self.update_option(name, checked))
            self.checks[key] = check
            options.addWidget(check)
        self.auto_download = QCheckBox("&Auto download after scans")
        self.auto_download.setChecked(True)
        options.addWidget(self.auto_download)
        self.scan_delay = QDoubleSpinBox()
        self.scan_delay.setObjectName("scanDelay")
        self.scan_delay.setAccessibleName("Delay in seconds")
        self.scan_delay.setRange(0, 3600)
        self.scan_delay.setDecimals(1)
        self.scan_delay.setSingleStep(0.1)
        self.scan_delay.setSuffix(" s")
        self.scan_delay.setToolTip("Delay between profile-scanning scrolls")
        self.scan_delay.setValue(self.settings.scroll_ms / 1000)
        self.scan_delay.valueChanged.connect(lambda seconds: self.update_option("scroll_ms", round(seconds * 1000)))
        scan_delay_label = QLabel("Scan &delay")
        scan_delay_label.setBuddy(self.scan_delay)
        options.addWidget(scan_delay_label)
        options.addWidget(self.scan_delay)
        options.addStretch()
        download_form.addRow(options)
        open_folder = QPushButton("Open &Downloads")
        open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.destination.text())))
        self.input_controls = (profiles_group, self.source, self.check_profile_button, self.destination, change,
                               self.profile_scans, self.sync_scans_button, self.refresh_scans_button)
        layout.addWidget(self.inputs)
        actions = QHBoxLayout()
        self.download = QPushButton("&New Session")
        self.download.setToolTip("Open a fresh browser session for login; save it automatically")
        self.download.setObjectName("downloadButton")
        self.download.clicked.connect(self.start_download)
        self.start_indexing = QPushButton("&Scan Profile")
        self.start_indexing.setObjectName("startIndexingButton")
        self.start_indexing.clicked.connect(self.begin_indexing)
        profile_actions = QHBoxLayout()
        profile_actions.addWidget(self.start_indexing)
        self.open_profile_downloads_button = QPushButton("Open Downloads")
        self.open_profile_downloads_button.setToolTip("Open the current profile's download folder")
        self.open_profile_downloads_button.clicked.connect(self.open_profile_downloads)
        profile_actions.addWidget(self.open_profile_downloads_button)
        profile_actions.addStretch()
        profile_separator = QFrame()
        profile_separator.setFrameShape(QFrame.Shape.HLine)
        profile_separator.setFrameShadow(QFrame.Shadow.Sunken)
        profile_form.addRow(profile_separator)
        profile_form.addRow(profile_actions)
        self.reset_session_button = QPushButton("&Clear Session")
        self.reset_session_button.setObjectName("resetSessionButton")
        self.reset_session_button.setToolTip("Delete saved browser cookies, local storage, and IndexedDB")
        self.reset_session_button.setEnabled(self.preferences.session_path.is_file())
        self.reset_session_button.clicked.connect(self.reset_session)
        self.download_videos = QPushButton("&Download Profile")
        self.download_videos.setEnabled(False)
        self.download_videos.clicked.connect(lambda: self.start_job(self.scanned_job, self.scanned_links))
        download_actions = QHBoxLayout()
        download_actions.addWidget(self.download_videos)
        download_actions.addWidget(open_folder)
        download_actions.addStretch()
        download_separator = QFrame()
        download_separator.setFrameShape(QFrame.Shape.HLine)
        download_separator.setFrameShadow(QFrame.Shadow.Sunken)
        download_form.addRow(download_separator)
        download_form.addRow(download_actions)
        self.inputs.setMinimumHeight(self.inputs.minimumSizeHint().height())
        self.source.textChanged.connect(self.clear_scan)
        self.destination.textChanged.connect(self.clear_scan)
        self.pause = QPushButton("&Pause")
        self.pause.clicked.connect(self.toggle_pause)
        self.stop = QPushButton("&Stop")
        self.stop.setToolTip("Stop the current operation and close its browser")
        self.stop.clicked.connect(self.stop_download)
        self.pause.setEnabled(False)
        self.stop.setEnabled(False)
        actions.addWidget(self.download)
        actions.addWidget(self.reset_session_button)
        actions.addStretch()
        layout.addLayout(actions)
        actions = QHBoxLayout()
        actions.addWidget(self.pause)
        actions.addWidget(self.stop)
        actions.addStretch()
        layout.addLayout(actions)
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
        settings_layout = QVBoxLayout(settings_content)
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
        config_actions = QHBoxLayout()
        open_config = QPushButton("Open config &folder")
        open_config.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.preferences.config_path.parent))))
        config_actions.addWidget(open_config)
        config_actions.addStretch()
        settings_form.addRow("", config_actions)
        self.state_path = QLineEdit(str(self.preferences.state_path))
        self.state_path.setReadOnly(True)
        settings_form.addRow("Saved state path", self.state_path)
        self.session_path = QLineEdit(str(self.preferences.session_path))
        self.session_path.setReadOnly(True)
        settings_form.addRow("Browser session file", self.session_path)
        self.scan_path = QLineEdit(str(self.preferences.scan_dir))
        self.scan_path.setReadOnly(True)
        settings_form.addRow("Saved scans folder", self.scan_path)
        scan_actions = QHBoxLayout()
        self.open_scans_button = QPushButton("Open saved scans folder")
        self.open_scans_button.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.preferences.scan_dir))))
        scan_actions.addWidget(self.open_scans_button)
        scan_actions.addStretch()
        settings_form.addRow("", scan_actions)
        settings_layout.addLayout(settings_form)
        settings_layout.addStretch()
        downloads_group = QGroupBox("Downloads")
        downloads_options = QHBoxLayout(downloads_group)
        for key, title in [("json_logs", "Save API JSON"), ("download_logs", "Save download log")]:
            check = QCheckBox(title)
            check.setChecked(getattr(self.settings, key))
            check.toggled.connect(lambda checked, name=key: self.update_option(name, checked))
            self.checks[key] = check
            downloads_options.addWidget(check)
        downloads_options.addStretch()
        settings_layout.addWidget(downloads_group)
        settings_separator = QFrame()
        settings_separator.setFrameShape(QFrame.Shape.HLine)
        settings_separator.setFrameShadow(QFrame.Shadow.Sunken)
        settings_layout.addWidget(settings_separator)
        settings_actions = QHBoxLayout()
        self.remember_settings = QCheckBox("&Remember settings")
        self.remember_settings.setChecked(self.settings.remember_settings)
        self.remember_settings.setToolTip("Automatically save settings before quitting")
        self.remember_settings.toggled.connect(lambda checked: self.update_option("remember_settings", checked))
        settings_actions.addWidget(self.remember_settings)
        self.save_settings_button = QPushButton("&Save Settings")
        self.save_settings_button.clicked.connect(self.save_config)
        self.restore_defaults_button = QPushButton("Restore &Defaults")
        self.restore_defaults_button.clicked.connect(self.reset_defaults)
        settings_actions.addStretch()
        settings_actions.addWidget(self.save_settings_button)
        settings_actions.addWidget(self.restore_defaults_button)
        settings_layout.addLayout(settings_actions)
        self.browser.currentTextChanged.connect(self.check_browser)
        self.executable.textChanged.connect(self.check_browser)
        self.check_browser()
        self.load_profile_list()
        self.profile_usernames.setCurrentIndex(self.profile_usernames.findText(self.settings.selected_username))

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
        self.download_videos.setEnabled(bool(self.scanned_links))
        self.check_browser()
        self.statusBar().showMessage(f"Browser installer exited with code {code}")
        if self.closing:
            self.close()

    def load_profile_list(self):
        self.profiles = read_links(self.profile_list.text())
        self.profile_filter.clear()
        self.filter_profiles()

    def filter_profiles(self):
        query = self.profile_filter.text().casefold()
        self.profile_usernames.blockSignals(True)
        self.profile_usernames.clear()
        self.profile_usernames.addItem("", None)
        for profile in self.profiles:
            username = profile_name(profile)
            if query in username.casefold():
                self.profile_usernames.addItem(username, profile)
        self.profile_usernames.blockSignals(False)
        self.select_profile(0)

    def sort_profile_list(self):
        path = Path(self.profile_list.text())
        text = path.read_text(encoding="utf-8-sig")
        lines = text.splitlines()
        lines.sort(key=lambda line: [int(part) if index % 2 else part.casefold()
                                    for index, part in enumerate(re.split(r"([0-9]+)", line))])
        path.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
        self.statusBar().showMessage("Profile list file sorted.")

    def sync_scanned_profiles(self):
        path = Path(self.profile_list.text())
        text = path.read_text(encoding="utf-8-sig")
        usernames = {profile_name(line.strip()).casefold()
                     for line in text.splitlines() if line.strip()}
        additions = []
        for scan in sorted(self.preferences.scan_dir.glob("*_combined_links.txt")):
            username = profile_name(scan.name.removesuffix("_combined_links.txt"))
            if username.casefold() not in usernames:
                additions.append(f"@{username}")
                usernames.add(username.casefold())
        if additions:
            with path.open("a", encoding="utf-8") as file:
                if text and not text.endswith("\n"):
                    file.write("\n")
                file.write("\n".join(additions) + "\n")
        self.load_profile_list()
        self.statusBar().showMessage(f"Added {len(additions)} scanned usernames to profile list.")

    def select_profile(self, index):
        profile = self.profile_usernames.itemData(index)
        if profile is not None:
            self.source.setText(profile)
            self.refresh_profile_scans()
        self.prev_profile_button.setEnabled(index > 0)
        self.next_profile_button.setEnabled(index < self.profile_usernames.count() - 1)

    def open_profile_downloads(self):
        folder = Path(self.destination.text()) / filename_component(profile_name(self.source.text()))
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Download folder", self.destination.text())
        if path:
            self.destination.setText(path)

    def current_state(self):
        return AppState(source=self.source.text(), folder=self.destination.text(),
                        selected_username=self.profile_usernames.currentText(),
                        window_geometry=bytes(self.saveGeometry().toHex()).decode("ascii"))

    def update_option(self, name, checked):
        setattr(self.settings, name, checked)
        if self.scanned_job is not None and name not in {"notifications", "remember_settings"}:
            setattr(self.scanned_job, name, checked)

    def save_config(self):
        self.preferences.save_config(**self.settings.model_dump(exclude=set(AppState.model_fields)))
        self.preferences.save_state(self.current_state())
        self.settings = self.preferences.values
        self.statusBar().showMessage("Configuration saved.")

    def apply_settings(self):
        self.remember_settings.setChecked(self.settings.remember_settings)
        self.scan_delay.setValue(self.settings.scroll_ms / 1000)
        self.source.setText(self.settings.source)
        self.destination.setText(self.settings.folder)
        self.profile_usernames.setCurrentIndex(self.profile_usernames.findText(self.settings.selected_username))
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

    def start_download(self, checked=False):
        settings = self.settings.model_dump(exclude={"source", "folder", "window_geometry", "selected_username", "notifications", "remember_settings"})
        self.start_job(Job(source=self.source.text(), folder=self.destination.text(),
                           new_session=True, **settings))

    def clear_scan(self):
        self.scanned_links = None
        self.scanned_job = None
        self.download_videos.setEnabled(False)

    def refresh_profile_scans(self):
        selected = self.profile_scans.currentText().removesuffix("*")
        profile = self.profile_usernames.currentData()
        if profile is not None:
            selected = profile_name(profile)
        self.profile_scans.clear()
        self.profile_scans.addItems(sorted(
            path.name.removesuffix("_combined_links.txt")
            for path in self.preferences.scan_dir.glob("*_combined_links.txt")))
        if selected:
            scan_index = next((index for index in range(self.profile_scans.count())
                               if self.profile_scans.itemText(index).casefold() == selected.casefold()), -1)
            if scan_index < 0:
                self.profile_scans.addItem(f"{selected}*")
                scan_index = self.profile_scans.count() - 1
                self.profile_scans.model().item(scan_index).setEnabled(False)
            self.profile_scans.setCurrentIndex(scan_index)
        self.restore_scan_button.setEnabled(
            self.profile_scans.isEnabled() and self.profile_scans.currentIndex() >= 0
            and not self.profile_scans.currentText().endswith("*"))

    def restore_scan(self):
        self.clear_scan()
        username = self.profile_scans.currentText()
        path = self.preferences.scan_dir / f"{username}_combined_links.txt"
        if path.exists():
            self.source.setText(f"https://www.tiktok.com/@{username.lstrip('@')}")
            self.scanned_links = read_links(path)
            settings = self.settings.model_dump(exclude={"source", "folder", "window_geometry", "selected_username", "notifications", "remember_settings"})
            self.scanned_job = Job(source=self.source.text(), folder=self.destination.text(), **settings)
            self.download_progress = None
            self.paused = self.stopping = False
            self.progress.setRange(0, max(len(self.scanned_links), 1))
            self.progress.setValue(0)
            self.progress.setFormat(f"{len(self.scanned_links)} scanned posts")
            self.work_status = f"Scan restored — {len(self.scanned_links)} results."
            self.log.appendPlainText(f"{self.work_status} Loaded {path}")
            self.statusBar().showMessage(self.work_status)
            self.download_videos.setEnabled(bool(self.scanned_links))
        else:
            self.statusBar().showMessage(f"No saved scan found: {path}")

    def start_job(self, job, links=None):
        job.session_path = str(self.preferences.session_path)
        job.scan_dir = str(self.preferences.scan_dir)
        job.index_dir = str(self.preferences.index_dir)
        if self.settings.remember_settings:
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
        self.pause.setEnabled(not self.scanning)
        self.statusBar().showMessage(self.work_status)
        self.process.setProgram(str(Path(sys.executable).with_name("python.exe")))
        self.process.setArguments(["-u", "-m", "tiktok_downloader.worker"])
        self.process.start()
        self.process.write((json.dumps({"job": asdict(job), "links": links}) + "\n").encode())

    def set_busy(self, busy):
        self.start_indexing.setEnabled(not busy)
        self.scan_delay.setEnabled(not busy)
        self.reset_session_button.setEnabled(not busy and self.preferences.session_path.is_file())
        for control in self.input_controls:
            control.setEnabled(not busy)
        self.restore_scan_button.setEnabled(not busy and self.profile_scans.currentIndex() >= 0
                                            and not self.profile_scans.currentText().endswith("*"))
        for control in (self.checks["images_only"], self.checks["notifications"], self.auto_download):
            control.setEnabled(not busy)
        self.download_videos.setEnabled(not busy and bool(self.scanned_links))
        self.download.setEnabled(not busy)
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
        if self.process.state() == QProcess.ProcessState.NotRunning:
            settings = self.settings.model_dump(exclude={"source", "folder", "window_geometry", "selected_username", "notifications", "remember_settings"})
            self.start_job(Job(source=self.source.text(), folder=self.destination.text(),
                               manual_start=False, **settings))
            return
        if self.settings.remember_settings:
            self.save_config()
        self.start_indexing.setEnabled(False)
        self.paused = False
        self.process.write(b"resume\n")
        self.pause.setText("&Pause")
        self.pause.setEnabled(True)
        self.work_status = "Indexing profile — 0 results"
        self.show_work_status()

    def stop_download(self):
        self.stopping = True
        self.status_timer.stop()
        self.download.setEnabled(False)
        self.start_indexing.setEnabled(False)
        self.pause.setEnabled(False)
        self.stop.setEnabled(False)
        self.statusBar().showMessage("Stopping…")
        if self.process.state() == QProcess.ProcessState.Running:
            self.cancel_started_process()

    def cancel_started_process(self):
        if self.stopping:
            if self.scanning:
                self.process.write(b"stop\n")
            else:
                subprocess.run(["taskkill", "/PID", str(self.process.processId()), "/T", "/F"],
                               check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def reset_session(self):
        self.preferences.session_path.unlink()
        self.reset_session_button.setEnabled(False)
        self.statusBar().showMessage("Saved browser session cleared.")

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
                self.pause.setEnabled(False)
                self.start_indexing.setEnabled(True)
                self.statusBar().showMessage("Waiting for you to click Scan Profile")
            elif event["type"] == "session_saved":
                self.log.appendPlainText(f"Browser session saved: {event['path']}")
                self.statusBar().showMessage("Browser session saved.")
            elif event["type"] == "scanned":
                self.scanned_links = event["links"]
                self.refresh_profile_scans()
            elif event["type"] == "indexing":
                self.work_status = f"Indexed {event['total']} unique posts, {event['added']} new posts found"
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
                self.statusBar().showMessage(f"Scan complete — {len(self.scanned_links)} results. Click Download Profile.")
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
            if self.settings.remember_settings:
                self.preferences.save_config(**self.settings.model_dump(exclude=set(AppState.model_fields)))
                self.preferences.save_state(self.current_state())
            else:
                self.preferences.save_config(remember_settings=False)
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName("TikTokDownloader2")
    app.setApplicationName("TikTok Downloader 2")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
