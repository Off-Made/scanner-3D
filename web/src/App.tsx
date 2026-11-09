import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { Archive, Camera, Home as HomeIcon } from 'lucide-react'
import { loadSession, onUnauthorized } from './api/client'
import { recoverInterruptedUploads } from './scan/submit'
import { PinGate } from './screens/PinGate'
import { Home } from './screens/Home'
import { CameraTest } from './screens/CameraTest'
import { ScanScreen } from './screens/Scan'
import { ProcessingScreen } from './screens/Processing'
// schermate 3D caricate solo quando servono (three.js pesa ~500 kB)
const ModelScreen = lazy(() => import('./screens/Model').then(m => ({ default: m.ModelScreen })))
const ExportScreen = lazy(() => import('./screens/Export').then(m => ({ default: m.ExportScreen })))
import { ArchiveScreen } from './screens/Archive'

type Theme = 'light' | 'dark'

/** Rotte: #/  #/scan  #/scan/<id>  #/model/<id>  #/export/<id>  #/archive  #/camera-test */
export function parseRoute(hash: string): { name: string; id?: string } {
  const [, name = '', id] = hash.replace(/^#/, '').split('/')
  return { name: name || 'home', id }
}

function useTheme(): [Theme, () => void] {
  const system = (): Theme => (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem('scan3d.theme') as Theme) || system())
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.querySelectorAll('meta[name="theme-color"]').forEach(m => m.setAttribute('content', theme === 'dark' ? '#121212' : '#f5f5f4'))
  }, [theme])
  return [theme, () => setTheme(t => { const n = t === 'dark' ? 'light' : 'dark'; localStorage.setItem('scan3d.theme', n); return n })]
}

export default function App() {
  const [authed, setAuthed] = useState(() => loadSession() !== null)
  const [route, setRoute] = useState(() => parseRoute(location.hash))
  const [theme, toggleTheme] = useTheme()

  useEffect(() => onUnauthorized(() => setAuthed(false)), [])
  useEffect(() => { recoverInterruptedUploads() }, [])
  useEffect(() => {
    const f = () => { setRoute(parseRoute(location.hash)); scrollTo(0, 0) }
    addEventListener('hashchange', f)
    return () => removeEventListener('hashchange', f)
  }, [])

  const go = useCallback((path: string) => { location.hash = path }, [])

  // Archivio, anteprima ed export funzionano anche offline (dati nel telefono): il PIN serve
  // solo per parlare con il server (scansione ed elaborazione).
  const needsServer = route.name === 'scan'
  if (!authed && needsServer) return <PinGate onReady={() => setAuthed(true)} />

  const tab = route.name === 'archive' || route.name === 'model' || route.name === 'export' ? 'archive' : route.name === 'scan' ? 'scan' : 'home'
  const tabs = [
    { id: 'home', label: 'Home', path: '/', Icon: HomeIcon },
    { id: 'scan', label: 'Scansione', path: '/scan', Icon: Camera },
    { id: 'archive', label: 'Archivio', path: '/archive', Icon: Archive },
  ]

  return (
    <>
      <main className="app" key={route.name + (route.id ?? '')}>
        {route.name === 'home' && <Home go={go} theme={theme} toggleTheme={toggleTheme} />}
        {route.name === 'scan' && !route.id && <ScanScreen go={go} />}
        {route.name === 'scan' && route.id && <ProcessingScreen id={route.id} go={go} />}
        <Suspense fallback={<div className="screen" style={{ alignItems: 'center', paddingTop: 80 }}><span className="spinner" /></div>}>
          {route.name === 'model' && route.id && <ModelScreen id={route.id} go={go} />}
          {route.name === 'export' && route.id && <ExportScreen id={route.id} go={go} />}
        </Suspense>
        {route.name === 'archive' && <ArchiveScreen go={go} />}
        {route.name === 'camera-test' && <CameraTest />}
      </main>
      <nav className="bottom-nav" aria-label="Navigazione principale">
        {tabs.map(({ id, label, path, Icon }) => (
          <button key={id} onClick={() => go(path)} aria-current={tab === id ? 'page' : undefined}>
            <Icon size={22} strokeWidth={tab === id ? 2 : 1.6} aria-hidden />{label}
          </button>
        ))}
      </nav>
    </>
  )
}
