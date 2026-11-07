"""What changed on the printer's tools and how it relates to the slicer's filament slots (tool N = slot N).

Pure logic for two notifications: a tool got another material loaded (offer to use it for slicing, or follow the
printer when the user turned that on), and a slot slices another material type than its tool has loaded.
"""

from __future__ import annotations

from dataclasses import dataclass

from .material_swap import printer_type, type_change
from .model import ToolState


@dataclass(frozen=True)
class Loaded:
    """What a tool reports as loaded, enough to tell a real load from a poll that saw the same spool."""

    material: str
    vendor: str
    name: str

    @staticmethod
    def of(tool: ToolState) -> Loaded | None:
        if not tool.is_loaded or not tool.material:
            return None
        return Loaded(printer_type(tool.material), tool.vendor, tool.name)

    @property
    def specific(self) -> bool:
        """A brand or product name, not only the type a menu load leaves."""
        return bool(self.vendor or self.name)

    @property
    def label(self) -> str:
        return " ".join(x for x in (self.vendor, self.name) if x) or self.material


def new_loads(before: dict[int, Loaded | None], tools: list[ToolState]) -> list[tuple[ToolState, Loaded]]:
    """Tools whose material type changed since `before` (a load); the first look at a tool is not a load."""
    out: list[tuple[ToolState, Loaded]] = []
    for tool in tools:
        if tool.tool_number not in before:
            continue
        now, was = Loaded.of(tool), before[tool.tool_number]
        if now is not None and (was is None or was.material != now.material):
            out.append((tool, now))
    return out


def slot_mismatches(tools: list[ToolState], slot_types: list[str]) -> list[tuple[int, str, str]]:
    """(tool number, loaded type, slot type) for slots that slice another material type than their tool has loaded."""
    out: list[tuple[int, str, str]] = []
    for tool in tools:
        i = tool.tool_number - 1
        loaded = Loaded.of(tool)
        if loaded is None or i >= len(slot_types) or not slot_types[i]:
            continue
        if type_change(loaded.material, slot_types[i]):
            out.append((tool.tool_number, loaded.material, printer_type(slot_types[i])))
    return out


def may_follow(slot_type: str, slot_is_user_preset: bool, loaded: Loaded) -> bool:
    """Whether following the printer may replace the slot's preset without asking.

    Never replace a tuned user preset of the same type, and never let a type-only record replace a slot that already
    slices that type (the slot is the more precise of the two).
    """
    same_type = not type_change(loaded.material, slot_type) if slot_type else False
    return not (same_type and (slot_is_user_preset or not loaded.specific))
