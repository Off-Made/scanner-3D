import { useState, type FormEvent } from 'react'
import { Lock } from 'lucide-react'
import { ApiError, BACKEND_START_URL, login } from '../api/client'

export function PinGate({ onReady }: { onReady: () => void }) {
  const [pin, setPin] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [offline, setOffline] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setError(null); setOffline(false)
    try {
      await login(pin)
      onReady()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Errore imprevisto.')
      setOffline(err instanceof ApiError && err.status === 0)
      setPin('')
    } finally { setBusy(false) }
  }

  return (
    <main className="app">
      <form className="screen" onSubmit={submit} style={{ marginTop: '18vh' }}>
        <div className="tile-icon" style={{ width: 56, height: 56, borderRadius: 16, background: 'var(--surface-2)', display: 'grid', placeItems: 'center' }}>
          <Lock size={24} strokeWidth={1.6} aria-hidden />
        </div>
        <h1 className="title">Inserisci il PIN</h1>
        <p className="subtitle">Serve per usare il server di ricostruzione. È il PIN stampato nel terminale del server (o impostato nei suoi segreti).</p>
        <input
          className="pin-input" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]*"
          maxLength={12} value={pin} onChange={e => setPin(e.target.value.replace(/\D/g, ''))}
          aria-label="PIN di accesso" autoFocus
        />
        {error && <div className="notice" role="alert">{error}</div>}
        {offline && BACKEND_START_URL && <a className="btn" href={BACKEND_START_URL} target="_blank" rel="noopener noreferrer">Accendi il server</a>}
        <button className="btn btn-primary btn-big" disabled={busy || pin.length < 4}>
          {busy ? 'Verifica…' : 'Entra'}
        </button>
      </form>
    </main>
  )
}
