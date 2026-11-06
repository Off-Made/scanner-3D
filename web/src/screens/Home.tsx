import { Archive, Camera, ChevronRight, Moon, Sun } from 'lucide-react'
import type { Route } from '../App'

export function Home({ go, theme, toggleTheme }: { go: (r: Route) => void; theme: 'light' | 'dark'; toggleTheme: () => void }) {
  return (
    <section className="screen">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 className="title">Scan3D</h1>
        <button className="btn" style={{ width: 'var(--tap)', padding: 0 }} onClick={toggleTheme}
                aria-label={theme === 'dark' ? 'Tema chiaro' : 'Tema scuro'}>
          {theme === 'dark' ? <Sun size={20} strokeWidth={1.6} /> : <Moon size={20} strokeWidth={1.6} />}
        </button>
      </div>
      <p className="subtitle">Fotografa un oggetto da tutti i lati e preparalo per la stampa 3D.</p>

      <button className="btn btn-primary btn-big" onClick={() => go('scan')}>
        <Camera size={22} strokeWidth={1.6} aria-hidden /> Nuova scansione
      </button>

      <button className="tile" onClick={() => go('archive')}>
        <span className="tile-icon"><Archive size={20} strokeWidth={1.6} aria-hidden /></span>
        <span style={{ flex: 1 }}><strong>Archivio</strong><span>Le tue scansioni salvate</span></span>
        <ChevronRight size={18} strokeWidth={1.6} aria-hidden />
      </button>

      <p className="muted">Versione di sviluppo · la scansione guidata arriva nella fase 1. Per ora “Nuova scansione” apre il test della fotocamera.</p>
    </section>
  )
}
