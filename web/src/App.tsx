import { useEffect, useState } from 'react'
import { Archive, Camera, Home as HomeIcon } from 'lucide-react'
import { loadSession, onUnauthorized } from './api/client'
import { PinGate } from './screens/PinGate'
import { Home } from './screens/Home'
import { CameraTest } from './screens/CameraTest'

export type Route = 'home' | 'scan' | 'archive'
type Theme = 'light' | 'dark'

const routeFromHash = (): Route => {
  const r = location.hash.replace('#/', '')
  return r === 'scan' || r === 'archive' ? r : 'home'
}

function useTheme(): [Theme, () => void] {
  const system = (): Theme => (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem('scan3d.theme') as Theme) || system())
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.querySelectorAll('meta[name="theme-color"]').forEach(m => m.setAttribute('content', theme === 'dark' ? '#151515' : '#f5f5f4'))
  }, [theme])
  return [theme, () => setTheme(t => { const n = t === 'dark' ? 'light' : 'dark'; localStorage.setItem('scan3d.theme', n); return n })]
}

export default function App() {
  const [authed, setAuthed] = useState(() => loadSession() !== null)
  const [route, setRoute] = useState<Route>(routeFromHash)
  const [theme, toggleTheme] = useTheme()

  useEffect(() => onUnauthorized(() => setAuthed(false)), [])
  useEffect(() => {
    const f = () => setRoute(routeFromHash())
    addEventListener('hashchange', f)
    return () => removeEventListener('hashchange', f)
  }, [])

  const go = (r: Route) => { location.hash = `/${r}` }

  if (!authed) return <PinGate onReady={() => setAuthed(true)} />

  const tabs: { id: Route; label: string; Icon: typeof HomeIcon }[] = [
    { id: 'home', label: 'Home', Icon: HomeIcon },
    { id: 'scan', label: 'Scansione', Icon: Camera },
    { id: 'archive', label: 'Archivio', Icon: Archive },
  ]

  return (
    <>
      <main className="app">
        {route === 'home' && <Home go={go} theme={theme} toggleTheme={toggleTheme} />}
        {route === 'scan' && <CameraTest />}
        {route === 'archive' && (
          <section className="screen">
            <h1 className="title">Archivio</h1>
            <p className="subtitle">Qui troverai le scansioni salvate (fase 3).</p>
          </section>
        )}
      </main>
      <nav className="bottom-nav" aria-label="Navigazione principale">
        {tabs.map(({ id, label, Icon }) => (
          <button key={id} onClick={() => go(id)} aria-current={route === id ? 'page' : undefined}>
            <Icon size={22} strokeWidth={route === id ? 2 : 1.6} aria-hidden />{label}
          </button>
        ))}
      </nav>
    </>
  )
}
