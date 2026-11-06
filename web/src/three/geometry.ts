// Geometria del modello e modifiche dell'utente (rotazioni a 90°, scala, appoggio sul piatto).
// Convenzione: millimetri, Z verso l'alto (come gli slicer). Il server normalizza il lato più
// lungo a 100 mm: finché l'utente non imposta una misura reale la scala è "indicativa".
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { mergeVertices } from 'three/examples/jsm/utils/BufferGeometryUtils.js'

import { IDENTITY_EDIT, type Axis, type Edit } from './edit'

export { IDENTITY_EDIT, type Axis, type Edit }

export function rotate90(edit: Edit, axis: Axis, dir: 1 | -1 = 1): Edit {
  const r = new THREE.Matrix4().makeRotationAxis(
    new THREE.Vector3(axis === 'x' ? 1 : 0, axis === 'y' ? 1 : 0, axis === 'z' ? 1 : 0), (dir * Math.PI) / 2)
  const cur = rotMatrix4(edit)
  const next = r.multiply(cur)
  // arrotondo a interi (le rotazioni di 90° hanno solo -1, 0, 1): niente errori che si accumulano
  const e = next.elements // column-major
  const rows = [e[0], e[4], e[8], e[1], e[5], e[9], e[2], e[6], e[10]].map(v => Math.round(v) || 0) // `|| 0` trasforma -0 in 0
  return { ...edit, rot: rows }
}

function rotMatrix4(edit: Edit): THREE.Matrix4 {
  const [a, b, c, d, e, f, g, h, i] = edit.rot
  return new THREE.Matrix4().set(a, b, c, 0, d, e, f, 0, g, h, i, 0, 0, 0, 0, 1)
}

/** Applica rotazione e scala, poi centra in XY e appoggia sul piatto (z min = 0). Restituisce una copia. */
export function bake(base: THREE.BufferGeometry, edit: Edit): THREE.BufferGeometry {
  const g = base.clone()
  g.applyMatrix4(rotMatrix4(edit))
  g.scale(edit.scale, edit.scale, edit.scale)
  layOnPlate(g)
  g.computeVertexNormals()
  g.computeBoundingBox()
  return g
}

export function layOnPlate(g: THREE.BufferGeometry) {
  g.computeBoundingBox()
  const b = g.boundingBox!
  g.translate(-(b.min.x + b.max.x) / 2, -(b.min.y + b.max.y) / 2, -b.min.z)
}

export function dimensions(g: THREE.BufferGeometry): { x: number; y: number; z: number } {
  g.computeBoundingBox()
  const s = g.boundingBox!.getSize(new THREE.Vector3())
  return { x: s.x, y: s.y, z: s.z }
}

/** Nuova scala per ottenere `mm` lungo l'asse scelto (proporzioni bloccate). */
export function scaleForDimension(base: THREE.BufferGeometry, edit: Edit, axis: Axis, mm: number): Edit {
  const current = dimensions(bake(base, { ...edit, scale: 1 }))[axis]
  if (!(mm > 0) || !(current > 0)) return edit
  return { ...edit, scale: mm / current, realScale: true }
}

export async function loadGlb(data: ArrayBuffer): Promise<THREE.BufferGeometry> {
  const gltf = await new GLTFLoader().parseAsync(data, '')
  const parts: THREE.BufferGeometry[] = []
  gltf.scene.updateMatrixWorld(true)
  gltf.scene.traverse(o => {
    const m = o as THREE.Mesh
    if (m.isMesh) {
      const g = m.geometry.clone()
      g.applyMatrix4(m.matrixWorld)
      parts.push(g)
    }
  })
  if (!parts.length) throw new Error('Il file non contiene una mesh.')
  // il server invia una sola mesh; per sicurezza unisco solo gli attributi di posizione
  const positions = parts.map(p => (p.index ? p.toNonIndexed() : p).getAttribute('position').array as Float32Array)
  const total = positions.reduce((n, a) => n + a.length, 0)
  const all = new Float32Array(total)
  let off = 0
  for (const a of positions) { all.set(a, off); off += a.length }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(all, 3))
  const merged = mergeVertices(g, 1e-5) // torna indicizzata: serve al 3MF e alleggerisce
  merged.computeVertexNormals()
  return merged
}

export interface BedCheck { fits: boolean; tooSmall: boolean; message: string }
export function checkBed(d: { x: number; y: number; z: number }, bed: { x: number; y: number; z: number }): BedCheck {
  const fits = d.x <= bed.x && d.y <= bed.y && d.z <= bed.z
  const tooSmall = Math.min(d.x, d.y, d.z) < 2
  const message = !fits
    ? `Il modello (${fmt(d.x)}×${fmt(d.y)}×${fmt(d.z)} mm) supera il piatto ${bed.x}×${bed.y}×${bed.z} mm: riducilo o ruotalo.`
    : tooSmall ? 'Alcune parti sono più sottili di 2 mm: potrebbero non stamparsi bene.' : 'Entra nel piatto di stampa.'
  return { fits, tooSmall, message }
}

export const fmt = (mm: number) => (mm >= 100 ? mm.toFixed(0) : mm.toFixed(1)).replace('.', ',')

/** Area (mm²) dei triangoli che poggiano sul piatto: rivolti in basso e a meno di 0,3 mm da z = 0. */
export function contactArea(g: THREE.BufferGeometry): number {
  const pos = g.getAttribute('position')
  const idx = g.index
  const n = idx ? idx.count / 3 : pos.count / 3
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), cr = new THREE.Vector3()
  let area = 0
  for (let t = 0; t < n; t++) {
    const i0 = idx ? idx.getX(t * 3) : t * 3, i1 = idx ? idx.getX(t * 3 + 1) : t * 3 + 1, i2 = idx ? idx.getX(t * 3 + 2) : t * 3 + 2
    a.fromBufferAttribute(pos, i0); b.fromBufferAttribute(pos, i1); c.fromBufferAttribute(pos, i2)
    if (Math.max(a.z, b.z, c.z) > 0.3) continue
    cr.subVectors(b, a).cross(new THREE.Vector3().subVectors(c, a))
    const len = cr.length()
    if (len > 0 && cr.z / len < -0.95) area += len / 2
  }
  return area
}

/** Sceglie, tra le 6 orientazioni "una faccia verso il basso", quella con più appoggio sul piatto. */
export function layFlat(base: THREE.BufferGeometry, edit: Edit): Edit {
  const candidates: Edit[] = [
    edit, rotate90(edit, 'x'), rotate90(rotate90(edit, 'x'), 'x'), rotate90(edit, 'x', -1), rotate90(edit, 'y'), rotate90(edit, 'y', -1),
  ]
  let best = edit, bestArea = -1
  for (const c of candidates) {
    const area = contactArea(bake(base, { ...c, scale: 1 }))
    if (area > bestArea * 1.02) { best = c; bestArea = area } // a parità tengo l'orientamento attuale
  }
  return best
}
