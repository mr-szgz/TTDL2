from pathlib import Path
import pytest
from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel
from tiktok_downloader.app import MainWindow, SettingsDialog
from tiktok_downloader.settings import Settings, load_settings, save_settings

@pytest.fixture
def window(qtbot, tmp_path):
    widget = MainWindow(tmp_path / "config.json")
    qtbot.addWidget(widget)
    widget.show()
    return widget

def test_hd_mass_only_screen(window, qtbot):
    assert not window.findChildren(QComboBox)
    assert not window.findChildren(QCheckBox)
    assert "Download activity" not in [label.text() for label in window.findChildren(QLabel)]
    assert window.download.text() == "Open &browser"
    assert window.start_indexing.isVisible()
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
    settings = Settings(str(tmp_path), True, True, True, True, "chromium", "")
    path = tmp_path / "settings.json"
    save_settings(settings, path)
    assert load_settings(path) == settings
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
    qtbot.mouseClick(window.start_indexing, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning, timeout=30000)
    assert window.statusBar().currentMessage() == "Completed"
    assert server[1]["/api/hd"] == 2
    assert (Path(job.folder) / "alice" / "Videos" / "123_HD.mp4").exists()
    assert window.download.isEnabled()
    assert not window.start_indexing.isEnabled()
    assert "Indexing page 1 — 1 total results" in statuses
    assert "Indexing page 2 — 2 total results" in statuses
    assert "Downloading (1/2)" in statuses
    assert "Downloading (2/2)" in statuses

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
    assert server[1]["/indexing"] == 0
    assert server[1]["/api/hd"] == 0
    assert existing.read_text() == "previously collected URLs"

def test_worker_traceback(window, qtbot, job_factory, server):
    window.start_job(job_factory(hd_api=server[0] + "/unavailable"))
    qtbot.waitUntil(lambda: window.process.state() == QProcess.ProcessState.NotRunning, timeout=30000)
    assert "Traceback" in window.log.toPlainText()
    assert "503" in window.log.toPlainText()
    assert "code 1" in window.statusBar().currentMessage()
    assert window.download.isEnabled()
