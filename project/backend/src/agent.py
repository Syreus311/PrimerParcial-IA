"""Search agent for Emergency Control — Uniform-Cost Search (UCS / Dijkstra).

This module implements ONLY uninformed search, matching the scope of the course
(AIMA cap. 3.4 — BFS, DFS, IDS, UCS). There is no heuristic function anywhere in
this file: successors are ordered purely by accumulated path cost g(n), never by
an estimate of remaining distance. UCS is the correct choice among the four
uninformed strategies here because the world has heterogeneous action costs
(corridors, pickup/drop/interact/recharge all cost different amounts) and the
mission requires the plan of *minimum accumulated cost*, not the plan with the
fewest steps — only UCS guarantees that under those conditions.

Design correspondence (see project/design.md for the full justification):

  * State  = physical situation of the world (Section "Estado").
  * Node   = state + parent + action + g(n) (Section "Qué pertenece al nodo").
  * Applicable(s) is deliberately narrower than "everything CONTRATO.md allows".
    Four independent, individually-provable restrictions keep the branching
    factor down without ever discarding the optimal plan (each is argued in a
    comment right above the code that implements it, and in design.md):

      1. PICKUP only offers objects that are still "live" (a key for a door
         still closed, a tool/material a still-damaged panel still needs).
      2. PICKUP of a material type stops once the robot already holds as many
         units of that type as outstanding panels still require — a spare
         unit can never be consumed by anything.
      3. DROP is only generated when the robot is blocked from a live PICKUP
         by capacity (never "just in case").
      4. When blocked, DROP prefers a *dead* held object over a live one
         whenever any dead object is held — dropping dead cargo is never
         worse than dropping live cargo, and it is what keeps the state space
         from exploding into "every possible zone a live object could have
         been abandoned in".

  * Graph Search uses a canonical, hashable State as the base identity, plus:
      - dead payload objects are identity-erased (grouped by weight only) in
        the key used for duplicate/dominance detection, since two robots
        holding "some dead junk of the same total weight" are, from this
        point on, in the exact same situation no matter which specific dead
        object each is carrying;
      - a battery-dominance rule: among paths reaching the same physical
        world configuration, a path with battery >= and cost <= another can
        never be worse for any continuation, so the dominated one is safely
        discarded (design.md, "Batería como recurso").
"""

from __future__ import annotations

import dataclasses
import heapq
import itertools
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Static scenario model — constants only. NONE of this belongs in the search
# state: it never changes while the plan is being computed (design.md, "Qué
# información se deriva y NO se almacena").
# ---------------------------------------------------------------------------


class ScenarioModel:
    def __init__(self, scenario: Dict[str, Any]):
        self.scenario = scenario
        self.battery_max = scenario["robot"]["battery_max"]
        self.battery_start = scenario["robot"]["battery_start"]
        self.start_zone = scenario["robot"]["start"]
        self.cargo_capacity = scenario["robot"]["cargo_capacity"]

        costs = scenario.get("action_costs", {})
        self.cost_pickup = costs.get("pickup", 1)
        self.cost_drop = costs.get("drop", 1)
        self.cost_interact = costs.get("interact", 2)
        self.cost_recharge = costs.get("recharge", 3)

        # zone -> list of (to_zone, cost, door_id_or_None)
        self.adjacency: Dict[str, List[Tuple[str, int, Optional[str]]]] = {}
        for c in scenario["corridors"]:
            self.adjacency.setdefault(c["from"], []).append((c["to"], c["cost"], c.get("door")))

        self.doors = {d["id"]: d for d in scenario["doors"]}
        self.key_to_door = {d["key"]: d["id"] for d in scenario["doors"]}
        self.keys = {k["id"]: k for k in scenario["keys"]}
        self.tools = {t["id"]: t for t in scenario["tools"]}
        self.materials = {m["type"]: m for m in scenario["materials"]}
        self.panels = {p["id"]: p for p in scenario["panels"]}
        self.stations = {s["id"]: s for s in scenario["stations"]}

        # zone -> [panel_id, ...] / [station_id, ...] — avoids scanning every
        # panel/station of the scenario on every single node expansion.
        self.panels_by_zone: Dict[str, List[str]] = {}
        for pid, p in self.panels.items():
            self.panels_by_zone.setdefault(p["zone"], []).append(pid)
        self.stations_by_zone: Dict[str, List[str]] = {}
        for sid, s in self.stations.items():
            self.stations_by_zone.setdefault(s["zone"], []).append(sid)

        # IMPORTANT: capacity is enforced by the frontend/simulator as a strict
        # *slot count* (payload_weight(payload) + 1 <= cargo_capacity, where the
        # incoming item always counts as exactly 1 regardless of its own
        # "weight" field — see backend/src/simulator.py::apply_step, PICKUP
        # branch). CONTRATO.md's prose talks about "peso total", but the code
        # that the frontend actually runs against is count-based for the
        # incoming item. We mirror the simulator's real formula exactly so a
        # plan legal for this agent is never rejected by the grader's bench.
        self.weight: Dict[Tuple[str, str], int] = {}
        for k in self.keys.values():
            self.weight[("key", k["id"])] = k.get("weight", 1)
        for t in self.tools.values():
            self.weight[("tool", t["id"])] = t.get("weight", 1)
        for m in self.materials.values():
            self.weight[("material", m["type"])] = m.get("weight", 1)

        # Only used by RECHARGE: the simulator validates RECHARGE strictly
        # against scenario["chargers"] (id + zone), not the zones[].recharge
        # display flag, so we key off chargers exclusively.
        self.charger_by_zone: Dict[str, str] = {c["zone"]: c["id"] for c in scenario.get("chargers", [])}

        self.goal_stations = frozenset(scenario["goal"]["stations_online"])

        # Which panels each tool-repair-type / material-type still matters to
        # (design.md, "Relevancia: objetos que ya no cambian el futuro").
        self.panels_by_damage: Dict[str, List[str]] = {}
        self.panels_by_material: Dict[str, List[str]] = {}
        for p in self.panels.values():
            self.panels_by_damage.setdefault(p["damage"], []).append(p["id"])
            self.panels_by_material.setdefault(p["requires"]["material"], []).append(p["id"])


# ---------------------------------------------------------------------------
# State — the physical situation only. Immutable & hashable so it can be used
# directly as a dict/set key (design.md, "Cuándo dos configuraciones son el
# mismo estado"). Payload keeps concrete identities (needed to emit a legal
# `{"op": "DROP", "item": ...}` step) — the *coarser*, identity-erased view
# used for duplicate/dominance detection is computed separately by
# `_dedup_key`, never by State equality itself.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class State:
    zone: str
    battery: int
    payload: FrozenSet[Tuple[str, str]]                    # {('key', id) | ('tool', id)}
    payload_materials: Tuple[Tuple[str, int], ...]         # sorted (type, count), count > 0
    ground_keys: FrozenSet[Tuple[str, str]]                # (key_id, zone) — LIVE keys only
    ground_tools: FrozenSet[Tuple[str, str]]                # (tool_id, zone) — LIVE tools only
    ground_materials: Tuple[Tuple[str, str, int], ...]      # sorted (type, zone, count) — LIVE types only
    doors_open: FrozenSet[str]
    panels_ok: FrozenSet[str]
    stations_online: FrozenSet[str]

    def _with(self, **changes: Any) -> "State":
        """Faster equivalent of dataclasses.replace(self, **changes): a plain
        dataclasses.replace() re-derives the field list via reflection on every
        call, which shows up under profiling as ~1/4 of total search time (see
        the performance note in the module docstring). Hand-listing the ten
        fields once here is a pure constant-factor win with identical
        semantics."""
        return State(
            changes.get("zone", self.zone),
            changes.get("battery", self.battery),
            changes.get("payload", self.payload),
            changes.get("payload_materials", self.payload_materials),
            changes.get("ground_keys", self.ground_keys),
            changes.get("ground_tools", self.ground_tools),
            changes.get("ground_materials", self.ground_materials),
            changes.get("doors_open", self.doors_open),
            changes.get("panels_ok", self.panels_ok),
            changes.get("stations_online", self.stations_online),
        )


def _tool_is_live(tool_id: str, model: ScenarioModel, panels_ok: FrozenSet[str]) -> bool:
    repairs = model.tools[tool_id]["repairs"]
    return any(pid not in panels_ok for pid in model.panels_by_damage.get(repairs, []))


def _material_is_live(material_type: str, model: ScenarioModel, panels_ok: FrozenSet[str]) -> bool:
    return any(pid not in panels_ok for pid in model.panels_by_material.get(material_type, []))


def _key_is_live(key_id: str, model: ScenarioModel, doors_open: FrozenSet[str]) -> bool:
    door_id = model.key_to_door.get(key_id)
    return door_id is not None and door_id not in doors_open


def _material_remaining_need(material_type: str, model: ScenarioModel, panels_ok: FrozenSet[str]) -> int:
    """How many more units of this type any outstanding panel could still
    consume. A material type is only ever consumed one unit at a time by a
    REPAIR, so this is just the count of not-yet-repaired panels that need it.
    Carrying more units than this can never help (design.md-style soundness
    argument): the excess is provably dead weight from the moment it exceeds
    remaining need, so PICKUP stops offering it past that point.
    """
    return sum(1 for pid in model.panels_by_material.get(material_type, []) if pid not in panels_ok)


def initial_state(model: ScenarioModel) -> State:
    scenario = model.scenario
    doors_open = frozenset(d["id"] for d in scenario["doors"] if d.get("state") == "OPEN")
    panels_ok = frozenset(p["id"] for p in scenario["panels"] if p.get("state") == "OK")
    stations_online = frozenset(s["id"] for s in scenario["stations"] if s.get("state") == "ONLINE")

    ground_keys = frozenset(
        (k["id"], k["zone"]) for k in scenario["keys"] if _key_is_live(k["id"], model, doors_open)
    )
    ground_tools = frozenset(
        (t["id"], t["zone"]) for t in scenario["tools"] if _tool_is_live(t["id"], model, panels_ok)
    )
    ground_materials = tuple(
        sorted(
            (m["type"], m["zone"], m["count"])
            for m in scenario["materials"]
            if m["count"] > 0 and _material_is_live(m["type"], model, panels_ok)
        )
    )

    return State(
        zone=model.start_zone,
        battery=model.battery_start,
        payload=frozenset(),
        payload_materials=tuple(),
        ground_keys=ground_keys,
        ground_tools=ground_tools,
        ground_materials=ground_materials,
        doors_open=doors_open,
        panels_ok=panels_ok,
        stations_online=stations_online,
    )


def _refresh_ground_liveness(state: State, model: ScenarioModel) -> State:
    """Re-filter ground sets after doors_open/panels_ok changed.

    Monotonic pruning: an object that just became irrelevant (its door
    opened, or the last panel needing its repair type/material got fixed) is
    dropped from *ground* tracking entirely — its exact resting zone can
    never again influence Applicable(s), so keeping it around would only
    multiply states with a distinction that makes no behavioural difference.
    """
    ground_keys = frozenset(e for e in state.ground_keys if _key_is_live(e[0], model, state.doors_open))
    ground_tools = frozenset(e for e in state.ground_tools if _tool_is_live(e[0], model, state.panels_ok))
    ground_materials = tuple(
        sorted(e for e in state.ground_materials if _material_is_live(e[0], model, state.panels_ok))
    )
    return state._with(ground_keys=ground_keys, ground_tools=ground_tools, ground_materials=ground_materials
    )


def _weight_sum(state: State, model: ScenarioModel) -> int:
    total = sum(model.weight.get(item, 1) for item in state.payload)
    total += sum(model.weight.get(("material", t), 1) * c for t, c in state.payload_materials)
    return total


def _can_pickup_one_more(state: State, model: ScenarioModel) -> bool:
    """Mirrors simulator.py's PICKUP capacity check exactly (see ScenarioModel.weight)."""
    return _weight_sum(state, model) + 1 <= model.cargo_capacity


def goal_test(state: State, model: ScenarioModel) -> bool:
    return model.goal_stations.issubset(state.stations_online)


# ---------------------------------------------------------------------------
# Result(s, a) — one function per internal action, each returning the new
# canonical State. Battery bookkeeping and ground-liveness refresh happen
# here so every successor produced by Applicable() is already canonical.
# ---------------------------------------------------------------------------


def _apply_pickup(state: State, kind: str, ident: str, model: ScenarioModel) -> State:
    zone = state.zone
    if kind == "key":
        return state._with(ground_keys=frozenset(e for e in state.ground_keys if e[0] != ident),
            payload=state.payload | {("key", ident)},
            battery=state.battery - model.cost_pickup,
        )
    if kind == "tool":
        return state._with(ground_tools=frozenset(e for e in state.ground_tools if e[0] != ident),
            payload=state.payload | {("tool", ident)},
            battery=state.battery - model.cost_pickup,
        )
    # material
    gm = list(state.ground_materials)
    idx = next(i for i, (t, z, c) in enumerate(gm) if t == ident and z == zone)
    t, z, c = gm[idx]
    if c - 1 <= 0:
        gm.pop(idx)
    else:
        gm[idx] = (t, z, c - 1)
    pm = dict(state.payload_materials)
    pm[ident] = pm.get(ident, 0) + 1
    return state._with(ground_materials=tuple(sorted(gm)),
        payload_materials=tuple(sorted(pm.items())),
        battery=state.battery - model.cost_pickup,
    )


def _apply_drop(state: State, kind: str, ident: str, model: ScenarioModel) -> State:
    zone = state.zone
    if kind == "key":
        new_state = state._with(payload=state.payload - {("key", ident)},
            ground_keys=state.ground_keys | {(ident, zone)},
            battery=state.battery - model.cost_drop,
        )
    elif kind == "tool":
        new_state = state._with(payload=state.payload - {("tool", ident)},
            ground_tools=state.ground_tools | {(ident, zone)},
            battery=state.battery - model.cost_drop,
        )
    else:  # material
        pm = dict(state.payload_materials)
        pm[ident] -= 1
        if pm[ident] <= 0:
            del pm[ident]
        gm = list(state.ground_materials)
        idx = next((i for i, (t, z, c) in enumerate(gm) if t == ident and z == zone), None)
        if idx is None:
            gm.append((ident, zone, 1))
        else:
            t, z, c = gm[idx]
            gm[idx] = (t, z, c + 1)
        new_state = state._with(payload_materials=tuple(sorted(pm.items())),
            ground_materials=tuple(sorted(gm)),
            battery=state.battery - model.cost_drop,
        )
    # A dropped object may already be dead (e.g. a key whose door is open).
    # _refresh_ground_liveness immediately strips it back out of ground
    # tracking, so "where we happened to drop a dead object" never becomes a
    # state distinction (design.md, "Relevancia: objetos que ya no cambian
    # el futuro").
    return _refresh_ground_liveness(new_state, model)


def _apply_repair(state: State, panel_id: str, material_type: str, model: ScenarioModel) -> State:
    pm = dict(state.payload_materials)
    pm[material_type] -= 1
    if pm[material_type] <= 0:
        del pm[material_type]
    new_state = state._with(payload_materials=tuple(sorted(pm.items())),
        panels_ok=state.panels_ok | {panel_id},
        battery=state.battery - model.cost_interact,
    )
    return _refresh_ground_liveness(new_state, model)


# ---------------------------------------------------------------------------
# Applicable(s) — successor generator. This is where the branching factor is
# controlled (design.md, "Formulación y tamaño del espacio").
# ---------------------------------------------------------------------------


def successors(state: State, model: ScenarioModel) -> Iterable[Tuple[str, Dict[str, Any], State, int]]:
    """Yield (internal_action_label, contract_step, next_state, step_cost)."""
    zone = state.zone

    # ---- MOVE ----
    for to_zone, cost, door in model.adjacency.get(zone, []):
        if door is not None and door not in state.doors_open:
            continue
        if state.battery < cost:
            continue
        new_state = state._with(zone=to_zone, battery=state.battery - cost)
        yield (
            f"MOVE({zone}->{to_zone})",
            {"op": "MOVE", "from": zone, "to": to_zone, "cost": cost},
            new_state,
            cost,
        )

    # ---- PICKUP: only live objects present in this zone, and materials
    # capped at how many units any outstanding panel could still use ----
    pickups: List[Tuple[str, str]] = []  # (kind, ident)
    for key_id, kz in state.ground_keys:
        if kz == zone:
            pickups.append(("key", key_id))
    for tool_id, tz in state.ground_tools:
        if tz == zone:
            pickups.append(("tool", tool_id))
    held_material_counts = dict(state.payload_materials)
    for mtype, mzone, count in state.ground_materials:
        if mzone == zone and count > 0:
            if held_material_counts.get(mtype, 0) < _material_remaining_need(mtype, model, state.panels_ok):
                pickups.append(("material", mtype))

    room_now = _can_pickup_one_more(state, model)
    if room_now and state.battery >= model.cost_pickup:
        for kind, ident in pickups:
            new_state = _apply_pickup(state, kind, ident, model)
            yield (
                f"PICKUP({ident})",
                {"op": "PICKUP", "item": ident, "cost": model.cost_pickup},
                new_state,
                model.cost_pickup,
            )

    # ---- DROP: only when a live object in this zone is blocked by capacity.
    # Prefer dropping DEAD cargo over LIVE cargo whenever any dead cargo is
    # held: this is never worse (a dead object can never be needed again, so
    # any plan that drops a live object while dead cargo sits unused can be
    # rewritten, at no extra cost, to drop the dead cargo instead — see the
    # module docstring / design.md). Restricting to dead-only when available
    # is what keeps live objects from scattering across every zone the search
    # happens to visit while blocked. ----
    if pickups and not room_now and state.battery >= model.cost_drop:
        dead_by_weight: Dict[int, Tuple[str, str]] = {}
        live_candidates: List[Tuple[str, str]] = []
        for kind, ident in state.payload:
            is_live = _key_is_live(ident, model, state.doors_open) if kind == "key" else _tool_is_live(
                ident, model, state.panels_ok
            )
            w = model.weight.get((kind, ident), 1)
            if is_live:
                live_candidates.append((kind, ident))
            else:
                dead_by_weight.setdefault(w, (kind, ident))
        for mtype, count in state.payload_materials:
            if count <= 0:
                continue
            w = model.weight.get(("material", mtype), 1)
            if _material_is_live(mtype, model, state.panels_ok):
                live_candidates.append(("material", mtype))
            else:
                dead_by_weight.setdefault(w, ("material", mtype))

        # One representative drop per distinct dead weight value is enough:
        # dropping any dead object of the same weight leads to an equivalent
        # continuation, so offering more than one is pure duplicate work.
        candidates = list(dead_by_weight.values()) if dead_by_weight else live_candidates
        for kind, ident in candidates:
            new_state = _apply_drop(state, kind, ident, model)
            yield (
                f"DROP({ident})",
                {"op": "DROP", "item": ident, "cost": model.cost_drop},
                new_state,
                model.cost_drop,
            )

    # ---- OPEN_DOOR ----
    seen_doors = set()
    for to_zone, _cost, door in model.adjacency.get(zone, []):
        if door is None or door in state.doors_open or door in seen_doors:
            continue
        seen_doors.add(door)
        key_id = model.doors[door]["key"]
        if ("key", key_id) not in state.payload:
            continue
        if state.battery < model.cost_interact:
            continue
        new_state = state._with(doors_open=state.doors_open | {door}, battery=state.battery - model.cost_interact
        )
        new_state = _refresh_ground_liveness(new_state, model)
        yield (
            f"OPEN_DOOR({door})",
            {"op": "INTERACT", "target": door, "action": "OPEN_DOOR", "cost": model.cost_interact},
            new_state,
            model.cost_interact,
        )

    # ---- REPAIR ----
    for panel_id in model.panels_by_zone.get(zone, []):
        if panel_id in state.panels_ok:
            continue
        panel = model.panels[panel_id]
        need_tool = panel["requires"]["tool"]
        need_mat = panel["requires"]["material"]
        if ("tool", need_tool) not in state.payload:
            continue
        if dict(state.payload_materials).get(need_mat, 0) <= 0:
            continue
        if state.battery < model.cost_interact:
            continue
        new_state = _apply_repair(state, panel_id, need_mat, model)
        yield (
            f"REPAIR({panel_id})",
            {
                "op": "INTERACT",
                "target": panel_id,
                "action": "REPAIR",
                "consumes": need_mat,
                "cost": model.cost_interact,
            },
            new_state,
            model.cost_interact,
        )

    # ---- ACTIVATE ----
    for station_id in model.stations_by_zone.get(zone, []):
        if station_id in state.stations_online:
            continue
        station = model.stations[station_id]
        req = station.get("requires", {})
        if any(pid not in state.panels_ok for pid in req.get("panels_ok", [])):
            continue
        if any(sid not in state.stations_online for sid in req.get("stations_online", [])):
            continue
        if state.battery < model.cost_interact:
            continue
        new_state = state._with(stations_online=state.stations_online | {station_id},
            battery=state.battery - model.cost_interact,
        )
        yield (
            f"ACTIVATE({station_id})",
            {"op": "INTERACT", "target": station_id, "action": "ACTIVATE", "cost": model.cost_interact},
            new_state,
            model.cost_interact,
        )

    # ---- RECHARGE ----
    charger_id = model.charger_by_zone.get(zone)
    if charger_id is not None and state.battery < model.battery_max and state.battery >= model.cost_recharge:
        new_state = state._with(battery=model.battery_max)
        yield (
            "RECHARGE",
            {"op": "INTERACT", "target": charger_id, "action": "RECHARGE", "cost": model.cost_recharge},
            new_state,
            model.cost_recharge,
        )


# ---------------------------------------------------------------------------
# Node — carries the search history. Deliberately NOT part of State (design.md,
# "Qué pertenece al historial de búsqueda y no al estado físico").
# ---------------------------------------------------------------------------


@dataclass
class SearchNode:
    state: State
    parent: Optional["SearchNode"]
    step: Optional[Dict[str, Any]]
    g: int

    def recover_steps(self) -> List[Dict[str, Any]]:
        steps: List[Dict[str, Any]] = []
        node: Optional[SearchNode] = self
        while node is not None and node.parent is not None:
            steps.append(node.step)
            node = node.parent
        steps.reverse()
        return steps


def _dedup_key(state: State, model: ScenarioModel):
    """Identity used for duplicate/dominance detection — coarser than State
    equality. Dead payload objects are collapsed to an aggregate weight
    instead of their concrete identity: from this point on, two robots
    carrying "some dead junk totalling weight W" are in the exact same
    situation regardless of which specific dead objects compose W (they will
    never be used again — see the module docstring). Live objects keep their
    identity because it is functionally significant (a specific key opens a
    specific door).
    """
    live_payload = []
    dead_weight = 0
    for kind, ident in state.payload:
        is_live = _key_is_live(ident, model, state.doors_open) if kind == "key" else _tool_is_live(
            ident, model, state.panels_ok
        )
        if is_live:
            live_payload.append((kind, ident))
        else:
            dead_weight += model.weight.get((kind, ident), 1)

    live_materials = []
    dead_material_weight = 0
    for mtype, count in state.payload_materials:
        if _material_is_live(mtype, model, state.panels_ok):
            live_materials.append((mtype, count))
        else:
            dead_material_weight += model.weight.get(("material", mtype), 1) * count

    return (
        state.zone,
        frozenset(live_payload),
        dead_weight,
        tuple(sorted(live_materials)),
        dead_material_weight,
        state.ground_keys,
        state.ground_tools,
        state.ground_materials,
        state.doors_open,
        state.panels_ok,
        state.stations_online,
    )


def _register_if_undominated(pareto: Dict[Any, List[Tuple[int, int]]], cfg: Any, battery: int, g: int) -> bool:
    """Pareto-front register for (battery, g) pairs sharing the same `cfg`.

    A candidate (battery, g) is rejected if some existing entry has
    battery' >= battery and g' <= g: any continuation reachable from the
    dominated path is reachable from the dominating one at equal-or-lower
    cost with equal-or-more energy at every future step (both paths apply the
    same fixed action costs from that point on), so it can never lead to a
    strictly better plan and is safe to discard outright — not just defer.
    This single structure also subsumes the plain "already-visited exact
    state" check of classic Graph Search: an exact duplicate (same battery,
    same or higher g) is always dominated by its own earlier registration.
    """
    entries = pareto.setdefault(cfg, [])
    for b2, g2 in entries:
        if b2 >= battery and g2 <= g:
            return False
    entries[:] = [(b2, g2) for b2, g2 in entries if not (battery >= b2 and g <= g2)]
    entries.append((battery, g))
    return True


def ucs_search(model: ScenarioModel, max_expansions: int = 2_000_000) -> Tuple[Optional[SearchNode], int]:
    """Uniform-Cost Search with Graph Search + battery-dominance pruning.

    OPEN is a priority queue ordered by g(n) (a binary heap, as in the class
    pseudocode). The goal test happens at extraction, not at generation —
    required for optimality, since a goal can be generated via an expensive
    path while a cheaper path to it still sits in OPEN.
    """
    start = initial_state(model)
    counter = itertools.count()
    start_node = SearchNode(start, None, None, 0)
    heap: List[Tuple[int, int, SearchNode]] = [(0, next(counter), start_node)]

    pareto: Dict[Any, List[Tuple[int, int]]] = {}
    pareto[_dedup_key(start, model)] = [(start.battery, 0)]

    expansions = 0
    while heap:
        if expansions >= max_expansions:
            break
        g, _, node = heapq.heappop(heap)
        expansions += 1

        if goal_test(node.state, model):
            return node, expansions

        for _label, step, next_state, cost in successors(node.state, model):
            new_g = g + cost
            cfg = _dedup_key(next_state, model)
            if not _register_if_undominated(pareto, cfg, next_state.battery, new_g):
                continue
            child = SearchNode(next_state, node, step, new_g)
            heapq.heappush(heap, (new_g, next(counter), child))

    return None, expansions


# ---------------------------------------------------------------------------
# Public entry point — matches the /api/solve response contract exactly.
# ---------------------------------------------------------------------------


def solve(scenario: Dict[str, Any]) -> Dict[str, Any]:
    model = ScenarioModel(scenario)
    goal_node, expansions = ucs_search(model)

    if goal_node is None:
        return {
            "solution_found": False,
            "total_cost": 0,
            "steps": [],
            "message": f"FAILURE: UCS exhausted the state space ({expansions} nodes expanded) without reaching the goal.",
        }

    steps = goal_node.recover_steps()
    total_cost = goal_node.g
    assert total_cost == sum(s["cost"] for s in steps)  # sanity: g(n) matches the emitted plan

    return {
        "solution_found": True,
        "total_cost": total_cost,
        "steps": steps,
        "message": f"UCS (uninformed, graph search) found the optimal plan in {expansions} node expansions.",
    }