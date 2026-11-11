import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertCircle, Camera, Images, Sparkles, Trash2, Zap, ZapOff } from 'lucide-react'
import { captureFrame, describeCameraError, detectBrowser, detectPlatform, requestOrientationPermission, startRearCamera, stopStream, type CameraProblem } from '../scan/camera'
import { Coverage, MAX_PHOTOS, RINGS, type PhotoView } from '../scan/coverage'
import { lightIssue, measure, SharpnessJudge } from '../scan/quality'
import { resizeImageFile, subsample } from '../scan/images'
import { startSubmission } from '../scan/submit'
import { getProviders, type ProviderInfo } from '../api/jobs'
import { defaultName } from '../db/scans'
import { Header, Segmented } from '../ui/components'

interface Shot { blob: Blob; url: string; view?: PhotoView }
interface Orientation { heading: number | null; beta: number | null; t: number }

function CoverageRing({ cov, photos, size = 92 }: { cov: Coverage; photos: number; size?: number }) {
  const c = size / 2
  const arcs = RINGS.map((r, ri) => {
    const radius = ri === 0 ? c - 6 : c - 20
    return Array.from({ length: r.sectors }, (_, i) => {
      const a0 = (i / r.sectors) * 2 * Math.PI - Math.PI / 2 + 0.03, a1 = ((i + 1) / r.sectors) * 2 * Math.PI - Math.PI / 2 - 0.03
      const p = (a: number) => `${c + radius * Math.cos(a)} ${c + radius * Math.sin(a)}`
      return <path key={`${ri}-${i}`} d={`M ${p(a0)} A ${radius} ${radius} 0 0 1 ${p(a1)}`} fill="none" strokeLinecap="round"
                   stroke={cov.filled[ri][i] ? '#f4f4f2' : 'rgba(244,244,242,0.25)'} strokeWidth={ri === 0 ? 6 : 5} />
    })
  })
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-label={`Copertura: ${cov.count(0)} di ${RINGS[0].sectors} angoli, ${cov.count(1)} di ${RINGS[1].sectors} dall'alto`}>
      {arcs}
      <text x={c} y={c + 5} textAnchor="middle" fontSize="15" fontWeight="600" fill="#f4f4f2">{photos}</text>
    </svg>
  )
}

export function ScanScreen({ go }: { go: (hash: string) => void }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const smallCanvas = useRef<HTMLCanvasElement>(document.createElement('canvas'))
  const orient = useRef<Orientation>({ heading: null, beta: null, t: 0 })
  const history = useRef<{ h: number; t: number }[]>([])
  const judge = useRef(new SharpnessJudge())
  const lastShot = useRef(0)
  const busy = useRef(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [provider, setProvider] = useState('photo')
  const [cov, setCov] = useState(() => new Coverage())
  const [shots, setShots] = useState<Shot[]>([])
  const [camOn, setCamOn] = useState(false)
  const [auto, setAuto] = useState(true)
  const [gyro, setGyro] = useState(false)
  const [problem, setProblem] = useState<CameraProblem | null>(null)
  const [live, setLive] = useState<{ light: ReturnType<typeof lightIssue>; sharp: boolean; stable: boolean }>({ light: null, sharp: true, stable: true })
  const [flash, setFlash] = useState(0)
  const [importing, setImporting] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [, force] = useState(0)

  const current = providers.find(p => p.id === provider)
  const minPhotos = current?.minPhotos ?? 12
  const platform = detectPlatform(), browser = detectBrowser()

  useEffect(() => {
    getProviders().then(ps => {
      setProviders(ps)
      const first = ps.find(p => p.id === 'photo' && p.available) ?? ps.find(p => p.available)
      if (first) setProvider(first.id)
    }).catch(e => setError(e.message))
    return () => stopStream(streamRef.current)
  }, [])
  useEffect(() => () => shots.forEach(s => URL.revokeObjectURL(s.url)), []) // eslint-disable-line

  const addShot = useCallback((blob: Blob, view?: PhotoView) => {
    setShots(prev => prev.length >= MAX_PHOTOS ? prev : [...prev, { blob, url: URL.createObjectURL(blob), view }])
  }, [])

  const shoot = useCallback(async () => {
    if (busy.current || !videoRef.current || shots.length >= MAX_PHOTOS) return
    busy.current = true
    try {
      const blob = await captureFrame(videoRef.current) // risoluzione piena del video (fino a 1920×1440)
      const o = orient.current
      cov.mark(o.heading ?? shots.length * 15, o.beta) // senza giroscopio: stima dal numero di foto
      // l'angolo vero lo mando solo se c'è la bussola: una stima sbagliata darebbe all'AI viste sbagliate
      addShot(blob, o.heading != null ? cov.viewOf(o.heading, o.beta) : undefined)
      lastShot.current = performance.now()
      setFlash(f => f + 1)
      navigator.vibrate?.(12)
      force(n => n + 1)
    } finally { busy.current = false }
  }, [cov, shots.length, addShot])

  // --- analisi continua del fotogramma (5 volte al secondo) + scatto automatico -----------
  useEffect(() => {
    if (!camOn) return
    const cv = smallCanvas.current
    cv.width = 128; cv.height = 96
    const ctx = cv.getContext('2d', { willReadFrequently: true })!
    const id = setInterval(() => {
      const v = videoRef.current
      if (!v || !v.videoWidth) return
      ctx.drawImage(v, 0, 0, cv.width, cv.height)
      const q = measure(ctx.getImageData(0, 0, cv.width, cv.height).data, cv.width, cv.height)
      judge.current.push(q.sharpness)
      const sharp = judge.current.isSharp(q.sharpness)
      const light = lightIssue(q.brightness)
      const now = performance.now()
      const hist = history.current.filter(h => now - h.t < 400)
      const o = orient.current
      const stable = o.heading == null || hist.length < 2 || Math.max(...hist.map(h => Math.abs(((h.h - o.heading! + 540) % 360) - 180))) < 4
      setLive(prev => (prev.sharp === sharp && prev.light === light && prev.stable === stable ? prev : { light, sharp, stable }))
      if (!auto || shots.length >= MAX_PHOTOS || !sharp || light || !stable) return
      const gap = now - lastShot.current
      const newAngle = o.heading != null ? cov.isNew(o.heading, o.beta) : gap > 1500
      if (newAngle && gap > 800) shoot()
    }, 200)
    return () => clearInterval(id)
  }, [camOn, auto, shots.length, cov, shoot])

  async function start() {
    setProblem(null)
    // iOS: i permessi di giroscopio e fotocamera vanno chiesti nello stesso tap
    const perm = await requestOrientationPermission()
    if (perm === 'granted' || perm === 'not-required') {
      const evt = 'ondeviceorientationabsolute' in window ? 'deviceorientationabsolute' : 'deviceorientation'
      window.addEventListener(evt, (e: Event) => {
        const d = e as DeviceOrientationEvent & { webkitCompassHeading?: number }
        const heading = d.webkitCompassHeading ?? (d.alpha != null ? 360 - d.alpha : null)
        if (heading == null) return
        orient.current = { heading, beta: d.beta, t: performance.now() }
        history.current.push({ h: heading, t: performance.now() })
        if (history.current.length > 30) history.current.shift()
        setGyro(true)
      })
    }
    try {
      streamRef.current = await startRearCamera(videoRef.current!)
      setCamOn(true)
    } catch (e) {
      setProblem(describeCameraError(e, platform, browser, window.isSecureContext))
    }
  }

  async function importFiles(list: FileList | null) {
    if (!list?.length) return
    const room = MAX_PHOTOS - shots.length
    const files = subsample(Array.from(list).filter(f => f.type.startsWith('image/') || /\.(heic|heif)$/i.test(f.name)), room)
    for (let i = 0; i < files.length; i++) {
      setImporting(`Preparazione foto ${i + 1}/${files.length}`)
      addShot(await resizeImageFile(files[i]))
      cov.mark(((shots.length + i) * 360) / Math.max(24, files.length), 90)
    }
    setImporting(list.length > room ? `Hai scelto ${list.length} foto: ne ho tenute ${files.length} distribuite in modo uniforme (massimo ${MAX_PHOTOS}).` : null)
    if (list.length <= room) setImporting(null)
    if (fileInput.current) fileInput.current.value = ''
    force(n => n + 1)
  }

  function removeLast() {
    setShots(prev => { const last = prev.at(-1); if (last) URL.revokeObjectURL(last.url); return prev.slice(0, -1) })
    if (shots.length <= 1) setCov(new Coverage())
  }

  async function submit() {
    setSubmitting(true); setError(null)
    try {
      stopStream(streamRef.current)
      const id = await startSubmission(defaultName(), provider, shots.map(s => s.blob), shots.map(s => s.view))
      go(`/scan/${id}`)
    } catch (e) {
      setError((e as Error).message); setSubmitting(false)
    }
  }

  const hint = useMemo(() => {
    if (!camOn) return null
    if (live.light === 'dark') return 'Serve più luce: avvicinati a una finestra o accendi una lampada'
    if (live.light === 'bright') return 'Troppa luce diretta: evita il sole o i riflessi forti'
    if (!live.stable || !live.sharp) return 'Fermo un attimo: la foto è mossa'
    if (!gyro && auto) return 'Gira attorno all’oggetto: scatto da solo ogni 1,5 secondi'
    return cov.hint(shots.length)
  }, [camOn, live, gyro, auto, cov, shots.length, flash]) // eslint-disable-line react-hooks/exhaustive-deps

  const options = providers.filter(p => p.id !== 'mock' || p.available).map(p => ({
    value: p.id, label: p.id === 'ai' ? '✦ ' + p.label : p.label, disabled: !p.available, hint: p.available ? p.description : p.reason,
  }))

  return (
    <section className="screen">
      <Header title="Nuova scansione" back={() => go('/')} />
      {options.length > 1 && <Segmented label="Motore di ricostruzione" value={provider} onChange={setProvider} options={options} />}
      {current && (current.available
        ? <p className="muted" style={{ margin: 0 }}>{current.description}</p>
        : <div className="notice" role="alert"><AlertCircle size={20} strokeWidth={1.6} />
            <div><strong>{current.label}: non disponibile ora</strong><div>{current.reason || 'Il server non può usare questo motore.'}</div></div></div>)}

      <div className="scan-stage">
        <div className="viewfinder">
          <video ref={videoRef} playsInline muted />
          <div className={`flash ${flash ? 'on' : ''}`} key={flash} />
          {camOn && <div className="scan-overlay">
            <div className="scan-top">
              <CoverageRing cov={cov} photos={shots.length} />
              <span className="pill count">{shots.length} / {MAX_PHOTOS}</span>
            </div>
            {hint && <div className="hint" aria-live="polite">{hint}</div>}
          </div>}
          {!camOn && <div className="scan-overlay" style={{ pointerEvents: 'auto', justifyContent: 'center', alignItems: 'center', gap: 12 }}>
            <button className="btn btn-primary btn-big" style={{ width: 'auto' }} onClick={start}><Camera size={22} strokeWidth={1.6} /> Inizia scansione</button>
            <span className="pill">oppure importa le foto dalla galleria</span>
          </div>}
        </div>
      </div>

      {problem && <div className="notice" role="alert"><AlertCircle size={20} strokeWidth={1.6} />
        <div><strong>{problem.title}</strong><div>{problem.message}</div>
          {problem.steps && <ol style={{ margin: '8px 0 0', paddingLeft: 18 }}>{problem.steps.map(s => <li key={s}>{s}</li>)}</ol>}
          <div style={{ marginTop: 6 }}>Puoi comunque importare foto dalla galleria.</div></div></div>}

      <div className="shutter-row">
        <button className="side-btn" onClick={() => fileInput.current?.click()}><Images size={24} strokeWidth={1.6} />Galleria</button>
        <button className="shutter" onClick={shoot} disabled={!camOn || shots.length >= MAX_PHOTOS} aria-label="Scatta foto" />
        <button className="side-btn" aria-pressed={auto} onClick={() => setAuto(a => !a)} disabled={!camOn}>
          {auto ? <Zap size={24} strokeWidth={1.6} /> : <ZapOff size={24} strokeWidth={1.6} />}{auto ? 'Auto' : 'Manuale'}
        </button>
      </div>
      <input ref={fileInput} type="file" accept="image/*,.heic,.heif" multiple hidden onChange={e => importFiles(e.target.files)} data-testid="file-input" />

      {importing && <div className="notice">{importing}</div>}
      {shots.length > 0 && <div className="row" style={{ alignItems: 'center' }}>
        <div className="thumbs" style={{ flex: 1 }}>{shots.slice(-8).reverse().map(s => <img key={s.url} src={s.url} alt="" />)}</div>
        <button className="icon-btn" onClick={removeLast} aria-label="Elimina l'ultima foto" style={{ flex: 'none' }}><Trash2 size={20} strokeWidth={1.6} /></button>
      </div>}

      {error && <div className="notice" role="alert"><AlertCircle size={20} strokeWidth={1.6} />{error}</div>}
      <button className="btn btn-primary btn-big" disabled={shots.length < minPhotos || submitting || !current?.available} onClick={submit}>
        <Sparkles size={22} strokeWidth={1.6} />
        {submitting ? 'Invio…' : shots.length < minPhotos ? `Servono almeno ${minPhotos} foto (${shots.length})` : `Elabora ${shots.length} foto`}
      </button>
      {provider === 'ai'
        ? <p className="muted" style={{ margin: 0 }}>Consigli: la <strong>prima foto è il fronte</strong> dell’oggetto. Poi gira tutto attorno all’altezza dell’oggetto:
          l’app sceglie da sola fronte, retro e fianchi (servono la bussola e almeno 8 foto). Oggetto intero e al centro, sfondo uniforme, luce diffusa.
          Le parti che nessuna foto vede vengono comunque stimate.</p>
        : <>
          <p className="muted" style={{ margin: 0 }}>Consigli: appoggia l’oggetto su un foglio di giornale o una tovaglia a disegni (aiutano a calcolare le posizioni), luce diffusa senza riflessi, 30–40 foto girando due volte: all’altezza dell’oggetto e dall’alto.</p>
          <details className="muted">
            <summary>Oggetti difficili: piccoli, con dettagli fini, lucidi o in tinta unita</summary>
            <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
              <li><strong>Lucidi o in tinta unita</strong> (plastica liscia, metallo, ceramica, oggetti bianchi): opacizzali con talco, borotalco spray o shampoo secco; su superfici lisce aggiungi qualche pezzetto di nastro di carta con segni di pennarello. Il <strong>trasparente</strong> (vetro) non si può ricostruire.</li>
              <li><strong>Piccoli</strong> (meno di 10 cm): avvicinati finché l’oggetto riempie metà inquadratura, ma resta a fuoco; tieni sempre un po’ di giornale visibile attorno.</li>
              <li><strong>Dettagli fini</strong> (fessure, scritte, parti sottili): dopo i due giri aggiungi 5–8 foto ravvicinate su quei punti, da angolazioni leggermente diverse.</li>
              <li>Mai il flash, mai controluce: meglio vicino a una finestra con il cielo coperto.</li>
            </ul>
          </details>
        </>}
    </section>
  )
}
