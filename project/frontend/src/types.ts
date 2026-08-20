export type DoorState = 'CLOSED' | 'OPEN'
export type PanelState = 'DAMAGED' | 'OK'
export type StationState = 'OFFLINE' | 'ONLINE'
export type DamageType = 'ELECTRICAL' | 'CIRCUIT' | 'WIRING'
export type MaterialType = 'FUSE' | 'CHIP' | 'CABLE'
export type VisualOp = 'MOVE' | 'PICKUP' | 'DROP' | 'INTERACT'

export interface RobotConfig {
  start: string
  battery_max: number
  battery_start: number
  cargo_capacity: number
}

export interface Zone {
  id: string
  name: string
  recharge: boolean
}

export interface Corridor {
  from: string
  to: string
  cost: number
  door: string | null
}

export interface Door {
  id: string
  color: string
  key: string
  state: DoorState
  between: [string, string]
}

export interface KeyItem {
  id: string
  color: string
  zone: string
  weight: number
}

export interface ToolItem {
  id: string
  repairs: DamageType
  zone: string
  weight: number
}

export interface MaterialStack {
  type: MaterialType
  zone: string
  count: number
  weight: number
}

export interface Panel {
  id: string
  zone: string
  damage: DamageType
  requires: { tool: string; material: MaterialType }
  state: PanelState
}

export interface Station {
  id: string
  kind: 'generator' | 'command' | 'artillery'
  zone: string
  state: StationState
  requires: {
    panels_ok?: string[]
    stations_online?: string[]
  }
}

export interface Charger {
  id: string
  zone: string
}

export interface ScenarioLayout {
  cell_size: number
  wall_height: number
  wall_thickness: number
  rooms: { id: string; x: number; z: number; w: number; d: number }[]
  corridor_cells: [number, number][]
  centers: Record<string, [number, number, number]>
  paths: Record<string, [number, number][]>
  door_positions: Record<
    string,
    { gx: number; gz: number; axis: 'x' | 'z'; height: number }
  >
  item_cells: Record<string, [number, number]>
}

export interface Scenario {
  meta: { id: string; title: string; description: string }
  robot: RobotConfig
  zones: Zone[]
  corridors: Corridor[]
  doors: Door[]
  keys: KeyItem[]
  tools: ToolItem[]
  materials: MaterialStack[]
  panels: Panel[]
  stations: Station[]
  chargers: Charger[]
  goal: { stations_online: string[] }
  action_costs: {
    pickup: number
    drop: number
    interact: number
    recharge: number
  }
  layout: ScenarioLayout
}

export type PayloadItem =
  | { kind: 'key'; id: string; color: string; weight: number }
  | { kind: 'tool'; id: string; repairs: DamageType; weight: number }
  | { kind: 'material'; type: MaterialType; weight: number }

export interface PlanStep {
  op: VisualOp
  from?: string
  to?: string
  item?: string
  target?: string
  action?: string
  consumes?: string
  cost: number
}

export interface SolveResponse {
  solution_found: boolean
  total_cost: number
  steps: PlanStep[]
  message?: string
}

export interface LogEntry {
  index: number
  text: string
  level: 'info' | 'ok' | 'error' | 'warn'
}

export interface WorldRuntime {
  robotZone: string
  battery: number
  energySpent: number
  payload: PayloadItem[]
  doors: Record<string, DoorState>
  panels: Record<string, PanelState>
  stations: Record<string, StationState>
  /** Ground items still in the world: key/tool ids or material type counts */
  groundKeys: Record<string, string>
  groundTools: Record<string, string>
  groundMaterials: Record<string, { type: MaterialType; count: number; zone: string }>
  robotPosition: [number, number, number]
  /** Yaw around vertical axis (radians). Visor faces +Z local. */
  robotYaw: number
}

export const COLOR_MAP: Record<string, string> = {
  cyan: '#22d3ee',
  yellow: '#facc15',
  magenta: '#e879f9',
  green: '#4ade80',
  red: '#f87171',
  blue: '#60a5fa',
  orange: '#fb923c',
}
