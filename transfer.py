#!/usr/bin/env python3
"""Перенос лайков из Яндекс.Музыки в «Любимые треки» Spotify.

Запуск без команды — пошаговый мастер, который проведёт через все шаги.
Отдельные шаги: setup, check, export, match, review, like, undo (см. --help).

Настройки хранятся в файле .env рядом со скриптом (его создаёт команда setup).
"""
import argparse
import csv
import json
import re
import sys
import time
import unicodedata
import warnings
from difflib import SequenceMatcher
from pathlib import Path

warnings.filterwarnings("ignore", message=".*OpenSSL.*")

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
LIKES_FILE = DATA / "yandex_likes.json"
MATCH_CACHE = DATA / "matches.json"
REPORT_FILE = DATA / "report.csv"
LIKED_LOG = DATA / "liked.json"
SPOTIFY_TOKEN_FILE = DATA / ".spotify_token"
VERSION = "0.2.0"

REPORT_FIELDS = [
    "status", "yandex_artist", "yandex_title", "spotify_artist", "spotify_title",
    "score", "duration_diff_s", "spotify_url", "spotify_id", "yandex_id",
]


# ---------- настройки ----------

ENV_FILE = BASE / ".env"
ENV_KEYS = ["YANDEX_TOKEN", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REDIRECT_URI"]
REDIRECT_URI = "http://127.0.0.1:8888/callback"
YANDEX_TOKEN_URL = ("https://oauth.yandex.ru/authorize?response_type=token"
                    "&client_id=23cabbbdc6cd418abb4b39c32c41195d")
SPOTIFY_DASHBOARD_URL = "https://developer.spotify.com/dashboard"
# как пользователю запускать команды — для подсказок в сообщениях
LAUNCHER = "start.bat" if sys.platform == "win32" else "./start.command"


class UserError(Exception):
    """Понятная пользователю ошибка: печатается без traceback."""


def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def save_env(env):
    lines = ["# Создано командой setup. Не публикуйте этот файл."]
    lines += [f"{k}={env.get(k, '')}" for k in ENV_KEYS]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        ENV_FILE.chmod(0o600)
    except OSError:
        pass


def require(env, key):
    if not env.get(key):
        raise UserError(f"Не заполнено {key}. Запустите настройку: {LAUNCHER} setup")
    return env[key]


def clean_yandex_token(token):
    # если скопирован кусок адреса целиком: …#access_token=XXX&token_type=…
    return token.split("access_token=")[-1].split("&")[0].strip()


def yandex_client(env):
    from yandex_music import Client
    from yandex_music.exceptions import UnauthorizedError
    try:
        return Client(clean_yandex_token(require(env, "YANDEX_TOKEN"))).init()
    except UnauthorizedError:
        raise UserError("Яндекс не принял токен: он неверный или устарел. "
                        f"Получите новый: {LAUNCHER} setup")


def spotify_auth(env, open_browser=True):
    from spotipy.oauth2 import SpotifyOAuth
    DATA.mkdir(exist_ok=True)
    return SpotifyOAuth(
        client_id=require(env, "SPOTIFY_CLIENT_ID"),
        client_secret=require(env, "SPOTIFY_CLIENT_SECRET"),
        redirect_uri=env.get("SPOTIFY_REDIRECT_URI") or REDIRECT_URI,
        # user-read-private нужен для поиска с market=from_token (регион аккаунта)
        scope="user-library-read user-library-modify user-read-private",
        cache_path=str(SPOTIFY_TOKEN_FILE),
        open_browser=open_browser,
    )


def spotify_client(env, auth=None):
    import spotipy
    auth = auth or spotify_auth(env)
    return spotipy.Spotify(auth_manager=auth, retries=5, status_retries=5, backoff_factor=1)


def check_spotify_keys(client_id, client_secret):
    """Проверяет формат ключей Spotify. Возвращает текст ошибки или None."""
    for value, label in ((client_id, "Client ID"), (client_secret, "Client secret")):
        if not re.fullmatch(r"[0-9a-fA-F]{32}", value):
            return (f"{label} не похож на ключ: он состоит из 32 символов 0-9 и a-f. "
                    "Скопируйте ещё раз.")
    return None


# ---------- диалог с пользователем ----------

def ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        raise KeyboardInterrupt


def confirm(prompt, default=True):
    hint = "[Д/н]" if default else "[д/Н]"
    answer = ask(f"{prompt} {hint} ").lower()
    if not answer:
        return default
    return answer in ("д", "да", "y", "yes", "l")  # l — «д» в английской раскладке


def open_url(url):
    import webbrowser
    try:
        webbrowser.open(url)
    except Exception:
        pass


def title(text):
    print(f"\n=== {text} ===")


# ---------- сравнение названий ----------

TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
})
NOISE = re.compile(r"\b(feat|ft|prod|remaster(ed)?|original mix|radio edit|explicit)\b.*", re.I)


def norm(text):
    text = unicodedata.normalize("NFKC", text or "").lower().replace("ё", "е")
    text = re.sub(r"[(\[].*?[)\]]", " ", text)  # скобки: (feat. …), [Remastered] и т.п.
    text = NOISE.sub(" ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def similarity(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    return max(
        SequenceMatcher(None, a, b).ratio(),
        SequenceMatcher(None, a.translate(TRANSLIT), b.translate(TRANSLIT)).ratio(),
    )


def score_candidate(track, cand):
    title_sim = similarity(track["title"], cand["name"])
    if track.get("version"):
        title_sim = max(title_sim, similarity(f'{track["title"]} {track["version"]}', cand["name"]))
    cand_artists = [a["name"] for a in cand["artists"]]
    artist_sim = max(
        (similarity(ya, sa) for ya in track["artists"] for sa in cand_artists), default=0.0
    ) if track["artists"] else 0.5
    diff = None
    if track.get("duration_ms") and cand.get("duration_ms"):
        diff = abs(track["duration_ms"] - cand["duration_ms"]) / 1000
    score = 0.55 * title_sim + 0.45 * artist_sim
    if diff is not None and diff > 10:
        score -= 0.1
    return score, title_sim, artist_sim, diff


def classify(score, title_sim, artist_sim, diff):
    if title_sim >= 0.9 and artist_sim >= 0.85 and (diff is None or diff <= 5):
        return "ok"
    if score >= 0.6:
        return "check"
    return "not_found"


# ---------- команды ----------

def cmd_setup(env, args):
    title("Настройка")
    print("Нужны два доступа: к Яндекс.Музыке (чтобы прочитать лайки) и к Spotify (чтобы их поставить).\n"
          f"Всё сохранится в файле {ENV_FILE.name} на этом компьютере и больше никуда не отправится.")

    # --- Яндекс ---
    if not env.get("YANDEX_TOKEN") or confirm("\nТокен Яндекса уже есть. Получить новый?", default=False):
        print("\n1. Токен Яндекс.Музыки\n"
              "   Сейчас откроется страница Яндекса. Войдите и нажмите «Разрешить».\n"
              "   Затем скопируйте из адресной строки ВЕСЬ адрес (он начинается с https://music.yandex.ru/#access_token=)\n"
              "   и вставьте его сюда. Лишнее программа отрежет сама.\n"
              "   Если адрес успел смениться: ⌥⌘I (Windows: F12) → вкладка Network → включите «Preserve log» → повторите.")
        ask("   Нажмите Enter, чтобы открыть страницу… ")
        open_url(YANDEX_TOKEN_URL)
        print(f"   (если браузер не открылся: {YANDEX_TOKEN_URL})")
        while True:
            token = clean_yandex_token(ask("   Вставьте адрес или токен: "))
            if not token:
                continue
            env["YANDEX_TOKEN"] = token
            try:
                me = yandex_client(env).me.account
                print(f"   ✓ Яндекс.Музыка: вход выполнен ({me.login or me.display_name})")
                break
            except UserError:
                print("   ✗ Яндекс не принял токен. Попробуйте скопировать ещё раз.")
        save_env(env)

    # --- Spotify ---
    if (not (env.get("SPOTIFY_CLIENT_ID") and env.get("SPOTIFY_CLIENT_SECRET"))
            or confirm("\nКлючи Spotify уже есть. Ввести новые?", default=False)):
        print("\n2. Ключи Spotify\n"
              "   Spotify разрешает программам ставить лайки только через «приложение разработчика».\n"
              "   Его создание бесплатно и занимает пару минут:\n"
              "   а) войдите на открывшейся странице и нажмите «Create app»;\n"
              "   б) App name и App description — любые (например, yandex-to-spotify);\n"
              f"   в) Redirect URIs — вставьте ровно: {REDIRECT_URI}  и нажмите «Add»;\n"
              "   г) в «Which API/SDKs are you planning to use?» отметьте «Web API»;\n"
              "   д) отметьте согласие с условиями и нажмите «Save»;\n"
              "   е) откройте «Settings»: там Client ID и (по кнопке «View client secret») Client secret.")
        ask("   Нажмите Enter, чтобы открыть страницу… ")
        open_url(SPOTIFY_DASHBOARD_URL)
        print(f"   (если браузер не открылся: {SPOTIFY_DASHBOARD_URL})")
        for key, label in (("SPOTIFY_CLIENT_ID", "Client ID"), ("SPOTIFY_CLIENT_SECRET", "Client secret")):
            while True:
                value = ask(f"   {label}: ").replace(" ", "")
                if not check_spotify_keys(value, value):
                    env[key] = value
                    break
                print("   Это не похоже на ключ: он состоит из 32 символов 0-9 и a-f. Скопируйте ещё раз.")
        env["SPOTIFY_REDIRECT_URI"] = env.get("SPOTIFY_REDIRECT_URI") or REDIRECT_URI
        save_env(env)

    print("\n   Проверяю Spotify: в браузере откроется страница входа — нажмите «Agree» / «Принимаю».")
    user = spotify_client(env).current_user()
    print(f"   ✓ Spotify: вход выполнен ({user.get('display_name') or user['id']})")
    print("\nНастройка завершена.")


def cmd_check(env, args):
    ya = yandex_client(env)
    me = ya.me.account
    print(f"✓ Яндекс.Музыка: вход выполнен ({me.login or me.display_name})")
    sp = spotify_client(env)
    user = sp.current_user()
    print(f"✓ Spotify: вход выполнен ({user.get('display_name') or user['id']})")


def cmd_export(env, args):
    count = export_likes(env, lambda n, total: print(
        f"Лайков в Яндекс.Музыке: {total}. Загружаю данные о треках…" if n == 0 else f"  {n}/{total}"))
    print(f"✓ Выгружено треков: {count}")
    return count


def export_likes(env, progress=None):
    """Выгружает лайки Яндекса в LIKES_FILE. progress(n, total) — ход загрузки."""
    ya = yandex_client(env)
    likes = ya.users_likes_tracks()
    shorts = list(likes.tracks) if likes else []
    if progress:
        progress(0, len(shorts))
    liked_at = {str(s.id): s.timestamp for s in shorts}
    ids = [s.track_id for s in shorts]
    full = {}
    for i in range(0, len(ids), 200):
        for t in ya.tracks(ids[i:i + 200]):
            full[str(t.id)] = t
        if progress:
            progress(min(i + 200, len(ids)), len(ids))
    result = []
    for s in shorts:  # порядок Яндекса: сначала самые новые лайки
        t = full.get(str(s.id))
        if t is None:
            continue
        result.append({
            "yandex_id": str(t.id),
            "title": t.title or "",
            "version": t.version or "",
            "artists": [a.name for a in (t.artists or []) if a.name],
            "album": t.albums[0].title if t.albums else "",
            "duration_ms": t.duration_ms,
            "available": bool(t.available),
            "liked_at": liked_at.get(str(s.id)),
        })
    DATA.mkdir(exist_ok=True)
    LIKES_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(result)


def search_candidates(sp, track):
    artist = track["artists"][0] if track["artists"] else ""
    queries = [f'track:"{track["title"]}" artist:"{artist}"', f'{artist} {track["title"]}']
    seen, cands = set(), []
    for q in queries:
        items = sp.search(q=q, type="track", limit=10, market="from_token")["tracks"]["items"]
        for it in items:
            if it and it["id"] not in seen:
                seen.add(it["id"])
                cands.append(it)
        if cands:
            best = max(score_candidate(track, c)[0] for c in cands)
            if best >= 0.9:
                break
    return cands


def read_report():
    if not REPORT_FILE.exists():
        raise UserError(f"Отчёта ещё нет. Сначала выполните: {LAUNCHER} match")
    with REPORT_FILE.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def write_report(rows):
    with REPORT_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REPORT_FIELDS, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def report_counts(rows):
    counts = {"ok": 0, "check": 0, "not_found": 0, "skip": 0}
    for r in rows:
        counts[r["status"].strip()] = counts.get(r["status"].strip(), 0) + 1
    return counts


def cmd_match(env, args):
    print("Ищу треки в Spotify. Это займёт несколько минут…")
    counts = match_tracks(env, getattr(args, "redo", False),
                          lambda n, total: (n % 20 == 0 or n == total) and print(f"  {n}/{total}"))
    print(f"✓ Найдено точно: {counts['ok']}, нужно проверить: {counts['check']}, "
          f"нет в Spotify: {counts['not_found']}")
    print(f"  Полный отчёт: {REPORT_FILE}")
    return counts


def match_tracks(env, redo=False, progress=None):
    """Ищет выгруженные треки в Spotify и пишет отчёт. Возвращает счётчики статусов."""
    if not LIKES_FILE.exists():
        raise UserError(f"Лайки ещё не выгружены. Сначала выполните: {LAUNCHER} export")
    tracks = json.loads(LIKES_FILE.read_text(encoding="utf-8"))
    cache = json.loads(MATCH_CACHE.read_text(encoding="utf-8")) if MATCH_CACHE.exists() else {}
    sp = spotify_client(env)
    for n, track in enumerate(tracks, 1):
        if track["yandex_id"] in cache and not redo:
            continue
        cands = search_candidates(sp, track)
        best = None
        for c in cands:
            s = score_candidate(track, c)
            if best is None or s[0] > best[0][0]:
                best = (s, c)
        row = {"status": "not_found", "score": 0, "duration_diff_s": "",
               "spotify_artist": "", "spotify_title": "", "spotify_url": "", "spotify_id": ""}
        if best:
            (score, t_sim, a_sim, diff), c = best
            row.update(
                status=classify(score, t_sim, a_sim, diff),
                score=round(score, 2),
                duration_diff_s="" if diff is None else round(diff),
                spotify_artist=", ".join(a["name"] for a in c["artists"]),
                spotify_title=c["name"],
                spotify_url=c["external_urls"].get("spotify", ""),
                spotify_id=c["id"],
            )
        cache[track["yandex_id"]] = row
        if n % 20 == 0 or n == len(tracks):
            MATCH_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        if progress:
            progress(n, len(tracks))
    MATCH_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    # решения, принятые вручную (review или правка CSV), не затираем при повторном поиске
    manual = {}
    if REPORT_FILE.exists():
        for r in read_report():
            auto = cache.get(r["yandex_id"])
            if auto and r["spotify_id"] == auto["spotify_id"] and r["status"] != auto["status"]:
                manual[r["yandex_id"]] = r["status"]

    rows = []
    for track in tracks:
        title_ = track["title"] + (f' ({track["version"]})' if track["version"] else "")
        row = {**cache[track["yandex_id"]], "yandex_artist": ", ".join(track["artists"]),
               "yandex_title": title_, "yandex_id": track["yandex_id"]}
        row["status"] = manual.get(track["yandex_id"], row["status"])
        rows.append(row)
    write_report(rows)
    return report_counts(rows)


def cmd_review(env, args):
    rows = read_report()
    todo = [r for r in rows if r["status"].strip() == "check"]
    if not todo:
        print("Сомнительных совпадений нет.")
        return
    print(f"Сомнительных совпадений: {len(todo)}. Для каждого ответьте:\n"
          "  д — это та же песня, лайкнуть;  н — не та, пропустить;\n"
          "  с — открыть в Spotify и послушать;  в — выйти (ответы сохранятся).")
    for n, r in enumerate(todo, 1):
        diff = f", разница в длительности {r['duration_diff_s']} с" if r["duration_diff_s"] else ""
        print(f"\n[{n}/{len(todo)}]\n  Яндекс:  {r['yandex_artist']} — {r['yandex_title']}\n"
              f"  Spotify: {r['spotify_artist']} — {r['spotify_title']}{diff}")
        while True:
            answer = ask("  Та же песня? [д/н/с/в] ").lower()
            if answer in ("с", "c", "s") and r["spotify_url"]:
                open_url(r["spotify_url"])
            elif answer in ("д", "да", "y", "l"):
                r["status"] = "ok"
                break
            elif answer in ("н", "нет", "n"):
                r["status"] = "skip"
                break
            elif answer in ("в", "q", "d"):
                write_report(rows)
                print(f"Ответы сохранены. Продолжить позже: {LAUNCHER} review")
                return
        write_report(rows)
    print("\n✓ Проверка завершена.")


def read_liked_log():
    return json.loads(LIKED_LOG.read_text()) if LIKED_LOG.exists() else []


def like_plan(sp):
    """Что осталось лайкнуть: (все треки со статусом ok, уже в «Любимых», осталось добавить)."""
    ids, seen = [], set()
    for r in read_report():
        sid = r["spotify_id"].strip()
        if r["status"].strip() == "ok" and sid and sid not in seen:
            seen.add(sid)
            ids.append(sid)
    ids.reverse()  # сначала самые старые, чтобы порядок в Spotify совпал с Яндексом
    done = set(read_liked_log())
    already = set()
    for i in range(0, len(ids), 40):
        chunk = ids[i:i + 40]
        for sid, saved in zip(chunk, sp.current_user_saved_tracks_contains(chunk)):
            if saved:
                already.add(sid)
    todo = [s for s in ids if s not in already and s not in done]
    return ids, already, todo


def like_tracks(sp, todo, progress=None):
    done = set(read_liked_log())
    for n, sid in enumerate(todo, 1):
        sp.current_user_saved_tracks_add([sid])  # по одному — чтобы сохранить порядок
        done.add(sid)
        LIKED_LOG.write_text(json.dumps(sorted(done)))
        if progress:
            progress(n, len(todo))
        time.sleep(0.2)
    return len(todo)


def undo_likes(sp, progress=None):
    ids = read_liked_log()
    for i in range(0, len(ids), 40):
        sp.current_user_saved_tracks_delete(ids[i:i + 40])
        LIKED_LOG.write_text(json.dumps(ids[i + 40:]))  # при обрыве продолжим с того же места
        if progress:
            progress(min(i + 40, len(ids)), len(ids))
    if LIKED_LOG.exists():
        LIKED_LOG.unlink()
    return len(ids)


def cmd_like(env, args):
    sp = spotify_client(env)
    ids, already, todo = like_plan(sp)
    print(f"К лайку: {len(ids)}, уже в «Любимых»: {len(already)}, осталось добавить: {len(todo)}")
    if getattr(args, "dry_run", False) or not todo:
        return len(todo)
    if getattr(args, "ask", False) and not confirm(f"Поставить лайк {len(todo)} трекам в Spotify?"):
        print("Отменено. Ничего не изменено.")
        return 0
    like_tracks(sp, todo, lambda n, total: (n % 25 == 0 or n == total) and print(f"  {n}/{total}"))
    print(f"✓ Добавлено в «Любимые»: {len(todo)}")
    return len(todo)


def cmd_undo(env, args):
    ids = read_liked_log()
    if not ids:
        raise UserError("Нечего отменять: программа ещё ничего не добавляла.")
    print(f"Будет убрано из «Любимых»: {len(ids)}")
    if args.dry_run:
        return
    if not confirm("Продолжить?", default=False):
        return
    undo_likes(spotify_client(env), lambda n, total: print(f"  {n}/{total}"))
    print("✓ Готово.")


def cmd_web(env, args):
    import webui
    webui.serve(open_browser=not args.no_browser)


def cmd_wizard(env, args):
    print("yandex-to-spotify — перенос лайков из Яндекс.Музыки в Spotify\n"
          "Программа проведёт вас по шагам и ничего не изменит без вашего подтверждения.\n"
          f"Удобнее в браузере? Запустите веб-интерфейс: {LAUNCHER} web")
    if not all(env.get(k) for k in ENV_KEYS[:3]):
        cmd_setup(env, args)
    else:
        title("Шаг 1 из 4. Проверка доступа")
        cmd_check(env, args)

    title("Шаг 2 из 4. Выгрузка лайков из Яндекс.Музыки")
    if LIKES_FILE.exists() and not confirm("Лайки уже выгружались раньше. Выгрузить заново?"):
        print("Использую прошлую выгрузку.")
    else:
        cmd_export(env, args)

    title("Шаг 3 из 4. Поиск треков в Spotify")
    counts = cmd_match(env, args)
    if counts["check"]:
        print(f"\n{counts['check']} совпадений сомнительны: другая версия, ремикс или написание.")
        if confirm("Проверить их сейчас? (иначе они будут пропущены)"):
            cmd_review(env, args)

    title("Шаг 4 из 4. Лайки в Spotify")
    args.ask = True
    cmd_like(env, args)

    rows = read_report()
    missing = [r for r in rows if r["status"].strip() == "not_found"]
    if missing:
        print(f"\nНе нашлись в Spotify ({len(missing)}):")
        for r in missing[:15]:
            print(f"  • {r['yandex_artist']} — {r['yandex_title']}")
        if len(missing) > 15:
            print(f"  … и ещё {len(missing) - 15} (полный список в {REPORT_FILE})")
    print(f"\nГотово! Если что-то пошло не так, отменить всё можно командой: {LAUNCHER} undo\n"
          "Если программа помогла — поддержите автора: https://boosty.to/iamaburu/donate")


def friendly_error(e):
    """Понятный текст для типичных ошибок сети, Яндекса и Spotify, иначе None."""
    import requests
    import spotipy
    if isinstance(e, UserError):
        return str(e)
    if isinstance(e, requests.exceptions.ConnectionError):
        return "Нет связи с сервером. Проверьте интернет (и VPN, если он включён) и повторите."
    if isinstance(e, spotipy.oauth2.SpotifyOauthError):
        return ("Spotify не принял ключи приложения. Проверьте Client ID / Client secret "
                f"и Redirect URI ({REDIRECT_URI}).")
    if isinstance(e, spotipy.SpotifyException) and e.http_status == 403:
        return ("Spotify отказал в доступе (403). Частая причина — аккаунт не добавлен в "
                "User Management вашего приложения на developer.spotify.com. Подробнее — раздел "
                "«Частые проблемы» в инструкции.")
    return None


COMMANDS = {
    "web": (cmd_web, "открыть веб-интерфейс в браузере"),
    "setup": (cmd_setup, "ввести токены Яндекса и Spotify"),
    "check": (cmd_check, "проверить доступ к обоим сервисам"),
    "export": (cmd_export, "выгрузить лайки из Яндекс.Музыки"),
    "match": (cmd_match, "найти треки в Spotify и составить отчёт (ничего не лайкает)"),
    "review": (cmd_review, "проверить сомнительные совпадения"),
    "like": (cmd_like, "поставить лайки трекам со статусом ok"),
    "undo": (cmd_undo, "убрать всё, что добавила программа"),
}


def main():
    p = argparse.ArgumentParser(
        description="Перенос лайков Яндекс.Музыки в Spotify. "
                    "Без команды запускается пошаговый мастер.")
    sub = p.add_subparsers(dest="cmd", metavar="команда")
    for name, (_, help_) in COMMANDS.items():
        sp_ = sub.add_parser(name, help=help_)
        if name == "match":
            sp_.add_argument("--redo", action="store_true", help="заново искать уже найденные треки")
        if name in ("like", "undo"):
            sp_.add_argument("--dry-run", action="store_true", help="только посчитать, ничего не менять")
        if name == "web":
            sp_.add_argument("--no-browser", action="store_true", help="не открывать браузер автоматически")
    args = p.parse_args()
    env = load_env()
    func = COMMANDS[args.cmd][0] if args.cmd else cmd_wizard
    try:
        func(env, args)
    except KeyboardInterrupt:
        sys.exit("\nПрервано. Запустите снова — программа продолжит с того же места.")
    except Exception as e:
        message = friendly_error(e)
        if message is None:
            raise
        if "ключи приложения" in message:
            message += f" Команда: {LAUNCHER} setup"
        sys.exit(f"\n✗ {message}")


if __name__ == "__main__":
    main()
