// Smoke test con emulazione iPhone 13 e fotocamera finta di Chromium.
// Usa il Chrome già installato (channel 'chrome'): nessun browser scaricato.
// Uso:  PIN=123456 node e2e/smoke.mjs   (con `npm run dev` attivo)
import { chromium, devices } from 'playwright-core'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5173'
const PIN = process.env.PIN
if (!PIN) { console.error('Imposta la variabile PIN'); process.exit(1) }
const OUT = fileURLToPath(new URL('./screens/', import.meta.url))
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch({
  channel: 'chrome',
  args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
})
const errors = []
let failed = false
const check = (cond, msg) => { console.log(`${cond ? '✓' : '✗'} ${msg}`); if (!cond) failed = true }

for (const scheme of ['light', 'dark']) {
  const ctx = await browser.newContext({ ...devices['iPhone 13'], colorScheme: scheme, permissions: ['camera'] })
  const page = await ctx.newPage()
  page.on('pageerror', e => errors.push(String(e)))
  // i 401 del test con PIN sbagliato sono attesi
  page.on('console', m => m.type() === 'error' && !/status of 401/.test(m.text()) && errors.push(m.text()))

  await page.goto(BASE)
  check(await page.getByText('Inserisci il PIN').isVisible(), `[${scheme}] schermata PIN mostrata senza token`)
  await page.screenshot({ path: OUT + `pin-${scheme}.png` })

  await page.getByLabel('PIN di accesso').fill('000000')
  await page.getByRole('button', { name: 'Entra' }).click()
  const wrong = await page.getByRole('alert').getByText('PIN errato').waitFor({ timeout: 5000 }).then(() => true, () => false)
  check(wrong, `[${scheme}] PIN errato rifiutato`)

  await page.getByLabel('PIN di accesso').fill(PIN)
  await page.getByRole('button', { name: 'Entra' }).click()
  await page.getByRole('heading', { name: 'Scan3D' }).waitFor()
  check(true, `[${scheme}] login con PIN corretto`)
  const token = await page.evaluate(() => JSON.parse(localStorage.getItem('scan3d.session') ?? '{}').token)
  const me = await page.evaluate(t => fetch('/api/me', { headers: { Authorization: `Bearer ${t}` } }).then(r => r.status), token)
  check(me === 200, `[${scheme}] chiamata API protetta con Bearer token -> ${me}`)
  await page.screenshot({ path: OUT + `home-${scheme}.png` })

  await page.getByRole('button', { name: 'Nuova scansione' }).click()
  await page.getByRole('button', { name: 'Avvia fotocamera' }).click()
  await page.getByRole('button', { name: 'Scatta' }).waitFor({ timeout: 10000 })
  await page.getByRole('button', { name: 'Scatta' }).click()
  await page.locator('.thumbs img').first().waitFor()
  check(await page.locator('.thumbs img').count() === 1, `[${scheme}] fotocamera finta avviata e frame catturato`)
  await page.screenshot({ path: OUT + `camera-${scheme}.png`, fullPage: true })

  // la nav in basso deve stare sopra la safe area e i bottoni devono essere grandi
  const navH = await page.locator('.bottom-nav').evaluate(e => e.getBoundingClientRect().height)
  check(navH >= 64, `[${scheme}] bottom nav alta ${Math.round(navH)} px`)
  await ctx.close()
}
await browser.close()
check(errors.length === 0, `nessun errore JS in console${errors.length ? ': ' + errors.join(' | ') : ''}`)
process.exit(failed ? 1 : 0)
