<img src="assets/purple/ttdl2-text-purple.png" alt="TTDL 2" width="480" style="max-width: 100%; height: auto;">

# TTDL 2

TikTok Downloader 2 is a Python / Qt app for **HD mass download by TikTok profile, without watermarks**.

## Run

On Windows x64, run `TTDL2-<version>-windows-x64-Setup.exe`, then open **TTDL 2**
from the Start menu. Setup installs for the current user, creates a private Python
environment, and downloads dependencies and Chromium. Internet access is required
during setup. It also offers an optional desktop shortcut.

For a source checkout, double-click `launch.cmd` after setting up this directory:

```powershell
uv sync --extra test
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m tiktok_downloader
```

## Flow

1. Enter a username or profile URL and select the download folder.
2. Click **Create Session**. A visible Playwright Chromium window opens.
3. Set up the session yourself: log in, solve CAPTCHA, and display the profile.
4. Return to the app and click **Scan Profile**. The Chromium browser minimizes
   and indexing runs in the background. There is no automatic start.
5. The app scrolls, collects video/photo URLs, saves the combined-links file, closes
   the browser, and automatically starts downloading by default.
6. **Automatically download videos**, below the buttons, keeps **Download Videos**
   disabled while checked. Uncheck it to enable manual downloads after scanning.
   Downloads use the original app's TikWM HD routine. Status shows (x/y), bytes downloaded, average MB/s (1 MB = 1,000,000 bytes), and a post-based batch ETA. Transfer statistics exclude paused time.

To work through a saved list, put one profile URL per line in a text file. **Profile
List** defaults to `ttdl2.txt` inside **Downloads Folder** and updates when that folder
changes. You can enter a different file path. Click **Load Profile List** to select
the first URL, then use **Next Profile** and **Prev Profile** to move through the
list. Navigation stops at either end; loading the file again starts at the first URL.

Each finished scan saves `<username>_combined_links.txt` in the selected **Downloads
Folder**. To resume from that file later, enter the same profile, select that folder,
and click **Restore Scan**, uncheck **Automatically download videos**, then click
**Download Videos**. Restoring does not open a browser.

The app uses native Qt widgets, fonts, colors and appearance. There are no custom
stylesheets or themes. There are no single-download, standard-quality or watermark modes.

**Cancel / Reset**, beside **Scan Profile**, cancels browser setup, scanning, or
downloading immediately by terminating the worker and its browser process tree.
It clears the session, scan results, progress, and log, and enables **Create Session**
again. Profile and folder inputs, saved scans, and downloaded files are preserved.
Closing the app also cancels its active operation and closes its browser.

Pause and Stop work between streamed 64 KiB chunks. An active network read can wait
up to its 120-second timeout; **Cancel / Reset** interrupts that wait.
Partial downloads use `.part` and become final files only on completion.

Files use `username/video/id_HD.mp4` and `username/photo/id_1.jpg`.
Existing final videos skip the metadata request as well as the transfer.
The provider's `hdplay` URL is used; `wmplay` is never used.
Requests identify this app with `User-Agent: TikTokDownloader2/2.0`.
Downloads reuse HTTP connections across the batch and have no fixed per-file delay.
TikWM limits metadata requests to one per second. Only metadata calls are paced;
time spent transferring files counts toward that interval. Carousel photos download
consecutively without a pacing delay.
The 10-second browser scrolling interval applies only to profile scanning.

Settings use platformdirs' per-user config directory: `%LOCALAPPDATA%\TikTokDownloader2`
on Windows. Preferences are saved in `config.json`, and profile, destination, and
window geometry are saved in `state.json`.
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

Original application © 2024 Jettcodey; MIT notice retained in `LICENSE`.
The C# source remains untouched.

## Build a release

On Windows x64, install PowerShell 7.4+, uv, and Inno Setup 6, then run `build.cmd` or:

```powershell
pwsh -NoProfile -File scripts/build.ps1
```

The script installs locked dependencies and Chromium, runs the tests, builds the
wheel and source archive, and tests the installed wheel in a separate environment
outside the source checkout. It also builds a Windows setup installer.
Artifacts and `SHA256SUMS.txt` are written to `dist/<version>/`.
The installer downloads its runtime; the Python packages require Python 3.12+.

To build just the setup installer, run `build-setup.cmd` or:

```powershell
pwsh -NoProfile -File scripts/build-setup.ps1
```

The setup build follows the YOLO Media Organizer and Spectra installer pattern.
It packages the app source, icon, lockfile, and uv 0.11.11. During setup, uv installs
Python 3.12.10 and the locked dependencies into a private environment under the
installation directory, then Playwright downloads Chromium into its per-user cache.
The purple ICO is used for the app, installer, shortcuts, and uninstall entry.
Uninstall removes the private runtime while preserving user settings and downloads.
Inno Setup defaults to `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`; pass
`-IsccPath "C:\path\to\ISCC.exe"` to `build-setup.cmd` for another installation.

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
annotated version tag, and publish the installer, wheel, source archive, and checksum file
with `gh release create --verify-tag --notes-file` using the changelog entry.
