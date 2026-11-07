"""Tools: nozzle and filament sync between Orca's presets and the printer, and per-tool material."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from ... import filament_sync
from ...material_swap import printer_type
from ...model import ToolState
from ...preset_sync import compare, preset_to_printer, printer_to_preset
from ..host import LOG, orca
from ..orca_state import filament_slots, printer_preset_nozzles
from .base import TabHandler


def _selected(message: dict[str, Any]) -> set[int]:
    return {int(n) for n in message.get("tools") or []}


class ToolsTab(TabHandler):
    COMMANDS: ClassVar[Mapping[str, str]] = {
        "sync_nozzles": "sync_nozzles",
        "sync_filaments": "sync_filaments",
    }

    def _tools(self) -> list[ToolState]:
        """The printer's tools; empty (and the user told) before the printer reported any."""
        snapshot = self.rt.snapshot
        if snapshot is None or not snapshot.tools:
            self.page.say("No tool data from the printer yet.")
            return []
        return snapshot.tools

    def sync_filaments(self, message: dict[str, Any]) -> None:
        # UI thread: read the slots here; preset writes and Connect calls go to a worker.
        direction = message.get("direction")
        tools = self._tools() if direction in ("to_orca", "to_printer") else []
        if not tools:
            return
        rt, say = self.rt, self.page.say
        slots, colours = filament_slots()
        selected = _selected(message)
        rows = [
            r
            for r in filament_sync.compare(tools, rt.presets, slots, colours)
            if r["tool_number"] in selected and r["slot"] is not None
        ]
        if not rows:
            say("Select at least one tool that has a slicer filament slot.")
            return
        if direction == "to_orca":

            def work() -> None:
                done = []
                for row in rows:
                    if row["preset_differs"]:
                        # Selecting the slot's preset happens in begin_update; there is nothing to stage.
                        tx = orca.host.preset.filament.begin_update(slot_number=row["tool_number"], preset_name=row["match"])
                        try:
                            tx.commit()
                        except Exception:
                            LOG.debug("empty filament commit", exc_info=True)
                        done.append(f"T{row['tool_number']} preset")
                # Orca only lets Script workers set slot colours (orca.host.tools), not a page's threads.
                differ = [f"T{r['tool_number']}" for r in rows if r["color_differs"]]
                note = (
                    (
                        f" Slot colours ({', '.join(differ)}): press Sync in the Device tab's filament area; "
                        "the slicer doesn't let plugin pages set them yet."
                    )
                    if differ
                    else ""
                )
                say(("Updated the slicer: " + ", ".join(done) + "." if done else "Filament presets already match.") + note)
        else:
            mismatched = [r for r in rows if r["type_differs"]]
            rows = [r for r in rows if not r["type_differs"]]
            # Connect refuses a spool of another type than the printer's; that takes an unload and a load.
            skipped = "; ".join(
                f"T{r['tool_number']} has {printer_type(r['printer']['material'])} loaded, the slicer slices {r['slot_type']}"
                for r in mismatched
            )
            skip_note = (
                f" Not recorded: {skipped}. Change the filament on the printer, or use Select filament on the tool."
                if skipped
                else ""
            )

            def work() -> None:
                done = []
                for row in rows:
                    preset = next((p for p in rt.presets if p.name == row["slot"]["preset"]), None)
                    if preset is None or not row["printer"]["loaded"]:
                        continue
                    assigned = rt.assign_tool_material(
                        row["tool_number"] - 1,
                        preset.vendor,
                        preset.name.split("@", 1)[0].strip(),
                        preset.type,
                        row["slot"]["color"],
                    )
                    done.append(f"T{row['tool_number']}: {assigned}")
                say(("Recorded in Prusa Connect: " + "; ".join(done) + "." if done else "Nothing recorded.") + skip_note)

        self.page.in_background(work, "Syncing filaments", kind="command", resource="sync-filaments")

    def sync_nozzles(self, message: dict[str, Any]) -> None:
        # UI thread (page message); the preset write and Connect commands go to workers.
        direction = message.get("direction")
        tools = self._tools() if direction in ("to_preset", "to_printer") else []
        if not tools:
            return
        rt, say = self.rt, self.page.say
        name, diameters, types = printer_preset_nozzles()
        selected = _selected(message)
        rows = [r for r in compare(tools, diameters, types) if r["tool_number"] in selected]
        if not rows:
            say("Select at least one tool.")
            return
        if direction == "to_preset":
            changes = printer_to_preset(rows, diameters, types)
            if not changes:
                say("The printer preset already matches the printer.")
                return

            def work() -> None:
                tx = orca.host.preset.printer.begin_update()
                for key, value in changes.items():
                    tx.set(key, value)
                tx.commit()
                say(f"Updated {name} from the printer. Save the preset to keep it.")

            # Waits for Orca's preset dialogs if any; no deadline.
            self.page.in_background(work, "Updating the printer preset", kind="upload", resource="sync-nozzles")
        else:
            commands = preset_to_printer(rows)
            if not commands:
                say("The printer already matches the preset.")
                return

            def done(errors: list[str]) -> None:
                say("; ".join(errors) if errors else f"Sent {len(commands)} tool setting(s) to the printer.")

            if not rt.run_commands(commands, done, label="Changing tool settings", resource="sync-nozzles"):
                say("Log in to Prusa Connect to change the printer's tool settings.")
