import json
from pathlib import Path
import subprocess
import pytest
from PySide6.QtCore import QBuffer, QIODevice, QProcess, Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel
from tiktok_downloader.app import MainWindow
from tiktok_downloader.settings import AppConfig, Settings

@pytest.fixture
def window(qtbot, tmp_path):
    widget = MainWindow(tmp_path)
    qtbot.addWidget(widget)
    widget.show()
    return widget

def test_profile_list_default_path(window, tmp_path):
    assert window.profile_list.text() == str(Path(window.destination.text()) / "ttdl2.txt")
    assert not window.next_profile_button.isEnabled()
    assert not window.prev_profile_button.isEnabled()
    window.destination.setText(str(tmp_path))
    assert window.profile_list.text() == str(tmp_path / "ttdl2.txt")
    assert window.profile_list.geometry().bottom() < window.load_profile_list_button.geometry().top()
    assert window.load_profile_list_button.mapToGlobal(window.load_profile_list_button.rect().bottomLeft()).y() < window.source.mapToGlobal(window.source.rect().topLeft()).y()


def test_session_saved_on_scan_and_loaded_after_restart(window, qtbot, job_factory, tmp_path, monkeypatch):
    assert not window.reset_session_button.isEnabled()
    assert window.session_path.text() == str(window.preferences.session_path)
    assert window.session_path.isReadOnly()
    window.auto_download.setChecked(False)
    window.start_job(job_factory(manual_start=True))
    qtbot.waitUntil(lambda: window.start_indexing.isEnabled(), timeout=30000)
    qtbot.mouseClick(window.start_indexing, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning, timeout=30000)
    path = tmp_path / "browser-session.json"
    assert "cookies" in json.loads(path.read_text())
    assert window.reset_session_button.isEnabled()
    reopened = MainWindow(tmp_path)
    qtbot.addWidget(reopened)
    reopened.show()
    assert reopened.reset_session_button.isEnabled()
    jobs = []
    monkeypatch.setattr(reopened, "start_job", lambda job: jobs.append(job))
    qtbot.mouseClick(reopened.start_indexing, Qt.MouseButton.LeftButton)
    assert not jobs[-1].new_session
    assert not jobs[-1].manual_start
    qtbot.mouseClick(reopened.download, Qt.MouseButton.LeftButton)
    assert jobs[-1].new_session
    assert jobs[-1].manual_start
    qtbot.mouseClick(reopened.reset_session_button, Qt.MouseButton.LeftButton)
    assert not path.exists()
    assert not reopened.reset_session_button.isEnabled()
    qtbot.mouseClick(reopened.download, Qt.MouseButton.LeftButton)
    assert jobs[-1].new_session


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"])
@pytest.mark.parametrize("content, expected", [
    ("@profile10\n@Profile2\n@profile1\n@profile2\n", "@profile1\n@Profile2\n@profile2\n@profile10\n"),
    ("@p2part10\n@p2part2\n@p1part20", "@p1part20\n@p2part2\n@p2part10"),
    ("@p10\n\n@p2\n@p2\n", "\n@p2\n@p2\n@p10\n"),
    ("", ""),
])
def test_sort_profile_list_file(window, qtbot, tmp_path, encoding, content, expected):
    path = tmp_path / "profiles.txt"
    path.write_text(content, encoding=encoding)
    window.profile_list.setText(str(path))
    qtbot.mouseClick(window.sort_file_button, Qt.MouseButton.LeftButton)
    assert path.read_text(encoding="utf-8") == expected
    assert window.statusBar().currentMessage() == "Profile list file sorted."


@pytest.mark.parametrize("count", [0, 1, 3])
def test_profile_list_navigation(window, qtbot, tmp_path, count):
    profiles = [f"https://www.tiktok.com/@profile{i}" for i in range(count)]
    path = tmp_path / "profiles.txt"
    path.write_text("\n\n".join(profiles) + "\n", encoding="utf-8-sig")
    window.source.setText("@manual")
    window.profile_list.setText(str(path))
    qtbot.mouseClick(window.load_profile_list_button, Qt.MouseButton.LeftButton)
    assert window.source.text() == "@manual"
    assert window.profile_usernames.currentIndex() == 0
    assert window.profile_usernames.currentData() is None
    assert window.profile_usernames.currentText() == ""
    assert not window.prev_profile_button.isEnabled()
    assert window.next_profile_button.isEnabled() == (count > 0)
    qtbot.mouseClick(window.prev_profile_button, Qt.MouseButton.LeftButton)
    assert window.source.text() == "@manual"
    for index in range(count):
        window.scanned_links = ["old scan"]
        qtbot.mouseClick(window.next_profile_button, Qt.MouseButton.LeftButton)
        assert window.profile_usernames.currentIndex() == index + 1
        assert window.source.text() == profiles[index]
        assert window.scanned_links is None
        assert window.prev_profile_button.isEnabled()
    assert not window.next_profile_button.isEnabled()
    qtbot.mouseClick(window.next_profile_button, Qt.MouseButton.LeftButton)
    assert window.profile_usernames.currentIndex() == count
    for index in range(count - 1, -1, -1):
        previous_source = window.source.text()
        qtbot.mouseClick(window.prev_profile_button, Qt.MouseButton.LeftButton)
        assert window.profile_usernames.currentIndex() == index
        assert window.source.text() == (profiles[index - 1] if index else previous_source)
    assert not window.prev_profile_button.isEnabled()


def test_profile_list_reload_and_busy_state(window, qtbot, tmp_path):
    path = tmp_path / "profiles.txt"
    path.write_text("https://www.tiktok.com/@alice\nhttps://www.tiktok.com/@bob\n", encoding="utf-8")
    window.profile_list.setText(str(path))
    qtbot.mouseClick(window.load_profile_list_button, Qt.MouseButton.LeftButton)
    window.profile_usernames.setCurrentIndex(2)
    window.set_busy(True)
    assert not window.profile_list.isEnabled()
    assert not window.load_profile_list_button.isEnabled()
    assert not window.profile_usernames.isEnabled()
    assert not window.prev_profile_button.isEnabled()
    window.set_busy(False)
    assert window.prev_profile_button.isEnabled()
    assert not window.next_profile_button.isEnabled()
    path.write_text("https://www.tiktok.com/@carol\n", encoding="utf-8")
    qtbot.mouseClick(window.load_profile_list_button, Qt.MouseButton.LeftButton)
    assert window.source.text() == "https://www.tiktok.com/@bob"
    assert window.profile_usernames.count() == 2
    assert window.profile_usernames.currentData() is None
    assert window.profile_usernames.currentText() == ""
    assert window.next_profile_button.isEnabled()
    assert not window.prev_profile_button.isEnabled()


def test_profile_list_username_selection_is_one_way(window, qtbot, tmp_path):
    path = tmp_path / "profiles.txt"
    path.write_text("https://www.tiktok.com/@alice\n@bob\ncarol\n", encoding="utf-8")
    window.profile_list.setText(str(path))
    qtbot.mouseClick(window.load_profile_list_button, Qt.MouseButton.LeftButton)
    assert [window.profile_usernames.itemText(i) for i in range(4)] == ["", "alice", "bob", "carol"]
    assert window.load_profile_list_button.geometry().bottom() < window.profile_usernames.geometry().top()
    assert window.profile_usernames.geometry().bottom() < window.source.geometry().top()
    assert window.prev_profile_button.geometry().top() == window.profile_usernames.geometry().top()
    assert window.next_profile_button.geometry().top() == window.profile_usernames.geometry().top()
    window.profile_usernames.setCurrentIndex(2)
    assert window.source.text() == "@bob"
    window.source.setText("@manual")
    assert window.profile_usernames.currentText() == "bob"
    assert window.profile_usernames.currentData() == "@bob"
    qtbot.mouseClick(window.next_profile_button, Qt.MouseButton.LeftButton)
    assert window.source.text() == "carol"
    assert window.profile_usernames.currentText() == "carol"
    qtbot.mouseClick(window.prev_profile_button, Qt.MouseButton.LeftButton)
    assert window.source.text() == "@bob"
    assert window.profile_usernames.currentText() == "bob"
    window.profile_usernames.setCurrentIndex(0)
    assert window.source.text() == "@bob"


def test_profile_list_filter_is_explicit_and_matches_usernames(window, qtbot, tmp_path):
    path = tmp_path / "profiles.txt"
    path.write_text("https://www.tiktok.com/@Alice\n@malice2\n@bob\n", encoding="utf-8")
    window.profile_list.setText(str(path))
    window.source.setText("@manual")
    qtbot.mouseClick(window.load_profile_list_button, Qt.MouseButton.LeftButton)
    assert window.profile_filter.placeholderText() == "Enter text to filter usernames"
    assert window.profile_usernames.geometry().bottom() < window.profile_filter.geometry().top()
    assert window.profile_filter.geometry().bottom() < window.source.geometry().top()
    assert window.profile_filter.geometry().top() == window.filter_profiles_button.geometry().top()
    qtbot.keyClicks(window.profile_filter, "LIcE")
    assert window.profile_usernames.count() == 4
    qtbot.mouseClick(window.filter_profiles_button, Qt.MouseButton.LeftButton)
    assert [window.profile_usernames.itemText(i) for i in range(3)] == ["", "Alice", "malice2"]
    assert window.profile_usernames.currentData() is None
    assert window.source.text() == "@manual"
    qtbot.mouseClick(window.next_profile_button, Qt.MouseButton.LeftButton)
    assert window.source.text() == "https://www.tiktok.com/@Alice"
    qtbot.mouseClick(window.next_profile_button, Qt.MouseButton.LeftButton)
    assert window.source.text() == "@malice2"
    assert not window.next_profile_button.isEnabled()
    window.profile_filter.setText("tiktok")
    qtbot.mouseClick(window.filter_profiles_button, Qt.MouseButton.LeftButton)
    assert window.profile_usernames.count() == 1
    assert window.source.text() == "@malice2"
    assert not window.next_profile_button.isEnabled()
    assert not window.prev_profile_button.isEnabled()
    window.profile_filter.clear()
    assert window.profile_usernames.count() == 1
    qtbot.mouseClick(window.filter_profiles_button, Qt.MouseButton.LeftButton)
    assert window.profile_usernames.count() == 4
    assert window.source.text() == "@malice2"
    assert window.profile_usernames.itemData(3) == "@bob"
    assert path.read_text() == "https://www.tiktok.com/@Alice\n@malice2\n@bob\n"


def test_hd_mass_only_screen(window, qtbot):
    assert window.download_tab.findChildren(QComboBox) == [window.profile_usernames, window.profile_scans]
    assert window.source.mapTo(window, window.source.rect().bottomLeft()).y() < window.profile_scans.mapTo(window, window.profile_scans.rect().topLeft()).y()
    assert window.profile_scans.geometry().top() == window.restore_scan_button.geometry().top()
    assert not window.restore_scan_button.isEnabled()
    assert window.download_tab.findChildren(QCheckBox) == [window.checks["images_only"], window.checks["notifications"], window.auto_download]
    assert window.settings_tab.findChildren(QCheckBox) == [window.checks["json_logs"], window.checks["download_logs"], window.remember_settings]
    assert window.auto_download.isChecked()
    assert window.auto_download.mapTo(window, window.auto_download.rect().bottomLeft()).y() < window.progress.mapTo(window, window.progress.rect().topLeft()).y()
    assert window.auto_download.mapTo(window, window.auto_download.rect().bottomLeft()).y() < window.download.mapTo(window, window.download.rect().topLeft()).y()
    assert "Download activity" not in [label.text() for label in window.findChildren(QLabel)]
    assert window.download.text() == "&New Session"
    assert window.start_indexing.isVisible()
    assert window.start_indexing.text() == "&Scan Profile"
    assert window.reset_session_button.text() == "&Clear Session"
    assert not window.reset_session_button.isEnabled()
    assert window.reset_session_button.geometry().top() == window.download.geometry().top()
    assert window.download_videos.text() == "&Download Profile"
    assert not window.download_videos.isEnabled()
    assert window.start_indexing.isEnabled()
    qtbot.keyClicks(window.source, "@alice")
    assert window.source.text() == "@alice"

def test_automatic_download_toggle_respects_scan_and_busy_state(window):
    window.auto_download.setChecked(False)
    assert not window.download_videos.isEnabled()
    window.scanned_links = ["https://www.tiktok.com/@alice/video/123"]
    window.set_busy(False)
    window.auto_download.setChecked(True)
    assert window.download_videos.isEnabled()
    window.auto_download.setChecked(False)
    assert window.download_videos.isEnabled()
    window.auto_download.setChecked(True)
    window.set_busy(True)
    window.auto_download.setChecked(False)
    assert not window.download_videos.isEnabled()
    window.set_busy(False)
    window.auto_download.setChecked(True)
    window.auto_download.setChecked(False)
    assert window.download_videos.isEnabled()
    window.source.setText("@another")
    assert not window.download_videos.isEnabled()


@pytest.mark.parametrize("code, status, completed, stopped", [
    (1, QProcess.ExitStatus.NormalExit, True, False),
    (0, QProcess.ExitStatus.CrashExit, True, False),
    (0, QProcess.ExitStatus.NormalExit, False, False),
    (0, QProcess.ExitStatus.NormalExit, True, True),
])
def test_unsuccessful_scan_does_not_auto_download(window, monkeypatch, code, status, completed, stopped):
    jobs = []
    monkeypatch.setattr(window, "start_job", lambda *args: jobs.append(args))
    window.scanning = True
    window.completed = completed
    window.stopping = stopped
    window.scanned_links = ["https://www.tiktok.com/@alice/video/123"]
    window.process_finished(code, status)
    assert jobs == []
    assert window.download_videos.isEnabled()


def test_native_defaults(window, qtbot):
    from PySide6.QtWidgets import QApplication
    assert QApplication.instance().styleSheet() == ""
    assert window.styleSheet() == ""
    window.resize(650, 480)
    qtbot.wait(30)
    assert window.height() == 480
    for tab, bottom_control in ((window.download_tab, window.copy_logs_button),
                                (window.settings_tab, window.save_settings_button)):
        window.tabs.setCurrentWidget(tab)
        qtbot.wait(30)
        assert tab.verticalScrollBar().maximum() > 0
        tab.ensureWidgetVisible(bottom_control)
        assert tab.viewport().rect().contains(bottom_control.mapTo(tab.viewport(), bottom_control.rect().center()))
    window.tabs.setCurrentWidget(window.download_tab)
    window.source.setFocus()
    assert window.source.hasFocus()

def test_settings(window, tmp_path):
    settings = AppConfig(folder=str(tmp_path), images_only=True, json_logs=True, download_logs=True, notifications=True)
    path = tmp_path / "config.json"
    settings.save(path)
    assert Settings(tmp_path).values == settings

def test_open_browser_click_uses_hd_mass_job(window, qtbot, monkeypatch, tmp_path):
    jobs = []
    monkeypatch.setattr(window, "start_job", jobs.append)
    window.source.setText("https://www.tiktok.com/@sydneysweeneyfann")
    window.destination.setText(str(tmp_path))
    qtbot.mouseClick(window.download, Qt.MouseButton.LeftButton)
    assert len(jobs) == 1
    assert jobs[0].source == "https://www.tiktok.com/@sydneysweeneyfann"
    assert jobs[0].manual_start is True
    assert jobs[0].headless is False
    assert jobs[0].browser == "chromium"
    assert not hasattr(jobs[0], "watermark")
    assert not hasattr(jobs[0], "mode")

def test_indexing_events_without_page(window, monkeypatch):
    events = QBuffer()
    events.setData(
        b'{"type":"indexing","total":1,"added":1}\n'
        b'{"type":"indexing","total":1,"added":0}\n'
        b'{"type":"scanned","links":["https://www.tiktok.com/@alice/video/123"]}\n'
        b'{"type":"done","stopped":false}\n'
    )
    events.open(QIODevice.OpenModeFlag.ReadOnly)
    monkeypatch.setattr(window.process, "canReadLine", events.canReadLine)
    monkeypatch.setattr(window.process, "readLine", events.readLine)

    window.read_events()

    assert window.log.toPlainText().splitlines() == [
        "Indexed 1 unique posts, 1 new posts found",
        "Indexed 1 unique posts, 0 new posts found",
    ]
    assert window.statusBar().currentMessage() == window.log.toPlainText().splitlines()[-1]
    assert window.scanned_links == ["https://www.tiktok.com/@alice/video/123"]
    assert window.completed


@pytest.mark.parametrize("automatic", [True, False])
def test_real_browser_waits_for_start_then_downloads(window, qtbot, job_factory, server, automatic):
    window.auto_download.setChecked(automatic)
    statuses = []
    window.statusBar().messageChanged.connect(statuses.append)
    job = job_factory(manual_start=True, headless=False)
    window.start_job(job)
    assert not window.download.isEnabled()
    qtbot.waitUntil(lambda: window.start_indexing.isEnabled(), timeout=30000)
    qtbot.wait(500)
    assert server[1]["/indexing"] == 0
    assert server[1]["/api/hd"] == 0
    assert not window.pause.isEnabled()
    assert not window.download_videos.isEnabled()
    qtbot.mouseClick(window.start_indexing, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning, timeout=30000)
    if not automatic:
        assert window.statusBar().currentMessage() == "Scan complete — 2 results. Click Download Profile."
        assert window.download_videos.isEnabled()
        qtbot.wait(500)
        assert server[1]["/api/hd"] == 0
        assert not list(Path(job.folder).rglob("*.mp4"))
    assert (Path(job.scan_dir) / "alice_combined_links.txt").read_text().splitlines() == window.scanned_links
    assert not window.status_timer.isActive()
    browser_visits = server[1]["/@alice"]
    if not automatic:
        qtbot.mouseClick(window.download_videos, Qt.MouseButton.LeftButton)
        assert not window.download_videos.isEnabled()
        assert window.pause.isEnabled()
        qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning, timeout=30000)
    assert window.download_videos.isEnabled()
    assert server[1]["/@alice"] == browser_visits
    assert window.statusBar().currentMessage() == "Completed"
    window.source.setText("@another")
    assert not window.download_videos.isEnabled()
    assert server[1]["/api/hd"] == 2
    assert (Path(job.folder) / "alice" / "video" / "123_HD.mp4").exists()
    assert window.download.isEnabled()
    assert window.start_indexing.isEnabled()
    assert any(message.startswith("Indexed 1 unique posts, 1 new posts found") for message in statuses)
    assert any(message.startswith("Indexed 2 unique posts, 1 new posts found") for message in statuses)
    assert "Downloading (1/2) — 0 bytes downloaded — 0.00 MB/s — ETA calculating…" in statuses
    assert any(message.startswith("Downloading (2/2) — ") and "MB/s — ETA" in message for message in statuses)
    assert not window.status_timer.isActive()
    qtbot.wait(1100)
    assert window.statusBar().currentMessage() == "Completed"

def test_stop_while_waiting_does_not_crawl(window, qtbot, job_factory, server):
    job = job_factory(manual_start=True)
    existing = window.preferences.scan_dir / "alice_combined_links.txt"
    existing.write_text("previously collected URLs")
    window.start_job(job)
    qtbot.waitUntil(lambda: window.start_indexing.isEnabled(), timeout=30000)
    qtbot.mouseClick(window.stop, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning, timeout=30000)
    assert window.statusBar().currentMessage() == "Stopped"
    assert not window.download_videos.isEnabled()
    assert server[1]["/indexing"] == 0
    assert server[1]["/api/hd"] == 0
    assert existing.read_text() == "previously collected URLs"


@pytest.mark.parametrize("stage", ["starting", "setup", "scanning", "paused"])
def test_stop_closes_scan_and_allows_restart(window, qtbot, job_factory, server, stage):
    job = job_factory(manual_start=True, headless=False, scroll_ms=10000)
    existing = window.preferences.scan_dir / "alice_combined_links.txt"
    existing.write_text("previously collected URLs")
    window.start_job(job)
    if stage != "starting":
        qtbot.waitUntil(lambda: window.start_indexing.isEnabled(), timeout=30000)
    if stage in ("scanning", "paused"):
        qtbot.mouseClick(window.start_indexing, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: server[1]["/indexing"] > 0, timeout=10000)
    if stage == "paused":
        qtbot.mouseClick(window.pause, Qt.MouseButton.LeftButton)
        assert window.paused
    if stage == "setup":
        command = ["powershell", "-NoProfile", "-Command",
                   "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Json -Compress"]
        processes = json.loads(subprocess.check_output(command, creationflags=subprocess.CREATE_NO_WINDOW))
        descendants = {window.process.processId()}
        while children := {p["ProcessId"] for p in processes
                           if p["ParentProcessId"] in descendants} - descendants:
            descendants.update(children)
        assert any(p["ProcessId"] in descendants and p["Name"] == "chrome.exe" for p in processes)
    assert not window.reset_session_button.isEnabled()
    retained_log = window.log.toPlainText()
    qtbot.mouseClick(window.reset_session_button, Qt.MouseButton.LeftButton)
    assert window.scanned_job is job
    assert window.process.state() != QProcess.ProcessState.NotRunning
    assert window.log.toPlainText() == retained_log
    qtbot.mouseClick(window.stop, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning, timeout=5000)
    assert window.process.state() == QProcess.ProcessState.NotRunning
    assert window.statusBar().currentMessage() == "Stopped"
    assert window.scanned_links is None
    assert window.scanned_job is job
    assert window.download_progress is None
    assert not window.status_timer.isActive()
    assert window.scanning
    assert not window.paused
    assert window.start_indexing.isEnabled()
    assert not window.download_videos.isEnabled()
    assert not window.pause.isEnabled()
    assert not window.stop.isEnabled()
    assert window.download.isEnabled()
    assert window.reset_session_button.isEnabled() == window.preferences.session_path.is_file()
    assert window.log.toPlainText() == retained_log
    assert existing.read_text() == "previously collected URLs"
    assert server[1]["/api/hd"] == 0
    if stage == "setup":
        remaining = json.loads(subprocess.check_output(command, creationflags=subprocess.CREATE_NO_WINDOW))
        assert not descendants.intersection(p["ProcessId"] for p in remaining)
    window.start_job(job)
    qtbot.waitUntil(lambda: window.start_indexing.isEnabled(), timeout=30000)
    qtbot.mouseClick(window.stop, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning, timeout=5000)


def test_clear_session_deletes_browser_state_without_changing_scan(window, qtbot, tmp_path, monkeypatch):
    window.source.setText("@alice")
    window.destination.setText(str(tmp_path))
    window.scanned_links = ["https://www.tiktok.com/@alice/video/123"]
    window.auto_download.setChecked(False)
    window.log.appendPlainText("Previous activity")
    window.progress.setRange(0, 5)
    window.progress.setValue(3)
    window.preferences.session_path.write_text('{"cookies": []}')
    window.set_busy(False)
    cancellations = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: cancellations.append(args))
    qtbot.mouseClick(window.reset_session_button, Qt.MouseButton.LeftButton)
    assert window.source.text() == "@alice"
    assert window.destination.text() == str(tmp_path)
    assert cancellations == []
    assert not window.preferences.session_path.exists()
    assert not window.reset_session_button.isEnabled()
    assert window.process.state() == QProcess.ProcessState.NotRunning
    assert window.log.toPlainText() == "Previous activity"
    assert window.progress.value() == 3
    assert window.scanned_links == ["https://www.tiktok.com/@alice/video/123"]
    assert window.download_videos.isEnabled()
    assert window.statusBar().currentMessage() == "Saved browser session cleared."


def test_stop_discards_queued_scan_completion(window, monkeypatch):
    events = QBuffer()
    events.setData(b'{"type":"manual","message":"Ready"}\n'
                   b'{"type":"scanned","links":["https://www.tiktok.com/@alice/video/123"]}\n'
                   b'{"type":"done","stopped":false}\n')
    events.open(QIODevice.OpenModeFlag.ReadOnly)
    monkeypatch.setattr(window.process, "canReadLine", events.canReadLine)
    monkeypatch.setattr(window.process, "readLine", events.readLine)
    window.stopping = True
    window.scanning = True
    jobs = []
    monkeypatch.setattr(window, "start_job", lambda *args: jobs.append(args))
    window.process_finished(1, QProcess.ExitStatus.CrashExit)
    assert jobs == []
    assert window.scanned_links is None
    assert window.statusBar().currentMessage() == "Stopped"


@pytest.mark.parametrize("action", ["stop", "close"])
def test_stop_interrupts_blocked_transfer(window, qtbot, tmp_path, action):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    from tiktok_downloader.core import Job

    transferring = threading.Event()
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path.startswith("/api/"):
                body = json.dumps({"data": {"author": {"unique_id": "alice"},
                    "hdplay": f"http://127.0.0.1:{self.server.server_port}/media"}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(200)
                self.send_header("Content-Length", "1000000")
                self.end_headers()
                self.wfile.write(b"x" * 65536)
                transferring.set()
                release.wait(15)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as http:
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{http.server_port}"
        job = Job(source="@alice", folder=str(tmp_path), hd_api=origin + "/api/")
        window.scanned_links = [origin + "/@alice/video/123"]
        window.scanned_job = job
        window.start_job(job, window.scanned_links)
        partial = tmp_path / "alice" / "video" / "123_HD.mp4.part"
        qtbot.waitUntil(lambda: transferring.is_set() and partial.exists() and partial.stat().st_size > 0,
                        timeout=10000)
        if action == "stop":
            qtbot.mouseClick(window.stop, Qt.MouseButton.LeftButton)
        else:
            window.close()
        qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning,
                        timeout=5000)
        release.set()
        http.shutdown()
        thread.join()
    assert window.scanned_links == [origin + "/@alice/video/123"]
    assert window.scanned_job is job
    assert window.download_progress is not None
    assert partial.exists()
    assert not partial.with_suffix("").exists()
    assert window.statusBar().currentMessage() == "Stopped"
    if action == "close":
        assert not window.isVisible()

def test_worker_traceback(window, qtbot, job_factory, server):
    window.auto_download.setChecked(False)
    window.start_job(job_factory(hd_api=server[0] + "/unavailable"))
    qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning, timeout=30000)
    assert server[1]["/unavailable"] == 0
    qtbot.mouseClick(window.download_videos, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning, timeout=30000)
    assert "Traceback" in window.log.toPlainText()
    assert "503" in window.log.toPlainText()
    assert "code 1" in window.statusBar().currentMessage()
    assert window.download.isEnabled()


@pytest.mark.parametrize("source", ["@alice", "https://www.tiktok.com/@alice/?lang=en"])
def test_check_profile_opens_default_browser(window, qtbot, monkeypatch, source):
    from PySide6.QtGui import QDesktopServices

    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    window.source.setText(source)
    qtbot.mouseClick(window.check_profile_button, Qt.MouseButton.LeftButton)
    assert opened == ["https://www.tiktok.com/@alice"]
    assert window.process.state() == QProcess.ProcessState.NotRunning


@pytest.mark.parametrize("source", ["@another", "https://www.tiktok.com/@another/?lang=en"])
@pytest.mark.parametrize("automatic", [False, True])
def test_restore_scan_then_download(window, qtbot, tmp_path, server, source, automatic):
    window.auto_download.setChecked(automatic)
    folder = tmp_path / "media"
    folder.mkdir()
    links = [server[0] + "/@alice/video/123", server[0] + "/@alice/photo/456"]
    (window.preferences.scan_dir / "alice_combined_links.txt").write_text("\n".join(links), encoding="utf-8-sig")
    (window.preferences.scan_dir / "bob_combined_links.txt").write_text("https://www.tiktok.com/@bob/video/789")
    window.refresh_profile_scans()
    window.profile_scans.setCurrentText("alice")
    window.source.setText(source)
    window.destination.setText(str(folder))
    qtbot.mouseClick(window.restore_scan_button, Qt.MouseButton.LeftButton)
    assert window.scanned_links == links
    assert window.source.text() == "https://www.tiktok.com/@alice"
    assert window.scanned_job.source == "https://www.tiktok.com/@alice"
    assert window.scanned_job.folder == str(folder)
    assert window.download_videos.isEnabled()
    assert window.statusBar().currentMessage() == "Scan restored — 2 results."
    assert window.process.state() == QProcess.ProcessState.NotRunning
    assert sum(server[1].values()) == 0
    window.scanned_job.hd_api = server[0] + "/api/hd"
    qtbot.mouseClick(window.download_videos, Qt.MouseButton.LeftButton)
    assert not window.restore_scan_button.isEnabled()
    assert not window.download_videos.isEnabled()
    window.auto_download.setChecked(not automatic)
    assert not window.download_videos.isEnabled()
    qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning, timeout=30000)
    assert window.statusBar().currentMessage() == "Completed"
    assert (folder / "alice" / "video" / "123_HD.mp4").exists()
    assert server[1]["/@alice"] == 0
    assert server[1]["/api/hd"] == 2


def test_new_profile_scan_placeholder_and_refresh(window, qtbot, tmp_path, monkeypatch):
    path = tmp_path / "profiles.txt"
    path.write_text("@alice\n@bob\n")
    window.profile_list.setText(str(path))
    window.load_profile_list()
    window.profile_usernames.setCurrentIndex(1)
    assert window.profile_scans.currentText() == "alice*"
    assert not window.profile_scans.model().item(window.profile_scans.currentIndex()).isEnabled()
    assert not window.restore_scan_button.isEnabled()
    window.profile_usernames.setCurrentIndex(2)
    assert window.profile_scans.currentText() == "bob*"
    assert window.profile_scans.findText("alice*") == -1
    (window.preferences.scan_dir / "alice_combined_links.txt").write_text("post")
    qtbot.mouseClick(window.refresh_scans_button, Qt.MouseButton.LeftButton)
    assert window.profile_scans.findText("alice") >= 0
    assert window.profile_scans.currentText() == "bob*"
    window.profile_scans.setCurrentText("alice")
    assert window.restore_scan_button.isEnabled()
    window.profile_usernames.setCurrentIndex(1)
    window.profile_usernames.setCurrentIndex(2)
    (window.preferences.scan_dir / "bob_combined_links.txt").write_text("post")
    events = QBuffer()
    events.setData(b'{"type":"scanned","links":["post"]}\n')
    events.open(QIODevice.OpenModeFlag.ReadOnly)
    monkeypatch.setattr(window.process, "canReadLine", events.canReadLine)
    monkeypatch.setattr(window.process, "readLine", events.readLine)
    window.read_events()
    assert window.profile_scans.currentText() == "bob"
    assert window.profile_scans.findText("bob*") == -1
    assert window.restore_scan_button.isEnabled()
    assert window.refresh_scans_button.geometry().top() == window.sync_scans_button.geometry().top()


def test_restore_missing_scan_disables_download(window, qtbot, tmp_path):
    window.auto_download.setChecked(False)
    window.source.setText("@alice")
    window.destination.setText(str(tmp_path))
    path = window.preferences.scan_dir / "alice_combined_links.txt"
    path.write_text("https://www.tiktok.com/@alice/video/123")
    window.refresh_profile_scans()
    qtbot.mouseClick(window.restore_scan_button, Qt.MouseButton.LeftButton)
    assert window.download_videos.isEnabled()
    path.unlink()
    qtbot.mouseClick(window.restore_scan_button, Qt.MouseButton.LeftButton)
    assert not window.download_videos.isEnabled()
    assert window.scanned_links is None
    assert window.statusBar().currentMessage() == f"No saved scan found: {path}"
