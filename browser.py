#!/usr/bin/env python3
"""
Freebuff Browser Control — entrypoint shim.

The engine lives in cli.py (client), daemon.py (Playwright daemon), and
snapshot.js (page JS). This shim keeps `uv run python browser.py <cmd>`
working as documented everywhere. Run `uv run python browser.py help`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli import main  # noqa: E402

if __name__ == "__main__":
    main()
