// npm run doctor (alias: check:tools): controlla pacchetti Python, COLMAP, OpenMVS e motori dell'app.
import { spawnSync } from 'node:child_process'
import { join } from 'node:path'
import { ROOT, PY, hasVenv } from './lib.mjs'

if (!hasVenv()) { console.error('Virtualenv mancante: esegui prima  npm run setup'); process.exit(1) }
process.exit(spawnSync(PY, [join(ROOT, 'scripts', 'doctor.py')], { stdio: 'inherit', cwd: ROOT }).status ?? 1)
