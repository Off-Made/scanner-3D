// Collaudo end-to-end con emulazione iPhone 13 (Chrome installato sul PC, fotocamera finta).
// Uso: BASE_URL=http://127.0.0.1:8000 PIN=... PROVIDER=mock IMAGES=<cartella> [N=30] node e2e/flow.mjs
// Salva i file esportati in e2e/out/ (verificati poi con trimesh).
import { chromium, devices } from 'playwright-core'
import { mkdirSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:8000'
const PIN = process.env.PIN
const PROVIDER = process.env.PROVIDER ?? 'mock'
const IMAGES = process.env.IMAGES
const N = Number(process.env.N ?? 30)
const TIMEOUT_MIN = Number(process.env.TIMEOUT_MIN ?? 30)
const OUT = fileURLToPath(new URL('./out/', import.meta.url))
const SHOTS = fileURLToPath(new URL('./screens/', import.meta.url))
mkdirSync(OUT, { recursive: true }); mkdirSync(SHOTS, { recursive: true })

let failed = false
const check = (ok, msg) => { console.log(`${ok ? '✓' : '✗'} ${msg}`); if (!ok) failed = true }
const label = { mock: 'Demo (test)', photo: 'Precisa (foto)', ai: '✦ Rapida (AI)' }[PROVIDER]

const browser = await chromium.launch({ channel: 'chrome', args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] })
const ctx = await browser.newContext({ ...devices['iPhone 13'], permissions: ['camera'], acceptDownloads: true })
const page = await ctx.newPage()
const errors = []
page.on('pageerror', e => errors.push(String(e)))
page.on('console', m => m.type() === 'error' && !/status of 40[19]/.test(m.text()) && errors.push(m.text()))
const shot = name => page.screenshot({ path: join(SHOTS, `${name}.png`) })

// --- 1. avvio, archivio vuoto, PIN richiesto solo per scansionare ---------------------------
await page.goto(BASE)
await page.getByRole('heading', { name: 'Scan3D' }).waitFor()
check(true, 'Home caricata senza PIN (archivio locale)')
await page.getByRole('button', { name: 'Nuova scansione' }).click()
await page.getByLabel('PIN di accesso').fill(PIN)
await page.getByRole('button', { name: 'Entra' }).click()
await page.getByRole('heading', { name: 'Nuova scansione' }).waitFor()
check(true, 'PIN accettato, schermata di scansione')

// --- 2. scatto automatico con la fotocamera finta --------------------------------------------
await page.getByRole('button', { name: 'Inizia scansione' }).click()
await page.locator('.hint').waitFor({ timeout: 10000 })
await page.waitForFunction(() => document.querySelectorAll('.thumbs img').length >= 2, null, { timeout: 15000 }).catch(() => {})
const autoShots = await page.locator('.thumbs img').count()
check(autoShots >= 2, `scatto automatico (senza giroscopio, ogni 1,5 s): ${autoShots} foto`)
await shot('scan-camera')
// tolgo gli scatti della fotocamera finta: per la ricostruzione uso le foto vere
while (await page.locator('.thumbs img').count() > 0) await page.getByLabel("Elimina l'ultima foto").click()

// --- 3. motore + import dalla galleria --------------------------------------------------------
await page.getByRole('radio', { name: label }).click()
const files = readdirSync(IMAGES).filter(f => /\.(jpe?g|png)$/i.test(f)).sort().map(f => join(IMAGES, f))
await page.getByTestId('file-input').setInputFiles(files.slice(0, Math.min(files.length, 60)))
await page.waitForFunction(() => !document.body.innerText.includes('Preparazione foto'), null, { timeout: 120000 })
const count = await page.locator('.count').textContent().catch(() => null)
const btn = page.getByRole('button', { name: /Elabora \d+ foto/ })
await btn.waitFor({ timeout: 10000 })
const nImported = Number((await btn.textContent()).match(/\d+/)[0])
check(nImported === Math.min(files.length, 40), `import galleria: ${files.length} scelte -> ${nImported} tenute (max 40)`)
await shot('scan-imported')

// --- 4. elaborazione con avanzamento ---------------------------------------------------------
const t0 = Date.now()
await btn.click()
await page.getByText(/Invio delle foto|Ricostruzione 3D/).first().waitFor({ timeout: 30000 })
let lastStep = ''
const seen = new Set()
while (!(await page.getByTestId('viewer').isVisible().catch(() => false))) {
  if (Date.now() - t0 > TIMEOUT_MIN * 60000) { check(false, 'timeout elaborazione'); break }
  const err = await page.getByText('Elaborazione non riuscita').isVisible().catch(() => false)
  if (err) { check(false, 'elaborazione fallita: ' + await page.locator('.big-progress p').textContent()); await shot('error'); break }
  const step = await page.locator('.big-progress .row span:last-child').textContent({ timeout: 500 }).catch(() => '')
  if (step && step !== lastStep) { seen.add(step); lastStep = step; console.log(`   · ${step} (${Math.round((Date.now() - t0) / 1000)} s)`) }
  if (seen.size === 3) await shot('processing')
  await page.waitForTimeout(1500)
}
const secs = Math.round((Date.now() - t0) / 1000)
check(await page.getByTestId('viewer').isVisible(), `modello pronto e mostrato nel viewer in ${secs} s`)
await page.waitForTimeout(1500)
await shot('model')

// --- 5. modifica: misura reale, rotazione, appoggio, controllo ---------------------------------
await page.getByRole('button', { name: 'Altezza' }).click()
await page.getByLabel('Misura in millimetri').fill('80')
await page.getByRole('button', { name: 'Applica misura' }).click()
await page.waitForFunction(() => [...document.querySelectorAll('.dim')].some(d => d.textContent.includes('Altezza') && d.textContent.includes('80')), null, { timeout: 5000 })
  .then(() => check(true, 'altezza impostata a 80 mm'), () => check(false, 'altezza non aggiornata'))
check(!(await page.getByText('Scala indicativa').isVisible()), 'avviso "scala indicativa" sparito dopo la misura reale')
await page.getByRole('radio', { name: 'Posizione' }).click()
await page.getByRole('button', { name: 'X 90°' }).click()
await page.getByRole('button', { name: 'Appoggia sulla base più ampia' }).click()
await page.getByRole('radio', { name: 'Controllo' }).click()
check(await page.getByText('Mesh chiusa (watertight)').isVisible(), 'report di stampabilità visibile')
await shot('check')

// --- 6. export dei tre formati ---------------------------------------------------------------
await page.getByRole('button', { name: 'Esporta per la stampa' }).click()
await page.getByLabel('Nome del file').fill('Collaudo e2e')
for (const f of ['stl', '3mf', 'obj']) {
  const [dl] = await Promise.all([page.waitForEvent('download'), page.getByTestId(`download-${f}`).click()])
  await dl.saveAs(join(OUT, dl.suggestedFilename()))
  check(dl.suggestedFilename() === `collaudo-e2e.${f}`, `export ${f.toUpperCase()} scaricato: ${dl.suggestedFilename()}`)
}
await shot('export')

// --- 7. archivio: miniatura, rinomina, offline, elimina ----------------------------------------
await page.getByRole('button', { name: 'Archivio' }).click()
await page.getByTestId('scan-item').first().waitFor()
check(await page.locator('.scan-item img.thumb').count() >= 1, 'miniatura generata nell’archivio')
await page.getByRole('button', { name: /Azioni per/ }).first().click()
await page.getByRole('button', { name: 'Rinomina' }).click()
await page.getByLabel('Nuovo nome').fill('Rinominata')
await page.getByRole('button', { name: 'Salva' }).click()
await page.getByText('Rinominata').waitFor({ timeout: 5000 }).then(() => check(true, 'rinomina'), () => check(false, 'rinomina'))
await shot('archive')

// offline: guscio della PWA dal service worker + dati da IndexedDB
const swReady = await page.evaluate(async () => !!(await navigator.serviceWorker?.ready.then(r => r.active).catch(() => null)))
await ctx.setOffline(true)
await page.reload()
await page.getByText('Rinominata').waitFor({ timeout: 10000 }).then(() => check(true, `offline: app e archivio disponibili (service worker attivo: ${swReady})`), () => check(false, 'offline: archivio non disponibile'))
await page.getByText('Rinominata').click()
await page.getByTestId('viewer').waitFor({ timeout: 15000 }).then(() => check(true, 'offline: modello apribile nel viewer'), () => check(false, 'offline: viewer non disponibile'))
await ctx.setOffline(false)
await page.getByRole('button', { name: 'Archivio' }).click()
await page.getByRole('button', { name: /Azioni per/ }).first().click()
await page.getByRole('button', { name: 'Elimina' }).click()
await page.getByRole('dialog').getByRole('button', { name: 'Elimina' }).click()
await page.getByText('Nessuna scansione salvata').waitFor().then(() => check(true, 'eliminazione'), () => check(false, 'eliminazione'))

await browser.close()
check(errors.length === 0, `nessun errore JS${errors.length ? ': ' + errors.slice(0, 3).join(' | ') : ''}`)
console.log(`TEMPO_ELABORAZIONE_S=${secs}`)
process.exit(failed ? 1 : 0)
