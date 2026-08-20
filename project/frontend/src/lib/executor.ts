import { getMovePath, pathCellsWorld, validatePath } from './grid'
import type {
  MaterialType,
  PayloadItem,
  PlanStep,
  Scenario,
  WorldRuntime,
} from '../types'

export interface StepResult {
  ok: boolean
  message: string
  runtime: WorldRuntime
  pathCells?: [number, number][]
}

function doorsOnPath(
  scenario: Scenario,
  cells: [number, number][],
): string[] {
  const ids: string[] = []
  for (const [gx, gz] of cells) {
    for (const [doorId, pos] of Object.entries(scenario.layout.door_positions)) {
      if (pos.gx === gx && pos.gz === gz && !ids.includes(doorId)) ids.push(doorId)
    }
  }
  return ids
}

function payloadWeight(payload: PayloadItem[]): number {
  return payload.reduce((s, p) => s + p.weight, 0)
}

function findCorridor(scenario: Scenario, from: string, to: string) {
  return scenario.corridors.find((c) => c.from === from && c.to === to)
}

function cloneRuntime(r: WorldRuntime): WorldRuntime {
  return {
    ...r,
    payload: [...r.payload],
    doors: { ...r.doors },
    panels: { ...r.panels },
    stations: { ...r.stations },
    groundKeys: { ...r.groundKeys },
    groundTools: { ...r.groundTools },
    groundMaterials: Object.fromEntries(
      Object.entries(r.groundMaterials).map(([k, v]) => [k, { ...v }]),
    ),
    robotPosition: [...r.robotPosition] as [number, number, number],
  }
}

function spend(runtime: WorldRuntime, cost: number, batteryMax: number): string | null {
  if (runtime.battery < cost) {
    return `Insufficient battery (have ${runtime.battery}, need ${cost})`
  }
  runtime.battery -= cost
  runtime.energySpent += cost
  if (runtime.battery > batteryMax) runtime.battery = batteryMax
  return null
}

function resolvePickupItem(
  scenario: Scenario,
  runtime: WorldRuntime,
  itemId: string,
): { item: PayloadItem; remove: () => void } | null {
  const key = scenario.keys.find((k) => k.id === itemId)
  if (key && runtime.groundKeys[itemId] === runtime.robotZone) {
    return {
      item: { kind: 'key', id: key.id, color: key.color, weight: key.weight },
      remove: () => {
        delete runtime.groundKeys[itemId]
      },
    }
  }
  const tool = scenario.tools.find((t) => t.id === itemId)
  if (tool && runtime.groundTools[itemId] === runtime.robotZone) {
    return {
      item: { kind: 'tool', id: tool.id, repairs: tool.repairs, weight: tool.weight },
      remove: () => {
        delete runtime.groundTools[itemId]
      },
    }
  }
  const mat = runtime.groundMaterials[itemId]
  if (mat && mat.zone === runtime.robotZone && mat.count > 0) {
    return {
      item: { kind: 'material', type: mat.type, weight: 1 },
      remove: () => {
        mat.count -= 1
        if (mat.count <= 0) delete runtime.groundMaterials[itemId]
      },
    }
  }
  return null
}

function removeFromPayload(runtime: WorldRuntime, itemId: string): PayloadItem | null {
  const idx = runtime.payload.findIndex((p) => {
    if (p.kind === 'key' || p.kind === 'tool') return p.id === itemId
    if (p.kind === 'material') return p.type === itemId
    return false
  })
  if (idx < 0) return null
  const [item] = runtime.payload.splice(idx, 1)
  return item
}

export function applyStep(
  scenario: Scenario,
  runtimeIn: WorldRuntime,
  step: PlanStep,
): StepResult {
  const runtime = cloneRuntime(runtimeIn)
  const cap = scenario.robot.cargo_capacity
  const batMax = scenario.robot.battery_max

  if (step.op === 'MOVE') {
    const from = step.from ?? runtime.robotZone
    const to = step.to
    if (!to) return { ok: false, message: 'MOVE missing destination', runtime: runtimeIn }
    if (from !== runtime.robotZone) {
      return {
        ok: false,
        message: `MOVE from ${from} but robot is in ${runtime.robotZone}`,
        runtime: runtimeIn,
      }
    }
    const corr = findCorridor(scenario, from, to)
    if (!corr) {
      return { ok: false, message: `No corridor ${from}→${to}`, runtime: runtimeIn }
    }
    if (corr.door && runtime.doors[corr.door] !== 'OPEN') {
      return {
        ok: false,
        message: `Door ${corr.door} is CLOSED — cannot MOVE ${from}→${to}`,
        runtime: runtimeIn,
      }
    }
    const pathCells = getMovePath(scenario, from, to)
    if (!pathCells) {
      return {
        ok: false,
        message: `No grid path defined for ${from}→${to}`,
        runtime: runtimeIn,
      }
    }
    const pathErr = validatePath(scenario, pathCells)
    if (pathErr) {
      return { ok: false, message: pathErr, runtime: runtimeIn }
    }
    for (const doorId of doorsOnPath(scenario, pathCells)) {
      if (runtime.doors[doorId] !== 'OPEN') {
        return {
          ok: false,
          message: `Door ${doorId} is CLOSED on path ${from}→${to}`,
          runtime: runtimeIn,
        }
      }
    }

    const cost = step.cost ?? corr.cost
    const err = spend(runtime, cost, batMax)
    if (err) return { ok: false, message: err, runtime: runtimeIn }
    runtime.robotZone = to
    const world = pathCellsWorld(pathCells, scenario.layout.cell_size)
    const end = world[world.length - 1]
    runtime.robotPosition = [end[0], 0.35, end[2]]
    return {
      ok: true,
      message: `MOVE ${from}→${to} (cost ${cost}, bat ${runtime.battery})`,
      runtime,
      pathCells,
    }
  }

  if (step.op === 'PICKUP') {
    const itemId = step.item
    if (!itemId) return { ok: false, message: 'PICKUP missing item', runtime: runtimeIn }
    const resolved = resolvePickupItem(scenario, runtime, itemId)
    if (!resolved) {
      return {
        ok: false,
        message: `Item ${itemId} not available in zone ${runtime.robotZone}`,
        runtime: runtimeIn,
      }
    }
    if (payloadWeight(runtime.payload) + resolved.item.weight > cap) {
      return {
        ok: false,
        message: `Cargo full (capacity ${cap}) — cannot PICKUP ${itemId}`,
        runtime: runtimeIn,
      }
    }
    const cost = step.cost ?? scenario.action_costs.pickup
    const err = spend(runtime, cost, batMax)
    if (err) return { ok: false, message: err, runtime: runtimeIn }
    resolved.remove()
    runtime.payload.push(resolved.item)
    return {
      ok: true,
      message: `PICKUP ${itemId} (cost ${cost}, bat ${runtime.battery})`,
      runtime,
    }
  }

  if (step.op === 'DROP') {
    const itemId = step.item
    if (!itemId) return { ok: false, message: 'DROP missing item', runtime: runtimeIn }
    const item = removeFromPayload(runtime, itemId)
    if (!item) {
      return { ok: false, message: `Item ${itemId} not in payload`, runtime: runtimeIn }
    }
    const cost = step.cost ?? scenario.action_costs.drop
    const err = spend(runtime, cost, batMax)
    if (err) return { ok: false, message: err, runtime: runtimeIn }
    if (item.kind === 'key') runtime.groundKeys[item.id] = runtime.robotZone
    else if (item.kind === 'tool') runtime.groundTools[item.id] = runtime.robotZone
    else {
      const existing = runtime.groundMaterials[item.type]
      if (existing && existing.zone === runtime.robotZone) existing.count += 1
      else
        runtime.groundMaterials[item.type] = {
          type: item.type,
          count: 1,
          zone: runtime.robotZone,
        }
    }
    return {
      ok: true,
      message: `DROP ${itemId} (cost ${cost}, bat ${runtime.battery})`,
      runtime,
    }
  }

  if (step.op === 'INTERACT') {
    const target = step.target
    const action = step.action
    if (!target || !action) {
      return { ok: false, message: 'INTERACT missing target/action', runtime: runtimeIn }
    }
    const cost =
      step.cost ??
      (action === 'RECHARGE' ? scenario.action_costs.recharge : scenario.action_costs.interact)

    if (action === 'OPEN_DOOR') {
      const door = scenario.doors.find((d) => d.id === target)
      if (!door) return { ok: false, message: `Unknown door ${target}`, runtime: runtimeIn }
      const [a, b] = door.between
      if (runtime.robotZone !== a && runtime.robotZone !== b) {
        return {
          ok: false,
          message: `Robot must be adjacent to ${target} (zones ${a}/${b})`,
          runtime: runtimeIn,
        }
      }
      if (runtime.doors[target] === 'OPEN') {
        return { ok: false, message: `Door ${target} already OPEN`, runtime: runtimeIn }
      }
      const hasKey = runtime.payload.some((p) => p.kind === 'key' && p.id === door.key)
      if (!hasKey) {
        return {
          ok: false,
          message: `Need ${door.key} in payload to open ${target}`,
          runtime: runtimeIn,
        }
      }
      const err = spend(runtime, cost, batMax)
      if (err) return { ok: false, message: err, runtime: runtimeIn }
      runtime.doors[target] = 'OPEN'
      return {
        ok: true,
        message: `INTERACT OPEN_DOOR ${target} (cost ${cost}, bat ${runtime.battery})`,
        runtime,
      }
    }

    if (action === 'REPAIR') {
      const panel = scenario.panels.find((p) => p.id === target)
      if (!panel) return { ok: false, message: `Unknown panel ${target}`, runtime: runtimeIn }
      if (runtime.robotZone !== panel.zone) {
        return {
          ok: false,
          message: `Robot must be in ${panel.zone} to repair ${target}`,
          runtime: runtimeIn,
        }
      }
      if (runtime.panels[target] === 'OK') {
        return { ok: false, message: `Panel ${target} already OK`, runtime: runtimeIn }
      }
      const hasTool = runtime.payload.some(
        (p) => p.kind === 'tool' && p.id === panel.requires.tool,
      )
      if (!hasTool) {
        return {
          ok: false,
          message: `Need tool ${panel.requires.tool} to repair ${target}`,
          runtime: runtimeIn,
        }
      }
      const matType = (step.consumes ?? panel.requires.material) as MaterialType
      if (matType !== panel.requires.material) {
        return {
          ok: false,
          message: `Wrong material ${matType} for ${target} (need ${panel.requires.material})`,
          runtime: runtimeIn,
        }
      }
      const matIdx = runtime.payload.findIndex(
        (p) => p.kind === 'material' && p.type === matType,
      )
      if (matIdx < 0) {
        return {
          ok: false,
          message: `Need material ${matType} in payload to repair ${target}`,
          runtime: runtimeIn,
        }
      }
      const err = spend(runtime, cost, batMax)
      if (err) return { ok: false, message: err, runtime: runtimeIn }
      runtime.payload.splice(matIdx, 1)
      runtime.panels[target] = 'OK'
      return {
        ok: true,
        message: `INTERACT REPAIR ${target} consumes=${matType} (cost ${cost}, bat ${runtime.battery})`,
        runtime,
      }
    }

    if (action === 'ACTIVATE') {
      const station = scenario.stations.find((s) => s.id === target)
      if (!station) return { ok: false, message: `Unknown station ${target}`, runtime: runtimeIn }
      if (runtime.robotZone !== station.zone) {
        return {
          ok: false,
          message: `Robot must be in ${station.zone} to activate ${target}`,
          runtime: runtimeIn,
        }
      }
      if (runtime.stations[target] === 'ONLINE') {
        return { ok: false, message: `Station ${target} already ONLINE`, runtime: runtimeIn }
      }
      for (const pid of station.requires.panels_ok ?? []) {
        if (runtime.panels[pid] !== 'OK') {
          return {
            ok: false,
            message: `Panel ${pid} must be OK before activating ${target}`,
            runtime: runtimeIn,
          }
        }
      }
      for (const sid of station.requires.stations_online ?? []) {
        if (runtime.stations[sid] !== 'ONLINE') {
          return {
            ok: false,
            message: `Station ${sid} must be ONLINE before activating ${target}`,
            runtime: runtimeIn,
          }
        }
      }
      const err = spend(runtime, cost, batMax)
      if (err) return { ok: false, message: err, runtime: runtimeIn }
      runtime.stations[target] = 'ONLINE'
      return {
        ok: true,
        message: `INTERACT ACTIVATE ${target} (cost ${cost}, bat ${runtime.battery})`,
        runtime,
      }
    }

    if (action === 'RECHARGE') {
      const charger = scenario.chargers.find((c) => c.id === target)
      const zoneOk =
        (charger && charger.zone === runtime.robotZone) ||
        scenario.zones.find((z) => z.id === runtime.robotZone)?.recharge
      if (!zoneOk) {
        return {
          ok: false,
          message: `No charger available in zone ${runtime.robotZone}`,
          runtime: runtimeIn,
        }
      }
      if (runtime.battery >= batMax) {
        return { ok: false, message: 'Battery already full', runtime: runtimeIn }
      }
      const err = spend(runtime, cost, batMax)
      if (err) return { ok: false, message: err, runtime: runtimeIn }
      runtime.battery = batMax
      return {
        ok: true,
        message: `INTERACT RECHARGE ${target} (cost ${cost}, bat ${runtime.battery})`,
        runtime,
      }
    }

    return { ok: false, message: `Unknown INTERACT action ${action}`, runtime: runtimeIn }
  }

  return { ok: false, message: `Unknown op ${(step as PlanStep).op}`, runtime: runtimeIn }
}

export function checkGoal(scenario: Scenario, runtime: WorldRuntime): boolean {
  return scenario.goal.stations_online.every((id) => runtime.stations[id] === 'ONLINE')
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
