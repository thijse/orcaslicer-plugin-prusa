"""Watches the printer's tools against the slicer's filament slots and tells the user, from the Prusa tab's push.

- A tool got another material loaded: a notification offers to use it for slicing ("Use in slot N"), and a link
  opens the Prusa tab's filament finder for that tool to pick the exact spool. With "Follow the printer" on, the
  slot is set without asking, except where filament_watch.may_follow says no.
- A slot slices another material type than its tool has loaded: one warning per mismatch, again after it changes.

Runs on the UI thread (the page push reads the slots there); preset changes go to a worker task.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..filament_watch import Loaded, may_follow, new_loads, slot_mismatches
from ..materials import FilamentPreset, match_preset
from ..model import ToolState
from ..tasks import TaskBusy
from .host import LOG, orca
from .runtime import Runtime


def _type_of(name: str, presets: list[FilamentPreset]) -> str:
    return next((p.type for p in presets if p.name == name), "")


def _is_user(name: str) -> bool:
    preset = orca.host.preset_bundle().filaments.find_preset(name) if name else None
    return bool(preset is not None and preset.is_user())


class FilamentWatch:
    def __init__(self, rt: Runtime, open_finder: Callable[[int], None]) -> None:
        self.rt = rt
        self.open_finder = open_finder
        self._seen: dict[int, Loaded | None] = {}
        self._warned: set[tuple[int, str, str]] = set()

    def check(self, tools: list[ToolState], slots: list[str]) -> None:
        presets = self.rt.presets
        if not presets:
            return
        planned = set(self.rt.swaps)
        for tool, loaded in new_loads(self._seen, tools):
            # A change the plugin started records the spool itself (Runtime._finish_swaps).
            if tool.tool_number not in planned:
                self._loaded(tool, loaded, slots, presets)
        self._seen = {t.tool_number: Loaded.of(t) for t in tools}
        self._mismatches(tools, [_type_of(s, presets) for s in slots])

    def _loaded(self, tool: ToolState, loaded: Loaded, slots: list[str], presets: list[FilamentPreset]) -> None:
        n = tool.tool_number
        slot = slots[n - 1] if n - 1 < len(slots) else ""
        match = match_preset(tool, presets)
        follow = bool(self.rt.settings.values.get("filament", {}).get("follow_printer"))
        if slot and match is not None and match.name == slot:
            return
        if follow and match is not None and slot and may_follow(_type_of(slot, presets), _is_user(slot), loaded):
            self._set_slot(n, match.name, f"T{n} has {loaded.label} loaded; slot {n} now slices with {match.name}.")
            return
        text = f"T{n} now has {loaded.label} loaded."
        if match is None:
            self._notify(f"{text} No slicer preset matches it yet.", "Find a filament", lambda: self.open_finder(n))
            return
        self._notify(
            f"{text} Slot {n} slices with {slot or 'nothing'}.",
            f"Use {match.name} in slot {n}",
            lambda: self._set_slot(n, match.name, f"Slot {n} now slices with {match.name}."),
        )
        self._notify(f"Pick the exact spool for T{n} from the filament list.", "Choose filament", lambda: self.open_finder(n))

    def _mismatches(self, tools: list[ToolState], slot_types: list[str]) -> None:
        current = set(slot_mismatches(tools, slot_types))
        for n, loaded, slot in sorted(current - self._warned):
            self._notify(
                f"Slot {n} slices {slot}, but T{n} has {loaded} loaded. The printer will warn at print start.",
                "Choose filament",
                lambda n=n: self.open_finder(n),
                warning=True,
            )
        self._warned = current

    def _set_slot(self, slot: int, preset: str, done: str) -> bool:
        def work() -> None:
            tx = orca.host.preset.filament.begin_update(slot_number=slot, preset_name=preset)
            try:
                tx.commit()
            except Exception:
                LOG.debug("empty filament commit", exc_info=True)
            self._notify(done, "", None)

        try:
            self.rt.tasks.submit(f"Slot {slot}: {preset}", work, kind="command", resource=f"slot-{slot}")
        except TaskBusy:
            LOG.info("slot %d is already being set", slot)
        return True

    @staticmethod
    def _notify(text: str, link: str, on_click: Callable[[], Any] | None, warning: bool = False) -> None:
        LOG.info("%s", text)
        if orca is None:
            return
        ui = orca.host.ui
        level = ui.NotificationLevel.WarningNotificationLevel if warning else ui.NotificationLevel.RegularNotificationLevel

        def click() -> bool:
            if on_click is not None:
                on_click()
            return True

        try:
            ui.push_notification(level, f"Prusa: {text}", link, click if on_click is not None else None)
        except Exception:
            LOG.exception("notification failed")
