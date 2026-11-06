// Invio in background: continua anche se l'utente cambia schermata (non se chiude l'app
// durante l'upload: in quel caso la scansione va in errore e si può rifare).
import { db, newScan, updateScan } from '../db/scans'
import { submitScan } from '../api/jobs'
import { ApiError } from '../api/client'

const running = new Map<string, Promise<void>>()

export async function startSubmission(name: string, provider: string, photos: Blob[]): Promise<string> {
  const scan = newScan(name, provider, photos.length)
  await db.scans.add(scan)
  const task = submitScan(scan, photos, () => {}).then(
    () => {},
    async e => {
      await updateScan(scan.id, { status: 'error', error: e instanceof ApiError ? e.message : 'Invio delle foto non riuscito.' })
    },
  ).finally(() => running.delete(scan.id))
  running.set(scan.id, task)
  return scan.id
}

export const isUploading = (id: string) => running.has(id)

/** All'avvio: le scansioni rimaste in "uploading" da una sessione precedente non possono riprendere. */
export async function recoverInterruptedUploads() {
  const stuck = await db.scans.where('status').equals('uploading').toArray()
  for (const s of stuck) if (!running.has(s.id)) {
    await updateScan(s.id, { status: 'error', error: 'Invio interrotto (app chiusa durante l’upload). Rifai la scansione.' })
  }
}
