"""Demo plan for Emergency Control — no AI, handcrafted for frontend testing."""

from __future__ import annotations

from typing import Any


def build_demo_plan(scenario: dict[str, Any]) -> dict[str, Any]:
    """Plan artesanal para probar el frontend. No es un agente de IA.

    Es legal y recorre todas las ops visuales, pero no es necesariamente
    óptimo (usa el pasillo caro Z2↔Z5 y por eso recarga). Los DROP no son
    decorativos: con cargo_capacity=3 hay que hacer hueco. El agente del
    estudiante debe *descubrir* cuándo soltar, no copiar esta secuencia,
    y no debe subir la capacidad para evitarlos.
    """
    costs = scenario.get("action_costs", {})
    pickup = costs.get("pickup", 1)
    drop = costs.get("drop", 1)
    interact = costs.get("interact", 2)
    recharge = costs.get("recharge", 3)

    def corridor_cost(frm: str, to: str) -> int:
        for c in scenario["corridors"]:
            if c["from"] == frm and c["to"] == to:
                return int(c["cost"])
        raise ValueError(f"missing corridor {frm}->{to}")

    steps: list[dict[str, Any]] = [
        # --- open path CONTROL -> STORAGE ---
        {"op": "PICKUP", "item": "KEY1", "cost": pickup},
        {"op": "INTERACT", "target": "DOOR1", "action": "OPEN_DOOR", "cost": interact},
        {"op": "MOVE", "from": "Z1", "to": "Z2", "cost": corridor_cost("Z1", "Z2")},
        # --- gather key2 + fuse (capacity pressure) ---
        {"op": "PICKUP", "item": "KEY2", "cost": pickup},
        {"op": "PICKUP", "item": "FUSE", "cost": pickup},
        {"op": "DROP", "item": "KEY1", "cost": drop},
        {"op": "INTERACT", "target": "DOOR2", "action": "OPEN_DOOR", "cost": interact},
        {"op": "MOVE", "from": "Z2", "to": "Z3", "cost": corridor_cost("Z2", "Z3")},
        # --- workshop: tool + key3 + recharge ---
        {"op": "PICKUP", "item": "MULTITOOL", "cost": pickup},
        {"op": "DROP", "item": "KEY2", "cost": drop},
        {"op": "PICKUP", "item": "KEY3", "cost": pickup},
        {"op": "INTERACT", "target": "CHARGER_1", "action": "RECHARGE", "cost": recharge},
        # --- generator bay ---
        {"op": "MOVE", "from": "Z3", "to": "Z4", "cost": corridor_cost("Z3", "Z4")},
        {"op": "INTERACT", "target": "DOOR3", "action": "OPEN_DOOR", "cost": interact},
        {
            "op": "INTERACT",
            "target": "PANEL_A",
            "action": "REPAIR",
            "consumes": "FUSE",
            "cost": interact,
        },
        {"op": "INTERACT", "target": "GENERATOR", "action": "ACTIVATE", "cost": interact},
        # --- fetch remaining tools/materials ---
        {"op": "MOVE", "from": "Z4", "to": "Z3", "cost": corridor_cost("Z4", "Z3")},
        {"op": "DROP", "item": "KEY3", "cost": drop},
        {"op": "DROP", "item": "MULTITOOL", "cost": drop},
        {"op": "PICKUP", "item": "SOLDERING", "cost": pickup},
        {"op": "PICKUP", "item": "WIRE_CUTTER", "cost": pickup},
        {"op": "MOVE", "from": "Z3", "to": "Z2", "cost": corridor_cost("Z3", "Z2")},
        {"op": "PICKUP", "item": "CHIP", "cost": pickup},
        {"op": "DROP", "item": "WIRE_CUTTER", "cost": drop},
        {"op": "PICKUP", "item": "CABLE", "cost": pickup},
        # --- command deck via expensive outer corridor Z2→Z5 (no door; alternate to Z4→DOOR3→Z5) ---
        {"op": "MOVE", "from": "Z2", "to": "Z5", "cost": corridor_cost("Z2", "Z5")},
        {
            "op": "INTERACT",
            "target": "PANEL_B",
            "action": "REPAIR",
            "consumes": "CHIP",
            "cost": interact,
        },
        {"op": "INTERACT", "target": "COMMAND", "action": "ACTIVATE", "cost": interact},
        # --- retrieve wire cutter for PANEL_C ---
        {"op": "DROP", "item": "SOLDERING", "cost": drop},
        {"op": "MOVE", "from": "Z5", "to": "Z2", "cost": corridor_cost("Z5", "Z2")},
        {"op": "PICKUP", "item": "WIRE_CUTTER", "cost": pickup},
        {"op": "MOVE", "from": "Z2", "to": "Z5", "cost": corridor_cost("Z2", "Z5")},
        {
            "op": "INTERACT",
            "target": "PANEL_C",
            "action": "REPAIR",
            "consumes": "CABLE",
            "cost": interact,
        },
        {"op": "INTERACT", "target": "ARTILLERY", "action": "ACTIVATE", "cost": interact},
    ]

    total = sum(int(s["cost"]) for s in steps)
    return {
        "solution_found": True,
        "total_cost": total,
        "steps": steps,
        "message": "Demo plan (no search). Exercises all frontend operations.",
    }
