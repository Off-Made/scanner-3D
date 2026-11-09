import { describe, expect, it } from 'vitest'
import { Coverage, ringFor, sectorFor } from './coverage'
import { laplacianVariance, lightIssue, SharpnessJudge, toGray } from './quality'
import { fitSize, subsample } from './images'

describe('copertura', () => {
  it('settori e anelli', () => {
    expect(sectorFor(0, 24)).toBe(0)
    expect(sectorFor(359, 24)).toBe(23)
    expect(sectorFor(-15, 24)).toBe(23)
    expect(ringFor(88)).toBe(0)
    expect(ringFor(40)).toBe(1)
    expect(ringFor(null)).toBe(0)
  })
  it('il primo scatto fa da origine e i suggerimenti seguono la copertura', () => {
    const c = new Coverage()
    expect(c.hint(0)).toMatch(/prima foto/)
    c.mark(200, 90)
    expect(c.isNew(205, 90)).toBe(false) // stesso settore da 15°
    expect(c.isNew(220, 90)).toBe(true)
    for (let a = 0; a < 360; a += 15) c.mark(200 + a, 90)
    expect(c.ratio(0)).toBe(1)
    expect(c.hint(24)).toMatch(/più in alto/)
    for (let a = 0; a < 360; a += 30) c.mark(200 + a, 45)
    expect(c.hint(36)).toMatch(/Ottima/)
    expect(c.hint(40)).toMatch(/massimo/)
  })
})

describe('qualità', () => {
  const W = 64, H = 48
  const img = (f: (x: number, y: number) => number) => {
    const a = new Uint8ClampedArray(W * H * 4)
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) { const v = f(x, y); a.set([v, v, v, 255], (y * W + x) * 4) }
    return a
  }
  it('una scacchiera è più nitida di un gradiente', () => {
    const sharp = laplacianVariance(toGray(img((x, y) => ((x >> 2) + (y >> 2)) % 2 ? 255 : 0), W, H), W, H)
    const blur = laplacianVariance(toGray(img(x => x * 4), W, H), W, H)
    expect(sharp).toBeGreaterThan(blur * 100)
  })
  it('giudizio relativo della nitidezza', () => {
    const j = new SharpnessJudge()
    for (let i = 0; i < 20; i++) j.push(200)
    expect(j.isSharp(190)).toBe(true)
    expect(j.isSharp(60)).toBe(false)
    expect(j.isSharp(5)).toBe(false)
  })
  it('luce', () => {
    expect(lightIssue(30)).toBe('dark')
    expect(lightIssue(128)).toBeNull()
    expect(lightIssue(250)).toBe('bright')
  })
})

describe('immagini', () => {
  it('sottocampiona in modo uniforme tenendo prima e ultima', () => {
    const s = subsample(Array.from({ length: 100 }, (_, i) => i), 40)
    expect(s).toHaveLength(40)
    expect(s[0]).toBe(0)
    expect(s[39]).toBe(99)
    expect(subsample([1, 2], 40)).toEqual([1, 2])
  })
  it('ridimensiona il lato lungo a 1600 senza ingrandire', () => {
    expect(fitSize(4032, 3024)).toEqual({ width: 1600, height: 1200 })
    expect(fitSize(640, 480)).toEqual({ width: 640, height: 480 })
  })
})
