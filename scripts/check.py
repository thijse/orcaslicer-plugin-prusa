"""Run every check CI runs, in order: format, lint, types, import contracts, tests.

Usage: uv run python scripts/check.py [--fix]
  --fix  apply Ruff's formatting and safe lint fixes first.
"""

import subprocess
import sys

FIX = "--fix" in sys.argv[1:]
STEPS = [
    ("format", ["ruff", "format"] if FIX else ["ruff", "format", "--check"]),
    ("lint", ["ruff", "check", "--fix"] if FIX else ["ruff", "check"]),
    ("types", ["basedpyright"]),
    ("imports", ["lint-imports"]),
    ("tests", ["pytest", "-q"]),
]

failed = []
for name, cmd in STEPS:
    print(f"== {name}: {' '.join(cmd)}", flush=True)
    if subprocess.run([sys.executable, "-m", *cmd] if cmd[0] == "pytest" else cmd).returncode != 0:
        failed.append(name)
print("== FAILED: " + ", ".join(failed) if failed else "== all checks passed")
sys.exit(1 if failed else 0)
