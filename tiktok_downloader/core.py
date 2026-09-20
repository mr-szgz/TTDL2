"""Port of MainForm.cs workflows. Browser collection precedes HTTP downloads."""
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import threading
from time import monotonic
from urllib.parse import quote, unquote, urljoin, urlsplit
import requests
from playwright.sync_api import sync_playwright
from .providers import create_provider
from .settings import CONFIG_DIR

@dataclass
class Job:
    source: str
    folder: str
    images_only: bool = False
    video_dir: str = "video"
    image_dir: str = "photo"
    download_logs: bool = False
    browser: str = "chromium"
    executable: str = ""
    headless: bool = False
    manual_start: bool = True
    scroll_ms: int = 10000
    site: str = "https://www.tiktok.com"
    hd_api: str = "https://www.tikwm.com/api/"
    api_method: str = "tikwm"
    tikwm_api_key: str = ""
    tiktok_cookie: str = ""
    session_path: str = str(CONFIG_DIR / "browser-session.json")
    new_session: bool = False
    scan_dir: str = str(CONFIG_DIR / "scans")
    index_dir: str = str(CONFIG_DIR / "indexes")

class Control:
    def __init__(self):
        self.ready = threading.Event()
        self.ready.set()
        self.stopped = threading.Event()

    def pause(self):
        self.ready.clear()

    def resume(self):
        self.ready.set()

    def stop(self):
        self.stopped.set()
        self.ready.set()

    def checkpoint(self):
        if self.stopped.is_set():
            return False
        self.ready.wait()
        return not self.stopped.is_set()

def post_parts(url):
    return re.fullmatch(r"/@([^/]+)/(video|photo)/(\d+)/?", unquote(urlsplit(url).path)).groups()

def filename_component(value):
    return "".join(c if c.isascii() and (c.isalnum() or c in "_.-")
                   else f"%{ord(c):X}" for c in str(value))

def profile_name(source):
    return unquote(urlsplit(source).path if "://" in source else source).strip("/@")

def read_links(path):
    return [line.strip() for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]

def system_browser():
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                       r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice") as key:
        prog_id = winreg.QueryValueEx(key, "ProgId")[0]
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id + r"\shell\open\command") as key:
        command = winreg.QueryValueEx(key, "")[0]
    return re.match(r'"?(.+?\.exe)', command, re.IGNORECASE)[1]

class Downloader:
    def __init__(self, job, emit, control):
        self.job, self.emit, self.control = job, emit, control

    def log(self, message):
        self.emit({"type": "log", "message": message})
        if self.job.download_logs:
            with (Path(self.job.folder) / "downloads.log").open("a", encoding="utf-8") as file:
                file.write(message + "\n")

    def collect_profile(self):
        """MassDownloadByUsername: browser, manual Resume, scroll, saved links."""
        job = self.job
        username = profile_name(job.source)
        with sync_playwright() as playwright:
            options = {"headless": job.headless}
            executable = job.executable
            if job.browser == "system" and not executable:
                executable = system_browser()
            engine = playwright.firefox if job.browser == "firefox" or "firefox" in executable.lower() else playwright.chromium
            if executable:
                options["executable_path"] = playwright.firefox.executable_path if "firefox" in executable.lower() else executable
            elif job.browser in ("chrome", "msedge"):
                options["channel"] = job.browser
            browser = engine.launch(**options)
            context = browser.new_context(storage_state=job.session_path
                                          if not job.new_session and Path(job.session_path).is_file() else None)
            page = context.new_page()
            page.goto(f"{job.site}/@{quote(username)}", wait_until="domcontentloaded", timeout=120000)
            context.storage_state(path=job.session_path, indexed_db=True)
            self.emit({"type": "session_saved", "path": job.session_path})
            if job.manual_start:
                self.control.pause()
                self.emit({"type": "manual", "message": "Set up the browser session: log in, solve CAPTCHA, and open the profile. Click Scan Profile in the app when ready."})
                while not self.control.ready.is_set() and not self.control.stopped.is_set():
                    page.wait_for_timeout(1000)
                    context.storage_state(path=job.session_path, indexed_db=True)
                context.storage_state(path=job.session_path, indexed_db=True)
            if self.control.checkpoint() and not job.headless:
                session = context.new_cdp_session(page)
                window_id = session.send("Browser.getWindowForTarget")["windowId"]
                session.send("Browser.setWindowBounds", {
                    "windowId": window_id, "bounds": {"windowState": "minimized"},
                })
                session.detach()
                self.log("Browser minimized. Indexing in the background — 0 results indexed.")
            indexed = {"video": [], "photo": []}
            total = 0
            scrolled = False
            while self.control.checkpoint():
                previous_total = total
                for kind in ("video", "photo"):
                    for anchor in page.locator(f'a[href*="/{kind}/"]').all():
                        link = urljoin(page.url, anchor.get_attribute("href"))
                        parsed = urlsplit(link)
                        if re.fullmatch(rf"/@{re.escape(username)}/{kind}/\d+/?", unquote(parsed.path)):
                            canonical = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                            if canonical not in indexed[kind]:
                                indexed[kind].append(canonical)
                total = len(indexed["video"]) + len(indexed["photo"])
                if scrolled and total == previous_total:
                    break
                self.emit({"type": "indexing", "total": total, "added": total - previous_total})
                page.keyboard.press("End")
                scrolled = True
                scroll_deadline = monotonic() + job.scroll_ms / 1000
                while not self.control.stopped.is_set() and monotonic() < scroll_deadline:
                    page.wait_for_timeout(min(100, (scroll_deadline - monotonic()) * 1000))
                context.storage_state(path=job.session_path, indexed_db=True)
            links = indexed["video"] + indexed["photo"]
            context.storage_state(path=job.session_path, indexed_db=True)
            context.close()
            browser.close()
            if self.control.stopped.is_set():
                return []
            Path(job.scan_dir).mkdir(parents=True, exist_ok=True)
            path = Path(job.scan_dir) / f"{filename_component(username)}_combined_links.txt"
            path.write_text("\n".join(links), encoding="utf-8")
            self.log(f"Indexing complete — {len(links)} results. Saved URLs to {path}")
        return read_links(path)

    def media(self, url, session):
        """Original HDMediaDownload: TikWM HD media after profile URL collection."""
        if urlsplit(url).hostname in ("vm.tiktok.com", "vt.tiktok.com") or "/t/" in urlsplit(url).path:
            with session.get(url, timeout=120) as response:
                response.raise_for_status()
                url = response.url
        username, kind, media_id = post_parts(url)
        job = self.job
        existing_video = Path(job.folder) / filename_component(username) / job.video_dir / f"{media_id}_HD.mp4"
        if kind == "video" and existing_video.exists():
            self.log(f"Already downloaded: {existing_video.name}")
            return True
        result = self.provider.resolve(url, username, kind, media_id, session)
        if result is None:
            return False
        username = result.username
        root = Path(job.folder) / filename_component(username)
        index_dir = Path(job.index_dir)
        index_dir.mkdir(parents=True, exist_ok=True)
        for asset in result.assets:
            if not self.control.checkpoint():
                return False
            if job.images_only and asset.category == "video":
                self.log(f"Skipped video {media_id} (images only)")
                continue
            destination = root / (job.image_dir if asset.category == "photo" else job.video_dir) / asset.name
            if destination.exists():
                self.log(f"Already downloaded: {destination.name}")
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.log(f"Downloading {destination.name}")
            partial = destination.with_suffix(destination.suffix + ".part")
            with session.get(asset.url, stream=True, timeout=120) as response:
                if response.status_code == 404:
                    self.log(f"Skipped unavailable media: {destination.name} (HTTP 404)")
                    continue
                response.raise_for_status()
                with partial.open("wb") as file:
                    pending_bytes = 0
                    last_update = monotonic()
                    while self.control.checkpoint():
                        chunk = response.raw.read(65536)
                        if not chunk:
                            break
                        file.write(chunk)
                        pending_bytes += len(chunk)
                        now = monotonic()
                        if now - last_update >= 0.25:
                            self.emit({"type": "transfer", "bytes": pending_bytes})
                            pending_bytes = 0
                            last_update = now
                    if pending_bytes:
                        self.emit({"type": "transfer", "bytes": pending_bytes})
            if self.control.stopped.is_set():
                return False
            partial.replace(destination)
            with (index_dir / f"{filename_component(username)}_index.txt").open("a", encoding="utf-8") as index:
                index.write(asset.index_id + "\n")
            self.log(f"Saved {destination}")
        return True

    def scan(self):
        job = self.job
        Path(job.folder).mkdir(parents=True, exist_ok=True)
        settings = asdict(job)
        settings["tikwm_api_key"] = "<configured>" if job.tikwm_api_key else "<not configured>"
        settings["tiktok_cookie"] = "<configured>" if job.tiktok_cookie else "<not configured>"
        self.log(f"Scan settings: {json.dumps(settings, sort_keys=True)}")
        links = self.collect_profile()
        if not self.control.stopped.is_set():
            self.emit({"type": "scanned", "links": links})
        self.emit({"type": "done", "stopped": self.control.stopped.is_set()})
        return links

    def run(self, links):
        Path(self.job.folder).mkdir(parents=True, exist_ok=True)
        settings = asdict(self.job)
        settings["tikwm_api_key"] = "<configured>" if self.job.tikwm_api_key else "<not configured>"
        settings["tiktok_cookie"] = "<configured>" if self.job.tiktok_cookie else "<not configured>"
        settings["link_count"] = len(links)
        self.log(f"Download settings: {json.dumps(settings, sort_keys=True)}")
        self.emit({"type": "progress", "current": 0, "total": len(links)})
        failed = False
        with requests.Session() as session, create_provider(self.job, self.emit, self.control) as provider:
            self.provider = provider
            session.headers.update({"User-Agent": "TikTokDownloader2/2.0", "Accept-Encoding": "identity"})
            for current, link in enumerate(links, 1):
                if not self.control.checkpoint():
                    break
                self.emit({"type": "downloading", "current": current, "total": len(links), "url": link})
                if not self.media(link, session):
                    failed = not self.control.stopped.is_set()
                    break
                self.emit({"type": "progress", "current": current, "total": len(links)})
        event = {"type": "done", "stopped": self.control.stopped.is_set()}
        if failed:
            event["failed"] = True
        self.emit(event)
