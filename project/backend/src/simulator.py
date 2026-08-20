"""Mini world simulator — validates demo plan legality against scenario.json."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "scenario.json"


def load_scenario() -> dict[str, Any]:
    with SCENARIO_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def initial_state(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        "zone": scenario["robot"]["start"],
        "battery": scenario["robot"]["battery_start"],
        "energy_spent": 0,
        "payload": [],
        "doors": {d["id"]: d["state"] for d in scenario["doors"]},
        "panels": {p["id"]: p["state"] for p in scenario["panels"]},
        "stations": {s["id"]: s["state"] for s in scenario["stations"]},
        "ground_keys": {k["id"]: k["zone"] for k in scenario["keys"]},
        "ground_tools": {t["id"]: t["zone"] for t in scenario["tools"]},
        "ground_materials": {
            m["type"]: {"type": m["type"], "count": m["count"], "zone": m["zone"]}
            for m in scenario["materials"]
        },
    }


def payload_weight(payload: list[dict[str, Any]]) -> int:
    return sum(p.get("weight", 1) for p in payload)


def spend(state: dict[str, Any], cost: int, battery_max: int) -> None:
    if state["battery"] < cost:
        raise AssertionError(
            f"Insufficient battery: have {state['battery']}, need {cost}"
        )
    state["battery"] -= cost
    state["energy_spent"] += cost


def find_corridor(scenario: dict[str, Any], frm: str, to: str) -> dict[str, Any]:
    for c in scenario["corridors"]:
        if c["from"] == frm and c["to"] == to:
            return c
    raise AssertionError(f"No corridor {frm}->{to}")


def apply_step(scenario: dict[str, Any], state: dict[str, Any], step: dict[str, Any]) -> None:
    state = state  # mutate in place
    bat_max = scenario["robot"]["battery_max"]
    cap = scenario["robot"]["cargo_capacity"]
    op = step["op"]
    cost = int(step["cost"])

    if op == "MOVE":
        frm = step.get("from", state["zone"])
        to = step["to"]
        assert frm == state["zone"], f"MOVE from {frm} but robot in {state['zone']}"
        corr = find_corridor(scenario, frm, to)
        if corr.get("door"):
            assert state["doors"][corr["door"]] == "OPEN", f"Door {corr['door']} closed"
        spend(state, cost, bat_max)
        state["zone"] = to
        return

    if op == "PICKUP":
        item = step["item"]
        assert payload_weight(state["payload"]) + 1 <= cap, "cargo full"
        if item in state["ground_keys"]:
            assert state["ground_keys"][item] == state["zone"]
            key = next(k for k in scenario["keys"] if k["id"] == item)
            spend(state, cost, bat_max)
            del state["ground_keys"][item]
            state["payload"].append(
                {"kind": "key", "id": item, "color": key["color"], "weight": key["weight"]}
            )
            return
        if item in state["ground_tools"]:
            assert state["ground_tools"][item] == state["zone"]
            tool = next(t for t in scenario["tools"] if t["id"] == item)
            spend(state, cost, bat_max)
            del state["ground_tools"][item]
            state["payload"].append(
                {
                    "kind": "tool",
                    "id": item,
                    "repairs": tool["repairs"],
                    "weight": tool["weight"],
                }
            )
            return
        if item in state["ground_materials"]:
            mat = state["ground_materials"][item]
            assert mat["zone"] == state["zone"] and mat["count"] > 0
            spend(state, cost, bat_max)
            mat["count"] -= 1
            if mat["count"] <= 0:
                del state["ground_materials"][item]
            state["payload"].append({"kind": "material", "type": item, "weight": 1})
            return
        raise AssertionError(f"Item {item} not on ground in {state['zone']}")

    if op == "DROP":
        item = step["item"]
        idx = next(
            (
                i
                for i, p in enumerate(state["payload"])
                if p.get("id") == item or p.get("type") == item
            ),
            None,
        )
        assert idx is not None, f"{item} not in payload"
        spend(state, cost, bat_max)
        obj = state["payload"].pop(idx)
        if obj["kind"] == "key":
            state["ground_keys"][obj["id"]] = state["zone"]
        elif obj["kind"] == "tool":
            state["ground_tools"][obj["id"]] = state["zone"]
        else:
            existing = state["ground_materials"].get(obj["type"])
            if existing and existing["zone"] == state["zone"]:
                existing["count"] += 1
            else:
                state["ground_materials"][obj["type"]] = {
                    "type": obj["type"],
                    "count": 1,
                    "zone": state["zone"],
                }
        return

    if op == "INTERACT":
        target = step["target"]
        action = step["action"]

        if action == "OPEN_DOOR":
            door = next(d for d in scenario["doors"] if d["id"] == target)
            a, b = door["between"]
            assert state["zone"] in (a, b)
            assert state["doors"][target] == "CLOSED"
            assert any(p.get("id") == door["key"] for p in state["payload"])
            spend(state, cost, bat_max)
            state["doors"][target] = "OPEN"
            return

        if action == "REPAIR":
            panel = next(p for p in scenario["panels"] if p["id"] == target)
            assert state["zone"] == panel["zone"]
            assert state["panels"][target] == "DAMAGED"
            assert any(p.get("id") == panel["requires"]["tool"] for p in state["payload"])
            mat = step.get("consumes", panel["requires"]["material"])
            assert mat == panel["requires"]["material"]
            midx = next(
                (
                    i
                    for i, p in enumerate(state["payload"])
                    if p.get("kind") == "material" and p.get("type") == mat
                ),
                None,
            )
            assert midx is not None, f"missing material {mat}"
            spend(state, cost, bat_max)
            state["payload"].pop(midx)
            state["panels"][target] = "OK"
            return

        if action == "ACTIVATE":
            station = next(s for s in scenario["stations"] if s["id"] == target)
            assert state["zone"] == station["zone"]
            assert state["stations"][target] == "OFFLINE"
            for pid in station["requires"].get("panels_ok", []):
                assert state["panels"][pid] == "OK", f"panel {pid} not OK"
            for sid in station["requires"].get("stations_online", []):
                assert state["stations"][sid] == "ONLINE", f"station {sid} offline"
            spend(state, cost, bat_max)
            state["stations"][target] = "ONLINE"
            return

        if action == "RECHARGE":
            charger = next(c for c in scenario["chargers"] if c["id"] == target)
            assert state["zone"] == charger["zone"]
            assert state["battery"] < bat_max
            spend(state, cost, bat_max)
            state["battery"] = bat_max
            return

        raise AssertionError(f"Unknown action {action}")

    raise AssertionError(f"Unknown op {op}")


def goal_satisfied(scenario: dict[str, Any], state: dict[str, Any]) -> bool:
    return all(
        state["stations"][sid] == "ONLINE" for sid in scenario["goal"]["stations_online"]
    )


def simulate(scenario: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    state = initial_state(scenario)
    for i, step in enumerate(steps):
        try:
            apply_step(scenario, state, step)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"Step {i} {step} failed: {exc}") from exc
    return state
