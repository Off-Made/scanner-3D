import { describe, expect, it } from 'vitest'
// L'import fallisce se vercel.json non è JSON valido (es. "\." invece di "\\."): Vercel lo rifiuterebbe.
import config from '../vercel.json'

describe('vercel.json', () => {
  const rewrite = new RegExp(`^${config.rewrites[0].source}$`)

  it('manda le rotte della PWA a index.html', () => {
    for (const p of ['/', '/scan/abc', '/archive']) expect(rewrite.test(p)).toBe(true)
  })

  it('lascia passare i file veri (service worker, asset, manifest)', () => {
    for (const p of ['/sw.js', '/assets/index.js', '/icons/a.png', '/manifest.webmanifest', '/registerSW.js']) {
      expect(rewrite.test(p)).toBe(false)
    }
  })
})
