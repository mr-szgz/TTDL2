# TikTok Downloader 2
# TikTok Downloader 2

Python / Qt edition, scoped to **HD mass download by TikTok profile, without watermarks**.

## Run

Double-click `launch.cmd`. Setup from this directory:

```powershell
uv sync --extra test
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m tiktok_downloader
```

## Flow

1. Enter a username or profile URL and select the download folder.
2. Click **Open browser**. A visible Playwright Chromium window opens.
3. Set up the session yourself: log in, solve CAPTCHA, and display the profile.
4. Return to the app and click **Start indexing**. The Chromium browser minimizes
   and indexing runs in the background. There is no automatic start.
5. The app scrolls, collects video/photo URLs, saves the combined-links file, closes
   the browser, then downloads through the original app's TikWM HD routine.

The app uses native Qt widgets, fonts, colors and appearance. There are no custom
stylesheets or themes. There are no single-download, standard-quality or watermark modes.

Pause and Stop work between streamed 8 KiB chunks. An active network read can wait
up to its 120-second timeout. Stopping before indexing preserves any previously
saved links file. Partial downloads use `.part` and become final files only on completion.

Files use `username/Videos/id_HD.mp4` and `username/Images/id_1.jpg`.
Existing final videos skip the metadata request as well as the transfer.
The provider's `hdplay` URL is used; `wmplay` is never used.
Requests identify this app with `User-Agent: TikTokDownloader2/2.0`.
The original 1.9-second delay before media transfers is retained.

Settings are stored separately under Qt's per-user AppConfigLocation.
Chromium is the default; settings also allow an explicit installed browser.
Firefox needs `python -m playwright install firefox` in this environment.

## Verify

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Tests use a local HTTP server, real Chromium (including a visible-browser Qt test),
real subprocesses, and streamed download payloads. They verify the manual Start
indexing gate, HD-only requests, byte integrity, duplicate skipping, cancellation,
settings, and native Qt styling. Failures propagate without retries or alternate providers.

Live verification on 2026-09-18 opened the requested profile
`https://www.tiktok.com/@sydneysweeneyfann`, collected 106 links after manual Start,
and saved HD video `7567041710119800086_HD.mp4` (752,298 bytes) through the download routine.
This verifies a real download, not every post's continuing availability.

Original application © 2024 Jettcodey; MIT notice retained in `LICENSE.txt`.
The C# source remains untouched.
Second edition of Jettcodey's TikTok Downloader, rewritten in Python with PySide6
(Qt Widgets) and Playwright. The original C# project is unchanged.

## Setup and launch

From this directory in PowerShell, with Python 3.12+ and uv installed:

```powershell
uv sync --extra test
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m tiktok_downloader
```

After setup, double-click `launch.cmd`, or run the installed
`.venv\Scripts\tiktok-downloader2.exe` entry point.

## Use

1. Select single post, text file, or profile mode, in standard or HD quality.
2. Enter a post URL, a text file containing one URL per line, or a username/profile URL.
3. Choose a destination. Click Open browser for profiles, or Download for single
   posts and text files.
4. For profiles, the browser opens and the app waits indefinitely. Log in, solve
   CAPTCHA, and set up the profile page in the browser. Return to the app and click
   **Start indexing**. Only then does Playwright scroll and collect video/photo URLs.
   The browser closes after collection, and the saved URLs are downloaded.

Standard downloads offer watermarked video and optional additional avatars. HD mode uses
the original app's TikWM provider; standard mode uses its TikTok feed endpoint.
Short `vm.tiktok.com`, `vt.tiktok.com`, and `/t/` links follow HTTP redirects.
No provider switching, retry, or substitution is performed.

Files are stored under `username/Videos`, `Images`, and `Avatars`. The port retains
the original names: `id_Save.mp4`, `id_Watermark.mp4`, `id_HD.mp4`, zero-based
`id_0.jpeg` standard photos, and one-based `id_1.jpg` HD photos. Existing final files are skipped;
new downloads write a `.part` file and rename it only after writing all bytes.
`username_index.txt` records completed assets. Profile links are exported to
`username_combined_links.txt`. UTF-8 text files support a BOM and blank lines;
duplicate input links skip files that have already been saved.

Pause and Stop are checked between streamed 8 KiB chunks and between posts. An in-flight request
can take up to the configured 120-second timeout. Closing while busy requests Stop;
close the window again after the worker exits. Browser contexts are temporary.

File → Settings controls images-only downloads, JSON/download logs, browser,
completion taskbar alerts, and system/light/dark themes. Chrome and Edge use installed
browser channels; System Default reads the Windows HTTP browser association as in
the original. Firefox requires `python -m playwright install firefox` using this
environment. A custom Chromium executable can be selected for Brave. System mode
uses native Qt/Windows colors and controls. Import/export uses the new JSON schema.
Configuration lives in Qt's per-user AppConfigLocation, under the separate
TikTokDownloader2 application identity. Defaults use Desktop/TikTokDownloads2.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Tests exercise all six modes with a local HTTP fixture server, actual streamed
HTTP downloads, actual Chromium scrolling of dynamically added posts, byte-for-byte
saved fixture payloads, redirects, duplicate skipping, avatars, watermark/HD
separation, images-only, pause/stop, settings and themes. pytest-qt also runs the
real subprocess download workflow, manual browser confirmation, and uncaught
provider failures through the UI. Fixture media verifies transport and persistence;
it is not a video-decoder test.

These are deterministic integration tests, **not proof that TikTok or TikWM currently
serves a given live post**. Live access depends on their availability, response schema,
region, authentication and CAPTCHA. Unavailable endpoints or changed responses
terminate the job and display the original traceback and process exit code.
The inherited standard endpoint and HD provider have no automatic replacement.

## Edition scope

The rewrite preserves the download workflows, folder selection, profile link export,
pause/stop, duplicate skipping, browser selection and configurable logs. Profile
mode opens Playwright, waits for manual login/CAPTCHA and Start indexing, scrolls, saves
URLs, closes the browser, and passes the saved list to the original standard/HD
download paths. Single-post and text-file modes directly use those download paths.
No page-hydration scraping or browser-per-post download flow is used.

Settings are independent of the first edition's XML. The old C# executable updater,
desktop shortcut creation, installer, memory-cache timer, and
unfinished sign-in dialog are not carried over. Sign-in/CAPTCHA interaction happens
in the real browser during profile collection. The new app does not call the old
update server or modify the first edition's installation.

## Project layout

- `tiktok_downloader/core.py`: original browser collection and subsequent HTTP download paths.
- `tiktok_downloader/worker.py`: isolated download process with stdin controls and JSON events.
- `tiktok_downloader/app.py`: Qt main window and settings dialog.
- `tiktok_downloader/settings.py`: independent configuration and import/export.
- `tiktok_downloader/theme.py`: semantic Fluent aliases, QPalette and one application QSS.
- `tests/`: local HTTP/browser and Qt integration tests.

The native title bar preserves Windows move, resize and snap behavior. Light/dark
colors come from the bundled Qt alias snapshot for Microsoft Fluent UI
`@fluentui/react-theme` 9.2.1 (snapshot provenance is inside the JSON resource).
Layout spacing and type sizes are Qt-specific choices.

Implementation references: [Playwright request contexts](https://playwright.dev/python/docs/api/class-apirequestcontext),
[Playwright browser contexts](https://playwright.dev/python/docs/api/class-browsercontext),
and [Qt QProcess](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QProcess.html).

Original application © 2024 Jettcodey. Original MIT notice retained in `LICENSE.txt`.
