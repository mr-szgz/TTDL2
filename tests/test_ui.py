from pathlib import Path
import pytest
from PySide6.QtCore import QProcess, Qt
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
    assert not window.findChildren(QCheckBox)
    assert "Download activity" not in [label.text() for label in window.findChildren(QLabel)]
    assert window.download.text() == "Open &browser"
    assert window.start_indexing.isVisible()
    assert window.start_indexing.text() == "&Scan Profile"
    assert window.download_videos.text() == "&Download Videos"
    assert not window.download_videos.isEnabled()
    assert not window.start_indexing.isEnabled()
    qtbot.keyClicks(window.source, "@alice")
    assert window.source.text() == "@alice"

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

def test_real_browser_waits_for_start_then_downloads(window, qtbot, job_factory, server):
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
    assert window.statusBar().currentMessage() == "Scan complete — 2 total results. Click Download Videos."
    assert window.download_videos.isEnabled()
    qtbot.wait(500)
    assert server[1]["/api/hd"] == 0
    assert not list(Path(job.folder).rglob("*.mp4"))
    assert (Path(job.folder) / "alice_combined_links.txt").read_text().splitlines() == window.scanned_links
    assert not window.status_timer.isActive()
    browser_visits = server[1]["/@alice"]
    qtbot.mouseClick(window.download_videos, Qt.MouseButton.LeftButton)
    assert not window.download_videos.isEnabled()
    assert window.pause.isEnabled()
    qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning, timeout=30000)
    assert server[1]["/@alice"] == browser_visits
    assert window.statusBar().currentMessage() == "Completed"
    window.source.setText("@another")
    assert not window.download_videos.isEnabled()
    assert server[1]["/api/hd"] == 2
    assert (Path(job.folder) / "alice" / "Videos" / "123_HD.mp4").exists()
    assert window.download.isEnabled()
    assert not window.start_indexing.isEnabled()
    assert "Indexing page 1 — 1 total results" in statuses
    assert "Indexing page 2 — 2 total results" in statuses
    assert "Downloading (1/2) — 0.00 items/sec — ETA calculating…" in statuses
    assert any(message.startswith("Downloading (2/2) — ") and "items/sec — ETA" in message for message in statuses)
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

def test_worker_traceback(window, qtbot, job_factory, server):
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
    window.scanned_job.transfer_delay_ms = 0
    qtbot.mouseClick(window.download_videos, Qt.MouseButton.LeftButton)
    assert not window.restore_scan_button.isEnabled()
    qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning, timeout=30000)
    assert window.statusBar().currentMessage() == "Completed"
    assert (folder / "alice" / "Videos" / "123_HD.mp4").exists()
    assert server[1]["/@alice"] == 0
    assert server[1]["/api/hd"] == 2


def test_restore_missing_scan_disables_download(window, qtbot, tmp_path):
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
