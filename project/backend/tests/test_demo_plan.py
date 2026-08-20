"""Tests: demo plan is legal and reaches the mission goal."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from demo_plan import build_demo_plan  # noqa: E402
from simulator import goal_satisfied, load_scenario, simulate  # noqa: E402


def test_demo_plan_reaches_goal() -> None:
    scenario = load_scenario()
    plan = build_demo_plan(scenario)
    assert plan["solution_found"] is True
    assert len(plan["steps"]) > 0
    assert plan["total_cost"] == sum(s["cost"] for s in plan["steps"])

    final = simulate(scenario, plan["steps"])
    assert goal_satisfied(scenario, final), final["stations"]
    assert final["energy_spent"] == plan["total_cost"]


def test_demo_plan_uses_all_ops() -> None:
    scenario = load_scenario()
    plan = build_demo_plan(scenario)
    ops = {s["op"] for s in plan["steps"]}
    assert ops == {"MOVE", "PICKUP", "DROP", "INTERACT"}
    actions = {s.get("action") for s in plan["steps"] if s["op"] == "INTERACT"}
    assert "OPEN_DOOR" in actions
    assert "REPAIR" in actions
    assert "ACTIVATE" in actions
    assert "RECHARGE" in actions


def test_demo_plan_opens_all_doors_and_stations() -> None:
    scenario = load_scenario()
    plan = build_demo_plan(scenario)
    final = simulate(scenario, plan["steps"])
    for d in scenario["doors"]:
        assert final["doors"][d["id"]] == "OPEN"
    for p in scenario["panels"]:
        assert final["panels"][p["id"]] == "OK"
    for s in scenario["stations"]:
        assert final["stations"][s["id"]] == "ONLINE"


if __name__ == "__main__":
    test_demo_plan_reaches_goal()
    test_demo_plan_uses_all_ops()
    test_demo_plan_opens_all_doors_and_stations()
    print("All demo plan tests passed.")
