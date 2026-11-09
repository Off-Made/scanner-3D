// Export per gli slicer: STL binario (universale), 3MF (con unità in mm), OBJ.
import * as THREE from 'three'
import { zipSync, strToU8 } from 'fflate'

export type Format = 'stl' | '3mf' | 'obj'

export const FORMATS: Record<Format, { label: string; mime: string; note: string }> = {
  stl: { label: 'STL', mime: 'model/stl', note: 'Il più compatibile: lo aprono tutti gli slicer.' },
  '3mf': { label: '3MF', mime: 'model/3mf', note: 'Moderno, conserva le unità in mm. Consigliato per Bambu Studio, PrusaSlicer, OrcaSlicer.' },
  obj: { label: 'OBJ', mime: 'model/obj', note: 'Formato generico, utile per altri programmi 3D.' },
}

function triangles(g: THREE.BufferGeometry): { pos: Float32Array; idx: Uint32Array } {
  const pos = g.getAttribute('position').array as Float32Array
  const idx = g.index ? Uint32Array.from(g.index.array as ArrayLike<number>) : Uint32Array.from({ length: pos.length / 3 }, (_, i) => i)
  return { pos, idx }
}

/** STL binario: header 80 byte, n triangoli, poi per ogni triangolo normale + 3 vertici + 2 byte. */
export function toSTL(g: THREE.BufferGeometry): Uint8Array {
  const { pos, idx } = triangles(g)
  const n = idx.length / 3
  const buf = new ArrayBuffer(84 + n * 50)
  const dv = new DataView(buf)
  const header = 'Scan3D - unita: millimetri'
  for (let i = 0; i < header.length; i++) dv.setUint8(i, header.charCodeAt(i))
  dv.setUint32(80, n, true)
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), nrm = new THREE.Vector3()
  let o = 84
  for (let t = 0; t < n; t++) {
    a.fromArray(pos, idx[t * 3] * 3); b.fromArray(pos, idx[t * 3 + 1] * 3); c.fromArray(pos, idx[t * 3 + 2] * 3)
    nrm.subVectors(c, b).cross(new THREE.Vector3().subVectors(a, b)).normalize()
    for (const v of [nrm, a, b, c]) { dv.setFloat32(o, v.x, true); dv.setFloat32(o + 4, v.y, true); dv.setFloat32(o + 8, v.z, true); o += 12 }
    o += 2
  }
  return new Uint8Array(buf)
}

export function toOBJ(g: THREE.BufferGeometry, name = 'scan3d'): Uint8Array {
  const { pos, idx } = triangles(g)
  const lines = [`# Scan3D - unita: millimetri`, `o ${name.replace(/\s+/g, '_')}`]
  for (let i = 0; i < pos.length; i += 3) lines.push(`v ${pos[i].toFixed(4)} ${pos[i + 1].toFixed(4)} ${pos[i + 2].toFixed(4)}`)
  for (let i = 0; i < idx.length; i += 3) lines.push(`f ${idx[i] + 1} ${idx[i + 1] + 1} ${idx[i + 2] + 1}`)
  return strToU8(lines.join('\n') + '\n')
}

const xmlEscape = (s: string) => s.replace(/[<>&"']/g, ch => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&apos;' })[ch]!)

/** 3MF = archivio zip con un XML del modello (specifica 3MF Core, unit="millimeter"). */
export function to3MF(g: THREE.BufferGeometry, name = 'Scan3D'): Uint8Array {
  const { pos, idx } = triangles(g)
  const v: string[] = []
  for (let i = 0; i < pos.length; i += 3) v.push(`<vertex x="${pos[i].toFixed(4)}" y="${pos[i + 1].toFixed(4)}" z="${pos[i + 2].toFixed(4)}"/>`)
  const t: string[] = []
  for (let i = 0; i < idx.length; i += 3) t.push(`<triangle v1="${idx[i]}" v2="${idx[i + 1]}" v3="${idx[i + 2]}"/>`)
  const model = `<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="it-IT" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
<metadata name="Title">${xmlEscape(name)}</metadata>
<metadata name="Application">Scan3D</metadata>
<resources><object id="1" type="model" name="${xmlEscape(name)}"><mesh><vertices>${v.join('')}</vertices><triangles>${t.join('')}</triangles></mesh></object></resources>
<build><item objectid="1"/></build>
</model>`
  const contentTypes = `<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>`
  const rels = `<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>`
  return zipSync({
    '[Content_Types].xml': strToU8(contentTypes),
    '_rels/.rels': strToU8(rels),
    '3D/3dmodel.model': strToU8(model),
  }, { level: 6 })
}

export function exportModel(g: THREE.BufferGeometry, format: Format, name: string): Blob {
  const data = format === 'stl' ? toSTL(g) : format === '3mf' ? to3MF(g, name) : toOBJ(g, name)
  return new Blob([data as BlobPart], { type: FORMATS[format].mime })
}

export function fileName(name: string, format: Format): string {
  const base = name.normalize('NFKD').replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-').toLowerCase() || 'scansione'
  return `${base}.${format}`
}
