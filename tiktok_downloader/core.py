"""Port of MainForm.cs workflows. Browser collection precedes HTTP downloads."""
from dataclasses import dataclass
import json
from pathlib import Path
import re
import threading
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen
from playwright.sync_api import sync_playwright

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
    transfer_delay_ms: int = 1900
    site: str = "https://www.tiktok.com"
    hd_api: str = "https://www.tikwm.com/api/"

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
    return re.fullmatch(r"/@([^/]+)/(video|photo)/(\d+)/?", urlsplit(url).path).groups()

def filename_component(value):
    return "".join(c if c.isascii() and (c.isalnum() or c in "_-")
                   else f"%{ord(c):X}" for c in str(value))

def profile_name(source):
    return (urlsplit(source).path if "://" in source else source).strip("/@")

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
            context = browser.new_context()
            page = context.new_page()
            page.goto(f"{job.site}/@{quote(username)}", wait_until="domcontentloaded", timeout=120000)
            if job.manual_start:
                self.control.pause()
                self.emit({"type": "manual", "message": "Set up the browser session: log in, solve CAPTCHA, and open the profile. Click Start indexing in the app when ready."})
            if self.control.checkpoint() and not job.headless:
                session = context.new_cdp_session(page)
                window_id = session.send("Browser.getWindowForTarget")["windowId"]
                session.send("Browser.setWindowBounds", {
                    "windowId": window_id, "bounds": {"windowState": "minimized"},
                })
                session.detach()
                self.log("Browser minimized. Indexing in the background — 0 total results indexed.")
            indexed = {"video": [], "photo": []}
            page_number = 1
            last_page = False
            while self.control.checkpoint():
                for kind in ("video", "photo"):
                    for link in page.locator(f'a[href*="/{kind}/"]').evaluate_all("nodes => nodes.map(n => n.href)"):
                        parsed = urlsplit(link)
                        if re.fullmatch(rf"/@{re.escape(username)}/{kind}/\d+/?", parsed.path):
                            canonical = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                            if canonical not in indexed[kind]:
                                indexed[kind].append(canonical)
                total = len(indexed["video"]) + len(indexed["photo"])
                self.emit({"type": "indexing", "page": page_number, "total": total})
                if last_page:
                    break
                height = page.evaluate("document.body.scrollHeight")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(job.scroll_ms)
                last_page = height == page.evaluate("document.body.scrollHeight")
                page_number += 1
            links = indexed["video"] + indexed["photo"]
            context.close()
            browser.close()
            if self.control.stopped.is_set():
                return []
            path = Path(job.folder) / f"{filename_component(username)}_combined_links.txt"
            path.write_text("\n".join(links), encoding="utf-8")
            self.log(f"Indexing complete — {len(links)} total results. Saved URLs to {path}")
        return read_links(path)

    def media(self, url):
        """Original HDMediaDownload: TikWM HD media after profile URL collection."""
        if urlsplit(url).hostname in ("vm.tiktok.com", "vt.tiktok.com") or "/t/" in urlsplit(url).path:
            with urlopen(url, timeout=120) as response:
                url = response.url
        username, kind, media_id = post_parts(url)
        job = self.job
        existing_video = Path(job.folder) / filename_component(username) / "Videos" / f"{media_id}_HD.mp4"
        if kind == "video" and existing_video.exists():
            self.log(f"Already downloaded: {existing_video.name}")
            return True
        request = Request(job.hd_api + "?" + urlencode({"url": media_id, "hd": "1"}),
                          headers={"User-Agent": "TikTokDownloader2/2.0"})
        with urlopen(request, timeout=120) as response:
            raw = json.load(response)
        data = raw["data"]
        username = data["author"]["unique_id"]
        if kind == "photo":
            assets = [("Images", f"{media_id}_{i}.jpg", image, f"{media_id}_{i}.jpg")
                      for i, image in enumerate(data["images"], 1)]
        else:
            assets = [("Videos", f"{media_id}_HD.mp4", data["hdplay"], f"{media_id}_HD")]
        root = Path(job.folder) / filename_component(username)
        root.mkdir(parents=True, exist_ok=True)
        if job.json_logs:
            (root / f"{media_id}_HD.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
        for category, name, asset_url, index_id in assets:
            if not self.control.checkpoint():
                return False
            if job.images_only and category == "Videos":
                self.log(f"Skipped video {media_id} (images only)")
                continue
            destination = root / category / name
            if destination.exists():
                self.log(f"Already downloaded: {destination.name}")
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.log(f"Downloading {destination.name}")
            partial = destination.with_suffix(destination.suffix + ".part")
            if self.control.stopped.wait(job.transfer_delay_ms / 1000):
                return False
            request = Request(asset_url, headers={"User-Agent": "TikTokDownloader2/2.0"})
            with urlopen(request, timeout=120) as response, partial.open("wb") as file:
                while self.control.checkpoint():
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    file.write(chunk)
            if self.control.stopped.is_set():
                return False
            partial.replace(destination)
            with (root / f"{filename_component(username)}_index.txt").open("a", encoding="utf-8") as index:
                index.write(index_id + "\n")
            self.log(f"Saved {destination}")
        return True

    def run(self):
        job = self.job
        Path(job.folder).mkdir(parents=True, exist_ok=True)
        links = self.collect_profile()
        self.emit({"type": "progress", "current": 0, "total": len(links)})
        for current, link in enumerate(links, 1):
            if not self.control.checkpoint():
                break
            self.emit({"type": "downloading", "current": current, "total": len(links)})
            if not self.media(link):
                break
            self.emit({"type": "progress", "current": current, "total": len(links)})
        self.emit({"type": "done", "stopped": self.control.stopped.is_set()})
