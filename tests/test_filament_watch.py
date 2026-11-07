from prusa_orca.filament_watch import Loaded, may_follow, new_loads, slot_mismatches
from prusa_orca.model import ToolState


def tool(n: int, material: str = "", vendor: str = "", name: str = "", loaded: bool = True) -> ToolState:
    return ToolState(index=n - 1, tool_number=n, material=material, vendor=vendor, name=name, is_loaded=loaded)


def test_first_look_is_not_a_load() -> None:
    assert new_loads({}, [tool(1, "PLA")]) == []


def test_type_change_is_a_load() -> None:
    before = {1: Loaded("PLA", "", ""), 2: None}
    found = new_loads(before, [tool(1, "PETG"), tool(2, "PLA"), tool(3, "ASA")])
    assert [(t.tool_number, now.material) for t, now in found] == [(1, "PETG"), (2, "PLA")]


def test_same_type_or_unload_is_not_a_load() -> None:
    before: dict[int, Loaded | None] = {1: Loaded("PLA", "", ""), 2: Loaded("PLA", "", "")}
    assert new_loads(before, [tool(1, "PLA", "Prusament"), tool(2, "PLA", loaded=False)]) == []


def test_related_types_count_as_one() -> None:
    before: dict[int, Loaded | None] = {1: Loaded("PETG", "", "")}
    assert new_loads(before, [tool(1, "PCTG")]) == []


def test_mismatches() -> None:
    tools = [tool(1, "PLA"), tool(2, "PETG"), tool(3, "", loaded=False), tool(4, "FLEX")]
    assert slot_mismatches(tools, ["PLA", "PLA", "ASA", "TPU"]) == [(2, "PETG", "PLA")]


def test_mismatch_without_slot() -> None:
    assert slot_mismatches([tool(1, "PLA"), tool(2, "PLA")], ["PETG"]) == [(1, "PLA", "PETG")]


def test_follow_keeps_user_preset_and_precise_slot() -> None:
    specific = Loaded("PLA", "Prusament", "PLA Galaxy Black")
    menu = Loaded("PLA", "", "")
    assert not may_follow("PLA", True, specific)
    assert not may_follow("PLA", False, menu)
    assert may_follow("PLA", False, specific)
    assert may_follow("PETG", True, menu)
    assert may_follow("", False, menu)
