"""Validation tests for the UCS agent (agent.py) — the 5 cases required by the
assignment (README.MD, "ENTREGABLE 3 — VALIDACIÓN").

Cases 1, 2, 4 and 5 use small synthetic scenarios built in this file instead
of the real scenarios/scenario.json, so the suite runs in well under a
second. scenario.json is a *harder* instance of the exact same rules (see
test_real_scenario_end_to_end at the bottom, which is intentionally NOT run
by default — it exercises the full demo mission and can take under a minute;
run it explicitly with `python tests/test_agent.py --slow`).
"""

from __future__ import annotations

import copy
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import agent as ucs_agent  # noqa: E402
from simulator import goal_satisfied, load_scenario, simulate  # noqa: E402


# ---------------------------------------------------------------------------
# A minimal but fully valid scenario, reused/adapted by several cases. Two
# zones (Z1 start, Z2 goal) connected two ways:
#   - a direct corridor Z1->Z2 that is CHEAP in steps (1 move) but EXPENSIVE
#     in cost (20);
#   - a detour Z1->Z3->Z2 that costs MORE steps (2 moves) but LESS total cost
#     (5 + 5 = 10).
# This is exactly the kind of instance Case 3 requires: fewer actions is not
# the same as lower cost, so only a cost-aware strategy (UCS) gets it right.
# ---------------------------------------------------------------------------

def _base_scenario() -> dict[str, Any]:
    return {
        "meta": {"id": "test_min", "title": "Minimal test scenario", "description": "synthetic"},
        "robot": {"start": "Z1", "battery_max": 100, "battery_start": 100, "cargo_capacity": 3},
        "zones": [
            {"id": "Z1", "name": "Z1", "recharge": False},
            {"id": "Z2", "name": "Z2", "recharge": False},
            {"id": "Z3", "name": "Z3", "recharge": False},
        ],
        "corridors": [
            {"from": "Z1", "to": "Z2", "cost": 20, "door": None},
            {"from": "Z2", "to": "Z1", "cost": 20, "door": None},
            {"from": "Z1", "to": "Z3", "cost": 5, "door": None},
            {"from": "Z3", "to": "Z1", "cost": 5, "door": None},
            {"from": "Z3", "to": "Z2", "cost": 5, "door": None},
            {"from": "Z2", "to": "Z3", "cost": 5, "door": None},
        ],
        "doors": [],
        "keys": [],
        "tools": [],
        "materials": [],
        "panels": [],
        "stations": [
            {"id": "BEACON", "kind": "generator", "zone": "Z2", "state": "OFFLINE", "requires": {}},
        ],
        "chargers": [],
        "goal": {"stations_online": ["BEACON"]},
        "action_costs": {"pickup": 1, "drop": 1, "interact": 2, "recharge": 3},
    }


# ---------------------------------------------------------------------------
# Case 1 — Estados equivalentes: two different pickup orders of two objects
# available in the same zone must land on the exact same logical State
# (equal, same hash), even though they were reached through different
# histories (design.md, "Cuándo dos configuraciones son el mismo estado").
# ---------------------------------------------------------------------------

def test_case1_equivalent_states_regardless_of_pickup_order() -> None:
    scenario = _base_scenario()
    scenario["keys"] = [
        {"id": "KEYA", "color": "cyan", "zone": "Z1", "weight": 1},
        {"id": "KEYB", "color": "yellow", "zone": "Z1", "weight": 1},
    ]
    scenario["doors"] = [
        {"id": "DOORA", "color": "cyan", "key": "KEYA", "state": "CLOSED", "between": ["Z1", "Z2"]},
        {"id": "DOORB", "color": "yellow", "key": "KEYB", "state": "CLOSED", "between": ["Z1", "Z3"]},
    ]
    model = ucs_agent.ScenarioModel(scenario)
    s0 = ucs_agent.initial_state(model)

    # order A: pick KEYA then KEYB
    a = ucs_agent._apply_pickup(s0, "key", "KEYA", model)
    a = ucs_agent._apply_pickup(a, "key", "KEYB", model)

    # order B: pick KEYB then KEYA
    b = ucs_agent._apply_pickup(s0, "key", "KEYB", model)
    b = ucs_agent._apply_pickup(b, "key", "KEYA", model)

    assert a == b, "same physical situation reached via different histories must be the same state"
    assert hash(a) == hash(b), "equal states must hash equal (required for CLOSED / dict lookups)"

    # And a genuinely different situation (one key still on the ground) must
    # NOT collapse into the same state.
    c = ucs_agent._apply_pickup(s0, "key", "KEYA", model)
    assert c != a


# ---------------------------------------------------------------------------
# Case 2 — Información relevante: two configurations that differ in
# information that can change future legal actions must remain distinct
# states (design.md, "Por qué cada variable es necesaria").
# ---------------------------------------------------------------------------

def test_case2_different_battery_means_different_state_and_options() -> None:
    scenario = _base_scenario()
    scenario["robot"]["battery_start"] = 20  # only enough for ONE expensive move
    model = ucs_agent.ScenarioModel(scenario)
    s_low = ucs_agent.initial_state(model)
    s_high = s_low._with(battery=100)

    assert s_low != s_high, "different battery must not be conflated into the same state"

    low_moves = {label for label, *_ in ucs_agent.successors(s_low, model) if label.startswith("MOVE")}
    high_moves = {label for label, *_ in ucs_agent.successors(s_high, model) if label.startswith("MOVE")}
    assert low_moves == high_moves, "both can afford every corridor once (sanity)"

    # Drain s_low further so the expensive Z1->Z2 corridor (cost 20) is no
    # longer affordable, while the detour via Z3 (cost 5) still is: this is
    # exactly the kind of divergence in *future legal actions* that makes
    # battery a required part of the state, not an incidental detail.
    s_tight = s_low._with(battery=6)
    tight_moves = {label for label, *_ in ucs_agent.successors(s_tight, model) if label.startswith("MOVE")}
    assert "MOVE(Z1->Z2)" not in tight_moves
    assert "MOVE(Z1->Z3)" in tight_moves


# ---------------------------------------------------------------------------
# Case 3 — Costos diferentes: the plan with fewer actions is NOT the plan
# with lower cost, and the agent must choose by cost (UCS), not step count.
# ---------------------------------------------------------------------------

def test_case3_cheapest_plan_is_not_the_shortest_plan() -> None:
    scenario = _base_scenario()
    result = ucs_agent.solve(scenario)

    assert result["solution_found"] is True
    # 2-hop detour (5+5) + ACTIVATE (interact=2) = 12, cheaper than the 1-hop
    # shortcut (20) + ACTIVATE (2) = 22, even though the detour has MORE moves.
    assert result["total_cost"] == 12, "must take the 2-hop detour (5+5+2), not the 1-hop shortcut (20+2)"
    moves = [s for s in result["steps"] if s["op"] == "MOVE"]
    assert len(moves) == 2, "the optimal plan has MORE steps than the naive 1-move alternative"

    final = simulate(scenario, result["steps"])
    assert goal_satisfied(scenario, final)
    assert final["energy_spent"] == result["total_cost"] == 12


# ---------------------------------------------------------------------------
# Case 4 — Sin solución: the agent must terminate and return FAILURE, not
# hang, when the mission is impossible.
# ---------------------------------------------------------------------------

def test_case4_returns_failure_without_hanging() -> None:
    scenario = _base_scenario()
    scenario["keys"] = [{"id": "LOST_KEY", "color": "cyan", "zone": "Z2", "weight": 1}]
    # A door between Z1 and Z3 whose key sits *only* in Z3 itself — Z3 is
    # unreachable without opening the door first, so the key can never be
    # collected and the mission cannot be completed.
    scenario["doors"] = [
        {"id": "DOOR_IMPOSSIBLE", "color": "grey", "key": "IMPOSSIBLE_KEY", "state": "CLOSED", "between": ["Z1", "Z3"]},
    ]
    # Also remove the direct Z1<->Z2 corridors so BEACON's zone is only
    # reachable through the (now impossible) Z3 corridor.
    scenario["corridors"] = [
        {"from": "Z1", "to": "Z3", "cost": 5, "door": "DOOR_IMPOSSIBLE"},
        {"from": "Z3", "to": "Z1", "cost": 5, "door": "DOOR_IMPOSSIBLE"},
        {"from": "Z3", "to": "Z2", "cost": 5, "door": None},
        {"from": "Z2", "to": "Z3", "cost": 5, "door": None},
    ]

    t0 = time.time()
    result = ucs_agent.solve(scenario)
    dt = time.time() - t0

    assert result["solution_found"] is False
    assert result["steps"] == []
    assert result["total_cost"] == 0
    assert dt < 5, "must terminate promptly (finite state space), not explore forever"


# ---------------------------------------------------------------------------
# Case 5 — Rutas alternativas: the same world conditions are reachable via
# more than one route, and the agent must consistently keep the one that
# matches its declared strategy (lowest accumulated cost).
# ---------------------------------------------------------------------------

def test_case5_alternative_routes_keeps_the_cheapest() -> None:
    scenario = _base_scenario()  # Z1->Z2 direct (20) vs Z1->Z3->Z2 (5+5)
    result = ucs_agent.solve(scenario)
    assert result["solution_found"] is True
    assert result["total_cost"] == 12

    # Sanity: the more expensive direct route is legal too (both routes exist
    # and reach the identical world condition — BEACON online) — the agent
    # must have discarded it because of cost, not because it was somehow
    # illegal or unreachable.
    manual_direct = [
        {"op": "MOVE", "from": "Z1", "to": "Z2", "cost": 20},
        {"op": "INTERACT", "target": "BEACON", "action": "ACTIVATE", "cost": 2},
    ]
    final = simulate(scenario, manual_direct)
    assert goal_satisfied(scenario, final)
    assert final["energy_spent"] == 22 > result["total_cost"]


# ---------------------------------------------------------------------------
# Optional slow integration test against the real demo scenario. NOT part of
# the default run (see __main__ below) — call explicitly with --slow.
# ---------------------------------------------------------------------------

def test_real_scenario_end_to_end() -> None:
    scenario = load_scenario()
    result = ucs_agent.solve(scenario)
    assert result["solution_found"] is True
    final = simulate(scenario, result["steps"])
    assert goal_satisfied(scenario, final)
    assert final["energy_spent"] == result["total_cost"]
    print(f"  real scenario: cost={result['total_cost']} steps={len(result['steps'])} — {result['message']}")


if __name__ == "__main__":
    fast_tests = [
        test_case1_equivalent_states_regardless_of_pickup_order,
        test_case2_different_battery_means_different_state_and_options,
        test_case3_cheapest_plan_is_not_the_shortest_plan,
        test_case4_returns_failure_without_hanging,
        test_case5_alternative_routes_keeps_the_cheapest,
    ]
    for t in fast_tests:
        t()
        print(f"OK  {t.__name__}")
    print("All 5 required cases passed.")

    if "--slow" in sys.argv:
        print("\nRunning slow end-to-end test against scenarios/scenario.json ...")
        test_real_scenario_end_to_end()
        print("OK  test_real_scenario_end_to_end")