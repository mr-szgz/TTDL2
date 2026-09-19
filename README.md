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
4. Return to the app and click **Scan Profile**. The Chromium browser minimizes
   and indexing runs in the background. There is no automatic start.
5. The app scrolls, collects video/photo URLs, saves the combined-links file, closes
   the browser, and enables **Download Videos**. Scanning does not download media.
6. Click **Download Videos** to download the scanned URLs through the original
   app's TikWM HD routine. Status shows (x/y), items/sec, and ETA.

Each finished scan saves `<username>_combined_links.txt` in the selected **Save to**
folder. To resume from that file later, enter the same profile, select that folder,
and click **Restore Scan**, then **Download Videos**. Restoring does not open a browser.

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
real subprocesses, and streamed download payloads. They verify the manual Scan
Profile gate, HD-only requests, byte integrity, duplicate skipping, cancellation,
settings, and native Qt styling. Failures propagate without retries or alternate providers.

Live verification on 2026-09-18 opened the requested profile
`https://www.tiktok.com/@sydneysweeneyfann`, collected 106 links after manual Start,
and saved HD video `7567041710119800086_HD.mp4` (752,298 bytes) through the download routine.
This verifies a real download, not every post's continuing availability.

Original application © 2024 Jettcodey; MIT notice retained in `LICENSE.txt`.
The C# source remains untouched.

## Build a release

On Windows, install PowerShell 7.4+ and uv, then run `build.cmd` or:

```powershell
pwsh -NoProfile -File scripts/build.ps1
```

The script installs locked dependencies and Chromium, runs the tests, builds the
wheel and source archive, and tests the installed wheel in a separate environment
outside the source checkout. Artifacts and `SHA256SUMS.txt` are written to
`dist/<version>/`. These are Python packages; Python 3.12+ is required.

To install a downloaded wheel into a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install .\ttdl2-2.1.0-py3-none-any.whl
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\ttdl2.exe
```

See [CHANGELOG.md](CHANGELOG.md) for release changes. Before a release, update the
version in `pyproject.toml` and `tiktok_downloader/__init__.py`, run `uv lock`, and
add a dated changelog entry. Run the build script, commit the release, push its
annotated version tag, and publish the wheel, source archive, and checksum file
with `gh release create --verify-tag --notes-file` using the changelog entry.
