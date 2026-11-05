"""Raise the version, check, commit, push and tag; the Release workflow then publishes prusa_plugin.whl.

Usage: uv run python scripts/release.py KIND [--dry-run]
  beta    0.3.0b1 -> 0.3.0b2, or 0.3.0 -> 0.3.1b1   (pre-release)
  rc      0.3.0b2 -> 0.3.0rc1, 0.3.0rc1 -> 0.3.0rc2  (pre-release)
  patch   0.3.0b2 -> 0.3.0, 0.3.0 -> 0.3.1
  minor   0.3.1 -> 0.4.0
  major   0.4.0 -> 1.0.0
  X.Y.Z[bN|rcN]   an explicit version
--dry-run shows the new version and changes nothing.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?$")
# Where the version is written: file, then the text before and after it.
PLACES = [
    ("pyproject.toml", 'version = "', '"'),
    ("prusa_plugin.py", '# version = "', '"'),
    ("prusa_orca/app/host.py", '__version__ = "', '"'),
]


def fail(message: str) -> None:
    sys.exit(f"release: {message}")


def run(*cmd: str, capture: bool = False) -> str:
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=capture)
    if result.returncode != 0:
        fail(f"'{' '.join(cmd)}' failed{': ' + result.stderr.strip() if capture else ''}")
    return result.stdout.strip() if capture else ""


def current_version() -> str:
    found = set()
    for name, before, after in PLACES:
        match = re.search(re.escape(before) + r"([^\"]+)" + re.escape(after), (ROOT / name).read_text(encoding="utf-8"))
        if match is None:
            fail(f"no version found in {name}")
        found.add(match.group(1))
    if len(found) != 1:
        fail(f"the version differs between files: {sorted(found)}")
    return found.pop()


def next_version(current: str, kind: str) -> str:
    match = VERSION.match(current)
    if match is None:
        fail(f"can't parse the current version {current!r}")
    major, minor, patch = (int(match.group(i)) for i in (1, 2, 3))
    pre, num = match.group(4), int(match.group(5) or 0)
    base = f"{major}.{minor}.{patch}"
    if kind == "beta":
        if pre == "b":
            return f"{base}b{num + 1}"
        if pre is None:
            return f"{major}.{minor}.{patch + 1}b1"
        fail(f"{current} is already past beta; use rc or patch")
    if kind == "rc":
        return f"{base}rc{num + 1}" if pre == "rc" else f"{base}rc1"
    if kind == "patch":
        return base if pre else f"{major}.{minor}.{patch + 1}"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    if kind == "major":
        return f"{major + 1}.0.0"
    if VERSION.match(kind):
        return kind
    fail(f"unknown kind {kind!r}; see the usage at the top of scripts/release.py")
    return ""


def write_version(old: str, new: str) -> None:
    for name, before, after in PLACES:
        path = ROOT / name
        data = path.read_bytes().decode("utf-8")
        updated = data.replace(before + old + after, before + new + after, 1)
        if updated == data:
            fail(f"could not update {name}")
        path.write_bytes(updated.encode("utf-8"))


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    if len(args) != 1:
        sys.exit(__doc__)
    old = current_version()
    new = next_version(old, args[0])
    pre = re.search(r"(a|b|rc)\d+$", new) is not None
    print(f"{old} -> {new} ({'pre-release' if pre else 'release'})")
    if "--dry-run" in sys.argv:
        return

    if run("git", "status", "--porcelain", capture=True):
        fail("commit or stash your changes first")
    if run("git", "rev-parse", "--abbrev-ref", "HEAD", capture=True) != "main":
        fail("release from the main branch")
    if run("git", "tag", "--list", f"v{new}", capture=True):
        fail(f"tag v{new} already exists")
    run("git", "fetch", "--quiet", "origin")
    if run("git", "rev-list", "--count", "HEAD..origin/main", capture=True) != "0":
        fail("origin/main has commits you don't have; pull first")

    write_version(old, new)
    run("uv", "lock", "--quiet")
    run("uv", "run", "python", "scripts/check.py")
    run("uv", "run", "python", "scripts/build_wheel.py")
    run("git", "add", "-A")
    run("git", "commit", "--quiet", "-m", f"Release {new}")
    run("git", "tag", "-a", f"v{new}", "-m", f"Release {new}")
    run("git", "push", "--quiet", "origin", "main", f"v{new}")
    print(
        f"pushed v{new}; the Release workflow publishes it at https://github.com/thijse/orcaslicer-plugin-prusa/releases/tag/v{new}"
    )


if __name__ == "__main__":
    main()
