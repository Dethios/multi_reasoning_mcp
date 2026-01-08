from pathlib import Path

from multi_reasoning_mcp.modes_registry import ModesRegistry


def test_modes_registry_loads():
    root = Path(__file__).resolve().parents[1]
    registry = ModesRegistry(root / "modes" / "modes.yaml")
    registry.load()
    mode_ids = {m.id for m in registry.all_modes()}
    expected = {
        "architect",
        "general_coder",
        "debugger",
        "deep_researcher_stage1",
        "deep_researcher_stage2_packet",
        "editor",
        "financial_planner",
        "latex_guru",
        "therapist",
    }
    assert expected.issubset(mode_ids)
