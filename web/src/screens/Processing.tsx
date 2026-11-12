import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, FileText, Trash2 } from 'lucide-react'
import { db } from '../db/scans'
import { deleteJob, downloadJobLog, syncScan } from '../api/jobs'
import { isUploading } from '../scan/submit'
import { formatDuration, Header, ProgressBar, useLive } from '../ui/components'

export function ProcessingScreen({ id, go }: { id: string; go: (h: string) => void }) {
  const scan = useLive(() => db.scans.get(id), [id])
  const [tick, setTick] = useState(0)
  const [logError, setLogError] = useState(false)

  // polling dello stato sul server ogni 2,5 s (riprende anche se riapri l'app più tardi)
  useEffect(() => {
    let stop = false
    const loop = async () => {
      while (!stop) {
        const s = await db.scans.get(id)
        if (!s || s.status === 'ready' || s.status === 'error') break
        if (s.status === 'processing') await syncScan(s).catch(() => {})
        setTick(t => t + 1)
        await new Promise(r => setTimeout(r, 2500))
      }
    }
    loop()
    return () => { stop = true }
  }, [id])

  useEffect(() => { if (scan?.status === 'ready') { const t = setTimeout(() => go(`/model/${id}`), 700); return () => clearTimeout(t) } }, [scan?.status, id, go])

  if (scan === undefined) return <section className="screen"><Header title="Elaborazione" back={() => go('/archive')} /></section>
  if (!scan) return <section className="screen"><Header title="Elaborazione" back={() => go('/archive')} /><p>Scansione non trovata.</p></section>

  async function remove() {
    if (scan!.jobId) deleteJob(scan!.jobId).catch(() => {})
    await db.scans.delete(id)
    go('/archive')
  }

  const uploading = scan.status === 'uploading'
  return (
    <section className="screen">
      <Header title={scan.name} back={() => go('/archive')} />
      {scan.status === 'error' ? (
        <div className="card big-progress">
          <AlertCircle size={36} strokeWidth={1.4} />
          <strong>Elaborazione non riuscita</strong>
          <p style={{ margin: 0 }}>{scan.error}</p>
          {scan.jobId && (
            <button className="btn" onClick={() => downloadJobLog(scan.jobId!).catch(() => setLogError(true))}>
              <FileText size={18} strokeWidth={1.6} /> Scarica il log
            </button>
          )}
          {logError && <span className="muted">Log non disponibile (la scansione non è più sul server).</span>}
          <div className="row">
            <button className="btn btn-primary" onClick={() => go('/scan')}>Nuova scansione</button>
            <button className="btn" onClick={remove}><Trash2 size={18} strokeWidth={1.6} /> Elimina</button>
          </div>
        </div>
      ) : scan.status === 'ready' ? (
        <div className="card big-progress"><CheckCircle2 size={36} strokeWidth={1.4} /><strong>Modello pronto</strong></div>
      ) : (
        <div className="card big-progress" aria-live="polite">
          <span className="muted">{uploading ? 'Invio delle foto' : 'Ricostruzione 3D'}</span>
          <span className="pct">{Math.round(scan.progress ?? 0)}%</span>
          <ProgressBar value={scan.progress ?? 0} label="Avanzamento" />
          <div className="row" style={{ alignItems: 'center' }}>
            <span className="spinner" style={{ flex: 'none' }} />
            <span style={{ flex: 1 }}>{scan.step}</span>
          </div>
          {!uploading && <span className="muted">Tempo trascorso: {formatDuration(scan.processingSeconds ?? 0)}{scan.provider === 'photo' ? ' · di solito 8–12 minuti' : ''}</span>}
        </div>
      )}
      {!['ready', 'error'].includes(scan.status) && (
        <p className="muted">
          {uploading && !isUploading(id)
            ? 'Upload interrotto.'
            : uploading ? 'Tieni l’app aperta finché le foto non sono state inviate.'
              : 'Ora puoi anche chiudere l’app: la ricostruzione continua sul server e la ritrovi in Archivio.'}
        </p>
      )}
      <span hidden>{tick}</span>
      {scan.status !== 'ready' && scan.status !== 'error' && <button className="btn" onClick={remove}>Annulla ed elimina</button>}
    </section>
  )
}
