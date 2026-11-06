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
  model?: Blob
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

export function defaultName(date = new Date()): string {
  return 'Scansione ' + date.toLocaleString('it-IT', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
