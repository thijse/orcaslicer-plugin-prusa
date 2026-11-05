# OrcaSlicer plugin for Prusa printers

Connects OrcaSlicer to Prusa Buddy-firmware printers (XL, MK4/MK4S, MK3.5/3.9, MINI, CORE One) through PrusaLink on your network and Prusa Connect, so Orca's Device tab and filament sync work as they do for Bambu printers.

Status: experimental. Developed against a Prusa XL 5T and a development build of OrcaSlicer with the Python plugin API.

## Features

- **Device tab:** status, temperatures, progress, camera (Buddy3D RTSP or Connect snapshots), pause/resume/stop.
- **Send and print** over PrusaLink, with a pre-flight check: model, nozzle diameter, high-flow and hardened nozzles, filament per tool.
- **Filament sync:** the printer's tools show as AMS-style slots; presets are synced in both directions.
- **Nozzle sync** between Orca's printer preset and the printer's tool settings.
- **Prusa tab:**
  - status, camera and controls;
  - files on the printer;
  - filament per tool;
  - print history with snapshots;
  - settings and notifications.
- **Consistency checks:** a LAN/Connect printer mismatch, or an Orca preset for another model.

## Requirements

- An OrcaSlicer build with Python plugin support (capabilities `printer_agent` and `pages`).
- PrusaLink enabled on the printer: its address and password, or an API key.
- Optional: a Prusa Connect account. It provides per-tool materials, controls and camera snapshots.

## Install

Put this folder (or a link to it) in OrcaSlicer's plugin folder, for example on Windows:

```powershell
New-Item -ItemType Junction -Path "$env:APPDATA\OrcaSlicer\orca_plugins\prusa" -Target <path-to-this-repo>
```

Restart OrcaSlicer, enable the plugin, open the **Prusa** tab and fill in **Settings**: the PrusaLink host and password, then log in to Prusa Connect and pick the printer.

## Development

```powershell
python -m pytest tests
```

The layers and conventions are in [docs/architecture.md](docs/architecture.md). Plugin API gaps found along the way are in [docs/upstream-gaps.md](docs/upstream-gaps.md). The scripts in `tools/` drive a running OrcaSlicer through its MCP server; set `ORCASLICER_SRC` to your OrcaSlicer checkout.

## Prusa Connect login

The Connect login currently uses PrusaSlicer's OAuth client. This is a stopgap until the plugin has its own client registration with Prusa.

## License

AGPL-3.0, the same as OrcaSlicer. Not affiliated with Prusa Research.
