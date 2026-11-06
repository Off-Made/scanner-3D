import { useState } from 'react'
import { AlertCircle, Box, Camera, MoreHorizontal } from 'lucide-react'
import { db, updateScan, type Scan } from '../db/scans'
import { deleteJob } from '../api/jobs'
import { formatDate, Header, Sheet, useLive, useObjectUrl } from '../ui/components'

function Thumb({ scan }: { scan: Scan }) {
  const url = useObjectUrl(scan.thumb)
  if (url) return <img className="thumb" src={url} alt="" />
  return <span className="thumb">{scan.status === 'error' ? <AlertCircle size={22} strokeWidth={1.5} /> : scan.status === 'ready' ? <Box size={22} strokeWidth={1.5} /> : <span className="spinner" />}</span>
}

const statusText = (s: Scan) =>
  s.status === 'ready' ? formatDate(s.createdAt)
    : s.status === 'error' ? 'Non riuscita'
      : `${s.step ?? 'In elaborazione'} · ${Math.round(s.progress ?? 0)}%`

export function ScanRow({ scan, go, onMore }: { scan: Scan; go: (h: string) => void; onMore?: (s: Scan) => void }) {
  return (
    <div className="scan-item" data-testid="scan-item">
      <button className="open" onClick={() => go(scan.status === 'ready' ? `/model/${scan.id}` : `/scan/${scan.id}`)}>
        <Thumb scan={scan} />
        <span className="scan-meta"><strong>{scan.name}</strong><span>{statusText(scan)}</span></span>
      </button>
      {onMore && <button className="icon-btn" onClick={() => onMore(scan)} aria-label={`Azioni per ${scan.name}`}><MoreHorizontal size={20} strokeWidth={1.6} /></button>}
    </div>
  )
}

export function ArchiveScreen({ go }: { go: (h: string) => void }) {
  const scans = useLive(() => db.scans.orderBy('createdAt').reverse().toArray(), [])
  const [menu, setMenu] = useState<Scan | null>(null)
  const [renaming, setRenaming] = useState<Scan | null>(null)
  const [confirm, setConfirm] = useState<Scan | null>(null)
  const [newName, setNewName] = useState('')

  async function remove(s: Scan) {
    if (s.jobId && s.status !== 'ready') deleteJob(s.jobId).catch(() => {})
    await db.scans.delete(s.id)
    setConfirm(null)
  }

  return (
    <section className="screen">
      <Header title="Archivio" />
      {scans && scans.length === 0 && <div className="empty">
        <Box size={40} strokeWidth={1.2} /><div>Nessuna scansione salvata.</div>
        <button className="btn btn-primary" style={{ width: 'auto' }} onClick={() => go('/scan')}><Camera size={20} strokeWidth={1.6} /> Nuova scansione</button>
      </div>}
      <div className="scan-list">{scans?.map(s => <ScanRow key={s.id} scan={s} go={go} onMore={setMenu} />)}</div>

      <Sheet open={!!menu} title={menu?.name ?? ''} onClose={() => setMenu(null)}>
        {menu?.status === 'ready' && <button className="btn" onClick={() => { go(`/model/${menu.id}`); setMenu(null) }}>Apri</button>}
        {menu?.status === 'ready' && <button className="btn" onClick={() => { go(`/export/${menu.id}`); setMenu(null) }}>Riesporta</button>}
        <button className="btn" onClick={() => { setNewName(menu!.name); setRenaming(menu); setMenu(null) }}>Rinomina</button>
        <button className="btn" onClick={() => { setConfirm(menu); setMenu(null) }}>Elimina</button>
      </Sheet>

      <Sheet open={!!renaming} title="Rinomina" onClose={() => setRenaming(null)}>
        <input className="input" value={newName} maxLength={80} autoFocus onChange={e => setNewName(e.target.value)} aria-label="Nuovo nome" />
        <button className="btn btn-primary" disabled={!newName.trim()} onClick={async () => { await updateScan(renaming!.id, { name: newName.trim() }); setRenaming(null) }}>Salva</button>
      </Sheet>

      <Sheet open={!!confirm} title="Eliminare la scansione?" onClose={() => setConfirm(null)}>
        <p style={{ margin: 0 }}>“{confirm?.name}” verrà eliminata da questo telefono. L’operazione non si può annullare.</p>
        <button className="btn btn-primary" onClick={() => confirm && remove(confirm)}>Elimina</button>
        <button className="btn" onClick={() => setConfirm(null)}>Annulla</button>
      </Sheet>
    </section>
  )
}
