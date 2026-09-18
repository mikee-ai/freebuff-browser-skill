# Freebuff Browser Control

A free, agent-ready browser toolkit: one persistent Chromium that an AI agent
(or you) can drive exactly like a human — browse, click, type, log in, scroll,
screenshot, download, run JS, manage tabs. Built on **Playwright** (Apache-2.0),
zero paid services.

## Why

Agents need state between steps (logins, cookies, open tabs) and a compact,
re-anchored view of the page. A long-lived daemon holds the real browser
session; each CLI call is one small, reliable action against it.

## Setup

```bash
uv add playwright          # already done
uv run playwright install chromium
uv run python browser.py start          # or: start --headed / start --headless
```

With no flag, `start` honors an installer-created `.freebuff-browser-headed`
preference file if present.

## Commands

```bash
uv run python browser.py help
```

| Command | What it does |
|---|---|
| `goto URL` | Navigate (auto-adds `https://`, opens local files) |
| `snapshot` | List visible interactive elements as `[uid]` handles |
| `click UID` / `fill UID "txt"` | Act on a snapshot uid (response echoes what was acted on) |
| `select UID "v"` / `check` / `uncheck` / `hover` | Form controls |
| `press KEY` / `scroll down 800` | Keyboard + mouse wheel |
| `screenshot [path] [--full]` | PNG into `shots/` |
| `text` / `eval "js"` | Read page text / run JavaScript |
| `tabs` / `tab N` / `tab-new` / `tab-close` | Tab management |
| `logs` | Console errors, failed network requests, dialogs |
| `back` / `forward` / `reload` / `wait` | Navigation helpers |
| `state-save` | Export cookies + localStorage |
| `downloads` | Files saved to `downloads/` |
| `stop` | Quit the browser |

## The agent loop

1. `goto` a URL
2. `snapshot` — every actionable element gets a `uid`
3. Act: `click e12`, `fill e3 "hello"`, `select e7 "CA"`…
4. Re-`snapshot` after navigation (uids are re-anchored each time)
5. `screenshot` when you need to *see* it; `logs` when something misbehaves

Human-like details: fields are typed with keystroke delays, elements are
scrolled into view before clicking, `navigator.webdriver` is hidden, and
dialogs are auto-accepted (logged to `logs`).

## Profile

The browser keeps a real profile in `.freebuff-browser-profile/`, so logins
and cookies survive restarts. Delete that folder to reset to a clean browser.
Run `start --headed` to watch the browser on screen instead of headless.
