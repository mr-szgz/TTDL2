# Ported execution path

Source: `S:\Spaces\Media-Capture\TikTok\TikTok-Downloader\src\MainForm.cs`.

The final requested scope is **HD profile mass downloading only, no watermarks**.

| Original routine | Python implementation |
| --- | --- |
| MassDownloadByUsername / WaitForManualScrollStartAsync | Visible Playwright browser; indefinite wait for the dedicated Scan Profile button; scroll and extract URLs |
| DownloadFromCombinedLinksFile | Save the collected links and restore that file or use the collected URLs when Download Videos is clicked after closing the browser |
| HDMediaDownload | Same TikWM provider, numeric media ID, hd=1; hdplay for videos and images for photos |
| DownloadVideoWithBufferedWrite | 64 KiB streaming, pause/stop, pooled HTTP session across the batch, no transfer pacing; TikWM metadata calls limited to one per second |
| UI event handling | Native Qt widgets; QProcess keeps browser/network work outside the UI loop |
| Cancel / Reset | Terminate the worker and its browser process tree; clear session state and enable browser setup |

No page-hydration scraping or browser-per-post flow is used.
Standard downloads, single-link modes and watermark paths have been removed.
The user's fail-fast policy excludes the original catch/retry/fallback routines.
Stylesheets, custom palettes, custom fonts and theme settings have been removed.
