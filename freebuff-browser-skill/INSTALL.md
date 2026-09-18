# Freebuff Browser Control — Giveaway Package

Give any Codebuff project a real browser it can drive like a human: browse,
click, fill forms, log in, screenshot, download. 100% free and local — no
accounts, no API keys, no paid services. Built on Playwright (Apache-2.0).

## What's in the box

```
freebuff-browser-skill/
├── INSTALL.md            ← you are here
├── install.sh            ← the one-command installer
└── bundle/
    ├── SKILL.md          ← the Codebuff skill (how agents use the browser)
    ├── browser.py        ← entrypoint shim (keep using `uv run python browser.py …`)
    ├── cli.py            ← CLI client (args, socket protocol, output)
    ├── daemon.py         ← the engine (persistent Chromium daemon)
    ├── snapshot.js       ← page-injection JS (snapshot/text/describe)
    ├── snapshot_js.py    ← JS loader
    └── README.md         ← full docs
```

## Install (one command)

1. Unzip this folder **inside your project root** (same folder as your `pyproject.toml`/`package.json`/repo root).
2. Run:

```bash
bash install.sh
```

That's it. The installer:

- drops the skill into `.codebuff/skills/browser-control/SKILL.md`
- drops the engine at `browser.py`
- installs Playwright + Chromium via `uv` or `pip` (whichever you have); if `pip` refuses
  (PEP 668 "externally-managed" systems like Homebrew Python), the installer self-heals
  by bootstrapping `uv` — no sudo needed
- runs a real smoke test — the browser opens a page and clicks a button
- cleans up after itself

Prefer to watch the browser on screen? `bash install.sh --headed` saves that
preference so future `start`s open visible windows.

## What your agents get

Once installed, any Codebuff thread in that project can be told, in plain language:

- "Open example.com and screenshot it"
- "Fill the signup form at localhost:3000/signup with test data and submit"
- "Log into GitHub with my saved session, go to my repo, and summarize open issues"
- "Download the PDF from this page and check its filename"

The skill teaches agents the whole interface: `goto`, `snapshot` (every
clickable/typable element gets a `uid`), `click`/`fill`/`select`/`check`,
tabs, screenshots, `eval` JS, downloads, console/network logs, and more.

## Manual control (no agent needed)

```bash
uv run python browser.py help          # every command
uv run python browser.py start
uv run python browser.py goto example.com
uv run python browser.py screenshot
uv run python browser.py stop
```

## Requirements

- macOS, Linux, or Windows (bash available via Git Bash / WSL on Windows)
- Python 3.9+ (installer fetches `uv` if you have no Python tooling)
- ~150 MB disk for Chromium (downloaded once, reused forever)

## Uninstall

```bash
rm browser.py cli.py daemon.py snapshot.js snapshot_js.py .freebuff-browser-headed
rm -rf .codebuff/skills/browser-control .freebuff-browser-profile shots downloads
```

(Leave Chromium in the OS cache if other tools use Playwright; remove
`~/Library/Caches/ms-playwright` on macOS or `~/.cache/ms-playwright` on
Linux/Windows to free the ~150 MB.)

## License

MIT — free to give away, modify, and share. 
