import { useEffect, useRef, useState } from 'react'
import { AlertCircle, Aperture, Compass, Power } from 'lucide-react'
import {
  captureFrame, describeCameraError, detectBrowser, detectPlatform, requestOrientationPermission,
  startRearCamera, stopStream, type CameraProblem,
} from '../scan/camera'

/** Fase 0: verifica di fotocamera, cattura e giroscopio su iPhone / Android. */
export function CameraTest() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const [problem, setProblem] = useState<CameraProblem | null>(null)
  const [info, setInfo] = useState<Record<string, string>>({})
  const [shots, setShots] = useState<string[]>([])
  const [heading, setHeading] = useState<string>('—')
  const [running, setRunning] = useState(false)
  const platform = detectPlatform()
  const browser = detectBrowser()

  useEffect(() => () => { stopStream(streamRef.current); shots.forEach(URL.revokeObjectURL) }, []) // eslint-disable-line

  async function start() {
    setProblem(null)
    try {
      const stream = await startRearCamera(videoRef.current!)
      streamRef.current = stream
      const s = stream.getVideoTracks()[0].getSettings()
      setInfo({
        Risoluzione: `${s.width ?? '?'} × ${s.height ?? '?'}`,
        Fotocamera: s.facingMode === 'environment' ? 'posteriore' : (s.facingMode ?? 'non indicata'),
      })
      setRunning(true)
    } catch (err) {
      setProblem(describeCameraError(err, platform, browser, window.isSecureContext))
    }
  }

  function stop() { stopStream(streamRef.current); streamRef.current = null; setRunning(false) }

  async function shoot() {
    const blob = await captureFrame(videoRef.current!)
    setShots(prev => [URL.createObjectURL(blob), ...prev].slice(0, 8))
    setInfo(i => ({ ...i, 'Ultimo scatto': `${Math.round(blob.size / 1024)} KB` }))
  }

  async function enableGyro() {
    const p = await requestOrientationPermission()
    if (p === 'denied' || p === 'unsupported') { setHeading(p === 'denied' ? 'permesso negato' : 'non supportato'); return }
    const evt = 'ondeviceorientationabsolute' in window ? 'deviceorientationabsolute' : 'deviceorientation'
    window.addEventListener(evt, (e: Event) => {
      const o = e as DeviceOrientationEvent & { webkitCompassHeading?: number }
      const a = o.webkitCompassHeading ?? (o.alpha != null ? 360 - o.alpha : null)
      setHeading(a == null ? 'nessun dato' : `${Math.round(a)}°`)
    })
  }

  return (
    <section className="screen">
      <h1 className="title">Test fotocamera</h1>
      <p className="subtitle">Verifica che fotocamera e sensori funzionino su questo telefono.</p>

      <div className="viewfinder"><video ref={videoRef} playsInline muted /></div>

      {problem && (
        <div className="notice" role="alert">
          <AlertCircle size={20} strokeWidth={1.6} aria-hidden />
          <div><strong>{problem.title}</strong><div>{problem.message}</div>
            {problem.steps && <ol style={{ margin: '8px 0 0', paddingLeft: 18 }}>{problem.steps.map(s => <li key={s}>{s}</li>)}</ol>}
          </div>
        </div>
      )}

      {!running
        ? <button className="btn btn-primary btn-big" onClick={start}><Aperture size={22} strokeWidth={1.6} aria-hidden /> Avvia fotocamera</button>
        : <div className="row">
            <button className="btn btn-primary btn-big" onClick={shoot}><Aperture size={22} strokeWidth={1.6} aria-hidden /> Scatta</button>
            <button className="btn btn-big" onClick={stop} aria-label="Spegni fotocamera" style={{ flex: '0 0 72px', padding: 0 }}><Power size={22} strokeWidth={1.6} /></button>
          </div>}

      <button className="btn" onClick={enableGyro}><Compass size={20} strokeWidth={1.6} aria-hidden /> Attiva giroscopio</button>

      {shots.length > 0 && <div className="thumbs">{shots.map(u => <img key={u} src={u} alt="Scatto di prova" />)}</div>}

      <dl className="card kv">
        <dt>Piattaforma</dt><dd>{platform} · {browser}</dd>
        <dt>HTTPS</dt><dd>{window.isSecureContext ? 'sì' : 'no'}</dd>
        <dt>App installata</dt><dd>{matchMedia('(display-mode: standalone)').matches ? 'sì' : 'no'}</dd>
        <dt>Orientamento</dt><dd>{heading}</dd>
        {Object.entries(info).map(([k, v]) => [<dt key={k}>{k}</dt>, <dd key={k + 'v'}>{v}</dd>])}
      </dl>
    </section>
  )
}
