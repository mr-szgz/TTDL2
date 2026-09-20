from dataclasses import asdict
import codecs
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys

from PySide6.QtCore import QByteArray, QProcess, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QTabWidget, QToolButton, QVBoxLayout, QWidget,
)
from playwright.sync_api import sync_playwright

from .core import Job, filename_component, profile_name, read_links, system_browser
from . import __version__
from .progress import DownloadProgress
from .settings import AppState, CONFIG_DIR, Settings


class ProfileListDialog(QDialog):
    profiles_saved = Signal(list)
    profile_selected = Signal(str)

    def __init__(self, profiles, parent=None):
        super().__init__(parent)
        self.profiles = list(profiles)
        self.profile_rows = []
        self.setObjectName("profileListDialog")
        self.setWindowTitle("Manage Profile List")
        self.resize(720, 480)
        self.setMinimumSize(500, 350)

        layout = QVBoxLayout(self)
        add_row = QHBoxLayout()
        add_label = QLabel("&URL or username")
        self.add_input = QLineEdit()
        self.add_input.setObjectName("profileToAdd")
        self.add_input.setAccessibleName("TikTok profile URL or username to add")
        self.add_input.setPlaceholderText("@username or TikTok profile URL")
        add_label.setBuddy(self.add_input)
        add_row.addWidget(add_label)
        add_row.addWidget(self.add_input, 1)
        self.add_profile_button = QPushButton("&Add Profile")
        self.add_profile_button.setObjectName("addProfile")
        self.add_profile_button.setEnabled(False)
        self.add_profile_button.clicked.connect(self.add_profile)
        self.add_input.textChanged.connect(self.update_add_button)
        self.add_input.returnPressed.connect(self.add_profile_button.click)
        add_row.addWidget(self.add_profile_button)
        layout.addLayout(add_row)

        list_actions = QHBoxLayout()
        self.sort_button = QPushButton("&Sort")
        self.sort_button.setObjectName("sortProfiles")
        self.sort_button.clicked.connect(self.sort_profiles)
        list_actions.addWidget(self.sort_button)
        self.deduplicate_button = QPushButton("&Deduplicate")
        self.deduplicate_button.setObjectName("deduplicateProfiles")
        self.deduplicate_button.clicked.connect(self.deduplicate_profiles)
        list_actions.addWidget(self.deduplicate_button)
        list_actions.addStretch()
        layout.addLayout(list_actions)

        header = QHBoxLayout()
        header.addWidget(QLabel("Profile URL"), 1)
        header.addWidget(QLabel("Actions"))
        layout.addLayout(header)
        self.profile_scroll = QScrollArea()
        self.profile_scroll.setObjectName("managedProfiles")
        self.profile_scroll.setWidgetResizable(True)
        self.profile_scroll.setAccessibleName("Profiles")
        self.profile_content = QWidget()
        self.profile_layout = QVBoxLayout(self.profile_content)
        self.profile_layout.setContentsMargins(0, 0, 0, 0)
        self.profile_layout.setSpacing(6)
        self.profile_scroll.setWidget(self.profile_content)
        layout.addWidget(self.profile_scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        self.save_button.setText("&Save List")
        self.save_button.setObjectName("saveProfileList")
        buttons.accepted.connect(self.save_profiles)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.refresh_rows()
        self.add_input.setFocus()

    def update_add_button(self, text):
        source = text.strip()
        username = profile_name(source)
        host = QUrl(source).host().casefold() if "://" in source else ""
        valid_host = "://" not in source or host in {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}
        self.add_profile_button.setEnabled(
            valid_host and re.fullmatch(r"[A-Za-z0-9._]+", username) is not None)

    def add_profile(self):
        username = profile_name(self.add_input.text().strip())
        self.profiles.append(f"https://www.tiktok.com/@{username}")
        self.add_input.clear()
        self.refresh_rows()

    def sort_profiles(self):
        self.profiles.sort(key=lambda profile: [
            int(part) if index % 2 else part.casefold()
            for index, part in enumerate(re.split(r"([0-9]+)", profile_name(profile)))
        ])
        self.refresh_rows()

    def deduplicate_profiles(self):
        usernames = set()
        profiles = []
        for profile in self.profiles:
            username = profile_name(profile).casefold()
            if username not in usernames:
                profiles.append(profile)
                usernames.add(username)
        self.profiles = profiles
        self.refresh_rows()

    def remove_profile(self, index):
        self.profiles.pop(index)
        self.refresh_rows()

    def select_profile(self, index):
        self.profile_selected.emit(self.profiles[index])
        self.accept()

    def save_profiles(self):
        self.profiles_saved.emit(self.profiles)
        self.accept()

    def refresh_rows(self):
        while self.profile_layout.count():
            item = self.profile_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.profile_rows = []
        if not self.profiles:
            empty = QLabel("No profiles in this list.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profile_layout.addWidget(empty)
        for index, profile in enumerate(self.profiles):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            profile_label = QLabel(profile)
            profile_label.setAccessibleName(f"Profile {profile}")
            profile_label.setToolTip(profile)
            profile_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            profile_label.setMinimumWidth(0)
            profile_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            row_layout.addWidget(profile_label, 1)
            remove_button = QPushButton("Remove")
            remove_button.setObjectName("removeProfile")
            remove_button.setAccessibleName(f"Remove {profile}")
            remove_button.clicked.connect(lambda checked=False, row_index=index: self.remove_profile(row_index))
            row_layout.addWidget(remove_button)
            select_button = QPushButton("Select")
            select_button.setObjectName("selectProfile")
            select_button.setAccessibleName(f"Select {profile}")
            select_button.clicked.connect(lambda checked=False, row_index=index: self.select_profile(row_index))
            row_layout.addWidget(select_button)
            row.profile = profile
            row.remove_button = remove_button
            row.select_button = select_button
            self.profile_layout.addWidget(row)
            self.profile_rows.append(row)
        self.profile_layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self, config_dir=None):
        super().__init__()
        self.preferences = Settings(config_dir if config_dir is not None else CONFIG_DIR)
        self.settings = self.preferences.values
        self.logger = logging.getLogger(f"{__name__}.{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.log_handler = logging.FileHandler(self.preferences.log_path, encoding="utf-8")
        self.log_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S"))
        self.logger.addHandler(self.log_handler)
        self.logger.info("Application started")
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
        self.auto_continuing = False
        self.download_progress = None
        self.scanned_links = None
        self.scanned_job = None
        self.scanning = False
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
        self.api_tab = QScrollArea()
        self.api_tab.setWidgetResizable(True)
        self.api_tab.setFrameShape(QFrame.Shape.NoFrame)
        api_content = QWidget()
        self.api_tab.setWidget(api_content)
        self.settings_tab = QScrollArea()
        self.settings_tab.setWidgetResizable(True)
        self.settings_tab.setFrameShape(QFrame.Shape.NoFrame)
        settings_content = QWidget()
        self.settings_tab.setWidget(settings_content)
        self.tabs.addTab(self.download_tab, "Downloader")
        self.tabs.addTab(self.api_tab, "API")
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
        self.manage_profile_list_button = QPushButton("&Manage List")
        self.manage_profile_list_button.setObjectName("manageProfileList")
        self.manage_profile_list_button.clicked.connect(self.manage_profile_list)
        self.next_profile_button = QPushButton("&Next Profile")
        self.next_profile_button.clicked.connect(lambda: self.profile_usernames.setCurrentIndex(
            self.profile_usernames.currentIndex() + 1))
        self.next_to_scan_button = QPushButton("Next to Scan")
        self.next_to_scan_button.clicked.connect(self.select_next_unscanned_profile)
        self.prev_profile_button = QPushButton("Pre&v Profile")
        self.prev_profile_button.clicked.connect(lambda: self.profile_usernames.setCurrentIndex(
            self.profile_usernames.currentIndex() - 1))
        self.next_profile_button.setEnabled(False)
        self.next_to_scan_button.setEnabled(False)
        self.prev_profile_button.setEnabled(False)
        profile_actions.addWidget(self.load_profile_list_button)
        profile_actions.addWidget(self.manage_profile_list_button)
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
        usernames_row.addWidget(self.next_to_scan_button)
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
        profile_form.addRow(scan_delay_label, self.scan_delay)
        self.auto_continue = QCheckBox("&Auto continue to next to scan")
        self.auto_continue.setObjectName("autoContinueToNextScan")
        self.auto_continue.setToolTip(
            "After each scan and any automatic downloads, scan the next profile without saved results")
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
        self.open_profile_downloads_button = QPushButton("Open profile downloads")
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
        self.progress.setTextVisible(False)
        self.progress_status = QLabel("Idle")
        self.progress_status.setObjectName("progressStatus")
        self.progress_status.setAccessibleName("Download progress count")
        self.progress_details = QLabel("0% — 0.00 items/s — ETA calculating…")
        self.progress_details.setObjectName("progressDetails")
        self.progress_details.setAccessibleName("Download rate and time remaining")
        self.progress_details.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress_status)
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.progress_details)
        layout.addLayout(progress_row)
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(1000)
        self.progress_timer.timeout.connect(self.refresh_progress_display)
        self.progress_timer.start()
        self.log = QPlainTextEdit()
        self.log.setObjectName("activityLog")
        self.log.setAccessibleName("Application log file tail")
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)
        log_actions = QHBoxLayout()
        self.remember_settings = QCheckBox("&Remember settings")
        self.remember_settings.setChecked(self.settings.remember_settings)
        self.remember_settings.setToolTip("Automatically save settings before quitting")
        self.remember_settings.toggled.connect(lambda checked: self.update_option("remember_settings", checked))
        log_actions.addWidget(self.remember_settings)
        log_actions.addWidget(self.auto_continue)
        log_actions.addWidget(self.auto_download)
        log_actions.addStretch()
        self.select_all_logs_button = QPushButton("Select all")
        self.select_all_logs_button.clicked.connect(self.log.selectAll)
        log_actions.addWidget(self.select_all_logs_button)
        self.copy_logs_button = QPushButton("Copy")
        self.copy_logs_button.clicked.connect(self.log.selectAll)
        self.copy_logs_button.clicked.connect(self.log.copy)
        log_actions.addWidget(self.copy_logs_button)
        layout.addLayout(log_actions)
        self.log_reader = self.preferences.log_path.open("r", encoding="utf-8")
        self.log_timer = QTimer(self)
        self.log_timer.setInterval(100)
        self.log_timer.timeout.connect(self.tail_log)
        self.tail_log()
        self.log_timer.start()
        api_layout = QVBoxLayout(api_content)
        api_layout.setSpacing(12)
        api_form = QFormLayout()
        self.api_method = QComboBox()
        self.api_method.setObjectName("apiMethod")
        self.api_method.setAccessibleName("Download API method")
        self.api_method.addItem("TikWM", "tikwm")
        self.api_method.addItem("TikTok Direct", "tiktok_direct")
        self.api_method.setCurrentIndex(self.api_method.findData(self.settings.api_method))
        api_method_label = QLabel("&Method")
        api_method_label.setBuddy(self.api_method)
        api_form.addRow(api_method_label, self.api_method)
        api_layout.addLayout(api_form)
        self.tiktok_direct_group = QGroupBox("TikTok Direct")
        self.tiktok_direct_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        tiktok_direct_form = QFormLayout(self.tiktok_direct_group)
        self.tiktok_cookie = QLineEdit(self.settings.tiktok_cookie)
        self.tiktok_cookie.setObjectName("tiktokCookie")
        self.tiktok_cookie.setAccessibleName("TikTok cookie")
        self.tiktok_cookie.setEchoMode(QLineEdit.EchoMode.Password)
        self.tiktok_cookie.textChanged.connect(lambda value: self.update_option("tiktok_cookie", value))
        tiktok_cookie_label = QLabel("&Cookie (optional)")
        tiktok_cookie_label.setBuddy(self.tiktok_cookie)
        tiktok_direct_form.addRow(tiktok_cookie_label, self.tiktok_cookie)
        api_layout.addWidget(self.tiktok_direct_group)
        self.tikwm_api_group = QGroupBox("TikWM API")
        self.tikwm_api_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        tikwm_api_form = QFormLayout(self.tikwm_api_group)
        self.tikwm_api_key = QLineEdit(self.settings.tikwm_api_key)
        self.tikwm_api_key.setObjectName("tikwmApiKey")
        self.tikwm_api_key.setAccessibleName("TikWM API key")
        self.tikwm_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.tikwm_api_key.textChanged.connect(lambda value: self.update_option("tikwm_api_key", value))
        tikwm_api_key_label = QLabel("API &key (optional)")
        tikwm_api_key_label.setBuddy(self.tikwm_api_key)
        tikwm_api_form.addRow(tikwm_api_key_label, self.tikwm_api_key)
        self.api_usage = QPlainTextEdit()
        self.api_usage.setObjectName("apiUsage")
        self.api_usage.setAccessibleName("TikWM API usage for the last 24 hours")
        self.api_usage.setReadOnly(True)
        self.api_usage.setPlainText("Waiting for server-reported API usage.")
        self.api_usage.setMaximumHeight(self.api_usage.fontMetrics().lineSpacing() * 4 + 24)
        api_usage_label = QLabel("&Usage (last 24 hours)")
        api_usage_label.setBuddy(self.api_usage)
        tikwm_api_form.addRow(api_usage_label, self.api_usage)
        api_layout.addWidget(self.tikwm_api_group)
        api_layout.addStretch()
        self.api_method.currentIndexChanged.connect(self.update_api_method)
        self.update_api_method()
        settings_layout = QVBoxLayout(settings_content)
        settings_form = QFormLayout()
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
        settings_layout.addLayout(settings_form)
        browser_group = QGroupBox("Browser")
        browser_form = QFormLayout(browser_group)
        self.browser = QComboBox()
        self.browser.addItems(["system", "chromium", "chrome", "msedge", "firefox"])
        self.browser.setCurrentText(self.settings.browser)
        self.browser.currentTextChanged.connect(lambda value: self.update_option("browser", value))
        browser_form.addRow("&Browser", self.browser)
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
        browser_form.addRow("", browser_actions)
        self.browser_status = QLabel()
        self.browser_status.setObjectName("browserStatus")
        self.browser_status.setWordWrap(True)
        browser_form.addRow("", self.browser_status)
        self.executable = QLineEdit(self.settings.executable)
        self.executable.setPlaceholderText("Optional custom browser executable, e.g. Brave")
        self.executable.textChanged.connect(lambda value: self.update_option("executable", value))
        browser_form.addRow("&Executable", self.executable)
        self.session_path = QLineEdit(str(self.preferences.session_path))
        self.session_path.setReadOnly(True)
        browser_form.addRow("Browser session file", self.session_path)
        settings_layout.addWidget(browser_group)
        downloads_group = QGroupBox("Scanning && Downloads")
        downloads_form = QFormLayout(downloads_group)
        self.scan_path = QLineEdit(str(self.preferences.scan_dir))
        self.scan_path.setReadOnly(True)
        downloads_form.addRow("Saved scans folder", self.scan_path)
        scan_actions = QHBoxLayout()
        self.open_scans_button = QPushButton("Open saved scans folder")
        self.open_scans_button.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.preferences.scan_dir))))
        scan_actions.addWidget(self.open_scans_button)
        scan_actions.addStretch()
        downloads_form.addRow("", scan_actions)
        self.video_dir = QLineEdit(self.settings.video_dir)
        self.video_dir.textChanged.connect(lambda value: self.update_option("video_dir", value))
        downloads_form.addRow("Video folder", self.video_dir)
        self.image_dir = QLineEdit(self.settings.image_dir)
        self.image_dir.textChanged.connect(lambda value: self.update_option("image_dir", value))
        downloads_form.addRow("Image folder", self.image_dir)
        downloads_options = QHBoxLayout()
        for key, title in [("download_logs", "Save download log")]:
            check = QCheckBox(title)
            check.setChecked(getattr(self.settings, key))
            check.toggled.connect(lambda checked, name=key: self.update_option(name, checked))
            self.checks[key] = check
            downloads_options.addWidget(check)
        downloads_options.addStretch()
        downloads_form.addRow(downloads_options)
        self.api_json_path = QLineEdit(str(Path(self.destination.text()) / "<username>" / "Data" / "json"))
        self.api_json_path.setReadOnly(True)
        self.destination.textChanged.connect(lambda folder: self.api_json_path.setText(
            str(Path(folder) / "<username>" / "Data" / "json")))
        downloads_form.addRow("API JSON folder", self.api_json_path)
        settings_layout.addWidget(downloads_group)
        settings_layout.addStretch()
        settings_separator = QFrame()
        settings_separator.setFrameShape(QFrame.Shape.HLine)
        settings_separator.setFrameShadow(QFrame.Shadow.Sunken)
        settings_layout.addWidget(settings_separator)
        settings_actions = QHBoxLayout()
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
        if Path(self.profile_list.text()).is_file():
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
        output = self.browser_install_decoder.decode(
            bytes(self.browser_install_process.readAllStandardOutput()))
        if output:
            self.logger.info(output.rstrip())

    def browser_install_finished(self, code, status):
        self.read_browser_install_output()
        self.set_busy(False)
        self.download_videos.setEnabled(bool(self.scanned_links))
        self.check_browser()
        self.logger.info("Browser installer exited with code %s", code)
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

    def manage_profile_list(self):
        self.profile_list_dialog = ProfileListDialog(self.profiles, self)
        self.profile_list_dialog.profiles_saved.connect(self.save_profile_list)
        self.profile_list_dialog.profile_selected.connect(self.select_managed_profile)
        self.profile_list_dialog.finished.connect(lambda: self.manage_profile_list_button.setFocus())
        self.profile_list_dialog.open()

    def save_profile_list(self, profiles):
        path = Path(self.profile_list.text())
        path.write_text("\n".join(profiles) + ("\n" if profiles else ""), encoding="utf-8")
        self.load_profile_list()
        self.logger.info("Profile list saved: %s", path)

    def select_managed_profile(self, profile):
        index = self.profile_usernames.findText(profile_name(profile))
        if index >= 0:
            self.profile_usernames.setCurrentIndex(index)
        else:
            self.source.setText(profile)

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
        self.logger.info("Added %s scanned usernames to profile list", len(additions))

    def select_profile(self, index):
        profile = self.profile_usernames.itemData(index)
        if profile is not None:
            self.source.setText(profile)
            self.refresh_profile_scans()
        self.prev_profile_button.setEnabled(index > 0)
        self.next_profile_button.setEnabled(index < self.profile_usernames.count() - 1)
        self.next_to_scan_button.setEnabled(index < self.profile_usernames.count() - 1)

    def select_next_unscanned_profile(self):
        scanned = {path.name.removesuffix("_combined_links.txt").casefold()
                   for path in self.preferences.scan_dir.glob("*_combined_links.txt")}
        for index in range(self.profile_usernames.currentIndex() + 1, self.profile_usernames.count()):
            if profile_name(self.profile_usernames.itemData(index)).casefold() not in scanned:
                self.profile_usernames.setCurrentIndex(index)
                return True
        return False

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
        if self.scanned_job is not None and name not in {
                "notifications", "remember_settings"}:
            setattr(self.scanned_job, name, checked)

    def update_api_method(self):
        method = self.api_method.currentData()
        self.update_option("api_method", method)
        self.tikwm_api_group.setEnabled(method == "tikwm")
        self.tiktok_direct_group.setEnabled(method == "tiktok_direct")

    def save_config(self):
        self.preferences.save_config(**self.settings.model_dump(exclude=set(AppState.model_fields)))
        self.preferences.save_state(self.current_state())
        self.settings = self.preferences.values
        self.logger.info("Configuration saved")

    def apply_settings(self):
        self.remember_settings.setChecked(self.settings.remember_settings)
        self.scan_delay.setValue(self.settings.scroll_ms / 1000)
        self.source.setText(self.settings.source)
        self.destination.setText(self.settings.folder)
        self.profile_usernames.setCurrentIndex(self.profile_usernames.findText(self.settings.selected_username))
        self.browser.setCurrentText(self.settings.browser)
        self.executable.setText(self.settings.executable)
        self.api_method.setCurrentIndex(self.api_method.findData(self.settings.api_method))
        self.tikwm_api_key.setText(self.settings.tikwm_api_key)
        self.tiktok_cookie.setText(self.settings.tiktok_cookie)
        self.update_api_method()
        self.video_dir.setText(self.settings.video_dir)
        self.image_dir.setText(self.settings.image_dir)
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
        self.logger.info("Defaults restored; click Save Settings to keep these values")

    def start_download(self, checked=False):
        settings = self.job_settings()
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
            settings = self.job_settings()
            self.scanned_job = Job(source=self.source.text(), folder=self.destination.text(), **settings)
            self.download_progress = None
            self.paused = self.stopping = False
            self.progress.setRange(0, max(len(self.scanned_links), 1))
            self.progress.setValue(0)
            self.progress_status.setText(f"Scanned ({len(self.scanned_links)} posts)")
            self.progress_details.clear()
            self.logger.info("Scan restored — %s results. Loaded %s", len(self.scanned_links), path)
            self.download_videos.setEnabled(bool(self.scanned_links))
        else:
            self.logger.error("No saved scan found: %s", path)

    def start_job(self, job, links=None):
        job.session_path = str(self.preferences.session_path)
        job.scan_dir = str(self.preferences.scan_dir)
        job.index_dir = str(self.preferences.index_dir)
        if self.settings.remember_settings:
            self.save_config()
        self.download_progress = None
        self.scanning = links is None
        if self.scanning:
            self.scanned_links = None
            self.scanned_job = job
        self.download_videos.setEnabled(False)
        self.stderr_decoder.reset()
        self.start_indexing.setEnabled(False)
        self.completed = self.stopping = self.paused = False
        operation = "Opening browser" if self.scanning else "Starting downloads"
        self.pause.setText("&Pause")
        self.progress.setRange(0, 0)
        if self.scanning:
            self.progress_status.setText("Scanning")
            self.progress_details.clear()
        else:
            self.progress_status.setText(f"Downloading (0 / {len(links)})")
            self.progress_details.setText("0% — 0.00 items/s — ETA calculating…")
        self.set_busy(True)
        self.pause.setEnabled(not self.scanning)
        self.logger.info(operation)
        self.process.setProgram(str(Path(sys.executable).with_name("python.exe")))
        self.process.setArguments(["-u", "-m", "tiktok_downloader.worker"])
        self.process.start()
        self.process.write((json.dumps({"job": asdict(job), "links": links}) + "\n").encode())

    def job_settings(self):
        return self.settings.model_dump(exclude={
            "source", "folder", "window_geometry", "selected_username",
            "notifications", "remember_settings",
        })

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
        self.api_tab.setEnabled(not busy)
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
        self.logger.info("Paused" if self.paused else "Resumed")

    def update_progress_display(self):
        self.progress_status.setText(
            f"Downloading ({self.download_progress.completed} / {self.download_progress.total})")
        self.progress_details.setText(self.download_progress.summary())

    def refresh_progress_display(self):
        if (self.download_progress is not None and not self.scanning
                and self.process.state() != QProcess.ProcessState.NotRunning):
            self.update_progress_display()

    def begin_indexing(self):
        self.auto_continuing = self.auto_continue.isChecked()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            settings = self.job_settings()
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
        self.logger.info("Indexing profile — 0 results")

    def stop_download(self):
        self.auto_continuing = False
        self.stopping = True
        self.download.setEnabled(False)
        self.start_indexing.setEnabled(False)
        self.pause.setEnabled(False)
        self.stop.setEnabled(False)
        self.logger.info("Stopping")
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
        self.logger.info("Saved browser session cleared")

    def process_error(self, _):
        if not self.stopping:
            self.logger.error(self.process.errorString())

    def tail_log(self):
        text = self.log_reader.read()
        if text:
            self.log.moveCursor(QTextCursor.MoveOperation.End)
            self.log.insertPlainText(text)
            self.log.moveCursor(QTextCursor.MoveOperation.End)

    def read_events(self):
        while self.process.canReadLine():
            event = json.loads(bytes(self.process.readLine()).decode())
            if event["type"] in ("log", "manual"):
                self.logger.info(event["message"])
            if self.stopping:
                continue
            if event["type"] == "manual":
                self.paused = True
                self.pause.setEnabled(False)
                self.start_indexing.setEnabled(True)
                self.logger.info("Waiting for you to click Scan Profile")
            elif event["type"] == "session_saved":
                self.logger.info("Browser session saved: %s", event["path"])
            elif event["type"] == "scanned":
                self.scanned_links = event["links"]
                self.refresh_profile_scans()
            elif event["type"] == "indexing":
                self.logger.info("Indexed %s unique posts, %s new posts found",
                                 event["total"], event["added"])
            elif event["type"] == "downloading":
                self.logger.info("Downloading (%s/%s): %s",
                                 event["current"], event["total"], event["url"])
            elif event["type"] == "transfer":
                self.download_progress.downloaded_bytes += event["bytes"]
            elif event["type"] == "api_usage":
                remaining = event["remaining"] if event["remaining"] is not None else "Not reported"
                reset = (f"{event['reset_seconds']} seconds"
                         if event["reset_seconds"] is not None else "Not reported")
                self.api_usage.setPlainText(
                    f"Requests remaining: {remaining}\nReset in: {reset}\nStatus: {event['message']}")
                self.logger.info("TikWM API usage — remaining: %s; reset: %s; status: %s",
                                 remaining, reset, event["message"])
            elif event["type"] == "api_error":
                self.auto_continuing = False
                self.logger.error(
                    f"TikWM API response for post {event['media_id']}\n"
                    f"Request: {event['request_url']}\n"
                    f"HTTP status: {event['status_code']}\n"
                    f"Requests remaining: {event['remaining']}\n"
                    f"Reset in: {event['reset_seconds']} seconds\n"
                    f"Saved response: {event['response_path']}\n"
                    f"{event['response_body']}")
            elif event["type"] == "progress":
                if event["current"] == 0:
                    self.download_progress = DownloadProgress(event["total"])
                    if self.paused:
                        self.download_progress.pause()
                self.download_progress.completed = event["current"]
                self.progress.setRange(0, max(event["total"], 1))
                self.progress.setValue(event["current"])
                self.update_progress_display()
            elif event["type"] == "done":
                self.completed = not event.get("failed", False)
                self.stopping = event["stopped"]

    def read_errors(self):
        text = self.stderr_decoder.decode(bytes(self.process.readAllStandardError()))
        if text:
            self.logger.error(text.rstrip())

    def process_finished(self, code, status):
        self.read_events()
        self.read_errors()
        self.set_busy(False)
        if self.stopping:
            self.auto_continuing = False
            self.paused = False
            self.pause.setText("&Pause")
            if self.progress.maximum() == 0:
                self.progress.setRange(0, 1)
                self.progress.setValue(0)
            self.logger.info("Stopped")
        elif code != 0 or status == QProcess.ExitStatus.CrashExit:
            self.auto_continuing = False
            self.logger.error("Process exited with code %s; see traceback above", code)
        elif self.completed:
            if self.scanning:
                if self.auto_download.isChecked():
                    self.start_job(self.scanned_job, self.scanned_links)
                    return
                if self.auto_continuing and self.select_next_unscanned_profile():
                    self.begin_indexing()
                    return
                self.logger.info("Scan complete — %s results. Click Download Profile",
                                 len(self.scanned_links))
            else:
                if self.auto_continuing and self.select_next_unscanned_profile():
                    self.begin_indexing()
                    return
                self.logger.info("Completed")
            self.auto_continuing = False
            if self.settings.notifications and not self.stopping:
                QApplication.alert(self)
        else:
            self.auto_continuing = False
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
            self.logger.info("Application closed")
            self.progress_timer.stop()
            self.log_timer.stop()
            self.log_reader.close()
            self.logger.removeHandler(self.log_handler)
            self.log_handler.close()
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName("TikTokDownloader2")
    app.setApplicationName("TikTok Downloader 2")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
