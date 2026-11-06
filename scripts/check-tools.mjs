// Verifica la presenza dei binari di fotogrammetria in tools/ (non li scarica: vedi README).
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { ROOT, isWin } from './lib.mjs'

const tools = isWin
  ? { 'COLMAP': 'tools/colmap/bin/colmap.exe', 'OpenMVS': 'tools/openmvs/vc17/x64/Release/DensifyPointCloud.exe' }
  : { 'COLMAP': 'tools/colmap/bin/colmap', 'OpenMVS': 'tools/openmvs/bin/DensifyPointCloud' }
let ok = true
for (const [name, rel] of Object.entries(tools)) {
  const found = existsSync(join(ROOT, rel))
  ok &&= found
  console.log(`${found ? '✓' : '✗'} ${name.padEnd(8)} ${rel}`)
}
if (!ok) console.log('\nAlcuni strumenti mancano: la fotogrammetria non funzionerà finché non li scarichi (vedi README, sezione "Strumenti").')
