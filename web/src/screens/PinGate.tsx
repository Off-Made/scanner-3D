import { useState, type FormEvent } from 'react'
import { Lock } from 'lucide-react'
import { ApiError, login } from '../api/client'

export function PinGate({ onReady }: { onReady: () => void }) {
  const [pin, setPin] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      await login(pin)
      onReady()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Errore imprevisto.')
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
        <p className="subtitle">Lo trovi nel terminale dove hai avviato il server.</p>
        <input
          className="pin-input" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]*"
          maxLength={12} value={pin} onChange={e => setPin(e.target.value.replace(/\D/g, ''))}
          aria-label="PIN di accesso" autoFocus
        />
        {error && <div className="notice" role="alert">{error}</div>}
        <button className="btn btn-primary btn-big" disabled={busy || pin.length < 4}>
          {busy ? 'Verifica…' : 'Entra'}
        </button>
      </form>
    </main>
  )
}
