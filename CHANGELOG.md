# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/mr-szgz/ttdl2/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/mr-szgz/ttdl2/releases/tag/v2.1.0
