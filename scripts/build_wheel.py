"""Build the plugin wheel and check it against the rules OrcaSlicer applies when it installs one.

Usage: uv run python scripts/build_wheel.py
Writes dist/prusa_plugin.whl.

OrcaSlicer keys a locally installed plugin by its file stem: that key names the settings folder
(orca_plugins/plugin_data/<key>) and is what printer presets store ("prusa_plugin;;prusa3d_plugin").
The standard wheel file name carries the version, so every release would get a new key. The wheel
is therefore shipped as prusa_plugin.whl, the same key as the single-file prusa_plugin.py.
"""

import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PLUGIN_FILE = DIST / "prusa_plugin.whl"
ENTRY_MODULE = "prusa_plugin"


def fail(message: str) -> None:
    sys.exit(f"wheel check failed: {message}")


def headers(text: str) -> dict[str, str]:
    """The RFC 822 headers before the first blank line."""
    out: dict[str, str] = {}
    for line in text.split("\n\n", 1)[0].splitlines():
        key, _, value = line.partition(":")
        out.setdefault(key.strip().lower(), value.strip())
    return out


def check(wheel: Path, version: str) -> None:
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        dist_infos = {n.split("/", 1)[0] for n in names if n.split("/", 1)[0].endswith(".dist-info")}
        if len(dist_infos) != 1:
            fail(f"expected one .dist-info, found {sorted(dist_infos)}")
        dist_info = dist_infos.pop()
        for required in ("METADATA", "WHEEL", "RECORD"):
            if f"{dist_info}/{required}" not in names:
                fail(f"{dist_info}/{required} is missing")

        meta = headers(z.read(f"{dist_info}/METADATA").decode())
        if meta.get("version") != version:
            fail(f"METADATA Version {meta.get('version')!r} is not {version!r}")
        if meta.get("import-name") != ENTRY_MODULE:
            fail(f"METADATA Import-Name {meta.get('import-name')!r} is not {ENTRY_MODULE!r}")

        tags = [line[4:].strip() for line in z.read(f"{dist_info}/WHEEL").decode().splitlines() if line.startswith("Tag:")]
        if not tags or not all(tag.endswith("-none-any") for tag in tags):
            fail(f"not a pure-Python wheel: {tags}")

        entry = f"{ENTRY_MODULE}.py"
        if entry not in names or "@orca.plugin" not in z.read(entry).decode():
            fail(f"{entry} with the @orca.plugin class is missing")
        if not any(n.startswith("prusa_orca/ui/assets/") for n in names):
            fail("the UI assets are missing")
        stray = [n for n in names if n != entry and not n.startswith(("prusa_orca/", dist_info))]
        if stray:
            fail(f"unexpected files: {stray}")


def main() -> None:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    header = re.search(r'^# version = "([^"]+)"', (ROOT / f"{ENTRY_MODULE}.py").read_text(encoding="utf-8"), re.M)
    if header is None or header.group(1) != version:
        fail(f"the PEP 723 version in {ENTRY_MODULE}.py does not match pyproject.toml ({version})")
    if f'__version__ = "{version}"' not in (ROOT / "prusa_orca" / "app" / "host.py").read_text(encoding="utf-8"):
        fail(f"__version__ in prusa_orca/app/host.py does not match pyproject.toml ({version})")

    for old in DIST.glob("*.whl"):
        old.unlink()
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(DIST)], cwd=ROOT, check=True)
    built = next(DIST.glob(f"*-{version}-py3-none-any.whl"))
    check(built, version)
    shutil.move(built, PLUGIN_FILE)
    print(f"built {PLUGIN_FILE.relative_to(ROOT)} (version {version})")


if __name__ == "__main__":
    main()
