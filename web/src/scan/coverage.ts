// Copertura degli angoli durante la scansione.
// Due "anelli": all'altezza dell'oggetto (24 settori da 15°) e dall'alto (12 settori da 30°).
// L'orientamento del telefono (bussola + inclinazione) indica da dove stai fotografando.

export const MAX_PHOTOS = 40

export interface RingSpec { id: 'low' | 'high'; sectors: number; label: string }
export const RINGS: RingSpec[] = [
  { id: 'low', sectors: 24, label: 'all’altezza dell’oggetto' },
  { id: 'high', sectors: 12, label: 'dall’alto' },
]

/** beta = inclinazione avanti/indietro (90° = telefono verticale). Sotto ~65° stai guardando verso il basso. */
export function ringFor(beta: number | null): 0 | 1 {
  return beta != null && beta < 65 ? 1 : 0
}

export function sectorFor(heading: number, sectors: number): number {
  const h = ((heading % 360) + 360) % 360
  return Math.floor(h / (360 / sectors)) % sectors
}

export class Coverage {
  readonly filled: boolean[][] = RINGS.map(r => Array(r.sectors).fill(false))
  private origin: number | null = null // il primo scatto definisce lo "zero" dell'anello

  /** Settore relativo al primo scatto (così l'anello parte sempre dall'alto). */
  locate(heading: number, beta: number | null): { ring: 0 | 1; sector: number } {
    const ring = ringFor(beta)
    const rel = this.origin == null ? 0 : heading - this.origin
    return { ring, sector: sectorFor(rel, RINGS[ring].sectors) }
  }

  isNew(heading: number, beta: number | null): boolean {
    const { ring, sector } = this.locate(heading, beta)
    return !this.filled[ring][sector]
  }

  mark(heading: number, beta: number | null) {
    if (this.origin == null) this.origin = heading
    const { ring, sector } = this.locate(heading, beta)
    this.filled[ring][sector] = true
  }

  count(ring: 0 | 1) { return this.filled[ring].filter(Boolean).length }
  ratio(ring: 0 | 1) { return this.count(ring) / RINGS[ring].sectors }

  /** Suggerimento principale da mostrare, in base a cosa manca. */
  hint(photos: number): string {
    if (photos === 0) return 'Inquadra l’oggetto al centro e scatta la prima foto'
    if (photos >= MAX_PHOTOS) return 'Hai raggiunto il massimo di foto: puoi elaborare'
    if (this.ratio(0) < 0.75) return 'Ruota lentamente attorno all’oggetto, tenendolo al centro'
    if (this.ratio(1) < 0.5) return 'Ora fai un giro più in alto, guardando l’oggetto dall’alto'
    return 'Ottima copertura: puoi elaborare o aggiungere dettagli'
  }
}
