# Step-by-step guide

This guide is for people who have never used a terminal. The whole transfer takes 15–20 minutes, and most of that is the automatic track search.

> The program's interface is in Russian. The prompts are short, and this guide explains every step.

- [1. Download](#1-download)
- [2. Run](#2-run)
- [3. Get a Yandex Music token](#3-get-a-yandex-music-token)
- [4. Create a Spotify app](#4-create-a-spotify-app)
- [5. Transfer](#5-transfer)
- [6. Tracks that were not found](#6-tracks-that-were-not-found)
- [7. Undo](#7-undo)
- [8. Troubleshooting](#8-troubleshooting)
- [9. Security](#9-security)

## 1. Download

1. Open the latest release: https://github.com/iamaburu/yandex-to-spotify/releases/latest
2. Under **Assets**, click **Source code (zip)**.
3. Unzip it. You can put the `yandex-to-spotify-…` folder anywhere.

You need **Python 3.9+**:
- **macOS:** if Python is missing, the program tells you how to install it.
- **Windows:** install Python from https://www.python.org/downloads/ and tick **Add python.exe to PATH**.
- **Linux:** Python is usually already installed.

## 2. Run

| System | What to do |
|---|---|
| macOS | Double-click `start.command` |
| Windows | Double-click `start.bat` |
| Linux | Run `./start.sh` in a terminal |

**macOS may block the first launch** ("cannot be verified" / "unidentified developer"):
1. Open **System Settings → Privacy & Security**.
2. Scroll down and click **Open Anyway** next to `start.command`.
3. Launch it again and confirm.

The first launch installs the required components, which takes about a minute. Then the setup wizard starts.

## 3. Get a Yandex Music token

The wizard opens the Yandex page for you.

1. Sign in to the account that has your likes and click **Allow** («Разрешить»).
2. You will be redirected to an address like
   `https://music.yandex.ru/#access_token=y0_AgAAAA…&token_type=bearer&expires_in=…`
3. Copy the **whole address** from the address bar and paste it into the program. Anything extra is removed automatically.
4. The program checks the token right away.

**If the address changes too quickly:**
1. Open DevTools (⌥⌘I on macOS, F12 on Windows).
2. Go to the **Network** tab and turn on **Preserve log**.
3. Open the Yandex page again.
4. Copy the request that starts with `music.yandex.ru/#access_token=`.

## 4. Create a Spotify app

Spotify only lets programs like this one like tracks through a free "developer app". Creating one is just a form on Spotify's website and takes two minutes. A Free or Premium account works.

1. The wizard opens https://developer.spotify.com/dashboard. Sign in with **the Spotify account you are transferring to**. Accept the developer terms and verify your email if Spotify asks.
2. Click **Create app** and fill in the form:
   - **App name** and **App description**: anything, e.g. `yandex-to-spotify`;
   - **Redirect URIs**: exactly `http://127.0.0.1:8888/callback`, then click **Add** (`localhost` will not work);
   - **Which API/SDKs are you planning to use?**: select **Web API**;
   - accept the terms and click **Save**.
3. Open **Settings**. Copy the **Client ID**, then click **View client secret** and copy the **Client secret**. Paste both into the program.
4. A Spotify page asking for access opens. Click **Agree**. When you see *Authentication status: successful*, you can close the tab.

## 5. Transfer

1. **Export from Yandex** takes a few seconds.
2. **Search on Spotify** takes about 5 minutes per 500 tracks. Every match is checked by title, artist and duration and gets one of three results:
   - *точно* — a confident match;
   - *нужно проверить* — probably the same song, but a different version or spelling;
   - *нет в Spotify* — the track is not on Spotify or not available in your country.
3. **Review doubtful matches.** For each pair, answer:
   - `д` (yes) — the same song, like it;
   - `н` (no) — a different song, skip it;
   - `с` — open it in Spotify to listen;
   - `в` — quit and save your answers.
4. **Likes.** The program shows how many tracks it will add and asks for confirmation. The original order is kept, so your newest likes end up at the top.

If the transfer is interrupted, just run the program again. It continues where it stopped and never likes a track twice.
To transfer new likes later, run it again and answer "yes" to «Выгрузить заново?» ("Export again?").

## 6. Tracks that were not found

The full report is saved to `data/report.csv` in the program folder. It opens in Numbers, Excel or LibreOffice and uses `;` as the separator.

Tracks that usually are not found:
- tracks that are not on Spotify or not available in your region;
- fan remixes, covers, audiobooks;
- tracks with titles in other scripts (Japanese, Korean, etc.) when Spotify spells them differently.

## 7. Undo

The program remembers which tracks it added. To remove them from Liked Songs:
- **macOS / Linux:** run `./start.command undo`;
- **Windows:** run `start.bat undo`.

Tracks you had liked before the transfer are not touched.

## 8. Troubleshooting

**"Яндекс не принял токен" (token rejected)**
Run the wizard again, or run `setup`, and get a new token.

**Spotify: "INVALID_CLIENT: Invalid redirect URI"**
The app's Redirect URI must be exactly `http://127.0.0.1:8888/callback`.

**"Spotify не принял ключи приложения" (keys rejected)**
Run `setup` and enter the Client ID and Client secret again.

**Spotify: 403 access denied**
You signed in with a different Spotify account than the one that owns the app. Add that account under **User Management** in your app on developer.spotify.com, or sign in with the right account.

**Browser does not open**
The program always prints the address. Copy it into the browser manually.

**Port 8888 already in use**
Close the program that uses the port, or reboot.

**"Нет связи с сервером" (no connection)**
Check your internet connection. Try with or without VPN or proxy.

**macOS: Python not found**
Run `xcode-select --install`, then start again.

**Windows: Python not found**
Install Python from python.org with **Add python.exe to PATH** ticked.

Still stuck? [Open an issue](https://github.com/iamaburu/yandex-to-spotify/issues/new/choose). **Never share your tokens or your `.env` file.**

## 9. Security

- Your Yandex token and Spotify keys stay on your computer in the `.env` file. They are sent only to Yandex and Spotify.
- Never share `.env`: the token gives access to your Yandex account.
- After the transfer, you can revoke access:
  - **Yandex:** https://id.yandex.ru/security;
  - **Spotify:** https://www.spotify.com/account/apps/. You can also delete the app on the developer dashboard.
- The source code is open. Everything the program does is in `transfer.py`.
