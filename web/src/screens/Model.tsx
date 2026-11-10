import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { AlertTriangle, CheckCircle2, Download, Layers, RotateCw, Ruler, ShieldCheck } from 'lucide-react'
import { db, modelBytes, updateScan, type Scan } from '../db/scans'
import { bake, checkBed, dimensions, fmt, IDENTITY_EDIT, layFlat, loadGlb, rotate90, scaleForDimension, type Axis, type Edit } from '../three/geometry'
import { Header, Segmented, useLive } from '../ui/components'

const Viewer = lazy(() => import('../three/Viewer'))

export const BEDS = [
  { id: '180', label: '180 mm', size: { x: 180, y: 180, z: 180 } },
  { id: '220', label: '220 mm', size: { x: 220, y: 220, z: 250 } },
  { id: '256', label: '256 mm', size: { x: 256, y: 256, z: 256 } },
  { id: '300', label: '300 mm', size: { x: 300, y: 300, z: 300 } },
]
export function useBed() {
  const [bedId, setBedId] = useState(() => localStorage.getItem('scan3d.bed') ?? '220')
  const bed = (BEDS.find(b => b.id === bedId) ?? BEDS[1]).size
  return { bed, bedId, setBedId: (id: string) => { localStorage.setItem('scan3d.bed', id); setBedId(id) } }
}

/** Geometria base dal modello salvato + geometria con le modifiche applicate. */
export function useModelGeometry(scan?: Scan) {
  const [base, setBase] = useState<THREE.BufferGeometry>()
  const [error, setError] = useState<string>()
  useEffect(() => {
    if (!scan?.model) return
    let alive = true
    modelBytes(scan.model).then(loadGlb).then(g => { if (alive) { setBase(g); setError(undefined) } })
      .catch(e => alive && setError(String(e.message ?? e)))
    return () => { alive = false }
    // Solo quando cambia la scansione o il modello arriva: NON a ogni aggiornamento (miniatura, modifiche),
    // altrimenti si rilegge il file ogni volta. In passato una di queste riletture falliva su Safari.
  }, [scan?.id, !!scan?.model]) // eslint-disable-line react-hooks/exhaustive-deps
  const baked = useMemo(() => (base && scan ? bake(base, scan.edit ?? IDENTITY_EDIT) : undefined), [base, scan?.edit]) // eslint-disable-line react-hooks/exhaustive-deps
  return { base, baked, error }
}

type Tab = 'size' | 'rotate' | 'check'

export function ModelScreen({ id, go }: { id: string; go: (h: string) => void }) {
  const scan = useLive(() => db.scans.get(id), [id])
  const { base, baked, error } = useModelGeometry(scan)
  const { bed, bedId, setBedId } = useBed()
  const [tab, setTab] = useState<Tab>('size')
  const [axis, setAxis] = useState<Axis>('z')
  const [mm, setMm] = useState('')
  const savingThumb = useRef(false)

  const dims = baked ? dimensions(baked) : null
  useEffect(() => { if (dims) setMm(fmt(dims[axis]).replace(',', '.')) }, [axis, baked]) // eslint-disable-line react-hooks/exhaustive-deps

  const setEdit = useCallback((e: Edit) => updateScan(id, { edit: e }), [id])

  const snapshot = useCallback((canvas: HTMLCanvasElement) => {
    if (!scan || scan.thumb || savingThumb.current || !canvas) return
    savingThumb.current = true
    const c = document.createElement('canvas')
    const s = Math.min(canvas.width, canvas.height)
    c.width = c.height = 256
    c.getContext('2d')!.drawImage(canvas, (canvas.width - s) / 2, (canvas.height - s) / 2, s, s, 0, 0, 256, 256)
    c.toBlob(b => b && updateScan(id, { thumb: b }), 'image/jpeg', 0.85)
  }, [scan, id])

  useEffect(() => { if (scan && scan.status !== 'ready') go(`/scan/${id}`) }, [scan, id, go])

  if (scan === undefined) return null
  if (!scan) return <section className="screen"><Header title="Modello" back={() => go('/archive')} /><p>Scansione non trovata.</p></section>
  if (scan.status !== 'ready') return null

  const edit = scan.edit ?? IDENTITY_EDIT
  const bedCheck = dims ? checkBed(dims, bed) : null
  const volume = scan.report ? scan.report.volumeMm3 * edit.scale ** 3 : 0

  function applySize() {
    const v = parseFloat(mm.replace(',', '.'))
    if (base && v > 0) setEdit(scaleForDimension(base, edit, axis, v))
  }

  return (
    <section className="screen">
      <Header title={scan.name} back={() => go('/archive')} />
      {error && <div className="notice" role="alert">{error}</div>}
      <Suspense fallback={<div className="viewer" style={{ display: 'grid', placeItems: 'center' }}><span className="spinner" /></div>}>
        {baked ? <Viewer geometry={baked} bed={bed} onSnapshot={snapshot} /> : <div className="viewer" style={{ display: 'grid', placeItems: 'center' }}><span className="spinner" /></div>}
      </Suspense>

      {dims && <div className="dims">
        {(['x', 'y', 'z'] as Axis[]).map(a => <div className="dim" key={a}><small>{a === 'x' ? 'Larghezza' : a === 'y' ? 'Profondità' : 'Altezza'}</small><b>{fmt(dims[a])}</b> mm</div>)}
      </div>}
      {!edit.realScale && <div className="notice"><Ruler size={20} strokeWidth={1.6} />
        <div><strong>Scala indicativa</strong><div>La fotografia non conosce le misure reali: misura un lato dell’oggetto con un righello e inseriscilo qui sotto.</div></div></div>}

      <Segmented label="Strumenti" value={tab} onChange={setTab} options={[
        { value: 'size', label: 'Misure' }, { value: 'rotate', label: 'Posizione' }, { value: 'check', label: 'Controllo' },
      ]} />

      {tab === 'size' && <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="chips" role="group" aria-label="Lato da misurare">
          {(['x', 'y', 'z'] as Axis[]).map(a => <button key={a} className="chip" aria-pressed={axis === a} onClick={() => setAxis(a)}>
            {a === 'x' ? 'Larghezza' : a === 'y' ? 'Profondità' : 'Altezza'}</button>)}
        </div>
        <label className="field">Misura reale in millimetri
          <input className="input" inputMode="decimal" value={mm} onChange={e => setMm(e.target.value)} aria-label="Misura in millimetri" />
        </label>
        <button className="btn btn-primary" onClick={applySize}><Ruler size={20} strokeWidth={1.6} /> Applica misura</button>
        <p className="muted" style={{ margin: 0 }}>Le proporzioni restano bloccate: cambia tutto il modello in scala.</p>
      </div>}

      {tab === 'rotate' && <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <button className="btn btn-primary" onClick={() => base && setEdit(layFlat(base, edit))}><Layers size={20} strokeWidth={1.6} /> Appoggia sulla base più ampia</button>
        <div className="grid-2" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
          {(['x', 'y', 'z'] as Axis[]).map(a => <button key={a} className="btn" onClick={() => setEdit(rotate90(edit, a))}><RotateCw size={18} strokeWidth={1.6} /> {a.toUpperCase()} 90°</button>)}
        </div>
        <button className="btn" onClick={() => setEdit({ ...IDENTITY_EDIT, scale: edit.scale, realScale: edit.realScale })}>Orientamento originale</button>
        <p className="muted" style={{ margin: 0 }}>Il modello resta sempre centrato e appoggiato sul piatto.</p>
      </div>}

      {tab === 'check' && <div className="card">
        {scan.report?.checks.map(c => <div className="check" key={c.id}>
          {c.ok ? <CheckCircle2 size={20} strokeWidth={1.6} /> : <AlertTriangle size={20} strokeWidth={1.6} />}
          <div><div>{c.label}</div>{c.hint && <div className="muted">{c.hint}</div>}</div></div>)}
        {bedCheck && <div className="check">
          {bedCheck.fits && !bedCheck.tooSmall ? <CheckCircle2 size={20} strokeWidth={1.6} /> : <AlertTriangle size={20} strokeWidth={1.6} />}
          <div style={{ flex: 1 }}><div>{bedCheck.message}</div>
            <div className="chips" style={{ marginTop: 8 }}>{BEDS.map(b => <button key={b.id} className="chip" aria-pressed={bedId === b.id} onClick={() => setBedId(b.id)}>{b.label}</button>)}</div>
          </div></div>}
        <div className="check"><ShieldCheck size={20} strokeWidth={1.6} />
          <div>Volume: {(volume / 1000).toFixed(1).replace('.', ',')} cm³ · {scan.report?.triangles.toLocaleString('it-IT')} triangoli</div></div>
        {scan.cleanup && scan.cleanup.length > 0 && <details style={{ marginTop: 8 }}><summary className="muted">Passi di pulizia eseguiti</summary>
          <ul style={{ margin: '8px 0 0', paddingLeft: 18, fontSize: 14 }}>{scan.cleanup.map(s => <li key={s}>{s}</li>)}</ul></details>}
      </div>}

      <button className="btn btn-primary btn-big" onClick={() => go(`/export/${id}`)}><Download size={22} strokeWidth={1.6} /> Esporta per la stampa</button>
    </section>
  )
}
