import { Html } from '@react-three/drei'
import { COLOR_MAP } from '../types'

interface FloatingLabelProps {
  name: string
  state: string
  position: [number, number, number]
  color?: string
}

export function FloatingLabel({ name, state, position, color = '#67e8f9' }: FloatingLabelProps) {
  return (
    <Html position={position} center distanceFactor={12} style={{ pointerEvents: 'none' }}>
      <div
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '11px',
          fontWeight: 700,
          letterSpacing: '0.04em',
          color,
          textShadow: '0 0 6px rgba(0,0,0,0.85), 0 1px 2px rgba(0,0,0,0.9)',
          whiteSpace: 'nowrap',
          userSelect: 'none',
        }}
      >
        {name}[{state}]
      </div>
    </Html>
  )
}

export function statusColor(state: string): string {
  if (state === 'OK' || state === 'ONLINE' || state === 'OPEN') return COLOR_MAP.green
  if (state === 'DAMAGED' || state === 'OFFLINE' || state === 'CLOSED') return COLOR_MAP.red
  return COLOR_MAP.cyan
}
