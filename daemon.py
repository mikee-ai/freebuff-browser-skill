#!/usr/bin/env python3
"""
Freebuff Browser Control — the persistent browser daemon.

Owns the Playwright/Chromium session and the unix-socket command server.
Started by cli.py's ensure_daemon(); never imports the CLI.
Run `uv run python browser.py serve` to start it manually.
"""

import json
import os
import re
import socketserver
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from snapshot_js import load  # noqa: E402

JS = load(Path(__file__).resolve().parent / "snapshot.js")

VERSION = "1.2.0"
PROJECT_ROOT = Path.cwd()
PROFILE_DIR = PROJECT_ROOT / ".freebuff-browser-profile"
SHOTS_DIR = PROJECT_ROOT / "shots"
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"


def socket_path() -> Path:
    import hashlib
    tag = hashlib.sha1(str(PROJECT_ROOT).encode()).hexdigest()[:10]
    return Path(f"/tmp/freebuff-browser-{tag}.sock")


class BrowserDaemon:
    def __init__(self, headed=None, width=1440, height=900):
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        PROFILE_DIR.mkdir(exist_ok=True)
        DOWNLOADS_DIR.mkdir(exist_ok=True)
        if headed is None:   # no explicit flag: honor install.sh's --headed preference
            headed = (PROJECT_ROOT / ".freebuff-browser-headed").exists()
        args = ["--disable-blink-features=AutomationControlled"]
        self.context = self.pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=not headed,
            viewport={"width": width, "height": height},
            accept_downloads=True,
            args=args,
        )
        self.context.set_default_timeout(10000)
        self.context.set_default_navigation_timeout(25000)
        self.context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            "window.chrome={runtime:{}};"
        )
        self.pages = []
        self.current = -1
        self.console = []      # ring buffer of console messages
        self.net_errors = []
        self.dialog_log = []
        self.context.on("page", self._on_page)

    # -- page management ----------------------------------------------------
    def _on_page(self, page):
        self._register(page)
        self.console.append(f"[popup] {page.url}")

    def _register(self, page):
        if page in self.pages:
            return
        self.pages.append(page)
        if self.current == -1:
            self.current = 0
        page.on("console", lambda m: self._log_console(m))
        page.on("pageerror", lambda e: self.console.append(f"[pageerror] {e}"))
        page.on("dialog", self._on_dialog(page))
        page.on("download", self._on_download)
        page.on("download-failed", lambda d: self.console.append(f"[download failed] {d.suggested_filename}"))
        page.on("close", lambda: self._forget(page))
        page.on("requestfailed", lambda r: self.net_errors.append(f"{r.method} {r.url} -> {r.failure}"))

    def _on_download(self, download):
        try:
            name = download.suggested_filename or f"download-{int(time.time())}"
            target = DOWNLOADS_DIR / name
            if target.exists():
                target = DOWNLOADS_DIR / f"{target.stem}-{int(time.time())}{target.suffix}"
            download.save_as(str(target))   # explicit save: temp copies are wiped on context close
            self.console.append(f"[download saved] {target.name}")
        except Exception as e:
            self.console.append(f"[download failed] {download.suggested_filename}: {e}")

    def _log_console(self, msg):
        text = msg.text or ""
        self.console.append(f"[{msg.type}] {text[:300]}")
        del self.console[:-500]

    def _on_dialog(self, page):
        def handler(dialog):
            self.dialog_log.append(f"{dialog.type}: {dialog.message} (auto-accepted)")
            self.console.append(f"[dialog:{dialog.type}] {dialog.message[:200]} -> accepted")
            try:
                dialog.accept()
            except Exception:
                pass
        return handler

    def _forget(self, page):
        if page in self.pages:
            i = self.pages.index(page)
            self.pages.remove(page)
            if self.current >= len(self.pages):
                self.current = len(self.pages) - 1
            elif i < self.current:
                self.current -= 1

    @property
    def page(self):
        if self.current == -1 or not self.pages:
            self._register(self.context.new_page())
            self.pages[0].goto("about:blank")
        return self.pages[self.current]

    # -- commands ------------------------------------------------------------
    def handle(self, cmd):
        name = cmd.get("cmd", "")
        method = getattr(self, "cmd_" + name.replace("-", "_"), None)
        if name == "ping":
            return {"ok": True, "version": VERSION}
        if method is None:
            return {"error": f"unknown command: {name} (version {VERSION})"}
        return method(cmd) or {"ok": True}

    def cmd_stop(self, _):
        threading.Thread(target=self._shutdown, daemon=True).start()
        return {"ok": True, "bye": True}

    def _shutdown(self):
        # Unlink the socket first so no client can reach a half-dead daemon.
        try:
            socket_path().unlink()
        except Exception:
            pass
        time.sleep(0.1)
        # Watchdog: context.close() can hang on an unclean Chromium.
        # Force-exit no matter what after 3 seconds.
        threading.Timer(3.0, lambda: os._exit(0)).start()
        try:
            self.context.close()
        except Exception:
            pass
        try:
            self.pw.stop()
        except Exception:
            pass
        os._exit(0)

    def cmd_status(self, _):
        return {
            "ok": True, "version": VERSION,
            "pages": [p.url for p in self.pages],
            "current": self.current,
        }

    def cmd_goto(self, cmd):
        url = cmd["url"]
        if "://" not in url:
            if url.startswith("localhost") or re.match(r"^\d+\.\d+\.\d+\.\d+", url):
                url = "http://" + url
            elif Path(url).exists():
                url = Path(url).resolve().as_uri()
            elif url.startswith(("./", "/")) or re.search(
                    r"\.(html?|png|jpe?g|gif|css|js|pdf|txt|csv|json)$", url, re.I):
                return {"error": f"local file not found: {url} (paths resolve from the project root)"}
            else:
                url = "https://" + url
        try:
            self.page.goto(url, wait_until="load")
        except Exception as e:
            raise RuntimeError(f"could not load {url} ({type(e).__name__}) — check the address or your network")
        try:
            self.page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass
        return {"ok": True, "url": self.page.url, "title": self.page.title()}

    def cmd_back(self, _):
        self.page.go_back(wait_until="load")
        return {"ok": True, "url": self.page.url}

    def cmd_forward(self, _):
        self.page.go_forward(wait_until="load")
        return {"ok": True, "url": self.page.url}

    def cmd_reload(self, _):
        self.page.reload(wait_until="load")
        return {"ok": True, "url": self.page.url, "title": self.page.title()}

    def cmd_snapshot(self, cmd):
        items = self.page.evaluate(JS["SNAPSHOT"])
        lines = [f"URL: {self.page.url}", f"Title: {self.page.title()}", ""]
        for it in items:
            u, r, n = it["uid"], it["role"], it["name"]
            desc = f'[{u}] {r}'
            if n:
                desc += f' "{n}"'
            extra = []
            if it.get("href"):
                extra.append(f'href={it["href"]}')
            if "value" in it and it["role"] in ("textbox", "combobox"):
                extra.append(f'value="{it["value"]}"')
            if it.get("checked") is not None:
                extra.append("checked" if it["checked"] else "unchecked")
            if it.get("type"):
                extra.append(f'type={it["type"]}')
            if it.get("required"):
                extra.append("*required")
            if it.get("disabled"):
                extra.append("disabled")
            if it.get("level"):
                extra.append(f'h{it["level"]}')
            if extra:
                desc += "  (" + ", ".join(extra) + ")"
            lines.append(desc)
        if cmd.get("json"):
            return {"ok": True, "url": self.page.url, "title": self.page.title(), "items": items}
        return {"ok": True, "text": "\n".join(lines)}

    def cmd_text(self, _):
        text = self.page.evaluate(JS["PAGE_TEXT"])
        return {"ok": True, "text": text[:60000]}

    def _resolve(self, uid):
        loc = self.page.locator(f'[data-fb-uid="{uid}"]')
        if loc.count() == 0:
            raise RuntimeError(f"no element with uid {uid} on this page — run `snapshot` first and use a uid from its output")
        return loc.first

    def _describe(self, uid):
        try:
            el = self.page.query_selector(f'[data-fb-uid="{uid}"]')
            if el is None:
                return None
            return el.evaluate(JS["DESCRIBE"])
        except Exception:
            return None

    def _with_target(self, uid):
        resp = {"ok": True}
        info = self._describe(uid)
        if info:
            resp["acted"] = f'{info["tag"]} "{info["name"]}"'
        return resp

    def cmd_click(self, cmd):
        loc = self._resolve(cmd["uid"])
        loc.scroll_into_view_if_needed()
        if cmd.get("right"):
            loc.click(button="right")
        elif cmd.get("double"):
            loc.dblclick()
        else:
            loc.click()
        self.page.wait_for_load_state("domcontentloaded")
        resp = {"ok": True, "url": self.page.url}
        info = self._describe(cmd["uid"])
        if info:
            resp["acted"] = f'{info["tag"]} "{info["name"]}"'
        return resp

    def cmd_fill(self, cmd):
        loc = self._resolve(cmd["uid"])
        loc.fill("")
        loc.type(cmd["text"], delay=25)
        return self._with_target(cmd["uid"])

    def cmd_select(self, cmd):
        self._resolve(cmd["uid"]).select_option(cmd["value"])
        return self._with_target(cmd["uid"])

    def cmd_check(self, cmd):
        self._resolve(cmd["uid"]).check()
        return self._with_target(cmd["uid"])

    def cmd_uncheck(self, cmd):
        self._resolve(cmd["uid"]).uncheck()
        return self._with_target(cmd["uid"])

    def cmd_hover(self, cmd):
        self._resolve(cmd["uid"]).hover()
        return self._with_target(cmd["uid"])

    def cmd_press(self, cmd):
        self.page.keyboard.press(cmd["key"])
        return {"ok": True}

    def cmd_scroll(self, cmd):
        d = cmd.get("dir", "down")
        amount = int(cmd.get("amount", 600))
        delta = {"down": (0, amount), "up": (0, -amount),
                 "right": (amount, 0), "left": (-amount, 0)}.get(d)
        if delta is None:
            return {"error": f"unknown scroll direction '{d}' (use down|up|left|right)"}
        dx, dy = delta
        self.page.mouse.move(720, 450)
        self.page.mouse.wheel(dx, dy)
        time.sleep(0.15)
        return {"ok": True}

    def cmd_screenshot(self, cmd):
        SHOTS_DIR.mkdir(exist_ok=True)
        path = Path(cmd.get("path") or SHOTS_DIR / f"shot-{time.strftime('%Y%m%d-%H%M%S')}.png")
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.suffix:
            path = path.with_suffix(".png")   # Playwright infers format from extension
        path.parent.mkdir(parents=True, exist_ok=True)
        if cmd.get("full"):
            self.page.screenshot(path=str(path), full_page=True)
        else:
            self.page.screenshot(path=str(path))
        return {"ok": True, "path": str(path)}

    def cmd_eval(self, cmd):
        result = self.page.evaluate(f"() => {{ const __f = () => ({cmd['js']}); return JSON.stringify(__f()); }}")
        try:
            return {"ok": True, "result": json.loads(result)}
        except Exception:
            return {"ok": True, "result": result}

    def cmd_tabs(self, _):
        return {"ok": True,
                "tabs": [{"i": i, "url": p.url, "title": _title(p)} for i, p in enumerate(self.pages)],
                "current": self.current}

    def cmd_tab(self, cmd):
        i = int(cmd["index"])
        if 0 <= i < len(self.pages):
            self.current = i
            self.page.bring_to_front()
            return {"ok": True, "url": self.pages[i].url}
        return {"error": f"no tab {i}"}

    def cmd_tab_new(self, cmd):
        page = self.context.new_page()
        self._register(page)
        self.current = len(self.pages) - 1
        if cmd.get("url"):
            return self.cmd_goto({"url": cmd["url"]})
        page.goto("about:blank")
        return {"ok": True, "url": page.url}

    def cmd_tab_close(self, cmd):
        if cmd.get("index") is not None:
            self.current = int(cmd["index"])
        page = self.page
        url = page.url
        page.close()
        self._forget(page)
        return {"ok": True, "closed": url, "current": self.current}

    def cmd_wait(self, cmd):
        if cmd.get("ms"):
            time.sleep(float(cmd["ms"]) / 1000)
            return {"ok": True}
        if cmd.get("selector"):
            sel = cmd["selector"]
            if sel.startswith("selector:"):
                sel = sel[len("selector:"):]   # our doc syntax; Playwright wants raw CSS
            try:
                self.page.wait_for_selector(sel, timeout=15000)
            except Exception:
                raise RuntimeError(
                    f"selector {sel} not found within 15s — page may be slow or the selector wrong"
                )
            return {"ok": True, "found": sel}
        return {"error": "pass ms: or selector:"}

    def cmd_logs(self, cmd):
        logs = self.console + [f"[net] {e}" for e in self.net_errors] + self.dialog_log
        if cmd.get("clear"):
            self.console.clear()
            self.net_errors.clear()
            self.dialog_log.clear()
        return {"ok": True, "logs": logs[-200:]}

    def cmd_url(self, _):
        return {"ok": True, "url": self.page.url}

    def cmd_title(self, _):
        return {"ok": True, "title": self.page.title()}

    def cmd_state_save(self, cmd):
        path = cmd.get("path", "storage-state.json")
        self.context.storage_state(path=str(path))
        return {"ok": True, "path": str(PROJECT_ROOT / path)}

    def cmd_downloads(self, _):
        try:
            self.page.evaluate("() => null")   # pump Playwright events so late download saves land
        except Exception:
            pass
        files = sorted(DOWNLOADS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        return {"ok": True, "files": [str(f) for f in files]}


def _title(p):
    try:
        return p.title()
    except Exception:
        return ""


class Handler(socketserver.StreamRequestHandler):  # runs on the main thread, where Playwright lives
    def handle(self):
        try:
            line = self.rfile.readline()
            if not line:
                return
            cmd = json.loads(line)
            daemon = self.server.daemon
            resp = daemon.handle(cmd)
        except Exception as e:
            resp = {"error": f"{type(e).__name__}: {e}"}
        try:
            self.wfile.write((json.dumps(resp) + "\n").encode())
        except Exception:
            pass


class Server(socketserver.UnixStreamServer):
    # Single-threaded on purpose: Playwright's sync API forbids cross-thread use.
    allow_reuse_address = True


def serve():
    # Refuse to double-start: if a healthy daemon already owns the socket, exit.
    try:
        from cli import send
        if send({"cmd": "ping"}, timeout=3).get("ok"):
            print("daemon already running", flush=True)
            os._exit(0)
    except SystemExit:
        raise
    except Exception:
        pass
    p = socket_path()
    try:
        p.unlink()
    except FileNotFoundError:
        pass
    # FREEBUFF_HEADED: "1"=force headed, "0"=force headless, unset=preference file decides
    env_headed = os.environ.get("FREEBUFF_HEADED")
    headed = None
    if env_headed == "1":
        headed = True
    elif env_headed == "0":
        headed = False
    daemon = BrowserDaemon(headed=headed)
    server = Server(str(p), Handler)
    server.daemon = daemon
    print(f"browser daemon v{VERSION} ready on {p}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    serve()
