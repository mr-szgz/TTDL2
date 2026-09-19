from dataclasses import asdict, dataclass
import json
from pathlib import Path

from PySide6.QtCore import QStandardPaths


@dataclass
class Settings:
    folder: str
    images_only: bool = False
    json_logs: bool = False
    download_logs: bool = False
    notifications: bool = False
    browser: str = "chromium"
    executable: str = ""


def settings_path():
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)) / "settings.json"


def save_settings(settings, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


def load_settings(path):
    if not path.exists():
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        save_settings(Settings(str(Path(desktop) / "TikTokDownloads2")), path)
    return Settings(**json.loads(path.read_text(encoding="utf-8")))
