import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import type { Group } from 'three'
import { COLOR_MAP } from '../types'
import { cellToWorld, itemWorldPos } from '../lib/grid'
import { FloatingLabel } from './FloatingLabel'
import { useSimStore } from '../store/simStore'

/** Sliding door that drops into the floor when OPEN — walls can fully enclose the station. */
export function SlidingDoor({ id, color }: { id: string; color: string }) {
  const scenario = useSimStore((s) => s.scenario)
  const state = useSimStore((s) => s.runtime?.doors[id] ?? 'CLOSED')
  const group = useRef<Group>(null)
  const pos = scenario?.layout.door_positions[id]
  const hex = COLOR_MAP[color] ?? color
  const cs = scenario?.layout.cell_size ?? 1
  const height = pos?.height ?? 1.55

  const closed = useMemo(() => {
    if (!pos) return [0, height / 2, 0] as [number, number, number]
    const [wx, , wz] = cellToWorld(pos.gx, pos.gz, cs, 0)
    return [wx, height / 2, wz] as [number, number, number]
  }, [pos, cs, height])

  const openY = -height / 2 - 0.05

  useFrame((_, dt) => {
    if (!group.current) return
    const targetY = state === 'OPEN' ? openY : closed[1]
    group.current.position.y += (targetY - group.current.position.y) * Math.min(1, dt * 5)
  })

  if (!pos) return null

  const isX = pos.axis === 'x'
  const size: [number, number, number] = isX ? [0.18, height, cs * 0.92] : [cs * 0.92, height, 0.18]

  return (
    <group ref={group} position={closed}>
      <mesh>
        <boxGeometry args={size} />
        <meshStandardMaterial
          color={hex}
          transparent
          opacity={0.5}
          emissive={hex}
          emissiveIntensity={0.25}
          roughness={0.2}
          metalness={0.4}
        />
      </mesh>
      <FloatingLabel name={id} state={state} position={[0, height / 2 + 0.35, 0]} color={hex} />
    </group>
  )
}

export function KeyVoxel({ id, color }: { id: string; color: string }) {
  const zone = useSimStore((s) => s.runtime?.groundKeys[id])
  const layout = useSimStore((s) => s.scenario?.layout)
  const offset = layout ? itemWorldPos(layout, id, 0.4) : null
  const ref = useRef<Group>(null)
  const hex = COLOR_MAP[color] ?? color

  useFrame((state) => {
    if (!ref.current || !offset) return
    ref.current.rotation.y = state.clock.elapsedTime * 1.5
    ref.current.position.y = offset[1] + Math.sin(state.clock.elapsedTime * 2) * 0.08
  })

  if (!zone || !offset) return null

  return (
    <group ref={ref} position={offset}>
      <mesh>
        <octahedronGeometry args={[0.22, 0]} />
        <meshStandardMaterial color={hex} emissive={hex} emissiveIntensity={0.7} />
      </mesh>
      <FloatingLabel name={id} state={color.toUpperCase()} position={[0, 0.55, 0]} color={hex} />
    </group>
  )
}

export function ToolVoxel({ id }: { id: string }) {
  const zone = useSimStore((s) => s.runtime?.groundTools[id])
  const layout = useSimStore((s) => s.scenario?.layout)
  const offset = layout ? itemWorldPos(layout, id, 0.35) : null
  if (!zone || !offset) return null
  return (
    <group position={offset}>
      <mesh>
        <boxGeometry args={[0.35, 0.2, 0.15]} />
        <meshStandardMaterial color="#94a3b8" metalness={0.6} roughness={0.3} />
      </mesh>
      <mesh position={[0.15, 0.12, 0]}>
        <boxGeometry args={[0.1, 0.25, 0.08]} />
        <meshStandardMaterial color="#f97316" />
      </mesh>
      <FloatingLabel name={id} state="READY" position={[0, 0.5, 0]} color="#fb923c" />
    </group>
  )
}

export function MaterialVoxel({ type }: { type: string }) {
  const mat = useSimStore((s) => s.runtime?.groundMaterials[type])
  const layout = useSimStore((s) => s.scenario?.layout)
  const offset = layout ? itemWorldPos(layout, type, 0.3) : null
  if (!mat || mat.count <= 0 || !offset) return null
  const colors: Record<string, string> = {
    FUSE: '#fbbf24',
    CHIP: '#34d399',
    CABLE: '#a78bfa',
  }
  const hex = colors[type] ?? '#fff'
  return (
    <group position={offset}>
      {Array.from({ length: Math.min(mat.count, 3) }).map((_, i) => (
        <mesh key={i} position={[i * 0.12, i * 0.08, 0]}>
          <boxGeometry args={[0.18, 0.12, 0.18]} />
          <meshStandardMaterial color={hex} emissive={hex} emissiveIntensity={0.3} />
        </mesh>
      ))}
      <FloatingLabel name={type} state={`x${mat.count}`} position={[0, 0.45, 0]} color={hex} />
    </group>
  )
}

export function PanelVoxel({ id }: { id: string }) {
  const panel = useSimStore((s) => s.scenario?.panels.find((p) => p.id === id))
  const state = useSimStore((s) => s.runtime?.panels[id] ?? 'DAMAGED')
  const layout = useSimStore((s) => s.scenario?.layout)
  const offset = layout ? itemWorldPos(layout, id, 0.9) : null
  if (!panel || !offset) return null
  const hex = state === 'OK' ? COLOR_MAP.blue : COLOR_MAP.red
  return (
    <group position={offset}>
      <mesh>
        <boxGeometry args={[0.15, 0.7, 0.55]} />
        <meshStandardMaterial color={hex} emissive={hex} emissiveIntensity={0.55} />
      </mesh>
      <FloatingLabel name={id} state={state} position={[0.4, 0.6, 0]} color={hex} />
    </group>
  )
}

export function StationVoxel({ id }: { id: string }) {
  const station = useSimStore((s) => s.scenario?.stations.find((st) => st.id === id))
  const state = useSimStore((s) => s.runtime?.stations[id] ?? 'OFFLINE')
  const layout = useSimStore((s) => s.scenario?.layout)
  const offset = layout ? itemWorldPos(layout, id, 0) : null
  if (!station || !offset) return null
  const hex = state === 'ONLINE' ? COLOR_MAP.green : COLOR_MAP.red

  return (
    <group position={offset}>
      {station.kind === 'generator' && (
        <>
          <mesh position={[0, 0.45, 0]}>
            <cylinderGeometry args={[0.35, 0.4, 0.9, 8]} />
            <meshStandardMaterial color="#64748b" metalness={0.5} />
          </mesh>
          <mesh position={[0, 1.0, 0]}>
            <sphereGeometry args={[0.22, 12, 12]} />
            <meshStandardMaterial color={hex} emissive={hex} emissiveIntensity={0.9} />
          </mesh>
        </>
      )}
      {station.kind === 'command' && (
        <>
          <mesh position={[0, 0.35, 0]}>
            <boxGeometry args={[0.7, 0.7, 0.5]} />
            <meshStandardMaterial color="#475569" />
          </mesh>
          <mesh position={[0, 0.75, 0.1]}>
            <boxGeometry args={[0.5, 0.25, 0.08]} />
            <meshStandardMaterial color={hex} emissive={hex} emissiveIntensity={0.8} />
          </mesh>
        </>
      )}
      {station.kind === 'artillery' && (
        <>
          <mesh position={[0, 0.25, 0]}>
            <boxGeometry args={[0.55, 0.5, 0.55]} />
            <meshStandardMaterial color="#334155" />
          </mesh>
          <mesh position={[0, 0.7, 0]} rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[0.08, 0.1, 0.8, 8]} />
            <meshStandardMaterial color={hex} emissive={hex} emissiveIntensity={0.6} />
          </mesh>
        </>
      )}
      <FloatingLabel name={id} state={state} position={[0, 1.5, 0]} color={hex} />
    </group>
  )
}

export function ChargerVoxel({ id }: { id: string }) {
  const charger = useSimStore((s) => s.scenario?.chargers.find((c) => c.id === id))
  const layout = useSimStore((s) => s.scenario?.layout)
  const offset = layout ? itemWorldPos(layout, id, 0) : null
  const ref = useRef<Group>(null)
  useFrame((state) => {
    if (!ref.current) return
    ref.current.rotation.y = state.clock.elapsedTime
  })
  if (!charger || !offset) return null
  return (
    <group position={offset}>
      <mesh position={[0, 0.15, 0]}>
        <cylinderGeometry args={[0.35, 0.4, 0.3, 8]} />
        <meshStandardMaterial color="#1e293b" />
      </mesh>
      <group ref={ref} position={[0, 0.55, 0]}>
        <mesh>
          <boxGeometry args={[0.12, 0.35, 0.08]} />
          <meshStandardMaterial color="#fbbf24" emissive="#f59e0b" emissiveIntensity={1} />
        </mesh>
        <mesh position={[0.08, -0.12, 0]}>
          <boxGeometry args={[0.2, 0.1, 0.08]} />
          <meshStandardMaterial color="#fbbf24" emissive="#f59e0b" emissiveIntensity={1} />
        </mesh>
      </group>
      <FloatingLabel name={id} state="READY" position={[0, 1.1, 0]} color="#fbbf24" />
    </group>
  )
}
