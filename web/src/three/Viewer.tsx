// Visualizzatore 3D: ruota (1 dito), zoom (pizzico), sposta (2 dita). Z verso l'alto, mm.
// Caricato in modo "pigro" (lazy) per non appesantire l'avvio dell'app.
import { useEffect, useMemo, useRef } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'

function css(name: string) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#999' }

function Fit({ size }: { size: THREE.Vector3 }) {
  const { camera, invalidate } = useThree()
  const fitted = useRef(false)
  useEffect(() => {
    if (fitted.current) return
    fitted.current = true
    const r = Math.max(size.x, size.y, size.z)
    camera.up.set(0, 0, 1)
    camera.position.set(r * 1.25, -r * 1.6, r * 1.05)
    camera.lookAt(0, 0, size.z / 2)
    ;(camera as THREE.PerspectiveCamera).far = r * 50
    camera.updateProjectionMatrix()
    invalidate()
  }, [size, camera, invalidate])
  return null
}

function Bed({ x, y }: { x: number; y: number }) {
  const grid = useMemo(() => {
    const step = 10
    const pts: number[] = []
    for (let i = -x / 2; i <= x / 2 + 0.01; i += step) pts.push(i, -y / 2, 0, i, y / 2, 0)
    for (let j = -y / 2; j <= y / 2 + 0.01; j += step) pts.push(-x / 2, j, 0, x / 2, j, 0)
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
    return g
  }, [x, y])
  return (
    <group position={[0, 0, -0.05]}>
      <mesh><planeGeometry args={[x, y]} /><meshBasicMaterial color={css('--surface')} /></mesh>
      <lineSegments geometry={grid} position={[0, 0, 0.02]}><lineBasicMaterial color={css('--border')} /></lineSegments>
    </group>
  )
}

export interface ViewerProps {
  geometry: THREE.BufferGeometry
  bed: { x: number; y: number }
  onSnapshot?: (canvas: HTMLCanvasElement) => void
}

export default function Viewer({ geometry, bed, onSnapshot }: ViewerProps) {
  const size = useMemo(() => { geometry.computeBoundingBox(); return geometry.boundingBox!.getSize(new THREE.Vector3()) }, [geometry])
  const target = useMemo(() => new THREE.Vector3(0, 0, size.z / 2), [size])
  const snapped = useRef(false)
  const r = Math.max(size.x, size.y, size.z)
  return (
    <div className="viewer" data-testid="viewer">
      <Canvas
        frameloop="demand" dpr={[1, 2]}
        gl={{ preserveDrawingBuffer: true, antialias: true }}
        camera={{ fov: 40, near: 0.5, far: 5000, up: [0, 0, 1] }}
        onCreated={({ gl }) => gl.setClearColor(css('--surface-2'))}
      >
        <Fit size={size} />
        <ambientLight intensity={0.55} />
        <directionalLight position={[r, -r, r * 2]} intensity={1.6} />
        <directionalLight position={[-r, r, r * 0.5]} intensity={0.5} />
        <Bed x={Math.max(bed.x, r * 1.3)} y={Math.max(bed.y, r * 1.3)} />
        <mesh geometry={geometry} onAfterRender={() => {
          if (!snapped.current && onSnapshot) { snapped.current = true; requestAnimationFrame(() => onSnapshot(document.querySelector('.viewer canvas') as HTMLCanvasElement)) }
        }}>
          <meshStandardMaterial color="#bdbdba" roughness={0.75} metalness={0.05} />
        </mesh>
        <OrbitControls makeDefault target={target} enableDamping={false} minDistance={r * 0.3} maxDistance={r * 8} />
      </Canvas>
    </div>
  )
}
