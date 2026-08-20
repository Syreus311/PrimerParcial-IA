import { create } from 'zustand'
import type {
  LogEntry,
  PayloadItem,
  PlanStep,
  Scenario,
  SolveResponse,
  WorldRuntime,
} from '../types'

function buildRuntime(scenario: Scenario): WorldRuntime {
  const center = scenario.layout.centers[scenario.robot.start] ?? [0, 0, 0]
  const groundKeys: Record<string, string> = {}
  for (const k of scenario.keys) groundKeys[k.id] = k.zone
  const groundTools: Record<string, string> = {}
  for (const t of scenario.tools) groundTools[t.id] = t.zone
  const groundMaterials: Record<string, { type: 'FUSE' | 'CHIP' | 'CABLE'; count: number; zone: string }> = {}
  for (const m of scenario.materials) {
    groundMaterials[m.type] = { type: m.type, count: m.count, zone: m.zone }
  }
  const doors: Record<string, 'CLOSED' | 'OPEN'> = {}
  for (const d of scenario.doors) doors[d.id] = d.state
  const panels: Record<string, 'DAMAGED' | 'OK'> = {}
  for (const p of scenario.panels) panels[p.id] = p.state
  const stations: Record<string, 'OFFLINE' | 'ONLINE'> = {}
  for (const s of scenario.stations) stations[s.id] = s.state

  return {
    robotZone: scenario.robot.start,
    battery: scenario.robot.battery_start,
    energySpent: 0,
    payload: [],
    doors,
    panels,
    stations,
    groundKeys,
    groundTools,
    groundMaterials,
    robotPosition: [center[0], 0.35, center[2]],
    robotYaw: 0,
  }
}

interface SimState {
  scenario: Scenario | null
  runtime: WorldRuntime | null
  plan: PlanStep[]
  totalCost: number
  stepIndex: number
  running: boolean
  log: LogEntry[]
  speed: number
  animTarget: [number, number, number] | null
  animWaypoints: [number, number, number][]
  error: string | null

  loadScenario: (scenario: Scenario) => void
  reset: () => void
  setPlan: (response: SolveResponse) => void
  setRunning: (v: boolean) => void
  setSpeed: (v: number) => void
  appendLog: (entry: Omit<LogEntry, 'index'>) => void
  applyRuntime: (runtime: WorldRuntime) => void
  setStepIndex: (i: number) => void
  setAnim: (waypoints: [number, number, number][], target: [number, number, number] | null) => void
  setRobotPosition: (pos: [number, number, number]) => void
  setRobotYaw: (yaw: number) => void
  setError: (msg: string | null) => void
  setPayload: (payload: PayloadItem[]) => void
}

export const useSimStore = create<SimState>((set, get) => ({
  scenario: null,
  runtime: null,
  plan: [],
  totalCost: 0,
  stepIndex: 0,
  running: false,
  log: [],
  speed: 1,
  animTarget: null,
  animWaypoints: [],
  error: null,

  loadScenario: (scenario) => {
    const runtime = buildRuntime(scenario)
    set({
      scenario,
      runtime,
      plan: [],
      totalCost: 0,
      stepIndex: 0,
      running: false,
      animTarget: null,
      animWaypoints: [],
      error: null,
      log: [
        {
          index: 0,
          text: '[000] System initialized. Awaiting plan...',
          level: 'info',
        },
      ],
    })
  },

  reset: () => {
    const { scenario } = get()
    if (!scenario) return
    get().loadScenario(scenario)
  },

  setPlan: (response) => {
    set({
      plan: response.steps,
      totalCost: response.total_cost,
      stepIndex: 0,
      error: response.solution_found ? null : (response.message ?? 'FAILURE'),
    })
  },

  setRunning: (v) => set({ running: v }),
  setSpeed: (v) => set({ speed: v }),
  setStepIndex: (i) => set({ stepIndex: i }),
  setError: (msg) => set({ error: msg }),
  setPayload: (payload) => {
    const runtime = get().runtime
    if (!runtime) return
    set({ runtime: { ...runtime, payload } })
  },

  appendLog: (entry) => {
    const log = get().log
    const index = log.length
    set({ log: [...log, { ...entry, index }] })
  },

  applyRuntime: (runtime) => set({ runtime }),

  setAnim: (waypoints, target) => set({ animWaypoints: waypoints, animTarget: target }),

  setRobotPosition: (pos) => {
    const runtime = get().runtime
    if (!runtime) return
    set({ runtime: { ...runtime, robotPosition: pos } })
  },

  setRobotYaw: (yaw) => {
    const runtime = get().runtime
    if (!runtime) return
    set({ runtime: { ...runtime, robotYaw: yaw } })
  },
}))

export { buildRuntime }
