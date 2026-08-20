import type { Scenario, ScenarioLayout } from '../types'

export type Cell = [number, number]

export function cellKey(gx: number, gz: number): string {
  return `${gx},${gz}`
}

/** Expand rooms + corridor cells into a walkable set. */
export function buildWalkable(layout: ScenarioLayout): Set<string> {
  const set = new Set<string>()
  for (const room of layout.rooms) {
    for (let x = room.x; x < room.x + room.w; x++) {
      for (let z = room.z; z < room.z + room.d; z++) {
        set.add(cellKey(x, z))
      }
    }
  }
  for (const [gx, gz] of layout.corridor_cells) {
    set.add(cellKey(gx, gz))
  }
  return set
}

export function cellToWorld(
  gx: number,
  gz: number,
  cellSize: number,
  y = 0.35,
): [number, number, number] {
  return [(gx + 0.5) * cellSize, y, (gz + 0.5) * cellSize]
}

export function itemWorldPos(
  layout: ScenarioLayout,
  id: string,
  y = 0.4,
): [number, number, number] | null {
  const cell = layout.item_cells[id]
  if (!cell) return null
  return cellToWorld(cell[0], cell[1], layout.cell_size, y)
}

export interface WallSegment {
  x: number
  y: number
  z: number
  w: number
  h: number
  d: number
}

/** Axis-aligned wall segments on every walkable / non-walkable edge. */
export function generateWalls(layout: ScenarioLayout): WallSegment[] {
  const walkable = buildWalkable(layout)
  const cs = layout.cell_size
  const h = layout.wall_height
  const t = layout.wall_thickness
  const walls: WallSegment[] = []
  const seen = new Set<string>()

  const add = (x: number, z: number, w: number, d: number) => {
    const key = `${x.toFixed(3)},${z.toFixed(3)},${w.toFixed(3)},${d.toFixed(3)}`
    if (seen.has(key)) return
    seen.add(key)
    walls.push({ x, y: h / 2, z, w, h, d })
  }

  for (const key of walkable) {
    const [gx, gz] = key.split(',').map(Number)
    // east edge
    if (!walkable.has(cellKey(gx + 1, gz))) {
      add((gx + 1) * cs, (gz + 0.5) * cs, t, cs)
    }
    // west edge
    if (!walkable.has(cellKey(gx - 1, gz))) {
      add(gx * cs, (gz + 0.5) * cs, t, cs)
    }
    // south (+z) edge
    if (!walkable.has(cellKey(gx, gz + 1))) {
      add((gx + 0.5) * cs, (gz + 1) * cs, cs, t)
    }
    // north (-z) edge
    if (!walkable.has(cellKey(gx, gz - 1))) {
      add((gx + 0.5) * cs, gz * cs, cs, t)
    }
  }
  return walls
}

export function pathCellsWorld(
  cells: Cell[],
  cellSize: number,
): [number, number, number][] {
  return cells.map(([gx, gz]) => cellToWorld(gx, gz, cellSize))
}

/** Validate a grid path: adjacent steps, all walkable. */
export function validatePath(
  scenario: Scenario,
  cells: Cell[],
): string | null {
  if (cells.length < 2) return 'Path too short'
  const walkable = buildWalkable(scenario.layout)
  for (let i = 0; i < cells.length; i++) {
    const [gx, gz] = cells[i]
    if (!walkable.has(cellKey(gx, gz))) {
      return `Path cell (${gx},${gz}) is not walkable (wall/out of bounds)`
    }
    if (i > 0) {
      const [px, pz] = cells[i - 1]
      const dist = Math.abs(gx - px) + Math.abs(gz - pz)
      if (dist !== 1) {
        return `Path jump (${px},${pz})→(${gx},${gz}) is not orthogonal adjacent`
      }
    }
  }
  return null
}

export function getMovePath(
  scenario: Scenario,
  from: string,
  to: string,
): Cell[] | null {
  const key = `${from}-${to}`
  const path = scenario.layout.paths[key]
  return path ? (path as Cell[]) : null
}
