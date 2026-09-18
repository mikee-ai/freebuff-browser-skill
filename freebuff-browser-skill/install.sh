#!/usr/bin/env bash
# Freebuff Browser Control — one-shot installer
# Drops the skill + engine into the current project and installs everything.
# Usage: bash install.sh            (default: free, fully headless)
#        bash install.sh --headed   (browser windows visible — great for demos)

set -euo pipefail

HEADED="0"
for arg in "$@"; do
  case "$arg" in
    --headed) HEADED="1" ;;
    *) echo "Unknown option: $arg (supported: --headed)"; exit 1 ;;
  esac
done

say()  { printf '\033[1;36m==>\033[0m %s\n' "$1"; }
fail() { printf '\033[1;31m==>\033[0m %s\n' "$1" >&2; exit 1; }

# 0. Locate this package's bundle/ — works whether you run install.sh from
#    inside the package or by path from anywhere else.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if   [ -f "bundle/browser.py" ];        then PKG="$(pwd)"
elif [ -f "$SCRIPT_DIR/bundle/browser.py" ]; then PKG="$SCRIPT_DIR"
else fail "Could not find bundle/browser.py next to install.sh or in the current folder."
fi

# 0b. Find the project root: walk up for a marker file, else use the package dir.
ROOT="$(pwd)"
d="$(pwd)"
while [ "$d" != "/" ]; do
  for marker in pyproject.toml package.json .git Cargo.toml go.mod; do
    if [ -e "$d/$marker" ]; then ROOT="$d"; break 2; fi
  done
  d="$(dirname "$d")"
done
say "Installing into project root: $ROOT"
[ "$ROOT" = "$PKG" ] || cd "$ROOT"   # run everything else from the project root

# 1. Find a package manager
PM=""
if command -v uv >/dev/null 2>&1; then PM="uv";
elif command -v pip3 >/dev/null 2>&1; then PM="pip3";
elif command -v pip >/dev/null 2>&1; then PM="pip";
else
  say "No uv/pip found — installing uv (free, single binary)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null 2>&1 || fail "uv install failed — install Python 3.10+ and pip, then rerun."
  PM="uv"
fi
say "Using package manager: $PM"

# 2. Drop files into the project root
mkdir -p "$ROOT/.codebuff/skills/browser-control"
cp "$PKG/bundle/SKILL.md" "$ROOT/.codebuff/skills/browser-control/SKILL.md"
for f in browser.py cli.py daemon.py snapshot.js snapshot_js.py; do
  cp "$PKG/bundle/$f" "$ROOT/$f"
done
[ -f "$ROOT/README.md" ] || cp "$PKG/bundle/README.md" "$ROOT/README.md"
say "Installed skill  -> .codebuff/skills/browser-control/SKILL.md"
say "Installed engine -> browser.py + cli.py + daemon.py + snapshot.js"

# 3. Dependencies (idempotent; safe to rerun)
say "Installing Playwright (free, Apache-2.0)..."
install_with_uv() {
  [ -f pyproject.toml ] || uv init --bare >/dev/null 2>&1 || true
  uv add playwright
  say "Downloading Chromium (~150 MB, one time)..."
  uv run playwright install chromium
  PYRUN="uv run python"
}
if [ "$PM" = "uv" ]; then
  install_with_uv
else
  PYRUN="python3"
  say "Installing Playwright with pip..."
  if python3 -m pip install playwright 2>&1 | tail -n 4 && python3 -c "import playwright" 2>/dev/null; then
    say "Downloading Chromium (~150 MB, one time)..."
    python3 -m playwright install chromium \
      || fail "Chromium download failed (network hiccup?) - rerun install.sh to retry."
  else
    say "pip refused or incomplete (often PEP 668 'externally-managed-environment')."
    say "Self-healing: installing uv (isolated Python - no sudo, no system changes)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 \
      || fail "Could not bootstrap uv. Install Python 3.10+ with a writable pip, then rerun install.sh."
    install_with_uv
    PM="uv"
  fi
fi

# 4. Record the headed preference
if [ "$HEADED" = "1" ]; then echo "1" > "$ROOT/.freebuff-browser-headed"; fi
say "Preference saved: $([ "$HEADED" = "1" ] && echo headed || echo headless) browser"

# 5. Smoke test: real browser, real page, real click
say "Smoke testing..."
cat > .fb-install-test.html <<'HTML'
<!doctype html><html><head><title>fb-test</title></head><body>
<button onclick="document.getElementById('o').textContent='WORKS'">Go</button>
<p id="o">nope</p></body></html>
HTML
R="$PYRUN"
$R browser.py start
$R browser.py goto .fb-install-test.html
$R browser.py snapshot | grep button >/dev/null
$R browser.py click e1
OUT=$($R browser.py text | grep -c WORKS || true)
$R browser.py stop >/dev/null 2>&1
rm -f .fb-install-test.html
[ "$OUT" -ge 1 ] || fail "Smoke test failed — run: $R browser.py start && $R browser.py goto example.com"
say "Smoke test passed (browser opened a page and clicked a button)."

cat <<EOF

  ✓ Freebuff Browser Control is installed.

  Any Codebuff agent thread in this project can now use the browser.
  Try saying:

    "Use the browser to open example.com and screenshot it"
    "Fill the contact form at http://localhost:3000/contact and submit it"

  Manual control:
    $R browser.py help

EOF
