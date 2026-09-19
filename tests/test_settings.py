import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMenuBar

from tiktok_downloader.app import MainWindow
from tiktok_downloader.settings import AppConfig, AppState, Settings


def test_first_launch_and_config_state_precedence(tmp_path):
    settings = Settings(tmp_path)
    assert settings.values == AppConfig()
    assert not settings.config_path.exists()
    assert not settings.state_path.exists()
    AppConfig(source="@configured", browser="firefox").save(settings.config_path)
    AppState(source="@remembered").save(settings.state_path)
    restored = Settings(tmp_path)
    assert restored.values.source == "@remembered"
    assert restored.values.browser == "firefox"
    assert "browser" not in json.loads(settings.state_path.read_text())


def test_invalid_config_surfaces(tmp_path):
    (tmp_path / "config.json").write_text('{"browser": "invalid"}')
    with pytest.raises(ValidationError):
        Settings(tmp_path)


def test_startup_loads_profiles_and_restores_selected_username(qtbot, tmp_path, monkeypatch):
    folder = tmp_path / "downloads"
    folder.mkdir()
    profiles = folder / "ttdl2.txt"
    profiles.write_text("@alice\nhttps://www.tiktok.com/@bob\n@carol\n", encoding="utf-8")
    AppState(folder=str(folder)).save(tmp_path / "state.json")
    window = MainWindow(tmp_path)
    qtbot.addWidget(window)
    assert [window.profile_usernames.itemText(i) for i in range(4)] == ["", "alice", "bob", "carol"]
    window.profile_usernames.setCurrentIndex(2)
    window.close()
    assert json.loads((tmp_path / "state.json").read_text())["selected_username"] == "bob"

    profiles.write_text("@carol\n@alice\n@bob\n", encoding="utf-8")
    restored = MainWindow(tmp_path)
    qtbot.addWidget(restored)
    assert restored.profile_usernames.currentText() == "bob"
    assert restored.profile_usernames.currentIndex() == 3
    assert restored.source.text() == "@bob"
    jobs = []
    monkeypatch.setattr(restored, "start_job", jobs.append)
    restored.start_download()
    assert jobs[0].source == "@bob"
    restored.close()


def test_save_restart_reset_and_close(qtbot, tmp_path):
    window = MainWindow(tmp_path)
    qtbot.addWidget(window)
    window.show()
    window.source.setText("@alice")
    window.destination.setText(str(tmp_path / "downloads"))
    window.resize(960, 720)
    window.tabs.setCurrentWidget(window.settings_tab)
    window.browser.setCurrentText("firefox")
    window.executable.setText("custom-browser")
    for check in window.checks.values():
        check.setChecked(True)
    assert not window.preferences.state_path.exists()
    qtbot.mouseClick(window.save_settings_button, Qt.MouseButton.LeftButton)
    restored = MainWindow(tmp_path)
    qtbot.addWidget(restored)
    restored.show()
    assert restored.source.text() == "@alice"
    assert restored.destination.text() == str(tmp_path / "downloads")
    assert restored.size() == window.size()
    assert restored.settings == window.settings
    assert all(check.isChecked() for check in restored.checks.values())
    assert restored.browser.currentText() == "firefox"
    assert restored.executable.text() == "custom-browser"
    restored.tabs.setCurrentWidget(restored.settings_tab)
    qtbot.mouseClick(restored.restore_defaults_button, Qt.MouseButton.LeftButton)
    assert restored.browser.currentText() == "chromium"
    assert restored.executable.text() == ""
    assert restored.settings == AppConfig()
    assert not any(check.isChecked() for check in restored.checks.values())
    assert restored.source.text() == ""
    assert restored.size().width() == 840
    restored.close()
    assert Settings(tmp_path).values.source == ""
    assert Settings(tmp_path).values.browser == "chromium"
    window.reset_defaults()
    window.save_config()
    assert Settings(tmp_path).values.source == ""
    assert Settings(tmp_path).values.browser == "chromium"


@pytest.mark.parametrize("remember", [True, False])
def test_close_remembers_settings_when_enabled(qtbot, tmp_path, remember):
    window = MainWindow(tmp_path)
    qtbot.addWidget(window)
    window.show()
    assert window.remember_settings.isChecked()
    window.source.setText("@saved")
    window.save_config()
    window.remember_settings.setChecked(remember)
    window.source.setText("@changed")
    window.checks["images_only"].setChecked(True)
    window.close()

    restored = MainWindow(tmp_path)
    qtbot.addWidget(restored)
    assert restored.remember_settings.isChecked() == remember
    assert restored.source.text() == ("@changed" if remember else "@saved")
    assert restored.checks["images_only"].isChecked() == remember


def test_settings_tab_save_paths_and_busy_state(qtbot, tmp_path):
    window = MainWindow(tmp_path)
    qtbot.addWidget(window)
    window.show()
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ["Downloader", "Settings"]
    assert window.tabs.currentWidget() == window.download_tab
    assert not window.findChildren(QDialog)
    assert not window.findChildren(QMenuBar)
    assert window.config_path.text() == str(tmp_path / "config.json")
    assert window.state_path.text() == str(tmp_path / "state.json")
    assert window.config_path.isReadOnly()
    assert window.state_path.isReadOnly()
    assert window.scan_path.text() == str(tmp_path / "scans")
    assert window.scan_path.isReadOnly()
    assert window.preferences.scan_dir.is_dir()
    assert window.preferences.index_dir == tmp_path / "indexes"
    assert window.preferences.index_dir.is_dir()
    window.checks["notifications"].setChecked(True)
    window.tabs.setCurrentWidget(window.settings_tab)
    qtbot.waitUntil(window.browser.isVisible)
    window.browser.setCurrentText("msedge")
    window.executable.setText("custom-browser")
    assert not window.preferences.config_path.exists()
    qtbot.mouseClick(window.save_settings_button, Qt.MouseButton.LeftButton)
    saved = Settings(tmp_path).values
    assert saved.browser == "msedge"
    assert saved.executable == "custom-browser"
    assert saved.notifications
    window.set_busy(True)
    assert not window.browser.isEnabled()
    assert not window.executable.isEnabled()
    assert not window.save_settings_button.isEnabled()
    assert not window.restore_defaults_button.isEnabled()
    window.tabs.setCurrentWidget(window.download_tab)
    assert not window.reset_session_button.isEnabled()
    window.set_busy(False)
    window.tabs.setCurrentWidget(window.settings_tab)
    assert window.browser.isEnabled()
    assert window.save_settings_button.isEnabled()


def test_browser_status_refreshes_from_disk(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "browsers"))
    window = MainWindow(tmp_path)
    qtbot.addWidget(window)
    window.show()
    window.tabs.setCurrentWidget(window.settings_tab)
    assert window.browser_status.text() == "Browser not installed"
    executable = Path(window.browser_status.toolTip())
    executable.parent.mkdir(parents=True)
    executable.touch()
    qtbot.mouseClick(window.check_browser_button, Qt.MouseButton.LeftButton)
    assert window.browser_status.text() == "Browser installed"
    executable.unlink()
    qtbot.mouseClick(window.check_browser_button, Qt.MouseButton.LeftButton)
    assert window.browser_status.text() == "Browser not installed"
    window.executable.setText(str(tmp_path / "custom.exe"))
    assert not window.download_browser_button.isEnabled()
    assert not window.reinstall_browser_button.isEnabled()
    assert window.check_browser_button.isEnabled()
    (tmp_path / "custom.exe").touch()
    qtbot.mouseClick(window.check_browser_button, Qt.MouseButton.LeftButton)
    assert window.browser_status.text().startswith("Browser installed")
    window.executable.clear()
    assert window.download_browser_button.isEnabled()


@pytest.mark.parametrize("force", [False, True])
def test_browser_install_process_refreshes_status(qtbot, tmp_path, monkeypatch, force):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "browsers"))
    window = MainWindow(tmp_path)
    qtbot.addWidget(window)
    window.show()
    window.tabs.setCurrentWidget(window.settings_tab)
    executable = Path(window.browser_status.toolTip())
    arguments = []
    set_arguments = window.browser_install_process.setArguments

    def local_installer(values):
        arguments.extend(values)
        set_arguments(["-c", "from pathlib import Path; "
                       f"p = Path({str(executable)!r}); "
                       "p.parent.mkdir(parents=True, exist_ok=True); p.touch()"])

    monkeypatch.setattr(window.browser_install_process, "setArguments", local_installer)
    button = window.reinstall_browser_button if force else window.download_browser_button
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert not window.check_browser_button.isEnabled()
    assert not window.download.isEnabled()
    assert not window.reset_session_button.isEnabled()
    assert arguments == ["-m", "playwright", "install", "chromium"] + (["--force"] if force else [])
    qtbot.waitUntil(lambda: window.check_browser_button.isEnabled(), timeout=10000)
    assert window.browser_status.text() == "Browser installed"
    assert window.download.isEnabled()
    assert not window.reset_session_button.isEnabled()
    assert window.statusBar().currentMessage() == "Browser installer exited with code 0"
