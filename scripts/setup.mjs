// npm run setup: installa tutto DENTRO la cartella del progetto (nessuna installazione di sistema).
import { spawnSync } from 'node:child_process'
import { existsSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { ROOT, PY, VENV, CACHE, hasVenv, isWin } from './lib.mjs'

const env = { ...process.env, PIP_CACHE_DIR: join(CACHE, 'pip') }
function run(cmd, args, opts = {}) {
  console.log(`\n> ${cmd} ${args.join(' ')}`)
  const r = spawnSync(cmd, args, { stdio: 'inherit', cwd: ROOT, env, shell: isWin && cmd === 'npm', ...opts })
  if (r.status !== 0) { console.error(`\nComando fallito (${r.status}). Setup interrotto.`); process.exit(1) }
}

run('npm', ['install', '--cache', join(CACHE, 'npm')], { cwd: join(ROOT, 'web') })
// Un virtualenv punta al Python con cui è stato creato. Dopo un rebuild del Codespace quel Python può
// cambiare percorso o versione: il .venv resta "a metà" (collegamenti morti) e va ricreato da zero.
const venvWorks = () => hasVenv() && spawnSync(PY, ['-c', 'import pip'], { stdio: 'ignore' }).status === 0
if (!venvWorks()) {
  if (existsSync(VENV)) { console.log('\nVirtualenv rotto o di un altro Python: lo ricreo da zero.'); rmSync(VENV, { recursive: true, force: true }) }
  run(isWin ? 'python' : 'python3', ['-m', 'venv', VENV])
}
run(PY, ['-m', 'pip', 'install', '--upgrade', 'pip', '-q'])
run(PY, ['-m', 'pip', 'install', '-r', join(ROOT, 'server', 'requirements.txt')])
// diagnostica informativa: se manca qualcosa lo dice, ma il setup resta riuscito
spawnSync(process.execPath, [join(ROOT, 'scripts', 'check-tools.mjs')], { stdio: 'inherit', cwd: ROOT, env })
console.log('\nSetup completato. Avvia con:  npm run dev')
