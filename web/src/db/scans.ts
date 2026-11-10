// Archivio delle scansioni nel telefono (IndexedDB). Il server non conserva nulla a lungo termine:
// appena il modello è pronto lo scarichiamo qui e cancelliamo il job dal server.
import Dexie, { type EntityTable } from 'dexie'
import { IDENTITY_EDIT, type Edit } from '../three/edit'

export type ScanStatus = 'uploading' | 'processing' | 'ready' | 'error'

export interface PrintReport {
  watertight: boolean
  windingConsistent: boolean
  volumeMm3: number
  extentsMm: number[]
  triangles: number
  components: number
  printable: boolean
  checks: { id: string; ok: boolean; label: string; hint: string }[]
}

export interface Scan {
  id: string
  name: string
  createdAt: number
  updatedAt: number
  provider: string
  status: ScanStatus
  photos: number
  jobId?: string
  step?: string
  progress?: number
  error?: string
  /** Il GLB. Le scansioni nuove lo salvano come ArrayBuffer: Safari a volte non riesce più a rileggere
   *  i Blob scaricati dalla rete e salvati in IndexedDB ("The object can not be found here."). */
  model?: Blob | ArrayBuffer
  thumb?: Blob
  report?: PrintReport
  cleanup?: string[]
  edit: Edit
  processingSeconds?: number
}

class ScanDB extends Dexie {
  scans!: EntityTable<Scan, 'id'>
  constructor() {
    super('scan3d')
    this.version(1).stores({ scans: 'id, createdAt, status' })
  }
}

export const db = new ScanDB()

export function newScan(name: string, provider: string, photos: number): Scan {
  const now = Date.now()
  return {
    id: crypto.randomUUID(), name, provider, photos, createdAt: now, updatedAt: now,
    status: 'uploading', edit: IDENTITY_EDIT, progress: 0, step: 'Invio delle foto',
  }
}

export async function updateScan(id: string, patch: Partial<Scan>) {
  await db.scans.update(id, { ...patch, updatedAt: Date.now() })
}

/** Byte del modello, qualunque sia il formato con cui è stato salvato. */
export async function modelBytes(model: Blob | ArrayBuffer): Promise<ArrayBuffer> {
  try {
    return model instanceof ArrayBuffer ? model : await model.arrayBuffer()
  } catch (e) {
    if ((e as Error)?.name === 'NotFoundError') {
      throw new Error('Il telefono non riesce più a leggere questo modello salvato (limite di Safari). Rifai la scansione: le nuove non hanno questo problema.')
    }
    throw e
  }
}

export function defaultName(date = new Date()): string {
  return 'Scansione ' + date.toLocaleString('it-IT', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
