from __future__ import annotations

from dataclasses import dataclass
import heapq
import itertools
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Estado y acciones internas
# ---------------------------------------------------------------------------

InventoryEntry = tuple[str, str, int]          # (kind, name, count)
GroundEntry = tuple[str, str, str, int]        # (kind, name, zone, count)


@dataclass(frozen=True, slots=True)
class State:
    """Situación física relevante del robot y del entorno."""

    position: str
    battery: int
    inventory: tuple[InventoryEntry, ...]
    ground: tuple[GroundEntry, ...]
    doors_open: frozenset[str]
    panels_repaired: frozenset[str]
    stations_online: frozenset[str]

    def world_key(self) -> tuple[Any, ...]:
        """Configuración física del mundo sin incluir la batería.

        Se usa únicamente para detectar llegadas claramente peores a la misma
        situación física. No es una heurística y no estima distancia a la meta.
        """

        return (
            self.position,
            self.inventory,
            self.ground,
            self.doors_open,
            self.panels_repaired,
            self.stations_online,
        )


@dataclass(frozen=True, slots=True)
class Action:
    """Acción interna del agente."""

    name: str
    cost: int
    target: str | None = None
    origin: str | None = None
    material: str | None = None

    def to_contract_step(self) -> dict[str, Any]:
        """Traduce una acción interna al contrato esperado por el frontend."""

        if self.name == "MOVER":
            return {
                "op": "MOVE",
                "from": self.origin,
                "to": self.target,
                "cost": self.cost,
            }

        if self.name == "RECOGER":
            return {
                "op": "PICKUP",
                "item": self.target,
                "cost": self.cost,
            }

        if self.name == "SOLTAR":
            return {
                "op": "DROP",
                "item": self.target,
                "cost": self.cost,
            }

        if self.name == "ABRIR_PUERTA":
            return {
                "op": "INTERACT",
                "target": self.target,
                "action": "OPEN_DOOR",
                "cost": self.cost,
            }

        if self.name == "REPARAR_PANEL":
            return {
                "op": "INTERACT",
                "target": self.target,
                "action": "REPAIR",
                "consumes": self.material,
                "cost": self.cost,
            }

        if self.name == "ACTIVAR_ESTACION":
            return {
                "op": "INTERACT",
                "target": self.target,
                "action": "ACTIVATE",
                "cost": self.cost,
            }

        if self.name == "RECARGAR":
            return {
                "op": "INTERACT",
                "target": self.target,
                "action": "RECHARGE",
                "cost": self.cost,
            }

        raise ValueError(f"Unknown internal action: {self.name}")


@dataclass(slots=True)
class SearchNode:
    """Nodo de búsqueda: estado + información del camino."""

    state: State
    g: int
    parent: int | None
    action: Action | None


# ---------------------------------------------------------------------------
# Formulación del problema
# ---------------------------------------------------------------------------

class EmergencyProblem:
    """Formulación del escenario como problema de búsqueda clásica."""

    def __init__(self, scenario: dict[str, Any]):
        self.scenario = scenario
        self.robot = scenario["robot"]
        self.costs = scenario["action_costs"]

        # Corredores indexados por zona de origen.
        self.corridors_from: dict[str, list[dict[str, Any]]] = {}
        for corridor in scenario.get("corridors", []):
            self.corridors_from.setdefault(
                corridor["from"], []
            ).append(corridor)

        # Entidades indexadas por id.
        self.doors = {
            door["id"]: door
            for door in scenario.get("doors", [])
        }

        self.panels = {
            panel["id"]: panel
            for panel in scenario.get("panels", [])
        }

        self.stations = {
            station["id"]: station
            for station in scenario.get("stations", [])
        }

        # Cargadores indexados por zona.
        self.chargers_by_zone: dict[str, list[dict[str, Any]]] = {}
        for charger in scenario.get("chargers", []):
            self.chargers_by_zone.setdefault(
                charger["zone"], []
            ).append(charger)

        # Pesos de objetos.
        self.key_weights = {
            key["id"]: int(key.get("weight", 1))
            for key in scenario.get("keys", [])
        }

        self.tool_weights = {
            tool["id"]: int(tool.get("weight", 1))
            for tool in scenario.get("tools", [])
        }

        self.material_weights: dict[str, int] = {}
        for material in scenario.get("materials", []):
            self.material_weights.setdefault(
                material["type"],
                int(material.get("weight", 1)),
            )

        # Estaciones necesarias para cumplir la meta, incluyendo dependencias.
        self.required_stations = self._station_dependency_closure(
            scenario.get("goal", {}).get("stations_online", [])
        )

        # Paneles necesarios para esas estaciones.
        self.required_panels: frozenset[str] = frozenset(
            panel_id
            for station_id in self.required_stations
            for panel_id in (
                self.stations.get(station_id, {})
                .get("requires", {})
                .get("panels_ok", [])
            )
        )

        self._validate_nonnegative_costs()
        self.initial = self._build_initial_state()

    # -----------------------------------------------------------------------
    # Validaciones y estado inicial
    # -----------------------------------------------------------------------

    def _validate_nonnegative_costs(self) -> None:
        """UCS requiere costos de acción no negativos."""

        values = [
            int(value)
            for value in self.costs.values()
        ]

        values.extend(
            int(corridor["cost"])
            for corridor in self.scenario.get("corridors", [])
        )

        if any(value < 0 for value in values):
            raise ValueError(
                "UCS requires non-negative action costs"
            )

    def _station_dependency_closure(
        self,
        goals: Iterable[str],
    ) -> frozenset[str]:
        """Incluye estaciones meta y dependencias obligatorias."""

        required: set[str] = set()
        stack = list(goals)

        while stack:
            station_id = stack.pop()

            if station_id in required:
                continue

            required.add(station_id)

            station = self.stations.get(station_id)

            if station is None:
                continue

            stack.extend(
                station
                .get("requires", {})
                .get("stations_online", [])
            )

        return frozenset(required)

    def _build_initial_state(self) -> State:
        """Construye el estado inicial a partir del escenario."""

        ground: dict[tuple[str, str, str], int] = {}

        for key in self.scenario.get("keys", []):
            ground[
                ("key", key["id"], key["zone"])
            ] = 1

        for tool in self.scenario.get("tools", []):
            ground[
                ("tool", tool["id"], tool["zone"])
            ] = 1

        for material in self.scenario.get("materials", []):
            ground_key = (
                "material",
                material["type"],
                material["zone"],
            )

            ground[ground_key] = (
                ground.get(ground_key, 0)
                + int(material.get("count", 1))
            )

        state = State(
            position=self.robot["start"],
            battery=int(self.robot["battery_start"]),
            inventory=(),
            ground=self._ground_tuple(ground),

            doors_open=frozenset(
                door["id"]
                for door in self.scenario.get("doors", [])
                if door.get("state") == "OPEN"
            ),

            panels_repaired=frozenset(
                panel["id"]
                for panel in self.scenario.get("panels", [])
                if panel.get("state") == "OK"
            ),

            stations_online=frozenset(
                station["id"]
                for station in self.scenario.get("stations", [])
                if station.get("state") == "ONLINE"
            ),
        )

        return self.canonicalize(state)

    # -----------------------------------------------------------------------
    # Representación canónica
    # -----------------------------------------------------------------------

    @staticmethod
    def _inventory_dict(
        state: State,
    ) -> dict[tuple[str, str], int]:

        return {
            (kind, name): count
            for kind, name, count in state.inventory
        }

    @staticmethod
    def _ground_dict(
        state: State,
    ) -> dict[tuple[str, str, str], int]:

        return {
            (kind, name, zone): count
            for kind, name, zone, count in state.ground
        }

    @staticmethod
    def _inventory_tuple(
        inventory: dict[tuple[str, str], int],
    ) -> tuple[InventoryEntry, ...]:

        return tuple(
            sorted(
                (kind, name, int(count))
                for (kind, name), count in inventory.items()
                if count > 0
            )
        )

    @staticmethod
    def _ground_tuple(
        ground: dict[tuple[str, str, str], int],
    ) -> tuple[GroundEntry, ...]:

        return tuple(
            sorted(
                (kind, name, zone, int(count))
                for (kind, name, zone), count in ground.items()
                if count > 0
            )
        )

    def canonicalize(
        self,
        state: State,
    ) -> State:
        """Mantiene una representación única de situaciones equivalentes.

        No calcula una distancia a la meta ni usa una heurística.
        Únicamente evita conservar en el suelo objetos que ya no pueden
        producir ninguna acción futura relevante.
        """

        ground = self._ground_dict(state)
        cleaned: dict[tuple[str, str, str], int] = {}

        for (kind, name, zone), count in ground.items():

            if kind == "key":
                if self._key_relevant(name, state):
                    cleaned[(kind, name, zone)] = 1
                continue

            if kind == "tool":
                if self._tool_relevant(name, state):
                    cleaned[(kind, name, zone)] = 1
                continue

            if kind == "material":
                need = self._material_remaining_need(
                    name,
                    state,
                )

                if need > 0:
                    cleaned[(kind, name, zone)] = min(
                        count,
                        need,
                    )

                continue

        return State(
            position=state.position,
            battery=state.battery,
            inventory=state.inventory,
            ground=self._ground_tuple(cleaned),
            doors_open=state.doors_open,
            panels_repaired=state.panels_repaired,
            stations_online=state.stations_online,
        )

    # -----------------------------------------------------------------------
    # Relevancia para Applicable(s)
    # -----------------------------------------------------------------------

    def _key_relevant(
        self,
        key_id: str,
        state: State,
    ) -> bool:
        """Una llave es relevante mientras exista una puerta pendiente que la use."""

        return any(
            door.get("key") == key_id
            and door_id not in state.doors_open
            for door_id, door in self.doors.items()
        )

    def _tool_relevant(
        self,
        tool_id: str,
        state: State,
    ) -> bool:
        """Una herramienta es relevante mientras quede un panel requerido que la use."""

        return any(
            panel_id not in state.panels_repaired
            and self.panels[panel_id]
            .get("requires", {})
            .get("tool") == tool_id

            for panel_id in self.required_panels

            if panel_id in self.panels
        )

    def _material_remaining_need(
        self,
        material: str,
        state: State,
    ) -> int:
        """Cantidad de reparaciones pendientes que todavía necesitan ese material."""

        return sum(
            1
            for panel_id in self.required_panels

            if panel_id in self.panels
            and panel_id not in state.panels_repaired
            and self.panels[panel_id]
            .get("requires", {})
            .get("material") == material
        )

    def _item_relevant_for_pickup(
        self,
        kind: str,
        name: str,
        state: State,
    ) -> bool:
        """Decide si recoger un objeto todavía puede habilitar acciones futuras."""

        if kind == "key":
            return self._key_relevant(
                name,
                state,
            )

        if kind == "tool":
            return self._tool_relevant(
                name,
                state,
            )

        if kind == "material":
            inventory = self._inventory_dict(state)

            carried = inventory.get(
                ("material", name),
                0,
            )

            return (
                carried
                < self._material_remaining_need(
                    name,
                    state,
                )
            )

        return False

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def item_weight(
        self,
        kind: str,
        name: str,
    ) -> int:

        if kind == "key":
            return self.key_weights.get(name, 1)

        if kind == "tool":
            return self.tool_weights.get(name, 1)

        if kind == "material":
            return self.material_weights.get(name, 1)

        raise ValueError(
            f"Unknown item kind: {kind}"
        )

    def inventory_weight(
        self,
        state: State,
    ) -> int:

        return sum(
            self.item_weight(kind, name) * count
            for kind, name, count in state.inventory
        )

    def _has_inventory(
        self,
        state: State,
        kind: str,
        name: str,
    ) -> bool:

        return (
            self._inventory_dict(state)
            .get((kind, name), 0)
            > 0
        )

    def _ground_items_here(
        self,
        state: State,
    ) -> list[tuple[str, str, int]]:

        return [
            (kind, name, count)

            for kind, name, zone, count
            in state.ground

            if zone == state.position
            and count > 0
        ]

    # -----------------------------------------------------------------------
    # Applicable(s)
    # -----------------------------------------------------------------------

    def applicable(
        self,
        state: State,
    ) -> list[Action]:
        """Devuelve las acciones aplicables en el estado actual."""

        actions: list[Action] = []

        battery = state.battery

        interact_cost = int(
            self.costs["interact"]
        )

        pickup_cost = int(
            self.costs["pickup"]
        )

        drop_cost = int(
            self.costs["drop"]
        )

        recharge_cost = int(
            self.costs["recharge"]
        )

        # -------------------------------------------------------------------
        # 1) MOVER
        # -------------------------------------------------------------------

        for corridor in self.corridors_from.get(
            state.position,
            [],
        ):
            cost = int(
                corridor["cost"]
            )

            door_id = corridor.get(
                "door"
            )

            if battery < cost:
                continue

            if (
                door_id
                and door_id not in state.doors_open
            ):
                continue

            actions.append(
                Action(
                    name="MOVER",
                    cost=cost,
                    target=corridor["to"],
                    origin=state.position,
                )
            )

        # -------------------------------------------------------------------
        # 2) RECOGER
        # -------------------------------------------------------------------

        current_weight = self.inventory_weight(
            state
        )

        capacity = int(
            self.robot["cargo_capacity"]
        )

        relevant_here: list[
            tuple[str, str, int]
        ] = []

        for (
            kind,
            name,
            _count,
        ) in self._ground_items_here(state):

            if not self._item_relevant_for_pickup(
                kind,
                name,
                state,
            ):
                continue

            weight = self.item_weight(
                kind,
                name,
            )

            relevant_here.append(
                (kind, name, weight)
            )

            if (
                battery >= pickup_cost
                and current_weight + weight <= capacity
            ):
                actions.append(
                    Action(
                        name="RECOGER",
                        cost=pickup_cost,
                        target=name,
                    )
                )

        # -------------------------------------------------------------------
        # 3) SOLTAR
        # -------------------------------------------------------------------
        # DROP solo se genera cuando hace falta liberar capacidad AHORA
        # para recoger un objeto relevante presente en la zona actual.

        needs_space_now = any(
            weight <= capacity
            and current_weight + weight > capacity

            for _kind, _name, weight
            in relevant_here
        )

        if (
            needs_space_now
            and battery >= drop_cost
        ):

            blocked_free = [
                current_weight + weight - capacity

                for _kind, _name, weight
                in relevant_here

                if (
                    weight <= capacity
                    and current_weight + weight > capacity
                )
            ]

            min_free_needed = (
                min(blocked_free)
                if blocked_free
                else 0
            )

            dead_candidates: list[
                tuple[int, str]
            ] = []

            other_candidates: list[
                tuple[str, str, int]
            ] = []

            inventory_map = self._inventory_dict(
                state
            )

            for (
                kind,
                name,
                count,
            ) in state.inventory:

                if count <= 0:
                    continue

                weight = self.item_weight(
                    kind,
                    name,
                )

                if weight <= 0:
                    continue

                other_candidates.append(
                    (kind, name, weight)
                )

                # Verificar si el objeto ya cumplió su función.
                dead = False

                if kind == "key":
                    dead = not self._key_relevant(
                        name,
                        state,
                    )

                elif kind == "tool":
                    dead = not self._tool_relevant(
                        name,
                        state,
                    )

                elif kind == "material":
                    remaining_need = (
                        self._material_remaining_need(
                            name,
                            state,
                        )
                    )

                    carried = inventory_map.get(
                        ("material", name),
                        0,
                    )

                    dead = carried > remaining_need

                # Si este objeto ya no sirve y por sí solo
                # libera el espacio necesario, es candidato.
                if (
                    dead
                    and weight >= min_free_needed
                ):
                    dead_candidates.append(
                        (weight, name)
                    )

            if dead_candidates:

                # Elegimos un solo representante entre opciones
                # equivalentes para no generar ramas redundantes.
                max_weight = max(
                    weight
                    for weight, _name
                    in dead_candidates
                )

                representative = min(
                    name
                    for weight, name
                    in dead_candidates
                    if weight == max_weight
                )

                actions.append(
                    Action(
                        name="SOLTAR",
                        cost=drop_cost,
                        target=representative,
                    )
                )

            else:

                # Si no existe un objeto claramente descartable,
                # se permiten las alternativas necesarias.
                for (
                    _kind,
                    name,
                    _weight,
                ) in other_candidates:

                    actions.append(
                        Action(
                            name="SOLTAR",
                            cost=drop_cost,
                            target=name,
                        )
                    )

        # -------------------------------------------------------------------
        # 4) ABRIR_PUERTA
        # -------------------------------------------------------------------

        if battery >= interact_cost:

            for (
                door_id,
                door,
            ) in self.doors.items():

                if door_id in state.doors_open:
                    continue

                if (
                    state.position
                    not in tuple(
                        door.get("between", [])
                    )
                ):
                    continue

                key_id = door.get(
                    "key"
                )

                if (
                    key_id
                    and self._has_inventory(
                        state,
                        "key",
                        key_id,
                    )
                ):
                    actions.append(
                        Action(
                            name="ABRIR_PUERTA",
                            cost=interact_cost,
                            target=door_id,
                        )
                    )

        # -------------------------------------------------------------------
        # 5) REPARAR_PANEL
        # -------------------------------------------------------------------

        if battery >= interact_cost:

            for panel_id in self.required_panels:

                panel = self.panels.get(
                    panel_id
                )

                if (
                    panel is None
                    or panel_id in state.panels_repaired
                ):
                    continue

                if (
                    panel.get("zone")
                    != state.position
                ):
                    continue

                requirements = panel.get(
                    "requires",
                    {},
                )

                tool = requirements.get(
                    "tool"
                )

                material = requirements.get(
                    "material"
                )

                if not tool or not material:
                    continue

                if (
                    self._has_inventory(
                        state,
                        "tool",
                        tool,
                    )
                    and self._has_inventory(
                        state,
                        "material",
                        material,
                    )
                ):
                    actions.append(
                        Action(
                            name="REPARAR_PANEL",
                            cost=interact_cost,
                            target=panel_id,
                            material=material,
                        )
                    )

        # -------------------------------------------------------------------
        # 6) ACTIVAR_ESTACION
        # -------------------------------------------------------------------

        if battery >= interact_cost:

            for station_id in self.required_stations:

                station = self.stations.get(
                    station_id
                )

                if (
                    station is None
                    or station_id in state.stations_online
                ):
                    continue

                if (
                    station.get("zone")
                    != state.position
                ):
                    continue

                requirements = station.get(
                    "requires",
                    {},
                )

                if not all(
                    panel_id in state.panels_repaired

                    for panel_id
                    in requirements.get(
                        "panels_ok",
                        [],
                    )
                ):
                    continue

                if not all(
                    required_station
                    in state.stations_online

                    for required_station
                    in requirements.get(
                        "stations_online",
                        [],
                    )
                ):
                    continue

                actions.append(
                    Action(
                        name="ACTIVAR_ESTACION",
                        cost=interact_cost,
                        target=station_id,
                    )
                )

        # -------------------------------------------------------------------
        # 7) RECARGAR
        # -------------------------------------------------------------------

        if (
            battery >= recharge_cost
            and battery < int(
                self.robot["battery_max"]
            )
            and state.position
            in self.chargers_by_zone
        ):

            for charger in (
                self.chargers_by_zone[
                    state.position
                ]
            ):
                actions.append(
                    Action(
                        name="RECARGAR",
                        cost=recharge_cost,
                        target=charger["id"],
                    )
                )

        return actions

    # -----------------------------------------------------------------------
    # Result(s, a)
    # -----------------------------------------------------------------------

    def result(
        self,
        state: State,
        action: Action,
    ) -> State:
        """Aplica una acción previamente validada por Applicable."""

        inventory = self._inventory_dict(
            state
        )

        ground = self._ground_dict(
            state
        )

        position = state.position
        battery = state.battery - action.cost

        doors_open = set(
            state.doors_open
        )

        panels_repaired = set(
            state.panels_repaired
        )

        stations_online = set(
            state.stations_online
        )

        # MOVER
        if action.name == "MOVER":
            position = str(
                action.target
            )

        # RECOGER
        elif action.name == "RECOGER":

            found: tuple[
                str,
                str,
                str,
            ] | None = None

            for (
                kind,
                name,
                zone,
            ) in ground:

                if (
                    name == action.target
                    and zone == state.position
                    and ground[
                        (kind, name, zone)
                    ] > 0
                ):
                    found = (
                        kind,
                        name,
                        zone,
                    )
                    break

            if found is None:
                raise ValueError(
                    "PICKUP target not on ground: "
                    f"{action.target}"
                )

            kind, name, _zone = found

            ground[found] -= 1

            if ground[found] <= 0:
                del ground[found]

            inventory[
                (kind, name)
            ] = (
                inventory.get(
                    (kind, name),
                    0,
                )
                + 1
            )

        # SOLTAR
        elif action.name == "SOLTAR":

            matches = [
                (kind, name)

                for (
                    kind,
                    name,
                ), count
                in inventory.items()

                if (
                    name == action.target
                    and count > 0
                )
            ]

            if not matches:
                raise ValueError(
                    "DROP target not in inventory: "
                    f"{action.target}"
                )

            kind, name = matches[0]

            inventory[
                (kind, name)
            ] -= 1

            if inventory[(kind, name)] <= 0:
                del inventory[(kind, name)]

            ground_key = (
                kind,
                name,
                state.position,
            )

            ground[ground_key] = (
                ground.get(
                    ground_key,
                    0,
                )
                + 1
            )

        # ABRIR_PUERTA
        elif action.name == "ABRIR_PUERTA":

            doors_open.add(
                str(action.target)
            )

        # REPARAR_PANEL
        elif action.name == "REPARAR_PANEL":

            material = str(
                action.material
            )

            material_key = (
                "material",
                material,
            )

            if (
                inventory.get(
                    material_key,
                    0,
                )
                <= 0
            ):
                raise ValueError(
                    f"Missing material {material}"
                )

            inventory[
                material_key
            ] -= 1

            if (
                inventory[
                    material_key
                ]
                <= 0
            ):
                del inventory[
                    material_key
                ]

            panels_repaired.add(
                str(action.target)
            )

        # ACTIVAR_ESTACION
        elif action.name == "ACTIVAR_ESTACION":

            stations_online.add(
                str(action.target)
            )

        # RECARGAR
        elif action.name == "RECARGAR":

            # El costo ya fue pagado.
            # Luego la batería queda en battery_max.
            battery = int(
                self.robot["battery_max"]
            )

        else:
            raise ValueError(
                f"Unknown action: {action.name}"
            )

        new_state = State(
            position=position,
            battery=battery,
            inventory=self._inventory_tuple(
                inventory
            ),
            ground=self._ground_tuple(
                ground
            ),
            doors_open=frozenset(
                doors_open
            ),
            panels_repaired=frozenset(
                panels_repaired
            ),
            stations_online=frozenset(
                stations_online
            ),
        )

        return self.canonicalize(
            new_state
        )

    # -----------------------------------------------------------------------
    # Goal(s)
    # -----------------------------------------------------------------------

    def goal(
        self,
        state: State,
    ) -> bool:
        """La meta se cumple cuando todas las estaciones objetivo están ONLINE."""

        return all(
            station_id in state.stations_online

            for station_id in (
                self.scenario
                .get("goal", {})
                .get(
                    "stations_online",
                    [],
                )
            )
        )


# ---------------------------------------------------------------------------
# Descarte de llegadas peores a la misma configuración
# ---------------------------------------------------------------------------

def _arrival_is_worse(
    arrivals: dict[tuple[Any, ...], list[tuple[int, int]]],
    state: State,
    g: int,
) -> bool:
    """Indica si ya existe una llegada que es claramente mejor.

    Para la misma configuración física del mundo (misma posición, inventario,
    objetos en suelo, puertas, paneles y estaciones), una llegada anterior
    domina a la nueva únicamente cuando:

    - tiene batería mayor o igual, y
    - tiene costo acumulado g menor o igual.

    Esa nueva llegada no habilita ninguna acción que la anterior no pudiera
    ejecutar y además no es más barata, por lo que puede descartarse.

    IMPORTANTE:
    esto NO usa h(n), no estima distancia a la meta y no cambia la prioridad
    de OPEN. La búsqueda sigue siendo Uniform Cost Search.
    """

    key = state.world_key()

    return any(
        old_battery >= state.battery
        and old_g <= g
        for old_battery, old_g
        in arrivals.get(key, [])
    )


def _register_arrival(
    arrivals: dict[tuple[Any, ...], list[tuple[int, int]]],
    state: State,
    g: int,
) -> None:
    """Registra una llegada y elimina llegadas que ahora son claramente peores."""

    key = state.world_key()
    current = arrivals.get(key, [])

    # Si la nueva llegada tiene >= batería y <= costo que otra llegada,
    # esa otra llegada queda reemplazada.
    current = [
        (old_battery, old_g)
        for old_battery, old_g in current
        if not (
            state.battery >= old_battery
            and g <= old_g
        )
    ]

    current.append(
        (state.battery, g)
    )

    arrivals[key] = current


def _arrival_is_active(
    arrivals: dict[tuple[Any, ...], list[tuple[int, int]]],
    state: State,
    g: int,
) -> bool:
    """Comprueba si una entrada de OPEN sigue siendo una llegada válida."""

    return (
        state.battery,
        g,
    ) in arrivals.get(
        state.world_key(),
        [],
    )


# ---------------------------------------------------------------------------
# Reconstrucción del plan
# ---------------------------------------------------------------------------

def _reconstruct(
    nodes: list[SearchNode],
    index: int,
) -> list[dict[str, Any]]:

    actions: list[Action] = []

    while True:
        node = nodes[index]

        if node.action is not None:
            actions.append(
                node.action
            )

        if node.parent is None:
            break

        index = node.parent

    actions.reverse()

    return [
        action.to_contract_step()
        for action in actions
    ]


# ---------------------------------------------------------------------------
# Uniform Cost Search (UCS) — búsqueda NO informada
# ---------------------------------------------------------------------------

def solve_scenario(
    scenario: dict[str, Any],
) -> dict[str, Any]:
    """Resuelve el escenario exclusivamente con Uniform Cost Search (UCS).

    OPEN se ordena solamente por g(n). No se utiliza ninguna heurística h(n),
    A*, Greedy, MST, lower bound ni otra estrategia informada.

    Para controlar estados redundantes se usa Graph Search y se descartan
    llegadas claramente peores a una misma configuración física: si ya existe
    una llegada con menor o igual costo y mayor o igual batería, la nueva no
    puede ofrecer ninguna ventaja futura.
    """

    try:
        problem = EmergencyProblem(
            scenario
        )

    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:

        return {
            "solution_found": False,
            "total_cost": 0,
            "steps": [],
            "message": (
                f"Invalid scenario for UCS: {exc}"
            ),
        }

    start = problem.initial

    # Si el estado inicial ya cumple la misión.
    if problem.goal(start):
        return {
            "solution_found": True,
            "total_cost": 0,
            "steps": [],
            "message": (
                "UCS: the initial state already satisfies the mission."
            ),
        }

    # -----------------------------------------------------------------------
    # Nodo raíz
    # -----------------------------------------------------------------------

    nodes: list[SearchNode] = [
        SearchNode(
            state=start,
            g=0,
            parent=None,
            action=None,
        )
    ]

    # -----------------------------------------------------------------------
    # OPEN
    # -----------------------------------------------------------------------
    # Cola de prioridad ordenada EXCLUSIVAMENTE por g(n).
    #
    # La segunda componente solamente rompe empates por orden de inserción.
    # No contiene información sobre la cercanía a la meta.

    frontier: list[
        tuple[int, int, int]
    ] = []

    counter = itertools.count()

    heapq.heappush(
        frontier,
        (
            0,
            next(counter),
            0,
        ),
    )

    # Mejor costo conocido para cada estado EXACTO, incluida la batería.
    best_g: dict[State, int] = {
        start: 0
    }

    # CLOSED de Graph Search.
    explored: set[State] = set()

    # Para una misma configuración física sin batería, conservamos únicamente
    # combinaciones costo/batería que no sean claramente peores que otra.
    #
    # Esto es descarte de estados redundantes, NO una función heurística.
    arrivals: dict[
        tuple[Any, ...],
        list[tuple[int, int]],
    ] = {}

    _register_arrival(
        arrivals,
        start,
        0,
    )

    expanded = 0
    generated = 1
    discarded_worse = 0

    # -----------------------------------------------------------------------
    # Uniform Cost Search
    # -----------------------------------------------------------------------

    while frontier:

        # UCS SIEMPRE extrae el nodo con menor g(n).
        g, _order, node_index = heapq.heappop(
            frontier
        )

        node = nodes[
            node_index
        ]

        state = node.state

        # Entrada vieja de OPEN:
        # ya apareció una ruta más barata al mismo estado exacto.
        if (
            g
            != best_g.get(state)
        ):
            continue

        # La entrada pudo quedar reemplazada por otra llegada a la misma
        # configuración con menor/equal costo y mayor/equal batería.
        if not _arrival_is_active(
            arrivals,
            state,
            g,
        ):
            continue

        # Graph Search: no reexpandir estados exactos de CLOSED.
        if state in explored:
            continue

        # En UCS la prueba de meta se realiza al EXTRAER el nodo de OPEN.
        if problem.goal(state):

            steps = _reconstruct(
                nodes,
                node_index,
            )

            return {
                "solution_found": True,
                "total_cost": g,
                "steps": steps,
                "message": (
                    "UCS found an optimal plan using only g(n). "
                    f"Expanded {expanded} states; "
                    f"generated {generated} nodes; "
                    f"discarded {discarded_worse} worse arrivals."
                ),
            }

        explored.add(
            state
        )

        expanded += 1

        # Diagnóstico únicamente.
        # No cambia la prioridad, las acciones ni el resultado de UCS.
        if expanded % 10000 == 0:
            print(
                f"[UCS] Expanded: {expanded} | "
                f"OPEN: {len(frontier)} | "
                f"Generated: {generated} | "
                f"Discarded: {discarded_worse} | "
                f"g: {g}"
            )

        # -------------------------------------------------------------------
        # Expandir acciones aplicables
        # -------------------------------------------------------------------

        for action in problem.applicable(
            state
        ):

            child = problem.result(
                state,
                action,
            )

            child_g = (
                g
                + action.cost
            )

            # Si el estado EXACTO ya fue expandido por UCS, no se reexpande.
            if child in explored:
                continue

            # Parent Discarding / mejor llegada al estado exacto.
            old_exact_g = best_g.get(
                child
            )

            if (
                old_exact_g is not None
                and old_exact_g <= child_g
            ):
                continue

            # Descartar únicamente una llegada que sea claramente peor:
            # misma configuración física, >= costo y <= batería.
            if _arrival_is_worse(
                arrivals,
                child,
                child_g,
            ):
                discarded_worse += 1
                continue

            # La nueva llegada es útil y se registra.
            best_g[
                child
            ] = child_g

            _register_arrival(
                arrivals,
                child,
                child_g,
            )

            child_index = len(
                nodes
            )

            nodes.append(
                SearchNode(
                    state=child,
                    g=child_g,
                    parent=node_index,
                    action=action,
                )
            )

            # La prioridad sigue siendo ÚNICAMENTE child_g = g(n).
            heapq.heappush(
                frontier,
                (
                    child_g,
                    next(counter),
                    child_index,
                ),
            )

            generated += 1

    return {
        "solution_found": False,
        "total_cost": 0,
        "steps": [],
        "message": (
            "FAILURE: no plan satisfies the mission. "
            f"Expanded {expanded} states; "
            f"generated {generated} nodes; "
            f"discarded {discarded_worse} worse arrivals."
        ),
    }
