// Qualità del fotogramma: luminosità e nitidezza, calcolate su un'immagine ridotta (veloce anche
// su telefoni di fascia media: ~128x96 pixel per controllo).

export interface FrameQuality { brightness: number; sharpness: number }

/** Da RGBA a scala di grigi (luma BT.601). */
export function toGray(rgba: Uint8ClampedArray, w: number, h: number): Float32Array {
  const g = new Float32Array(w * h)
  for (let i = 0, j = 0; i < g.length; i++, j += 4) g[i] = 0.299 * rgba[j] + 0.587 * rgba[j + 1] + 0.114 * rgba[j + 2]
  return g
}

/** Varianza del Laplaciano: alta = bordi netti, bassa = foto mossa o sfocata. */
export function laplacianVariance(g: Float32Array, w: number, h: number): number {
  let sum = 0, sum2 = 0, n = 0
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x
      const v = g[i - w] + g[i + w] + g[i - 1] + g[i + 1] - 4 * g[i]
      sum += v; sum2 += v * v; n++
    }
  }
  if (!n) return 0
  const mean = sum / n
  return sum2 / n - mean * mean
}

export function measure(rgba: Uint8ClampedArray, w: number, h: number): FrameQuality {
  const g = toGray(rgba, w, h)
  let s = 0
  for (const v of g) s += v
  return { brightness: s / g.length, sharpness: laplacianVariance(g, w, h) }
}

/** Valuta la nitidezza rispetto alla scena (le soglie assolute variano da telefono a telefono). */
export class SharpnessJudge {
  private recent: number[] = []
  push(v: number) { this.recent.push(v); if (this.recent.length > 40) this.recent.shift() }
  /** Nitido se vicino ai valori migliori visti di recente e sopra un minimo assoluto. */
  isSharp(v: number): boolean {
    if (v < 15) return false
    if (this.recent.length < 5) return true
    const sorted = [...this.recent].sort((a, b) => a - b)
    const p80 = sorted[Math.floor(sorted.length * 0.8)]
    return v >= p80 * 0.6
  }
}

export type LightIssue = 'dark' | 'bright' | null
export function lightIssue(brightness: number): LightIssue {
  if (brightness < 55) return 'dark'
  if (brightness > 230) return 'bright'
  return null
}
