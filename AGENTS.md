# Prusa for OrcaSlicer — agent guide

OrcaSlicer plugin (Python) for Prusa Buddy printers over PrusaLink and Prusa Connect. User-facing overview: [README.md](README.md). Design: [docs/architecture.md](docs/architecture.md). Gaps in Orca's plugin API: [docs/upstream-gaps.md](docs/upstream-gaps.md).

Orca's plugin contract: [Plugin System Overview](https://github.com/OrcaSlicer/OrcaSlicer/wiki/plugin_system), [Plugin Development](https://github.com/OrcaSlicer/OrcaSlicer/wiki/plugin_development), [Printer Agent](https://github.com/OrcaSlicer/OrcaSlicer/wiki/printer_agent), [Pages](https://github.com/OrcaSlicer/OrcaSlicer/wiki/pages), [Plugin Audit Hook](https://github.com/OrcaSlicer/OrcaSlicer/wiki/plugin_audit_hook). Keep the plugin name, the capability names (`prusa3d_plugin`, `Prusa`) and the agent ID stable, because presets store them.

## Commands

```sh
uv sync                                  # dev tools from uv.lock
uv run python scripts/check.py           # everything CI runs: format, lint, types, import contracts, tests
uv run python scripts/check.py --fix     # apply Ruff formatting and safe fixes first
uv run pytest tests/test_core.py -q      # one test file
uv run python scripts/build_wheel.py     # build and check dist/prusa_plugin.whl
```

The wheel must stay named `prusa_plugin.whl`: OrcaSlicer keys a local plugin by its file stem, and that key names the settings folder and is what presets store. The version is in three places that `build_wheel.py` checks against each other: `pyproject.toml`, the PEP 723 header in `prusa_plugin.py`, and `__version__` in `prusa_orca/app/host.py`.

Run `scripts/check.py` before you report a change as done, and fix what it reports.

## Rules for changes

- **Fix failures; don't weaken the checks.** No `# type: ignore`, `# pyright: ignore`, `noqa`, `cast(Any, ...)`, skipped or deleted tests, loosened assertions, or edits to the Ruff, basedpyright or import-linter settings to get green. If a suppression or a changed expectation is really right, say so in your reply and explain why. The maintainer reviews these explicitly.
- **The plugin runs on OrcaSlicer's embedded Python with the standard library only.** Nothing outside the standard library may be imported under `prusa_orca/` or in `prusa_plugin.py` (`tests/test_layers.py` checks it). Dev-only packages go in the `dev` or `tools` group in `pyproject.toml`.
- **Keep the layers** (enforced by `lint-imports` and `tests/test_layers.py`):
  - **Core** (`prusa_orca/*.py`): pure logic; no network and no `orca`.
  - **Backends** (`prusa_orca/backends/`): HTTP to the printer and Connect.
  - **UI** (`prusa_orca/ui/`): the page HTML/JS and its art.
  - **App** (`prusa_orca/app/`): the only code that touches Orca, through `app.host.orca`.
  
  Logic that can be tested without Orca belongs in the core.
- **Treat every printer, Connect and settings JSON as untrusted.** Read it through `prusa_orca/jsonview.py` (`obj`, `objs`) or with `isinstance` checks, and keep the existing defaults; firmware and server versions differ.
- **Threads:** Orca calls page messages and preset reads on its UI thread, so never wait on the network there. Network work runs in a `TaskRunner` task (`page.in_background`, `runtime.run_commands`), which gives the busy bar, timeouts and one action per resource.
- **Behaviour changes need a test.** For parsing and decisions, add a unit test in `tests/` with small inline data or an anonymised fixture in `tests/fixtures/`.
- **Every command the page sends needs a handler** in an `app/pages/*` class's `COMMANDS` table; `tests/test_app_wiring.py` checks this.

## Safety and privacy

- **Never start a print, move axes, change temperatures or send printer commands while testing without the user's explicit OK.** Reading status, files and snapshots is fine.
- **Never commit:**
  - personal data: real IPs, serial numbers, printer UUIDs, names, tokens, camera images of rooms;
  - anything under `tests/fixtures/raw/` (it's gitignored, and it holds real API captures);
  - Orca's plugin data folder.
  
  Anonymise data before adding it as a fixture.
- **The Prusa Connect login uses PrusaSlicer's OAuth client ID** (`backends/connect.py`). Don't spread it to new places.

## Running the plugin in OrcaSlicer

The plugin is linked into `%APPDATA%\OrcaSlicer\orca_plugins\prusa` and needs an OrcaSlicer build with the Python plugin API. The scripts in `tools/` drive a running OrcaSlicer through its MCP server; they need `ORCASLICER_SRC` and the `tools` dependency group (`uv sync --group tools`):

- `tools/page_eval.py "<js>"`: evaluate JavaScript in the Prusa tab.
- `tools/shot_pages.py OUT_DIR status files filament history settings`: screenshots of the Prusa tab's pages.
- `tools/readme_shots.py docs/images`: README screenshots with personal data masked.

After changing Python code, restart OrcaSlicer: plugins load once at startup.
