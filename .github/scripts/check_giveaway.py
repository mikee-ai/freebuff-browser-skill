#!/usr/bin/env python3
"""Fail if the giveaway has drifted from the live engine.

The bundle inside freebuff-browser-skill/ is a hand-kept copy of the engine, and
freebuff-browser-skill.zip is a copy of that copy. Nothing else keeps them in
sync, so this check is the sync: change an engine file and forget to rebuild the
giveaway, and this fails naming the exact file that drifted.
"""
import pathlib
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
PKG = ROOT / "freebuff-browser-skill"
ZIP = ROOT / "freebuff-browser-skill.zip"
PREFIX = "freebuff-browser-skill/"

# zip entry (below the prefix) -> the live file it must be identical to
EXPECTED = {
    "LICENSE": PKG / "LICENSE",
    "install.sh": PKG / "install.sh",
    "INSTALL.md": PKG / "INSTALL.md",
    "bundle/README.md": ROOT / "README.md",
    "bundle/SKILL.md": ROOT / ".codebuff/skills/browser-control/SKILL.md",
    "bundle/browser.py": ROOT / "browser.py",
    "bundle/cli.py": ROOT / "cli.py",
    "bundle/daemon.py": ROOT / "daemon.py",
    "bundle/snapshot.js": ROOT / "snapshot.js",
    "bundle/snapshot_js.py": ROOT / "snapshot_js.py",
}


def rel(path):
    return path.relative_to(ROOT)


def main():
    if not ZIP.exists():
        print(f"FAIL missing giveaway zip: {rel(ZIP)}")
        return 1

    with zipfile.ZipFile(ZIP) as zf:
        in_zip = {
            name[len(PREFIX):]: zf.read(name)
            for name in zf.namelist()
            if not name.endswith("/")
        }

    problems = []
    for entry, source in EXPECTED.items():
        if not source.exists():
            problems.append(f"FAIL missing source file: {rel(source)}")
            continue
        want = source.read_bytes()

        have = in_zip.get(entry)
        if have is None:
            problems.append(f"FAIL zip is missing entry: {PREFIX}{entry}")
        elif have != want:
            problems.append(f"FAIL zip is stale: {PREFIX}{entry} != {rel(source)}")

        # the copy unpacked inside the package must match the live file too
        if entry.startswith("bundle/"):
            on_disk = PKG / entry
            if not on_disk.exists():
                problems.append(f"FAIL missing package file: {rel(on_disk)}")
            elif on_disk.read_bytes() != want:
                problems.append(f"FAIL bundle is stale: {rel(on_disk)} != {rel(source)}")

    for entry in sorted(set(in_zip) - set(EXPECTED)):
        problems.append(f"FAIL unexpected zip entry: {PREFIX}{entry}")

    if problems:
        print("The giveaway is out of sync with the live engine:\n")
        print("\n".join(problems))
        print(
            "\nRebuild it from the repo root:\n"
            "  zip -r freebuff-browser-skill.zip freebuff-browser-skill "
            "-x '*.DS_Store' '*__pycache__*'"
        )
        return 1

    print(f"Giveaway in sync: {len(EXPECTED)} files match the live engine (package + zip).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
