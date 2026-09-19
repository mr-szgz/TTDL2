# Source-to-port map
# Ported execution path

Source: `S:\Spaces\Media-Capture\TikTok\TikTok-Downloader\src\MainForm.cs`.

The final requested scope is **HD profile mass downloading only, no watermarks**.

| Original routine | Python implementation |
| --- | --- |
| MassDownloadByUsername / WaitForManualScrollStartAsync | Visible Playwright browser; indefinite wait for the dedicated Start indexing button; scroll and extract URLs |
| DownloadFromCombinedLinksFile | Save the collected links and consume that file after closing the browser |
| HDMediaDownload | Same TikWM provider, numeric media ID, hd=1; hdplay for videos and images for photos |
| DownloadVideoWithBufferedWrite | 8192-byte streaming, pause/stop, 1.9-second transfer pacing |
| UI event handling | Native Qt widgets; QProcess keeps browser/network work outside the UI loop |

No page-hydration scraping or browser-per-post flow is used.
Standard downloads, single-link modes and watermark paths have been removed.
The user's fail-fast policy excludes the original catch/retry/fallback routines.
Stylesheets, custom palettes, custom fonts and theme settings have been removed.
Source: `S:\Spaces\Media-Capture\TikTok\TikTok-Downloader\src\MainForm.cs`.

| C# workflow | Python implementation |
| --- | --- |
| `MassDownloadByUsername` + `WaitForManualScrollStartAsync` | `Downloader.collect_profile`: visible Playwright browser, wait indefinitely for the dedicated Start indexing button, scroll until height stops changing, video URLs then photo URLs, username filtering, combined-links file, close browser |
| `DownloadFromCombinedLinksFile` | `read_links` consumes the exported file, then `Downloader.run` processes its URLs |
| `DownloadFromTextFile` / `HDDownloadFromTextFile` | `read_links` and the standard/HD branch of `Downloader.media` |
| `SingleMediaDownload` / `HDSingleMediaDownload` | Direct call to the appropriate download branch; no browser launch |
| `GetRedirectUrl` / `GetMediaID` | HTTP redirect resolution for short links, username/type/ID parsed from the resolved post URL |
| `GetMedia` | Same TikTok feed endpoint, OPTIONS request, device parameters, matching aweme ID, play/download address and image URLs |
| `HDMediaDownload` | Same TikWM endpoint with numeric media ID and `hd=1`; `hdplay` for videos, `images` for photos |
| `DownloadMedia` | Standard `_Save`/`_Watermark` videos, zero-based JPEG photos, per-user index |
| `DownloadAvatars` | Additional author JPEG/GIF avatar files after media, retaining the original naming pattern |
| `DownloadVideoWithBufferedWrite` | Streamed 8192-byte chunks; pause/stop checkpoints |
| `BrowserUtility` | Windows default browser association, selected browser channel, explicit executable, Playwright Firefox |
| Pause/Stop and UI updates | QProcess worker with stdin controls and Qt signals; work stays outside the UI event loop |

The user-required fail-fast policy replaces the C# catch/retry/fallback paths:
exceptions are not caught, retried, substituted or turned into successful completion.
The Qt process log displays the worker's original stderr and exit code.

Language/runtime changes: settings use independent JSON rather than XML; partial
files are renamed only after download completion; responsive Qt layouts replace
fixed WinForms geometry. The original C# source and installation are untouched.
