import json

import pytest
from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog

from tiktok_downloader.app import MainWindow, SettingsDialog
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
    window.settings.browser = "firefox"
    window.settings.executable = "custom-browser"
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
    restored.reset_action.trigger()
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


def test_settings_dialog_save_cancel_and_paths(qtbot, tmp_path, monkeypatch):
    window = MainWindow(tmp_path)
    qtbot.addWidget(window)
    dialog = SettingsDialog(window.settings, window)
    qtbot.addWidget(dialog)
    assert dialog.config_path.text() == str(tmp_path / "config.json")
    assert dialog.state_path.text() == str(tmp_path / "state.json")
    assert dialog.config_path.isReadOnly()
    assert not dialog.findChildren(QCheckBox)
    window.checks["notifications"].setChecked(True)

    def accept(dialog):
        dialog.browser.setCurrentText("msedge")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SettingsDialog, "exec", accept)
    window.edit_settings()
    assert Settings(tmp_path).values.browser == "msedge"
    assert Settings(tmp_path).values.notifications
    assert not window.preferences.state_path.exists()
    before = window.preferences.config_path.read_bytes()
    monkeypatch.setattr(SettingsDialog, "exec", lambda _: QDialog.DialogCode.Rejected)
    window.edit_settings()
    assert window.preferences.config_path.read_bytes() == before
