import { useEffect, useState, type ReactNode } from 'react'
import { liveQuery } from 'dexie'
import { X } from 'lucide-react'

/** Dati da IndexedDB che si aggiornano da soli quando cambiano (Dexie liveQuery). */
export function useLive<T>(query: () => Promise<T>, deps: unknown[] = []): T | undefined {
  const [value, setValue] = useState<T>()
  useEffect(() => {
    const sub = liveQuery(query).subscribe({ next: setValue, error: e => console.error(e) })
    return () => sub.unsubscribe()
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  return value
}

export function Sheet({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    if (!open) return
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    addEventListener('keydown', k)
    return () => removeEventListener('keydown', k)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title} onClick={e => e.stopPropagation()}>
        <div className="sheet-head">
          <strong>{title}</strong>
          <button className="icon-btn" onClick={onClose} aria-label="Chiudi"><X size={20} strokeWidth={1.6} /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; label: string; onChange: (v: T) => void
  options: { value: T; label: string; disabled?: boolean; hint?: string }[]
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map(o => (
        <button key={o.value} role="radio" aria-checked={value === o.value} disabled={o.disabled}
                title={o.hint} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  )
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  return (
    <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value)} aria-label={label}>
      <div style={{ width: `${Math.max(2, Math.min(100, value))}%` }} />
    </div>
  )
}

export function Header({ title, back, right }: { title: string; back?: () => void; right?: ReactNode }) {
  return (
    <div className="header">
      {back ? <button className="icon-btn" onClick={back} aria-label="Indietro">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>
      </button> : <span style={{ width: 44 }} />}
      <h1 className="header-title">{title}</h1>
      {right ?? <span style={{ width: 44 }} />}
    </div>
  )
}

export function useObjectUrl(blob?: Blob): string | undefined {
  const [url, setUrl] = useState<string>()
  useEffect(() => {
    if (!blob) { setUrl(undefined); return }
    const u = URL.createObjectURL(blob)
    setUrl(u)
    return () => URL.revokeObjectURL(u)
  }, [blob])
  return url
}

export function formatDate(ms: number) {
  return new Date(ms).toLocaleString('it-IT', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function formatDuration(s: number) {
  if (!s) return '—'
  const m = Math.floor(s / 60), r = Math.round(s % 60)
  return m ? `${m} min ${r} s` : `${r} s`
}
