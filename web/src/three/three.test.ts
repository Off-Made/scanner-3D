import { describe, expect, it } from 'vitest'
import * as THREE from 'three'
import { strFromU8, unzipSync } from 'fflate'
import { bake, checkBed, dimensions, IDENTITY_EDIT, rotate90, scaleForDimension } from './geometry'
import { fileName, to3MF, toOBJ, toSTL } from './exporters'

const box = () => new THREE.BoxGeometry(10, 20, 30) // indicizzata, 12 triangoli

describe('modifiche al modello', () => {
  it('appoggia sul piatto e centra', () => {
    const g = bake(box(), IDENTITY_EDIT)
    expect(g.boundingBox!.min.z).toBeCloseTo(0)
    expect(g.boundingBox!.min.x).toBeCloseTo(-5)
  })
  it('rotazione di 90° attorno a X scambia Y e Z, e 4 rotazioni tornano all’inizio', () => {
    const e = rotate90(IDENTITY_EDIT, 'x')
    const d = dimensions(bake(box(), e))
    expect(d.y).toBeCloseTo(30)
    expect(d.z).toBeCloseTo(20)
    let r = IDENTITY_EDIT
    for (let i = 0; i < 4; i++) r = rotate90(r, 'z')
    expect(r.rot).toEqual(IDENTITY_EDIT.rot)
  })
  it('imposta una misura reale mantenendo le proporzioni', () => {
    const e = scaleForDimension(box(), IDENTITY_EDIT, 'z', 60)
    const d = dimensions(bake(box(), e))
    expect(d.z).toBeCloseTo(60)
    expect(d.x).toBeCloseTo(20)
    expect(e.realScale).toBe(true)
  })
  it('controllo del piatto', () => {
    expect(checkBed({ x: 100, y: 100, z: 100 }, { x: 220, y: 220, z: 250 }).fits).toBe(true)
    expect(checkBed({ x: 300, y: 10, z: 10 }, { x: 220, y: 220, z: 250 }).fits).toBe(false)
    expect(checkBed({ x: 1, y: 10, z: 10 }, { x: 220, y: 220, z: 250 }).tooSmall).toBe(true)
  })
})

describe('export', () => {
  const g = bake(box(), IDENTITY_EDIT)
  it('STL binario con 12 triangoli', () => {
    const stl = toSTL(g)
    expect(stl.length).toBe(84 + 12 * 50)
    expect(new DataView(stl.buffer).getUint32(80, true)).toBe(12)
  })
  it('3MF valido: zip con content types, relazioni e modello in millimetri', () => {
    const files = unzipSync(to3MF(g, 'Prova & <test>'))
    expect(Object.keys(files).sort()).toEqual(['3D/3dmodel.model', '[Content_Types].xml', '_rels/.rels'])
    const model = strFromU8(files['3D/3dmodel.model'])
    expect(model).toContain('unit="millimeter"')
    expect(model.match(/<triangle /g)).toHaveLength(12)
    expect(model).toContain('Prova &amp; &lt;test&gt;')
  })
  it('OBJ con indici a base 1', () => {
    const obj = new TextDecoder().decode(toOBJ(g))
    expect(obj.match(/^f /gm)).toHaveLength(12)
    expect(obj).not.toMatch(/^f .*\b0\b/m)
  })
  it('nomi file puliti', () => {
    expect(fileName('Vaso di nonna è bello!', 'stl')).toBe('vaso-di-nonna-e-bello.stl')
    expect(fileName('***', '3mf')).toBe('scansione.3mf')
  })
})

describe('appoggia sul piatto', () => {
  it('mette giù la faccia più grande', async () => {
    const { layFlat, contactArea } = await import('./geometry')
    // lastra 40x40x4 messa in piedi (faccia piccola in basso)
    const slab = new THREE.BoxGeometry(40, 4, 40)
    const e = layFlat(slab, IDENTITY_EDIT)
    const g = bake(slab, e)
    expect(dimensions(g).z).toBeCloseTo(4)
    expect(contactArea(g)).toBeCloseTo(1600, 0)
  })
})
