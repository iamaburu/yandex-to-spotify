# Changelog

## [0.2.0] — 2026-09-26
- Web interface: double-click `start-web.command` (macOS) / `start-web.bat` (Windows) / `./start-web.sh` (Linux). Connect Yandex and Spotify, export, search with progress, review matches in tabs with search, like with a preview, undo. Local only (127.0.0.1) and protected with a one-time access key; Spotify login works through the same Redirect URI.
- Doubtful and low-score matches can be accepted or rejected one by one in the browser.

## [0.1.0] — 2026-09-23
First public release.
- Step-by-step wizard: double-click `start.command` (macOS) / `start.bat` (Windows) / `./start.sh` (Linux).
- Guided setup of the Yandex token and the Spotify app, with instant validation.
- Matching with Cyrillic/Latin transliteration and duration check.
- Interactive review of doubtful matches.
- Likes keep the original Yandex order. Re-runs skip already liked tracks.
- `undo` removes everything the program added.
