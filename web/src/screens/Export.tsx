import { useState } from 'react'
import { Download, Share } from 'lucide-react'
import { db, updateScan } from '../db/scans'
import { exportModel, fileName, FORMATS, type Format } from '../three/exporters'
import { dimensions, fmt } from '../three/geometry'
import { canShareFiles, downloadFile, shareFile } from '../share'
import { Header, useLive } from '../ui/components'
import { useModelGeometry } from './Model'

export function ExportScreen({ id, go }: { id: string; go: (h: string) => void }) {
  const scan = useLive(() => db.scans.get(id), [id])
  const { baked } = useModelGeometry(scan)
  const [toast, setToast] = useState<string | null>(null)
  const [name, setName] = useState<string | null>(null)
  const share = canShareFiles()

  if (!scan) return null
  const currentName = name ?? scan.name
  const d = baked ? dimensions(baked) : null

  async function run(format: Format, mode: 'share' | 'download') {
    if (!baked) return
    const blob = exportModel(baked, format, currentName)
    const file = fileName(currentName, format)
    if (mode === 'download') { downloadFile(blob, file); setToast(`${file} scaricato`) }
    else {
      const r = await shareFile(blob, file)
      setToast(r === 'shared' ? 'Condiviso' : r === 'downloaded' ? `${file} scaricato` : 'Condivisione annullata')
    }
    setTimeout(() => setToast(null), 2500)
  }

  return (
    <section className="screen">
      <Header title="Esporta" back={() => go(`/model/${id}`)} />
      <label className="field">Nome del file
        <input className="input" value={currentName} maxLength={80}
               onChange={e => setName(e.target.value)} onBlur={() => name && updateScan(id, { name: name.trim() || scan.name })} />
      </label>
      {d && <p className="muted" style={{ margin: 0 }}>Dimensioni: {fmt(d.x)} × {fmt(d.y)} × {fmt(d.z)} mm{scan.edit?.realScale ? '' : ' (scala indicativa)'}</p>}

      {(Object.keys(FORMATS) as Format[]).map(f => (
        <div className="card format-card" key={f}>
          <h3>{FORMATS[f].label}</h3>
          <p className="muted" style={{ margin: 0 }}>{FORMATS[f].note}</p>
          <div className="row">
            {share && <button className="btn btn-primary" disabled={!baked} onClick={() => run(f, 'share')}><Share size={18} strokeWidth={1.6} /> Condividi</button>}
            <button className={share ? 'btn' : 'btn btn-primary'} disabled={!baked} onClick={() => run(f, 'download')} data-testid={`download-${f}`}>
              <Download size={18} strokeWidth={1.6} /> Scarica</button>
          </div>
        </div>
      ))}
      <p className="muted">Si aprono in Cura, PrusaSlicer, Bambu Studio e OrcaSlicer. Su iPhone, “Condividi” permette AirDrop o il salvataggio in File.</p>
      {toast && <div className="toast" role="status">{toast}</div>}
    </section>
  )
}
