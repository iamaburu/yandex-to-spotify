# yandex-to-spotify

[Русская версия](README.ru.md)

**Move your Yandex Music likes to Spotify Liked Songs in about 15 minutes.** Double-click to start, and a step-by-step wizard guides you through everything. No programming needed.

- **Nothing changes without your OK.** Confident matches are liked automatically. Doubtful ones (live versions, remixes, different spellings) are shown to you first.
- **Smart matching.** Artists written in Cyrillic and Latin are recognized as the same (`Сплин` = `Splean`), and track durations are compared.
- **Keeps the order.** Your newest Yandex likes end up at the top in Spotify.
- **Safe to re-run.** Tracks you already have are skipped, and an interrupted transfer continues where it stopped. Run it again later to move new likes.
- **Undo.** One command removes everything the program added.
- **Private.** Your tokens stay on your computer. The code is open.

> The program's interface is in Russian.

## Quick start

1. [Download the latest release](https://github.com/iamaburu/yandex-to-spotify/releases/latest) (**Source code (zip)**) and unzip it.
2. Double-click **`start.command`** on macOS or **`start.bat`** on Windows. On Linux, run `./start.sh`.
3. Follow the wizard. It opens every page you need and checks everything you paste.

You need Python 3.9+. On macOS the wizard tells you how to install it if it is missing.
On Windows, get it from [python.org](https://www.python.org/downloads/) and tick **Add python.exe to PATH**.

**[📖 Step-by-step guide and troubleshooting →](docs/GUIDE.md)**

## What you will need
- A Yandex Music account. The wizard helps you get an access token in two clicks.
- A Spotify account (Free or Premium) and a free Spotify "developer app". The wizard walks you through creating it in about two minutes.

## For advanced users

Every step is also available as a separate command:
```sh
./start.command <command>        # Windows: start.bat <command>
```
| command | what it does |
|---|---|
| *(none)* | step-by-step wizard |
| `setup` | enter Yandex and Spotify credentials |
| `check` | verify access to both services |
| `export` | export Yandex likes → `data/yandex_likes.json` |
| `match` | find tracks on Spotify → `data/report.csv` (likes nothing) |
| `review` | review doubtful matches |
| `like [--dry-run]` | like all tracks with status `ok` |
| `undo [--dry-run]` | remove everything the program added |

You can also edit `data/report.csv` by hand. Rows with status `ok` get liked, and `check`, `skip` and `not_found` are ignored.

## Disclaimer
- Yandex Music has no public API. This tool uses the unofficial [`yandex-music`](https://github.com/MarshalX/yandex-music-api) library and the OAuth client of the official Yandex Music app, so it may stop working if Yandex changes something.
- This project is not affiliated with Yandex or Spotify. Use it at your own risk.

## Support the author
If this tool saved you time, you can say thanks on **[Boosty](https://boosty.to/iamaburu/donate)**. ⭐ A star on GitHub helps too.

## License
[MIT](LICENSE) © 2026 iamaburu
