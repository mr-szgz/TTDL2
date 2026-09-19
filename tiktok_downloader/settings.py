"""User configuration, saved UI state, and app-owned directories."""

from pathlib import Path
from typing import Literal

from platformdirs import PlatformDirs, user_desktop_path
from pydantic import BaseModel, Field

dirs = PlatformDirs("TikTokDownloader2", appauthor=False)
CONFIG_DIR = dirs.user_config_path


class AppState(BaseModel):
    source: str = ""
    selected_username: str = ""
    folder: str = Field(default_factory=lambda: str(user_desktop_path() / "TikTokDownloads2"))
    window_geometry: str = ""

    def save(self, path: Path):
        path.write_text(self.model_dump_json(indent=2, exclude_unset=True), encoding="utf-8")


class AppConfig(AppState):
    remember_settings: bool = True
    images_only: bool = False
    json_logs: bool = False
    download_logs: bool = False
    notifications: bool = False
    scroll_ms: int = 10000
    browser: Literal["system", "chromium", "chrome", "msedge", "firefox"] = "chromium"
    executable: str = ""

    def save(self, path: Path):
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")


class Settings:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.config_path = directory / "config.json"
        self.state_path = directory / "state.json"
        self.session_path = directory / "browser-session.json"
        self.scan_dir = directory / "scans"
        self.index_dir = directory / "indexes"
        self.scan_dir.mkdir(exist_ok=True)
        self.index_dir.mkdir(exist_ok=True)
        self.config = (AppConfig.model_validate_json(self.config_path.read_text(encoding="utf-8"))
                       if self.config_path.exists() else AppConfig())
        self.state = (AppState.model_validate_json(self.state_path.read_text(encoding="utf-8"))
                      if self.state_path.exists() else AppState())
        self.values = AppConfig.model_validate(
            self.config.model_dump() | self.state.model_dump(exclude_unset=True)
        )

    def save_state(self, state: AppState):
        self.state = state
        self.values = AppConfig.model_validate(self.values.model_dump() | state.model_dump(exclude_unset=True))
        self.state.save(self.state_path)

    def reset_state(self):
        self.values = AppConfig()

    def save_config(self, **changes):
        self.config = AppConfig.model_validate(self.config.model_dump() | changes)
        self.config.save(self.config_path)
        self.values = AppConfig.model_validate(self.values.model_dump() | changes)
