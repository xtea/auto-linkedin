#!/usr/bin/env python3
"""Bump the version in pyproject.toml.

Usage:
    scripts/bump.py patch       # 0.1.1 -> 0.1.2
    scripts/bump.py minor       # 0.1.1 -> 0.2.0
    scripts/bump.py major       # 0.1.1 -> 1.0.0
    scripts/bump.py 0.2.0       # explicit version

`__version__` is read from package metadata at runtime, so this script
only touches pyproject.toml. After bumping, it prints the git commands
to commit + tag + push — execute those yourself once you've reviewed
the diff.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"

VERSION_RE = re.compile(r'^(version = ")([^"]+)(")', re.MULTILINE)
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def read_current() -> str:
    text = PYPROJECT.read_text()
    m = VERSION_RE.search(text)
    if not m:
        sys.exit("Could not find `version = \"...\"` in pyproject.toml")
    return m.group(2)


def write_new(new_version: str) -> None:
    text = PYPROJECT.read_text()
    new_text, n = VERSION_RE.subn(rf'\g<1>{new_version}\g<3>', text, count=1)
    if n != 1:
        sys.exit("Failed to substitute version line in pyproject.toml")
    PYPROJECT.write_text(new_text)


def bump(current: str, kind: str) -> str:
    if SEMVER_RE.match(kind):
        return kind
    m = SEMVER_RE.match(current)
    if not m:
        sys.exit(
            f"Current version '{current}' is not a plain X.Y.Z semver — "
            "pass an explicit version instead of a bump kind."
        )
    major, minor, patch = (int(g) for g in m.groups())
    if kind == "patch":
        patch += 1
    elif kind == "minor":
        minor += 1
        patch = 0
    elif kind == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        sys.exit(f"Unknown bump kind: {kind!r}. Use patch | minor | major | <X.Y.Z>")
    return f"{major}.{minor}.{patch}"


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    current = read_current()
    new = bump(current, sys.argv[1])
    if new == current:
        sys.exit(f"No-op: version is already {current}")

    write_new(new)

    print(f"pyproject.toml: {current} -> {new}\n")
    print("Diff:")
    subprocess.run(["git", "--no-pager", "diff", "pyproject.toml"], cwd=ROOT, check=False)
    print("\nNext steps:\n")
    print(f"  git commit -am 'Release v{new}'")
    print(f"  git tag v{new}")
    print(f"  git push origin main v{new}")
    print("\nThe publish workflow takes over from there.")


if __name__ == "__main__":
    main()
