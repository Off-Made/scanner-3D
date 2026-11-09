// Smoke test veloce: PIN, temi chiaro/scuro, test fotocamera con fotocamera finta, nav in basso.
// Uso:  BASE_URL=http://127.0.0.1:8000 PIN=123456 node e2e/smoke.mjs
import { chromium, devices } from 'playwright-core'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5173'
const PIN = process.env.PIN
if (!PIN) { console.error('Imposta la variabile PIN'); process.exit(1) }
const OUT = fileURLToPath(new URL('./screens/', import.meta.url))
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch({ channel: 'chrome', args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] })
const errors = []
let failed = false
const check = (cond, msg) => { console.log(`${cond ? '✓' : '✗'} ${msg}`); if (!cond) failed = true }

for (const [device, scheme] of [['iPhone 13', 'light'], ['iPhone SE', 'dark'], ['Galaxy S9+', 'light']]) {
  const ctx = await browser.newContext({ ...devices[device], colorScheme: scheme, permissions: ['camera'] })
  const page = await ctx.newPage()
  page.on('pageerror', e => errors.push(String(e)))
  page.on('console', m => m.type() === 'error' && !/status of 401/.test(m.text()) && errors.push(m.text()))
  const tag = `[${device}, ${scheme}]`

  await page.goto(BASE)
  await page.getByRole('heading', { name: 'Scan3D' }).waitFor()
  await page.screenshot({ path: `${OUT}home-${device.replace(/\W/g, '')}-${scheme}.png` })
  await page.getByRole('button', { name: 'Nuova scansione' }).click()
  check(await page.getByText('Inserisci il PIN').isVisible(), `${tag} PIN richiesto per scansionare`)
  await page.getByLabel('PIN di accesso').fill('000000')
  await page.getByRole('button', { name: 'Entra' }).click()
  const wrong = await page.getByRole('alert').getByText('PIN errato').waitFor({ timeout: 5000 }).then(() => true, () => false)
  check(wrong, `${tag} PIN errato rifiutato`)
  await page.getByLabel('PIN di accesso').fill(PIN)
  await page.getByRole('button', { name: 'Entra' }).click()
  await page.getByRole('heading', { name: 'Nuova scansione' }).waitFor()
  await page.getByRole('button', { name: 'Inizia scansione' }).click()
  await page.locator('.hint').waitFor({ timeout: 10000 })
  // otturatore visibile senza scorrere (pollice)
  const vh = page.viewportSize().height
  const shutter = await page.getByLabel('Scatta foto').boundingBox()
  check(shutter && shutter.y + shutter.height <= vh, `${tag} otturatore visibile senza scorrere (${Math.round(shutter?.y ?? 0)} / ${vh} px)`)
  await page.screenshot({ path: `${OUT}scan-${device.replace(/\W/g, '')}-${scheme}.png` })

  const navH = await page.locator('.bottom-nav').evaluate(e => e.getBoundingClientRect().height)
  check(navH >= 64, `${tag} nav in basso alta ${Math.round(navH)} px`)
  await ctx.close()
}
await browser.close()
check(errors.length === 0, `nessun errore JS in console${errors.length ? ': ' + errors.join(' | ') : ''}`)
process.exit(failed ? 1 : 0)
