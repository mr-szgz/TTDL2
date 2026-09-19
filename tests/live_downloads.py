"""Verify the download stage with the profile URLs collected in the live GUI."""
from pathlib import Path
import json
from tiktok_downloader.core import Control, Downloader, Job, read_links
from tiktok_downloader.settings import CONFIG_DIR

folder = Path.home() / "Desktop" / "TikTokDownloads2"
links = read_links(CONFIG_DIR / "scans" / "sydneysweeneyfann_combined_links.txt")
job = Job(source="https://www.tiktok.com/@sydneysweeneyfann", folder=str(folder), download_logs=True)
downloader = Downloader(job, lambda event: print(json.dumps(event), flush=True), Control())
downloader.run(links)
