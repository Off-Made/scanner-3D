import { Camera, ChevronRight, Lightbulb, Moon, Sun } from 'lucide-react'
import { db } from '../db/scans'
import { useLive } from '../ui/components'
import { ScanRow } from './Archive'

export function Home({ go, theme, toggleTheme }: { go: (h: string) => void; theme: 'light' | 'dark'; toggleTheme: () => void }) {
  const recent = useLive(() => db.scans.orderBy('createdAt').reverse().limit(3).toArray(), [])
  return (
    <section className="screen">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 className="title">Scan3D</h1>
        <button className="icon-btn" onClick={toggleTheme} aria-label={theme === 'dark' ? 'Tema chiaro' : 'Tema scuro'}>
          {theme === 'dark' ? <Sun size={22} strokeWidth={1.6} /> : <Moon size={22} strokeWidth={1.6} />}
        </button>
      </div>
      <p className="subtitle">Fotografa un oggetto da tutti i lati e preparalo per la stampa 3D.</p>

      <button className="btn btn-primary btn-big" onClick={() => go('/scan')}>
        <Camera size={22} strokeWidth={1.6} aria-hidden /> Nuova scansione
      </button>

      {recent && recent.length > 0 && <>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
          <strong>Recenti</strong>
          <button className="chip" onClick={() => go('/archive')}>Tutte <ChevronRight size={16} strokeWidth={1.6} /></button>
        </div>
        <div className="scan-list">{recent.map(s => <ScanRow key={s.id} scan={s} go={go} />)}</div>
      </>}

      <div className="card" style={{ display: 'flex', gap: 12 }}>
        <Lightbulb size={22} strokeWidth={1.5} style={{ flex: 'none', marginTop: 2 }} />
        <div style={{ fontSize: 15 }}>
          <strong>Per un buon risultato</strong>
          <ul style={{ margin: '6px 0 0', paddingLeft: 18, color: 'var(--text-2)' }}>
            <li>oggetti opachi e con dettagli (no vetro, metallo lucido, superfici lisce bianche)</li>
            <li>luce diffusa, niente ombre nette</li>
            <li>oggetto su un tavolo, sfondo semplice</li>
            <li>30–40 foto: un giro all’altezza dell’oggetto e uno dall’alto</li>
          </ul>
        </div>
      </div>
      <button className="chip" style={{ alignSelf: 'flex-start' }} onClick={() => go('/camera-test')}>Test fotocamera e sensori</button>
    </section>
  )
}
