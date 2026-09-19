import json
from pathlib import Path
import subprocess
import pytest
from PySide6.QtCore import QBuffer, QIODevice, QProcess, Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel
from tiktok_downloader.app import MainWindow, SettingsDialog
from tiktok_downloader.settings import AppConfig, Settings

@pytest.fixture
def window(qtbot, tmp_path):
    widget = MainWindow(tmp_path)
    qtbot.addWidget(widget)
    widget.show()
    return widget

def test_hd_mass_only_screen(window, qtbot):
    assert not window.findChildren(QComboBox)
    assert window.findChildren(QCheckBox) == [window.auto_download]
    assert window.auto_download.isChecked()
    assert window.auto_download.geometry().bottom() < window.progress.geometry().top()
    assert window.auto_download.geometry().top() > window.download.geometry().bottom()
    assert "Download activity" not in [label.text() for label in window.findChildren(QLabel)]
    assert window.download.text() == "Setup &Browser"
    assert window.start_indexing.isVisible()
    assert window.start_indexing.text() == "&Scan Profile"
    assert window.cancel_reset.text() == "&Cancel / Reset"
    assert window.cancel_reset.isEnabled()
    assert window.cancel_reset.geometry().top() == window.download.geometry().top()
    assert window.download_videos.text() == "&Download Videos"
    assert not window.download_videos.isEnabled()
    assert not window.start_indexing.isEnabled()
    qtbot.keyClicks(window.source, "@alice")
    assert window.source.text() == "@alice"

def test_automatic_download_toggle_respects_scan_and_busy_state(window):
    window.auto_download.setChecked(False)
    assert not window.download_videos.isEnabled()
    window.scanned_links = ["https://www.tiktok.com/@alice/video/123"]
    window.auto_download.setChecked(True)
    assert not window.download_videos.isEnabled()
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
    assert not window.download_videos.isEnabled()


def test_native_defaults(window, qtbot):
    from PySide6.QtWidgets import QApplication
    assert QApplication.instance().styleSheet() == ""
    assert window.styleSheet() == ""
    window.resize(650, 480)
    qtbot.wait(30)
    assert window.centralWidget().rect().contains(window.log.geometry())
    window.source.setFocus()
    assert window.source.hasFocus()

def test_settings(window, tmp_path):
    settings = AppConfig(folder=str(tmp_path), images_only=True, json_logs=True, download_logs=True, notifications=True)
    path = tmp_path / "config.json"
    settings.save(path)
    assert Settings(tmp_path).values == settings
    assert SettingsDialog(settings, window).settings() == settings

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
        "Indexed 1 unique posts — 1 new posts found",
        "Indexed 1 unique posts — 0 new posts found",
    ]
    assert window.statusBar().currentMessage() == "Indexed 1 unique posts — 0 new posts found"
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
        assert window.statusBar().currentMessage() == "Scan complete — 2 total results. Click Download Videos."
        assert window.download_videos.isEnabled()
        qtbot.wait(500)
        assert server[1]["/api/hd"] == 0
        assert not list(Path(job.folder).rglob("*.mp4"))
    assert (Path(job.folder) / "alice_combined_links.txt").read_text().splitlines() == window.scanned_links
    assert not window.status_timer.isActive()
    browser_visits = server[1]["/@alice"]
    if not automatic:
        qtbot.mouseClick(window.download_videos, Qt.MouseButton.LeftButton)
        assert not window.download_videos.isEnabled()
        assert window.pause.isEnabled()
        qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning, timeout=30000)
    assert window.download_videos.isEnabled() == (not automatic)
    assert server[1]["/@alice"] == browser_visits
    assert window.statusBar().currentMessage() == "Completed"
    window.source.setText("@another")
    assert not window.download_videos.isEnabled()
    assert server[1]["/api/hd"] == 2
    assert (Path(job.folder) / "alice" / "video" / "123_HD.mp4").exists()
    assert window.download.isEnabled()
    assert not window.start_indexing.isEnabled()
    assert "Indexed 1 unique posts — 1 new posts found" in statuses
    assert "Indexed 2 unique posts — 1 new posts found" in statuses
    assert "Downloading (1/2) — 0 bytes downloaded — 0.00 MB/s — ETA calculating…" in statuses
    assert any(message.startswith("Downloading (2/2) — ") and "MB/s — ETA" in message for message in statuses)
    assert not window.status_timer.isActive()
    qtbot.wait(1100)
    assert window.statusBar().currentMessage() == "Completed"

def test_stop_while_waiting_does_not_crawl(window, qtbot, job_factory, server):
    job = job_factory(manual_start=True)
    existing = Path(job.folder) / "alice_combined_links.txt"
    existing.parent.mkdir(parents=True)
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


@pytest.mark.parametrize("stage", ["starting", "setup", "scanning"])
def test_cancel_reset_closes_scan_and_allows_restart(window, qtbot, job_factory, server, stage):
    job = job_factory(manual_start=True, headless=False, scroll_ms=10000)
    existing = Path(job.folder) / "alice_combined_links.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("previously collected URLs")
    window.start_job(job)
    if stage != "starting":
        qtbot.waitUntil(lambda: window.start_indexing.isEnabled(), timeout=30000)
    if stage == "scanning":
        qtbot.mouseClick(window.start_indexing, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: server[1]["/indexing"] > 0, timeout=10000)
    if stage == "setup":
        command = ["powershell", "-NoProfile", "-Command",
                   "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Json -Compress"]
        processes = json.loads(subprocess.check_output(command, creationflags=subprocess.CREATE_NO_WINDOW))
        descendants = {window.process.processId()}
        while children := {p["ProcessId"] for p in processes
                           if p["ParentProcessId"] in descendants} - descendants:
            descendants.update(children)
        assert any(p["ProcessId"] in descendants and p["Name"] == "chrome.exe" for p in processes)
    qtbot.mouseClick(window.cancel_reset, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.resetting, timeout=5000)
    assert window.process.state() == QProcess.ProcessState.NotRunning
    assert window.statusBar().currentMessage() == "Ready"
    assert window.scanned_links is None
    assert window.scanned_job is None
    assert window.download_progress is None
    assert not window.status_timer.isActive()
    assert not window.scanning
    assert not window.paused
    assert not window.start_indexing.isEnabled()
    assert not window.download_videos.isEnabled()
    assert not window.pause.isEnabled()
    assert not window.stop.isEnabled()
    assert window.download.isEnabled()
    assert window.cancel_reset.isEnabled()
    assert window.log.toPlainText() == ""
    assert existing.read_text() == "previously collected URLs"
    assert server[1]["/api/hd"] == 0
    if stage == "setup":
        remaining = json.loads(subprocess.check_output(command, creationflags=subprocess.CREATE_NO_WINDOW))
        assert not descendants.intersection(p["ProcessId"] for p in remaining)
    window.start_job(job)
    qtbot.waitUntil(lambda: window.start_indexing.isEnabled(), timeout=30000)
    qtbot.mouseClick(window.cancel_reset, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.resetting, timeout=5000)


def test_reset_idle_clears_restored_scan_without_changing_inputs(window, qtbot, tmp_path):
    window.source.setText("@alice")
    window.destination.setText(str(tmp_path))
    window.scanned_links = ["https://www.tiktok.com/@alice/video/123"]
    window.auto_download.setChecked(False)
    qtbot.mouseClick(window.cancel_reset, Qt.MouseButton.LeftButton)
    assert window.source.text() == "@alice"
    assert window.destination.text() == str(tmp_path)
    assert window.scanned_links is None
    assert not window.download_videos.isEnabled()
    assert window.statusBar().currentMessage() == "Ready"


def test_cancel_discards_queued_scan_completion(window, monkeypatch):
    events = QBuffer()
    events.setData(b'{"type":"manual","message":"Ready"}\n'
                   b'{"type":"scanned","links":["https://www.tiktok.com/@alice/video/123"]}\n'
                   b'{"type":"done","stopped":false}\n')
    events.open(QIODevice.OpenModeFlag.ReadOnly)
    monkeypatch.setattr(window.process, "canReadLine", events.canReadLine)
    monkeypatch.setattr(window.process, "readLine", events.readLine)
    window.resetting = True
    window.scanning = True
    jobs = []
    monkeypatch.setattr(window, "start_job", lambda *args: jobs.append(args))
    window.process_finished(1, QProcess.ExitStatus.CrashExit)
    assert jobs == []
    assert window.scanned_links is None
    assert window.statusBar().currentMessage() == "Ready"


@pytest.mark.parametrize("action", ["reset", "close"])
def test_cancel_interrupts_blocked_transfer(window, qtbot, tmp_path, action):
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
        window.start_job(job, [origin + "/@alice/video/123"])
        partial = tmp_path / "alice" / "video" / "123_HD.mp4.part"
        qtbot.waitUntil(lambda: transferring.is_set() and partial.exists() and partial.stat().st_size > 0,
                        timeout=10000)
        if action == "reset":
            qtbot.mouseClick(window.cancel_reset, Qt.MouseButton.LeftButton)
        else:
            window.close()
        qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning and not window.resetting,
                        timeout=5000)
        release.set()
        http.shutdown()
        thread.join()
    assert partial.exists()
    assert not partial.with_suffix("").exists()
    assert window.statusBar().currentMessage() == "Ready"
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
def test_restore_scan_then_download(window, qtbot, tmp_path, server, source):
    window.auto_download.setChecked(False)
    folder = tmp_path / "media"
    folder.mkdir()
    links = [server[0] + "/@alice/video/123", server[0] + "/@alice/photo/456"]
    (folder / "alice_combined_links.txt").write_text("\n".join(links), encoding="utf-8-sig")
    window.source.setText(source)
    window.destination.setText(str(folder))
    qtbot.mouseClick(window.restore_scan_button, Qt.MouseButton.LeftButton)
    assert window.scanned_links == links
    assert window.scanned_job.source == source
    assert window.scanned_job.folder == str(folder)
    assert window.download_videos.isEnabled()
    assert window.statusBar().currentMessage() == "Scan restored — 2 total results."
    assert window.process.state() == QProcess.ProcessState.NotRunning
    assert sum(server[1].values()) == 0
    window.scanned_job.hd_api = server[0] + "/api/hd"
    qtbot.mouseClick(window.download_videos, Qt.MouseButton.LeftButton)
    assert not window.restore_scan_button.isEnabled()
    qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning, timeout=30000)
    assert window.statusBar().currentMessage() == "Completed"
    assert (folder / "alice" / "video" / "123_HD.mp4").exists()
    assert server[1]["/@alice"] == 0
    assert server[1]["/api/hd"] == 2


def test_restore_missing_scan_disables_download(window, qtbot, tmp_path):
    window.auto_download.setChecked(False)
    window.source.setText("@alice")
    window.destination.setText(str(tmp_path))
    path = tmp_path / "alice_combined_links.txt"
    path.write_text("https://www.tiktok.com/@alice/video/123")
    qtbot.mouseClick(window.restore_scan_button, Qt.MouseButton.LeftButton)
    assert window.download_videos.isEnabled()
    path.unlink()
    qtbot.mouseClick(window.restore_scan_button, Qt.MouseButton.LeftButton)
    assert not window.download_videos.isEnabled()
    assert window.scanned_links is None
    assert window.statusBar().currentMessage() == f"No saved scan found: {path}"
