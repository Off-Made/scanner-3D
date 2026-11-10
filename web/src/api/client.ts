// Client API: aggiunge `Authorization: Bearer <token>` a ogni chiamata.
// In locale VITE_API_URL è vuoto -> stessa origine, Vite fa da proxy verso FastAPI.
// Su Vercel VITE_API_URL punta al backend (Codespace / HF Space).

const API_BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')
const KEY = 'scan3d.session'

/** Pagina da cui accendere il backend quando è spento (Codespace: la lista dei tuoi Codespace). */
export const BACKEND_START_URL: string | null = import.meta.env.VITE_BACKEND_START_URL
  || (/\.app\.github\.dev$/.test(hostOf(API_BASE)) ? 'https://github.com/codespaces' : null)

function hostOf(url: string): string {
  try { return new URL(url).hostname } catch { return '' }
}

/** Messaggio quando il server non risponde: se è un Codespace, quasi sempre è solo spento. */
export function unreachableMessage(startUrl: string | null = BACKEND_START_URL): string {
  return startUrl
    ? 'Il server è spento. Accendilo da github.com/codespaces (si avvia da solo in 2–3 minuti), poi riprova.'
    : 'Server non raggiungibile. Controlla la connessione o che il backend sia acceso.'
}

export interface Session { token: string; expiresAt: number } // expiresAt in secondi Unix

export interface TokenStore { getItem(k: string): string | null; setItem(k: string, v: string): void; removeItem(k: string): void }

export function loadSession(store: TokenStore = localStorage, nowSec = Date.now() / 1000): Session | null {
  try {
    const s = JSON.parse(store.getItem(KEY) ?? 'null') as Session | null
    if (s && typeof s.token === 'string' && s.expiresAt > nowSec + 30) return s
  } catch { /* valore corrotto: lo ignoriamo */ }
  store.removeItem(KEY)
  return null
}

export function saveSession(s: Session, store: TokenStore = localStorage) { store.setItem(KEY, JSON.stringify(s)) }
export function clearSession(store: TokenStore = localStorage) { store.removeItem(KEY) }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

type Listener = () => void
const unauthorizedListeners = new Set<Listener>()
/** Chiamato quando il server risponde 401 (token scaduto o server riavviato). */
export function onUnauthorized(fn: Listener): () => void {
  unauthorizedListeners.add(fn)
  return () => { unauthorizedListeners.delete(fn) }
}

export async function apiBlob(path: string): Promise<Blob> {
  const s = loadSession()
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { headers: s ? { Authorization: `Bearer ${s.token}` } : {} })
  } catch {
    throw new ApiError(0, unreachableMessage())
  }
  if (res.status === 401) { clearSession(); unauthorizedListeners.forEach(f => f()) }
  if (!res.ok) throw new ApiError(res.status, `Errore ${res.status}`)
  return res.blob()
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const s = loadSession()
  if (s) headers.set('Authorization', `Bearer ${s.token}`)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, unreachableMessage())
  }
  if (res.status === 401 && path !== '/api/auth') { clearSession(); unauthorizedListeners.forEach(f => f()) }
  if (!res.ok) {
    const detail = await res.json().then(j => j?.detail).catch(() => null)
    throw new ApiError(res.status, typeof detail === 'string' ? detail : `Errore ${res.status}`)
  }
  return res.json() as Promise<T>
}

export async function login(pin: string): Promise<Session> {
  const s = await api<Session>('/api/auth', { method: 'POST', body: JSON.stringify({ pin }) })
  saveSession(s)
  return s
}
