---
name: browser-control
description: Drive a real Chromium browser like a human from any thread — persistent daemon with logins/cookies, snapshot-with-uids interaction, click/fill/select, tabs, screenshots, downloads. Use whenever the task involves browsing, form filling, scraping, or verifying web pages.
---

# Browser Control

Drive a real, persistent Chromium via `browser.py` in the project root.
**Never read `browser.py` source to learn the commands — they are all here.**

## Core rules

1. Every command has the form `uv run python browser.py <cmd> [args]` (alias `B`).
2. **Interact by uid, not by CSS.** Take a `snapshot`, pick a `[uid]`, act on it.
   Uids are re-anchored on every snapshot — after navigation or DOM changes,
   snapshot again before the next action.
3. The browser runs as a **daemon**: state (cookies, logins, tabs, scroll
   position) persists across commands. You do NOT need to re-login or re-navigate
   between steps.
4. The engine is split: `browser.py` (shim) → `cli.py` (client) → `daemon.py`
   (Playwright daemon) → `snapshot.js` (page JS). Editing any of them does NOT
   affect a running daemon — run `stop`, then `start` to pick up changes.
5. Run at most **one browser command chain at a time**; the daemon serializes
   requests but a 90s+ hang means it's stuck — run `stop`, then `start` to reset.
6. Run `stop` when finished (it exits cleanly; `status` reports "Not running").

## Command reference

```bash
B="uv run python browser.py"

# Lifecycle
$B start [--headed]     # start daemon (headless default; --headed shows a window)
$B status               # read-only check, no side effects
$B stop

# Navigate
$B goto example.com     # auto-adds https:// ; bare paths open local files
$B back | forward | reload | url | title

# SEE the page
$B snapshot             # interactive elements as [uid] role "name" (attrs)
$B snapshot --json      # machine-readable items
$B text                 # full visible page text (first 60k chars)
$B screenshot [path] [--full]   # PNG; extension optional (.png assumed)
$B logs [--clear]       # console messages, network failures, dialogs
$B wait 3000            # sleep ms — use after clicks that trigger async loads
$B wait selector:.result-row    # wait for an element to appear

# ACT (uids come from the most recent snapshot)
$B click e12 [--double|--right]
$B fill e3 "text"       # clears the field, types with human-like delay
$B select e7 "value"    # <select> options; value from snapshot
$B check e9 | uncheck e9
$B hover e5
$B press Enter          # or Tab, Escape, Control+a, etc.
$B scroll down 800      # down|up|left|right
$B eval "document.title"   # JS expression, returns JSON result

# Tabs
$B tabs                 # list with * marking current
$B tab 1 | tab-new [URL] | tab-close [N]

# Files & state
$B downloads            # files landed in downloads/
$B state-save [path]    # export cookies+localStorage as JSON
```

## The working loop

```bash
B="uv run python browser.py"
$B start
$B goto "https://example.com/form"
$B snapshot                 # read uids — find input fields and buttons
$B fill e3 "Jane Doe"
$B select e5 "pro"
$B check e9
$B click e12                # submit
$B wait 2000 && $B snapshot # verify the result state
$B screenshot result && $B stop
```

## Reading a snapshot

```
[e3] textbox "Your name"  (*required)
[e5] combobox "Free Pro"  (value="free")
[e7] checkbox "on"  (unchecked, type=checkbox)
[e8] button "Submit"
[e9] link "Pricing"  (href=https://example.com/pricing)
```

Pick elements by their `name`/`placeholder`/`value` text, not position — uid
numbers change between snapshots.

Action commands echo what they touched: `{"acted": "input \"key me\"}`.
If the `acted` name is not the element you meant, you picked the wrong uid —
snapshot again rather than forcing the same uid.

## Failure modes

| Symptom | Meaning | Fix |
|---|---|---|
| `no element with uid eN on this page` | uids re-anchored after DOM change | `snapshot` again, use fresh uid |
| `daemon socket vanished; retry` | daemon died mid-call | rerun the command (auto-restarts) |
| click/scroll did nothing | async page updated late | `wait 1500`, re-`snapshot` |
| output frozen 90s+ | daemon stuck (rare) | `stop`, `start`, re-`goto` |
| page looks wrong | you need pixels, not text | `screenshot` and look at it |

## Capabilities & limits

- Login flows work: fill password fields, press Enter, cookies persist in
  `.freebuff-browser-profile/` across daemon restarts. Delete that folder to reset.
- Dialogs (alert/confirm) are auto-accepted and logged to `logs`.
- Downloads land in `downloads/` (list with `$B downloads`).
- Two-factor auth, captchas, and webcam permissions are not solvable — flag to
  the user instead of retrying.
- SPA navigation: `goto` waits for load+networkidle; inside an SPA prefer
  `click` then `wait selector:` rather than `goto`.

## Multi-thread etiquette

The daemon is project-global. If another thread may also be driving it:
- Treat the current tab as shared — `goto` can stomp someone else's page.
- Prefer `tab-new` for your own work, and `tab-close` it when done.
- Snapshot immediately before each action to re-anchor uids.
