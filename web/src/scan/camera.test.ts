import { describe, expect, it } from 'vitest'
import { describeCameraError, detectBrowser, detectPlatform } from './camera'

const UA = {
  iphone: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
  ipad: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15',
  samsung: 'Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/26.0 Chrome/122.0.0.0 Mobile Safari/537.36',
  chromeAndroid: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36',
}

describe('rilevamento piattaforma', () => {
  it('riconosce iPhone e iPad (che si presenta come Mac)', () => {
    expect(detectPlatform(UA.iphone, 5)).toBe('ios')
    expect(detectPlatform(UA.ipad, 5)).toBe('ios')
    expect(detectPlatform(UA.ipad, 0)).toBe('other') // vero Mac
  })
  it('distingue Samsung Internet da Chrome', () => {
    expect(detectBrowser(UA.samsung)).toBe('samsung')
    expect(detectBrowser(UA.chromeAndroid)).toBe('chrome')
    expect(detectBrowser(UA.iphone)).toBe('safari')
    expect(detectPlatform(UA.samsung, 5)).toBe('android')
  })
})

describe('messaggi di errore fotocamera', () => {
  it('senza HTTPS spiega il problema prima di tutto', () => {
    expect(describeCameraError({ name: 'NotAllowedError' }, 'ios', 'safari', false).title).toMatch(/sicura/)
  })
  it('permesso negato: istruzioni specifiche per iOS e Samsung', () => {
    const ios = describeCameraError({ name: 'NotAllowedError' }, 'ios', 'safari', true)
    expect(ios.steps?.join(' ')).toMatch(/Impostazioni › Safari/)
    const sam = describeCameraError({ name: 'NotAllowedError' }, 'android', 'samsung', true)
    expect(sam.steps?.join(' ')).toMatch(/Samsung Internet/)
  })
  it('fotocamera occupata e non trovata', () => {
    expect(describeCameraError({ name: 'NotReadableError' }, 'android', 'chrome', true).title).toMatch(/occupata/)
    expect(describeCameraError({ name: 'NotFoundError' }, 'ios', 'safari', true).title).toMatch(/non trovata/)
  })
})
