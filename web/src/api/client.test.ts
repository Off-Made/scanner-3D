import { describe, expect, it } from 'vitest'
import { loadSession, saveSession, unreachableMessage, type TokenStore } from './client'

function memStore(): TokenStore {
  const m = new Map<string, string>()
  return { getItem: k => m.get(k) ?? null, setItem: (k, v) => void m.set(k, v), removeItem: k => void m.delete(k) }
}

describe('sessione', () => {
  it('restituisce il token valido', () => {
    const s = memStore()
    saveSession({ token: 'abc', expiresAt: 2000 }, s)
    expect(loadSession(s, 1000)?.token).toBe('abc')
  })
  it('scarta token scaduti o in scadenza entro 30 s', () => {
    const s = memStore()
    saveSession({ token: 'abc', expiresAt: 1010 }, s)
    expect(loadSession(s, 1000)).toBeNull()
    expect(s.getItem('scan3d.session')).toBeNull()
  })
  it('ignora valori corrotti', () => {
    const s = memStore()
    s.setItem('scan3d.session', '{not json')
    expect(loadSession(s, 0)).toBeNull()
  })
})

describe('server non raggiungibile', () => {
  it('con un Codespace dice che è spento e come accenderlo', () => {
    expect(unreachableMessage('https://github.com/codespaces')).toMatch(/spento.*github\.com\/codespaces/)
  })
  it('senza pagina di avvio resta il messaggio generico', () => {
    expect(unreachableMessage(null)).toMatch(/non raggiungibile/)
  })
})
