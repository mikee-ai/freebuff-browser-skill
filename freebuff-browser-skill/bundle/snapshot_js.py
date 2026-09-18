r"""Load the page-JS snippets from snapshot.js — single source for the JS layer.

snapshot.js stays runnable/checkable by Node (node --check), and the daemon
extracts the `const NAME = \`...\`;` template literals at startup.
"""

import re
from pathlib import Path


def load(path) -> dict:
    src = Path(path).read_text(encoding="utf-8")
    snippets = {}
    for m in re.finditer(r"const (\w+) = `([\s\S]*?)`;", src):
        snippets[m.group(1)] = m.group(2)
    if not snippets:
        raise RuntimeError(f"no JS snippets found in {path}")
    return snippets
