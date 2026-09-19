"""Port of MainForm.cs workflows. Browser collection precedes HTTP downloads."""
from dataclasses import dataclass
import json
from pathlib import Path
import re
import threading
from time import monotonic
from urllib.parse import quote, unquote, urlsplit
import requests
from playwright.sync_api import sync_playwright
from .settings import CONFIG_DIR

@dataclass
class Job:
    source: str
    folder: str
    images_only: bool = False
    json_logs: bool = False
    download_logs: bool = False
    browser: str = "chromium"
    executable: str = ""
    headless: bool = False
    manual_start: bool = True
    scroll_ms: int = 10000
    site: str = "https://www.tiktok.com"
    hd_api: str = "https://www.tikwm.com/api/"
    session_path: str = ""
    restore_session: bool = False
    check_session: bool = False
    scan_dir: str = str(CONFIG_DIR / "scans")

class Control:
    def __init__(self):
        self.ready = threading.Event()
        self.ready.set()
        self.stopped = threading.Event()
        self.save_session = threading.Event()

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
        self.metadata_ready_at = 0.0

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
            restore = Path(job.session_path).is_file() if job.check_session else job.restore_session
            context = browser.new_context(storage_state=job.session_path if restore else None)
            page = context.new_page()
            page.goto(f"{job.site}/@{quote(username)}", wait_until="domcontentloaded", timeout=120000)
            if job.check_session:
                page.wait_for_load_state("load", timeout=120000)
                page.wait_for_timeout(3000)
                challenge = any(locator.is_visible() for frame in page.frames
                                for locator in frame.get_by_text("Drag the slider to fit the puzzle", exact=True).all())
                self.control.pause()
                if not challenge:
                    context.storage_state(path=job.session_path, indexed_db=True)
                self.emit({"type": "session_checked", "challenge": challenge})
            if job.manual_start or job.check_session:
                if not job.check_session:
                    self.control.pause()
                    self.emit({"type": "manual", "message": "Set up the browser session: log in, solve CAPTCHA, and open the profile. Click Scan Profile in the app when ready."})
                while not self.control.ready.is_set() and not self.control.stopped.is_set():
                    if self.control.save_session.is_set():
                        self.control.save_session.clear()
                        context.storage_state(path=job.session_path, indexed_db=True)
                        self.emit({"type": "session_saved", "path": job.session_path})
                    page.wait_for_timeout(100)
            if self.control.checkpoint() and not job.headless:
                session = context.new_cdp_session(page)
                window_id = session.send("Browser.getWindowForTarget")["windowId"]
                session.send("Browser.setWindowBounds", {
                    "windowId": window_id, "bounds": {"windowState": "minimized"},
                })
                session.detach()
                self.log("Browser minimized. Indexing in the background — 0 total results indexed.")
            indexed = {"video": [], "photo": []}
            total = 0
            last_page = False
            delay_ms = 0.0
            scroll_elapsed_ms = 0.0
            while self.control.checkpoint():
                scan_started = monotonic()
                previous_total = total
                for kind in ("video", "photo"):
                    for link in page.locator(f'a[href*="/{kind}/"]').evaluate_all("nodes => nodes.map(n => n.href)"):
                        parsed = urlsplit(link)
                        if re.fullmatch(rf"/@{re.escape(username)}/{kind}/\d+/?", unquote(parsed.path)):
                            canonical = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                            if canonical not in indexed[kind]:
                                indexed[kind].append(canonical)
                total = len(indexed["video"]) + len(indexed["photo"])
                scan_ms = (monotonic() - scan_started) * 1000
                self.emit({"type": "indexing", "total": total, "added": total - previous_total,
                           "scan_ms": scan_ms, "delay_ms": delay_ms,
                           "round_ms": scroll_elapsed_ms + scan_ms})
                if last_page:
                    break
                scroll_started = monotonic()
                height = page.evaluate("document.body.scrollHeight")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                delay_started = monotonic()
                page.wait_for_timeout(job.scroll_ms)
                delay_ms = (monotonic() - delay_started) * 1000
                last_page = height == page.evaluate("document.body.scrollHeight")
                scroll_elapsed_ms = (monotonic() - scroll_started) * 1000
            links = indexed["video"] + indexed["photo"]
            context.close()
            browser.close()
            if self.control.stopped.is_set():
                return []
            Path(job.scan_dir).mkdir(parents=True, exist_ok=True)
            path = Path(job.scan_dir) / f"{filename_component(username)}_combined_links.txt"
            path.write_text("\n".join(links), encoding="utf-8")
            self.log(f"Indexing complete — {len(links)} total results. Saved URLs to {path}")
        return read_links(path)

    def media(self, url, session):
        """Original HDMediaDownload: TikWM HD media after profile URL collection."""
        if urlsplit(url).hostname in ("vm.tiktok.com", "vt.tiktok.com") or "/t/" in urlsplit(url).path:
            with session.get(url, timeout=120) as response:
                response.raise_for_status()
                url = response.url
        username, kind, media_id = post_parts(url)
        job = self.job
        existing_video = Path(job.folder) / filename_component(username) / "video" / f"{media_id}_HD.mp4"
        if kind == "video" and existing_video.exists():
            self.log(f"Already downloaded: {existing_video.name}")
            return True
        # TikWM's free API permits one metadata request per second. Media transfers
        # use that interval too; there is no delay between files in a photo set.
        if self.control.stopped.wait(max(0, self.metadata_ready_at - monotonic())):
            return False
        if not self.control.checkpoint():
            return False
        with session.get(job.hd_api, params={"url": media_id, "hd": "1"}, timeout=120) as response:
            response.raise_for_status()
            raw = response.json()
        self.metadata_ready_at = monotonic() + 1.0
        data = raw["data"]
        username = data["author"]["unique_id"]
        if kind == "photo":
            assets = [("photo", f"{media_id}_{i}.jpg", image, f"{media_id}_{i}.jpg")
                      for i, image in enumerate(data["images"], 1)]
        else:
            assets = [("video", f"{media_id}_HD.mp4", data["hdplay"], f"{media_id}_HD")]
        root = Path(job.folder) / filename_component(username)
        root.mkdir(parents=True, exist_ok=True)
        if job.json_logs:
            (root / f"{media_id}_HD.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
        for category, name, asset_url, index_id in assets:
            if not self.control.checkpoint():
                return False
            if job.images_only and category == "video":
                self.log(f"Skipped video {media_id} (images only)")
                continue
            destination = root / category / name
            if destination.exists():
                self.log(f"Already downloaded: {destination.name}")
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.log(f"Downloading {destination.name}")
            partial = destination.with_suffix(destination.suffix + ".part")
            with session.get(asset_url, stream=True, timeout=120) as response, partial.open("wb") as file:
                response.raise_for_status()
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
            with (root / f"{filename_component(username)}_index.txt").open("a", encoding="utf-8") as index:
                index.write(index_id + "\n")
            self.log(f"Saved {destination}")
        return True

    def scan(self):
        job = self.job
        Path(job.folder).mkdir(parents=True, exist_ok=True)
        links = self.collect_profile()
        if not self.control.stopped.is_set():
            self.emit({"type": "scanned", "links": links})
        self.emit({"type": "done", "stopped": self.control.stopped.is_set()})
        return links

    def run(self, links):
        self.emit({"type": "progress", "current": 0, "total": len(links)})
        with requests.Session() as session:
            session.headers.update({"User-Agent": "TikTokDownloader2/2.0", "Accept-Encoding": "identity"})
            for current, link in enumerate(links, 1):
                if not self.control.checkpoint():
                    break
                self.emit({"type": "downloading", "current": current, "total": len(links)})
                if not self.media(link, session):
                    break
                self.emit({"type": "progress", "current": current, "total": len(links)})
        self.emit({"type": "done", "stopped": self.control.stopped.is_set()})
