"""Веб-интерфейс yandex-to-spotify: локальный сервер, который открывается в браузере.

Запуск: ./start-web.command (или ./start.command web).
Сервер слушает только 127.0.0.1 на порту из Redirect URI приложения Spotify (по умолчанию 8888)
и сам принимает ответ Spotify после входа (/callback). Запросы к API принимаются только
с секретным ключом, который получает страница, открытая самой программой.
"""
import json
import secrets
import sys
import threading
import traceback
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

import transfer as core

INDEX_FILE = core.BASE / "web" / "index.html"
STATUSES = ("ok", "check", "skip", "not_found")


def unexpected(e):
    traceback.print_exception(type(e), e, e.__traceback__)
    return (f"Непредвиденная ошибка: {e.__class__.__name__}: {e}. "
            "Подробности — в окне терминала, из которого запущена программа.")


def explain(e):
    return core.friendly_error(e) or unexpected(e)


class App:
    def __init__(self, token):
        self.token = token
        self.lock = threading.Lock()
        self.job = None
        self.oauth_state = None
        self.yandex = {"key": None, "name": "", "error": None}
        self.spotify = {"key": None, "name": "", "error": None}

    # ---------- подключения ----------

    def yandex_status(self, env):
        token = env.get("YANDEX_TOKEN", "")
        if not token:
            return {"connected": False, "name": "", "error": None}
        if self.yandex["key"] != token:
            try:
                me = core.yandex_client(env).me.account
                self.yandex.update(key=token, name=me.login or me.display_name or "", error=None)
            except Exception as e:
                self.yandex.update(key=token, name="", error=explain(e))
        return {"connected": not self.yandex["error"], "name": self.yandex["name"],
                "error": self.yandex["error"]}

    def spotify_status(self, env):
        has_keys = bool(env.get("SPOTIFY_CLIENT_ID") and env.get("SPOTIFY_CLIENT_SECRET"))
        result = {"keys": has_keys, "connected": False, "name": "", "error": None,
                  "redirect_uri": env.get("SPOTIFY_REDIRECT_URI") or core.REDIRECT_URI}
        if not has_keys or not core.SPOTIFY_TOKEN_FILE.exists():
            return result
        key = (env["SPOTIFY_CLIENT_ID"], core.SPOTIFY_TOKEN_FILE.stat().st_mtime)
        if self.spotify["key"] != key:
            try:
                auth = core.spotify_auth(env, open_browser=False)
                if not auth.get_cached_token():
                    raise core.UserError("Нужно войти в Spotify.")
                user = core.spotify_client(env, auth).current_user()
                self.spotify.update(key=key, name=user.get("display_name") or user["id"], error=None)
            except Exception as e:
                self.spotify.update(key=key, name="", error=explain(e))
        result.update(connected=not self.spotify["error"], name=self.spotify["name"],
                      error=self.spotify["error"])
        return result

    def sp_client(self, env):
        """Клиент Spotify без открытия браузера: вход делается через страницу."""
        auth = core.spotify_auth(env, open_browser=False)
        if not auth.get_cached_token():
            raise core.UserError("Сначала войдите в Spotify (кнопка «Войти в Spotify» вверху страницы).")
        return core.spotify_client(env, auth)

    # ---------- состояние ----------

    def busy(self):
        return bool(self.job and self.job["running"])

    def state(self, _body):
        env = core.load_env()
        likes = None
        if core.LIKES_FILE.exists():
            stamp = datetime.fromtimestamp(core.LIKES_FILE.stat().st_mtime)
            likes = {"count": len(json.loads(core.LIKES_FILE.read_text(encoding="utf-8"))),
                     "date": stamp.strftime("%d.%m.%Y %H:%M")}
        report = core.report_counts(core.read_report()) if core.REPORT_FILE.exists() else None
        return {
            "yandex": self.yandex_status(env),
            "spotify": self.spotify_status(env),
            "likes": likes,
            "report": report,
            "liked_by_program": len(core.read_liked_log()),
            "job": self.job,
            "version": core.VERSION,
        }

    # ---------- настройка ----------

    def set_yandex(self, body):
        token = core.clean_yandex_token(str(body.get("token", "")))
        if not token:
            raise core.UserError("Вставьте адрес страницы или токен.")
        env = core.load_env()
        env["YANDEX_TOKEN"] = token
        try:
            me = core.yandex_client(env).me.account
        except core.UserError:
            raise core.UserError("Яндекс не принял токен. Скопируйте адрес ещё раз — целиком, "
                                 "сразу после нажатия «Разрешить».")
        core.save_env(env)
        self.yandex.update(key=token, name=me.login or me.display_name or "", error=None)
        return {"ok": True}

    def set_spotify_keys(self, body):
        client_id = str(body.get("client_id", "")).replace(" ", "")
        client_secret = str(body.get("client_secret", "")).replace(" ", "")
        error = core.check_spotify_keys(client_id, client_secret)
        if error:
            raise core.UserError(error)
        env = core.load_env()
        if env.get("SPOTIFY_CLIENT_ID") != client_id and core.SPOTIFY_TOKEN_FILE.exists():
            core.SPOTIFY_TOKEN_FILE.unlink()  # вход относился к другому приложению
        env.update(SPOTIFY_CLIENT_ID=client_id, SPOTIFY_CLIENT_SECRET=client_secret)
        env["SPOTIFY_REDIRECT_URI"] = env.get("SPOTIFY_REDIRECT_URI") or core.REDIRECT_URI
        core.save_env(env)
        self.spotify["key"] = None
        return {"ok": True}

    def spotify_login(self, _body):
        self.oauth_state = secrets.token_urlsafe(16)
        auth = core.spotify_auth(core.load_env(), open_browser=False)
        return {"url": auth.get_authorize_url(state=self.oauth_state)}

    def spotify_callback(self, query):
        """Ответ Spotify после входа. Возвращает код результата для страницы."""
        state = query.get("state", [""])[0]
        if not self.oauth_state or not secrets.compare_digest(state, self.oauth_state):
            return "state"
        self.oauth_state = None
        if "error" in query:
            return "denied"
        try:
            auth = core.spotify_auth(core.load_env(), open_browser=False)
            auth.get_access_token(query.get("code", [""])[0], check_cache=False)
        except Exception as e:
            print(f"Spotify: {explain(e)}")
            return "error"
        self.spotify["key"] = None
        return "ok"

    def spotify_logout(self, _body):
        if core.SPOTIFY_TOKEN_FILE.exists():
            core.SPOTIFY_TOKEN_FILE.unlink()
        self.spotify["key"] = None
        return {"ok": True}

    # ---------- отчёт ----------

    def report(self, _body):
        rows = core.read_report()
        return {"rows": [{k: r.get(k, "") for k in (
            "status", "yandex_artist", "yandex_title", "spotify_artist", "spotify_title",
            "duration_diff_s", "spotify_url", "spotify_id", "yandex_id")} for r in rows]}

    def report_update(self, body):
        changes = body.get("changes") or {}
        if not isinstance(changes, dict):
            raise core.UserError("Неверный формат запроса.")
        rows = core.read_report()
        for r in rows:
            status = changes.get(r["yandex_id"])
            if status in ("ok", "skip") and r["spotify_id"].strip():
                r["status"] = status
        core.write_report(rows)
        return {"ok": True}

    # ---------- долгие операции ----------

    def start_job(self, kind, fn):
        with self.lock:
            if self.busy():
                raise core.UserError("Уже выполняется другая операция. Дождитесь её окончания.")
            self.job = {"kind": kind, "running": True, "n": 0, "total": None,
                        "result": None, "error": None}
        job = self.job

        def progress(n, total):
            job["n"], job["total"] = n, total

        def run():
            try:
                job["result"] = fn(core.load_env(), progress)
            except Exception as e:
                job["error"] = explain(e)
            finally:
                job["running"] = False
        threading.Thread(target=run, daemon=True).start()
        return {"ok": True}

    def export(self, _body):
        return self.start_job("export", lambda env, progress: {"count": core.export_likes(env, progress)})

    def match(self, body):
        redo = bool(body.get("redo"))

        def run(env, progress):
            self.sp_client(env)  # проверяем вход заранее, чтобы не открывался браузер из терминала
            return core.match_tracks(env, redo, progress)
        return self.start_job("match", run)

    def like_check(self, _body):
        def run(env, progress):
            ids, already, todo = core.like_plan(self.sp_client(env))
            return {"total": len(ids), "already": len(already), "todo": len(todo)}
        return self.start_job("like_check", run)

    def like(self, _body):
        def run(env, progress):
            sp = self.sp_client(env)
            _, _, todo = core.like_plan(sp)
            return {"count": core.like_tracks(sp, todo, progress)}
        return self.start_job("like", run)

    def undo(self, _body):
        def run(env, progress):
            return {"count": core.undo_likes(self.sp_client(env), progress)}
        return self.start_job("undo", run)


ROUTES = {
    ("GET", "/api/state"): App.state,
    ("GET", "/api/report"): App.report,
    ("POST", "/api/report"): App.report_update,
    ("POST", "/api/yandex"): App.set_yandex,
    ("POST", "/api/spotify/keys"): App.set_spotify_keys,
    ("POST", "/api/spotify/login"): App.spotify_login,
    ("POST", "/api/spotify/logout"): App.spotify_logout,
    ("POST", "/api/export"): App.export,
    ("POST", "/api/match"): App.match,
    ("POST", "/api/like/check"): App.like_check,
    ("POST", "/api/like"): App.like,
    ("POST", "/api/undo"): App.undo,
}


def make_handler(app, callback_path, server_ref):
    token = app.token

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # не засоряем терминал логом запросов

        def send(self, status, body, content_type="application/json; charset=utf-8", headers=None):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def host_ok(self):
            # защита от DNS rebinding: страница должна быть открыта именно по 127.0.0.1/localhost
            port = self.server.server_address[1]
            return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def handle_any(self, method):
            if not self.host_ok():
                return self.send(403, {"error": "Доступ запрещён."})
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if method == "GET" and url.path == "/":
                if query.get("t", [""])[0] != token:
                    return self.send(403, "Откройте ссылку, которую показала программа в терминале.".encode(),
                                     "text/plain; charset=utf-8")
                html = INDEX_FILE.read_text(encoding="utf-8").replace("__TOKEN__", token)
                return self.send(200, html.encode(), "text/html; charset=utf-8")
            if method == "GET" and url.path == callback_path:
                result = app.spotify_callback(query)
                return self.send(302, b"", headers={"Location": f"/?t={quote(token)}&spotify={result}"})
            if method == "POST" and url.path == "/api/quit" and self.headers.get("X-Token") == token:
                self.send(200, {"ok": True})
                threading.Thread(target=server_ref[0].shutdown, daemon=True).start()
                return
            route = ROUTES.get((method, url.path))
            if route is None:
                return self.send(404, {"error": "Не найдено."})
            if not secrets.compare_digest(self.headers.get("X-Token", ""), token):
                return self.send(403, {"error": "Неверный ключ доступа. Откройте ссылку из терминала заново."})
            body = {}
            if method == "POST":
                length = int(self.headers.get("Content-Length") or 0)
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    return self.send(400, {"error": "Неверный формат запроса."})
            try:
                return self.send(200, route(app, body))
            except Exception as e:
                return self.send(400, {"error": explain(e)})

        def do_GET(self):
            self.handle_any("GET")

        def do_POST(self):
            self.handle_any("POST")
    return Handler


def serve(open_browser=True):
    redirect = urlparse(core.load_env().get("SPOTIFY_REDIRECT_URI") or core.REDIRECT_URI)
    if redirect.hostname not in ("127.0.0.1", "localhost") or not redirect.port:
        raise core.UserError(f"Для веб-интерфейса Redirect URI приложения Spotify должен быть "
                             f"{core.REDIRECT_URI}. Исправьте его в настройках приложения и в файле .env.")
    token = secrets.token_urlsafe(24)
    app = App(token)
    server_ref = []
    try:
        server = ThreadingHTTPServer(("127.0.0.1", redirect.port),
                                     make_handler(app, redirect.path or "/callback", server_ref))
    except OSError:
        raise core.UserError(f"Порт {redirect.port} занят: возможно, программа уже запущена в другом окне. "
                             "Закройте его и запустите снова.")
    server.daemon_threads = True
    server_ref.append(server)
    url = f"http://127.0.0.1:{redirect.port}/?t={token}"
    print("yandex-to-spotify — веб-интерфейс\n"
          f"Откройте в браузере: {url}\n"
          "Не закрывайте это окно, пока работаете. Чтобы завершить — кнопка «Завершить» "
          "на странице или Ctrl+C здесь.")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    print("Веб-интерфейс остановлен.")
    sys.stdout.flush()
