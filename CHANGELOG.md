# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Add an **Auto continue to next to scan** option that advances through profiles without saved scans, waiting for automatic downloads when enabled and stopping with the active operation.

## [3.4.4] - 2026-09-19

### Added

- Add an in-app profile-list manager for adding, selecting, removing, sorting, and deduplicating profiles before saving the list.

### Changed

- Replace the main-window **Sort file** action with **Manage List** and reload the profile controls after saving changes.

## [3.4.3] - 2026-09-19

### Fixed

- Skip unavailable media that returns HTTP 404 and continue downloading the rest of the batch.

## [3.4.2] - 2026-09-19

### Added

- Add configurable video and image download folder names under **Scanning & Downloads**, defaulting to `video` and `photo`.
- Show the API JSON output folder template beside the API save controls.

### Changed

- Save API JSON responses under each profile's `<username>/Data/json` folder.
- Place the saved state path directly below the user configuration path controls.

## [3.4.1] - 2026-09-19

### Changed

- Move the user configuration path to the top of Settings, group the browser controls and session file under **Browser**, and combine saved scans with download logging under **Scanning & Downloads**.
- Move **Remember settings** from Settings to the bottom-left of the Downloader tab.

## [3.4.0] - 2026-09-19

### Added

- Add a **Next to Scan** button that advances to the next profile without saved scan results.
- Add controls to refresh saved scans and sync their usernames to the profile list.

### Changed

- Automatically save and reuse the browser session during profile setup and scanning; replace the manual session controls with **New Session** and **Clear Session**.
- Reorganize the **Downloader** tab into **Profiles List**, **Scan Profiles**, and **Downloads** sections, move **Scan delay** alongside the scan controls, and rename the profile-folder action to **Open profile downloads**.
- Keep **Remember settings** and the download logging options in the main Settings list while leaving **Save Settings** and **Restore Defaults** in the footer.
- Store per-profile download index files in the app data directory instead of profile download folders.

### Fixed

- Start normally when the default profile-list file has not been created yet.
- Allow an active profile scan to stop promptly while waiting between page scrolls.

## [3.3.0] - 2026-09-19

### Fixed

- Create the installer's private Python environment and install Chromium using Windows' built-in command processor, removing the unbundled PowerShell 7 requirement.
- Include the PNG icon required to build the installed application package.

## [3.2.1] - 2026-09-19

### Changed

- Package the settings persistence and profile-list improvements for the Windows release.

## [3.2.0] - 2026-09-19

### Added

- Automatically save settings before quitting, controlled by a default-checked **Remember settings** checkbox. The choice persists across launches; **Save Settings** remains available for explicit saves.
- Profile list opening, username filtering, natural sorting, and Next/Prev navigation controls.
- Indexing metrics showing new posts, scan time, delay, and total time.

### Changed

- Separate **Stop** from **Reset session** so stopping preserves progress and logs until explicitly reset.
- Simplify the downloads folder label and remove the Check Session workflow.

## [3.1.0] - 2026-09-19

### Added

- Save and restore browser sessions, including cookies, local storage, and IndexedDB.
- Download, check, and reinstall the selected browser from Settings.
- Saved scans path and an Open saved scans folder button in Settings.

### Changed

- Moved settings into a dedicated tab.
- Store profile scans in the app's user configuration directory, independently of the downloads folder. Move existing `*_combined_links.txt` files into its `scans` subfolder to restore them.
- Consolidated Windows release builds into `scripts/build.ps1` and switched installer runtime setup to PowerShell 7.4 or later.

## [3.0.0] - 2026-09-19

### Added

- Windows setup installer with a private Python runtime, dependencies, and Chromium.
- Profile lists loaded from text files, with Next and Prev controls that stop at either end.
- Persistent configuration and saved window state.

### Changed

- Downloads start automatically after scanning by default; manual downloads remain available.
- Download progress reports transferred bytes, average speed, and a post-based ETA.
- Renamed session and folder controls and simplified the settings layout.
- Simplified the README with direct installer and releases links and `uv run ttdl2` for local runs.

### Fixed

- Removed the 1.9-second wait before every video and photo; reuse HTTP connections across each download batch and stream in 64 KiB chunks.
- Pace only TikWM metadata calls to respect its one-request-per-second limit, counting file-transfer time toward the interval.
- Added **Cancel / Reset** beside **Scan Profile** to interrupt browser setup, indexing, and downloads, close the browser process tree, and clear the session for another setup.
- Closing the app now cancels the active operation and its browser instead of waiting for page or network timeouts.

## [2.1.0] - 2026-09-18

### Added

- Separate **Download Videos** button to download collected URLs after a profile scan.
- **Restore Scan** button to load the profile's saved combined-links TXT from the selected folder without opening a browser.
- Indexing page numbers and running result totals in status messages.
- Download counts, average items/sec, and ETA, excluding paused time.
- Windows build scripts producing a Python wheel, source archive, and SHA-256 checksums, with source and installed-wheel tests.

### Changed

- Renamed **Start indexing** to **Scan Profile**. Scanning saves the profile TXT and closes the browser; downloads now require a separate click.
- Minimize the browser while scanning after the user finishes login or CAPTCHA setup.
- Use `ttdl2` as the Python package distribution and launcher name.

[Unreleased]: https://github.com/mr-szgz/ttdl2/compare/v3.4.4...HEAD
[3.4.4]: https://github.com/mr-szgz/ttdl2/compare/v3.4.3...v3.4.4
[3.4.3]: https://github.com/mr-szgz/ttdl2/compare/v3.4.2...v3.4.3
[3.4.2]: https://github.com/mr-szgz/ttdl2/compare/v3.4.1...v3.4.2
[3.4.1]: https://github.com/mr-szgz/ttdl2/compare/v3.4.0...v3.4.1
[3.4.0]: https://github.com/mr-szgz/ttdl2/compare/v3.3.0...v3.4.0
[3.3.0]: https://github.com/mr-szgz/ttdl2/releases/tag/v3.3.0
[3.2.0]: https://github.com/mr-szgz/ttdl2/releases/tag/v3.2.0
[3.1.0]: https://github.com/mr-szgz/ttdl2/releases/tag/v3.1.0
[3.0.0]: https://github.com/mr-szgz/ttdl2/releases/tag/v3.0.0
[2.1.0]: https://github.com/mr-szgz/ttdl2/releases/tag/v2.1.0

[3.2.1]: https://github.com/mr-szgz/ttdl2/releases/tag/v3.2.1
