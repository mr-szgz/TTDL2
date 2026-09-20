"""Download metadata providers with one normalized media result contract."""

from dataclasses import dataclass
import json
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


@dataclass(frozen=True)
class MediaAsset:
    category: str
    name: str
    url: str
    index_id: str


@dataclass(frozen=True)
class MediaResult:
    username: str
    assets: list[MediaAsset]


def filename_component(value):
    return "".join(c if c.isascii() and (c.isalnum() or c in "_.-")
                   else f"%{ord(c):X}" for c in str(value))


class TikWMProvider:
    def __init__(self, job, emit, control):
        self.job = job
        self.emit = emit
        self.control = control
        self.metadata_ready_at = 0.0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def resolve(self, url, username, kind, media_id, session):
        if self.control.stopped.wait(max(0, self.metadata_ready_at - monotonic())):
            return None
        if not self.control.checkpoint():
            return None
        with session.get(self.job.hd_api, params={"url": media_id, "hd": "1"}, timeout=120) as response:
            response.raise_for_status()
            response_body = response.text
            raw = json.loads(response_body)
            status_code = response.status_code
            request_url = response.url
            remaining = response.headers.get("X-Limit-Request-Remaining")
            reset_seconds = response.headers.get("X-Limit-Request-Reset")
            self.emit({
                "type": "api_usage",
                "remaining": remaining,
                "reset_seconds": reset_seconds,
                "message": raw["msg"],
            })
        self.metadata_ready_at = monotonic() + 1.0
        response_path = self._save_response(username, media_id, raw)
        if raw["code"] != 0:
            self.emit({
                "type": "api_error",
                "media_id": media_id,
                "status_code": status_code,
                "request_url": request_url,
                "remaining": remaining,
                "reset_seconds": reset_seconds,
                "response": raw,
                "response_body": response_body,
                "response_path": str(response_path),
            })
            return None
        data = raw["data"]
        username = data["author"]["unique_id"]
        if kind == "photo":
            assets = [MediaAsset("photo", f"{media_id}_{index}.jpg", image,
                                 f"{media_id}_{index}.jpg")
                      for index, image in enumerate(data["images"], 1)]
        else:
            assets = [MediaAsset("video", f"{media_id}_HD.mp4", data["hdplay"],
                                 f"{media_id}_HD")]
        return MediaResult(username, assets)

    def _save_response(self, username, media_id, raw):
        json_dir = Path(self.job.folder) / filename_component(username) / "Data" / "json"
        json_dir.mkdir(parents=True, exist_ok=True)
        path = json_dir / f"{media_id}_HD.json"
        path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        return path


class TikTokDirectProvider:
    def __init__(self, job, emit, control):
        self.job = job
        self.emit = emit
        self.control = control

    def __enter__(self):
        self.playwright = sync_playwright().start()
        options = {"headless": True}
        executable = self.job.executable
        if self.job.browser == "system" and not executable:
            executable = self._system_browser()
        engine = (self.playwright.firefox
                  if self.job.browser == "firefox" or "firefox" in executable.lower()
                  else self.playwright.chromium)
        if executable:
            options["executable_path"] = (self.playwright.firefox.executable_path
                                          if "firefox" in executable.lower() else executable)
        elif self.job.browser in ("chrome", "msedge"):
            options["channel"] = self.job.browser
        self.browser = engine.launch(**options)
        self.context = self.browser.new_context(
            storage_state=self.job.session_path if Path(self.job.session_path).is_file() else None)
        self.page = self.context.new_page()
        return self

    def __exit__(self, *_):
        self.context.close()
        self.browser.close()
        self.playwright.stop()

    def resolve(self, url, username, kind, media_id, session):
        if self.job.tiktok_cookie:
            cookie_url = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
            self.context.add_cookies([
                {"name": name, "value": value, "url": cookie_url}
                for name, value in (part.strip().split("=", 1)
                                    for part in self.job.tiktok_cookie.split(";") if part.strip())
            ])
        self.page.goto(url, wait_until="domcontentloaded", timeout=120000)
        raw = json.loads(self.page.locator(
            "script#__UNIVERSAL_DATA_FOR_REHYDRATION__").text_content())
        item = raw["__DEFAULT_SCOPE__"]["webapp.video-detail"]["itemInfo"]["itemStruct"]
        username = item["author"]["uniqueId"]
        self._save_response(username, media_id, raw)
        session.headers.update({
            "User-Agent": self.page.evaluate("navigator.userAgent"),
            "Referer": self.page.url,
        })
        for cookie in self.context.cookies():
            session.cookies.set(cookie["name"], cookie["value"],
                                domain=cookie["domain"], path=cookie["path"])
        if kind == "photo":
            assets = [MediaAsset("photo", f"{media_id}_{index}.jpg",
                                 image["imageURL"]["urlList"][0], f"{media_id}_{index}.jpg")
                      for index, image in enumerate(item["imagePost"]["images"], 1)]
        else:
            variant = max(item["video"]["bitrateInfo"], key=lambda value: (
                max(value["PlayAddr"]["Width"], value["PlayAddr"]["Height"]),
                value["Bitrate"], int(value["PlayAddr"]["DataSize"])))
            assets = [MediaAsset("video", f"{media_id}_HD.mp4",
                                 variant["PlayAddr"]["UrlList"][0], f"{media_id}_HD")]
        return MediaResult(username, assets)

    def _save_response(self, username, media_id, raw):
        json_dir = Path(self.job.folder) / filename_component(username) / "Data" / "json"
        json_dir.mkdir(parents=True, exist_ok=True)
        path = json_dir / f"{media_id}_DIRECT.json"
        path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _system_browser():
        import re
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice") as key:
            prog_id = winreg.QueryValueEx(key, "ProgId")[0]
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id + r"\shell\open\command") as key:
            command = winreg.QueryValueEx(key, "")[0]
        return re.match(r'"?(.+?\.exe)', command, re.IGNORECASE)[1]


PROVIDERS = {
    "tikwm": TikWMProvider,
    "tiktok_direct": TikTokDirectProvider,
}


def create_provider(job, emit, control):
    return PROVIDERS[job.api_method](job, emit, control)
