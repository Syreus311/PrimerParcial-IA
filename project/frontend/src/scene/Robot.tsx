import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import type { Group } from 'three'
import { useSimStore } from '../store/simStore'

export function Robot() {
  const group = useRef<Group>(null)
  const pos = useSimStore(
    (s) => s.runtime?.robotPosition ?? ([0, 0.35, 0] as [number, number, number]),
  )
  const yaw = useSimStore((s) => s.runtime?.robotYaw ?? 0)

  useFrame(() => {
    if (!group.current) return
    group.current.position.x = pos[0]
    group.current.position.y = pos[1]
    group.current.position.z = pos[2]
    group.current.rotation.y = yaw
  })

  return (
    <group ref={group} position={[pos[0], pos[1], pos[2]]} rotation={[0, yaw, 0]}>
      <mesh position={[0, 0.15, 0]}>
        <boxGeometry args={[0.55, 0.4, 0.55]} />
        <meshStandardMaterial color="#f1f5f9" roughness={0.35} metalness={0.2} />
      </mesh>
      <mesh position={[0, 0.4, 0]}>
        <boxGeometry args={[0.45, 0.12, 0.45]} />
        <meshStandardMaterial color="#e2e8f0" />
      </mesh>
      {/* Visor faces local +Z — yaw aligns +Z with movement direction */}
      <mesh position={[0, 0.22, 0.28]}>
        <boxGeometry args={[0.38, 0.1, 0.06]} />
        <meshStandardMaterial color="#22d3ee" emissive="#0891b2" emissiveIntensity={1.2} />
      </mesh>
      {[
        [-0.22, -0.02, -0.22],
        [0.22, -0.02, -0.22],
        [-0.22, -0.02, 0.22],
        [0.22, -0.02, 0.22],
      ].map((p, i) => (
        <mesh key={i} position={p as [number, number, number]}>
          <boxGeometry args={[0.12, 0.1, 0.12]} />
          <meshStandardMaterial color="#0f172a" />
        </mesh>
      ))}
    </group>
  )
}
