// API dei job di ricostruzione + orchestrazione: upload foto, avvio, polling, download del modello.
import { api, apiBlob, ApiError } from './client'
import { db, updateScan, type PrintReport, type Scan } from '../db/scans'
import type { PhotoView } from '../scan/coverage'

export interface ProviderInfo {
  id: string; label: string; description: string; minPhotos: number; maxPhotos: number; available: boolean; reason: string
}

export interface JobInfo {
  id: string; provider: string; name: string; status: 'uploading' | 'queued' | 'running' | 'done' | 'error' | 'cancelled'
  photos: number; progress: number; step: string; error: string | null; report: PrintReport | null
  cleanup: string[]; elapsedSeconds: number; queue_position: number
}

export const getProviders = () => api<ProviderInfo[]>('/api/providers')
export const getJob = (id: string) => api<JobInfo>(`/api/jobs/${id}`)
export const deleteJob = (id: string) => api<{ ok: boolean }>(`/api/jobs/${id}`, { method: 'DELETE' })

/** Scarica il log di diagnosi di un job (comandi lanciati, output dei programmi, errore). */
export async function downloadJobLog(id: string): Promise<void> {
  const blob = await apiBlob(`/api/jobs/${id}/log`)
  const url = URL.createObjectURL(new Blob([blob], { type: 'text/plain' }))
  const a = document.createElement('a')
  a.href = url
  a.download = `scan3d-${id}.log`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 30_000)
}

async function uploadWithRetry(jobId: string, blob: Blob, i: number, view?: PhotoView) {
  for (let attempt = 1; ; attempt++) {
    const fd = new FormData()
    fd.append('photo', blob, `foto-${String(i + 1).padStart(2, '0')}.jpg`)
    if (view) {
      fd.append('angle', view.angle.toFixed(1))
      fd.append('ring', String(view.ring))
    }
    try {
      return await api<{ photos: number }>(`/api/jobs/${jobId}/photos`, { method: 'POST', body: fd })
    } catch (e) {
      // errori di rete: riprovo fino a 3 volte; errori di validazione (400): mi fermo subito
      if (!(e instanceof ApiError) || e.status !== 0 || attempt >= 3) throw e
      await new Promise(r => setTimeout(r, 1000 * attempt))
    }
  }
}

/** Crea il job, carica le foto una alla volta (con avanzamento) e avvia l'elaborazione. */
export async function submitScan(scan: Scan, photos: Blob[], onProgress: (sent: number) => void,
                                 views: (PhotoView | undefined)[] = []): Promise<string> {
  const job = await api<JobInfo>('/api/jobs', { method: 'POST', body: JSON.stringify({ provider: scan.provider, name: scan.name }) })
  await updateScan(scan.id, { jobId: job.id })
  for (let i = 0; i < photos.length; i++) {
    await uploadWithRetry(job.id, photos[i], i, views[i])
    onProgress(i + 1)
    await updateScan(scan.id, { progress: Math.round(((i + 1) / photos.length) * 100), step: `Invio foto ${i + 1}/${photos.length}` })
  }
  await api<JobInfo>(`/api/jobs/${job.id}/start`, { method: 'POST' })
  await updateScan(scan.id, { status: 'processing', progress: 0, step: 'In coda' })
  return job.id
}

/** Aggiorna lo stato locale dal server. Quando il modello è pronto lo scarica e libera il server. */
export async function syncScan(scan: Scan): Promise<Scan> {
  if (!scan.jobId || scan.status !== 'processing') return scan
  let job: JobInfo
  try {
    job = await getJob(scan.jobId)
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      await updateScan(scan.id, { status: 'error', error: 'Il server non ha più questa scansione (riavviato o scaduta).' })
    }
    return (await db.scans.get(scan.id))!
  }
  if (job.status === 'done') {
    // ArrayBuffer e non Blob: vedi Scan.model (difetto di Safari con i Blob in IndexedDB)
    const model = await (await apiBlob(`/api/jobs/${job.id}/model.glb`)).arrayBuffer()
    await updateScan(scan.id, {
      status: 'ready', model, report: job.report ?? undefined, cleanup: job.cleanup,
      progress: 100, step: 'Completato', processingSeconds: job.elapsedSeconds,
    })
    deleteJob(job.id).catch(() => {}) // il modello ora è nel telefono
  } else if (job.status === 'error' || job.status === 'cancelled') {
    await updateScan(scan.id, { status: 'error', error: job.error ?? 'Elaborazione annullata.' })
  } else {
    const step = job.status === 'queued'
      ? (job.queue_position > 1 ? `In coda (posizione ${job.queue_position})` : 'In coda')
      : job.step
    await updateScan(scan.id, { progress: job.progress, step, processingSeconds: job.elapsedSeconds })
  }
  return (await db.scans.get(scan.id))!
}
