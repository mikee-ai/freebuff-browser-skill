#!/usr/bin/env python3
"""
Freebuff Browser Control — the CLI half.

Parses arguments, talks to the daemon over the unix socket, and renders
results. Spawns daemon.py when needed. Never touches Playwright.
"""

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

VERSION = "1.2.0"
PROJECT_ROOT = Path.cwd()


def socket_path() -> Path:
    import hashlib
    tag = hashlib.sha1(str(PROJECT_ROOT).encode()).hexdigest()[:10]
    return Path(f"/tmp/freebuff-browser-{tag}.sock")


def send(cmd, timeout=60):
    p = socket_path()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(str(p))
    s.sendall((json.dumps(cmd) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
    s.close()
    return json.loads(buf)


def ensure_daemon(headed=None):
    try:
        r = send({"cmd": "ping"}, timeout=5)
        if r.get("version") == VERSION:
            return
        # stale version -> restart
        try:
            send({"cmd": "stop"})
            time.sleep(1)
        except Exception:
            pass
    except Exception:
        pass
    here = Path(__file__).resolve().parent
    env = os.environ.copy()
    if headed is not None:
        env["FREEBUFF_HEADED"] = "1" if headed else "0"
    subprocess.Popen(
        [sys.executable, str(here / "daemon.py"), "serve"],
        cwd=str(PROJECT_ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(60):
        try:
            if send({"cmd": "ping"}, timeout=3).get("ok"):
                return
        except Exception:
            pass
        time.sleep(0.5)
    print("Error: browser daemon failed to start. Try: uv run python browser.py serve", file=sys.stderr)
    sys.exit(1)


USAGE = """Freebuff Browser Control v{v} — commands:

  start [--headed]          start the persistent browser daemon
  stop                      close the browser
  status                    is it running? which tabs are open?
  goto URL                  navigate (auto-adds https://, handles file paths)
  back | forward | reload   history navigation
  snapshot [--json]         interactive elements with [uid] handles (use uids to act)
  text                      full page visible text
  click UID [--double|--right]
  fill UID "text"           clear + type into a field
  select UID "value"        choose <select> option
  check / uncheck UID       toggle checkbox/radio
  hover UID                 hover over element
  press KEY                 press a key on focused element (Enter, Tab, Control+a…)
  scroll [down|up|left|right] [px]
  screenshot [path] [--full]
  eval "js expression"      run JS in the page, get the result
  wait ms | wait selector:.class
  tabs | tab N | tab-new [URL] | tab-close [N]
  logs [--clear]            console messages, network failures, dialogs
  url | title               current page URL / title
  state-save [path]         save cookies+localStorage for reuse
  downloads                 list downloaded files

Typical loop:  goto URL  ->  snapshot  ->  click/fill/select by uid  ->  screenshot
"""


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("help", "-h", "--help"):
        print(USAGE.format(v=VERSION))
        return

    cmd_name, rest = args[0], args[1:]

    unknown = [a for a in rest if a.startswith("--") and a not in ("--headed", "--headless", "--json",
                                                                    "--double", "--right", "--full", "--clear")]
    if unknown:
        print(f"Note: ignoring unknown flag(s): {' '.join(unknown)}", file=sys.stderr)

    if cmd_name == "serve":
        import daemon
        daemon.serve()
        return

    cmd = {"cmd": cmd_name}

    if cmd_name == "start":
        headed = None
        if "--headed" in rest:
            headed = True
        elif "--headless" in rest:
            headed = False
        ensure_daemon(headed=headed)
        print("Browser daemon ready. Try: uv run python browser.py goto example.com")
        return

    if cmd_name == "stop":
        try:
            send({"cmd": "stop"}, timeout=10)
        except Exception:
            pass
        stopped = False
        for _ in range(20):          # wait until it is really gone
            try:
                send({"cmd": "ping"}, timeout=2)
                time.sleep(0.25)
            except Exception:
                stopped = True
                break
        print("Browser stopped." if stopped else "Browser may still be shutting down.")
        return

    if cmd_name == "status":
        try:
            r = send({"cmd": "status"}, timeout=5)
            print(f"Running v{r['version']}, tab {r['current']} of {len(r['pages'])}")
            for i, u in enumerate(r["pages"]):
                print(f"  [{i}] {u}")
        except Exception:
            print("Not running. Start with: uv run python browser.py start")
        return

    ensure_daemon()

    # arg parsing
    flags = [a for a in rest if a.startswith("--")]
    pos = [a for a in rest if not a.startswith("--")]
    for f in flags:
        cmd[f[2:].replace("-", "_")] = True
    if cmd_name in ("goto", "fill", "select", "eval", "press", "wait", "state-save") and pos:
        cmd[{"goto": "url", "fill": "text", "select": "value", "eval": "js",
             "press": "key", "wait": "ms", "state-save": "path"}[cmd_name]] = pos[0]
        if cmd_name == "wait" and not re.fullmatch(r"\d+", pos[0]):
            cmd["selector"] = pos[0]
            del cmd["ms"]
    if cmd_name in ("click", "fill", "select", "check", "uncheck", "hover") and pos:
        cmd["uid"] = pos[0]
        if cmd_name == "fill" and len(pos) > 1:
            cmd["text"] = pos[1]
        if cmd_name == "select" and len(pos) > 1:
            cmd["value"] = pos[1]
    if cmd_name == "scroll" and pos:
        cmd["dir"] = pos[0]
        if len(pos) > 1:
            cmd["amount"] = pos[1]
    if cmd_name in ("tab", "tab-close") and pos:
        cmd["index"] = pos[0]
    if cmd_name == "tab-new" and pos:
        cmd["url"] = pos[0]
    if cmd_name == "screenshot" and pos:
        cmd["path"] = pos[0]

    try:
        timeout = 90 if cmd_name in ("goto", "screenshot", "snapshot") else 45
        r = send(cmd, timeout=timeout)
    except FileNotFoundError:
        print("Error: daemon socket vanished; retry the command.", file=sys.stderr)
        sys.exit(1)

    if r.get("error"):
        print(f"Error: {r['error'].strip()}", file=sys.stderr)
        sys.exit(1)

    if "text" in r:
        print(r["text"])
    elif cmd_name == "tabs":
        for t in r["tabs"]:
            cur = " *" if t["i"] == r["current"] else "  "
            print(f"{cur}[{t['i']}] {t['title'][:60]}  {t['url']}")
    elif cmd_name == "logs":
        for line in r["logs"]:
            print(line)
        if not r["logs"]:
            print("(no console output)")
    elif cmd_name == "downloads":
        for f in r["files"]:
            print(f)
        if not r["files"]:
            print("(none)")
    elif cmd_name == "eval":
        print(json.dumps(r.get("result"), indent=2, ensure_ascii=False))
    elif cmd_name == "screenshot":
        print(f"Saved: {r['path']}")
    elif cmd_name == "state_save":
        print(f"Saved state: {r['path']}")
    else:
        # generic concise output
        out = {k: v for k, v in r.items() if k not in ("ok",)}
        if out:
            print(json.dumps(out, indent=2, ensure_ascii=False))
