import json

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
    saved_config = window.preferences.config_path.read_bytes()
    saved_state = window.preferences.state_path.read_bytes()
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
    assert window.preferences.config_path.read_bytes() == saved_config
    assert window.preferences.state_path.read_bytes() == saved_state
    window.reset_defaults()
    window.save_config()
    assert Settings(tmp_path).values.source == ""
    assert Settings(tmp_path).values.browser == "chromium"


def test_settings_tab_save_paths_and_busy_state(qtbot, tmp_path):
    window = MainWindow(tmp_path)
    qtbot.addWidget(window)
    window.show()
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ["Download", "Settings"]
    assert window.tabs.currentWidget() == window.download_tab
    assert not window.findChildren(QDialog)
    assert not window.findChildren(QMenuBar)
    assert window.config_path.text() == str(tmp_path / "config.json")
    assert window.state_path.text() == str(tmp_path / "state.json")
    assert window.config_path.isReadOnly()
    assert window.state_path.isReadOnly()
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
    assert window.cancel_reset.isEnabled()
    window.set_busy(False)
    window.tabs.setCurrentWidget(window.settings_tab)
    assert window.browser.isEnabled()
    assert window.save_settings_button.isEnabled()
