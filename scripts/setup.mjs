// npm run setup: installa tutto DENTRO la cartella del progetto (nessuna installazione di sistema).
import { spawnSync } from 'node:child_process'
import { join } from 'node:path'
import { ROOT, PY, CACHE, hasVenv, isWin } from './lib.mjs'

const env = { ...process.env, PIP_CACHE_DIR: join(CACHE, 'pip') }
function run(cmd, args, opts = {}) {
  console.log(`\n> ${cmd} ${args.join(' ')}`)
  const r = spawnSync(cmd, args, { stdio: 'inherit', cwd: ROOT, env, shell: isWin && cmd === 'npm', ...opts })
  if (r.status !== 0) { console.error(`\nComando fallito (${r.status}). Setup interrotto.`); process.exit(1) }
}

run('npm', ['install', '--cache', join(CACHE, 'npm')], { cwd: join(ROOT, 'web') })
if (!hasVenv()) run(isWin ? 'python' : 'python3', ['-m', 'venv', join(ROOT, 'server', '.venv')])
run(PY, ['-m', 'pip', 'install', '--upgrade', 'pip', '-q'])
run(PY, ['-m', 'pip', 'install', '-r', join(ROOT, 'server', 'requirements.txt')])
run(process.execPath, [join(ROOT, 'scripts', 'check-tools.mjs')])
console.log('\nSetup completato. Avvia con:  npm run dev')
