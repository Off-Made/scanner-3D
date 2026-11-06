// npm run dev: avvia backend (FastAPI, porta 8000) e frontend (Vite, porta 5173), solo su 127.0.0.1.
import { spawn } from 'node:child_process'
import { join } from 'node:path'
import { ROOT, PY, hasVenv, isWin } from './lib.mjs'

if (!hasVenv()) { console.error('Virtualenv mancante: esegui prima  npm run setup'); process.exit(1) }

const procs = [
  ['api', PY, ['-m', 'uvicorn', 'app.main:app', '--app-dir', join(ROOT, 'server'), '--host', '127.0.0.1', '--port', '8000', '--reload', '--reload-dir', join(ROOT, 'server', 'app')]],
  ['web', 'npm', ['run', 'dev'], join(ROOT, 'web')],
].map(([tag, cmd, args, cwd]) => {
  const p = spawn(cmd, args, { cwd: cwd ?? ROOT, shell: isWin && cmd === 'npm', env: { ...process.env, PYTHONUNBUFFERED: '1' } })
  const out = d => d.toString().split(/\r?\n/).filter(Boolean).forEach(l => console.log(`[${tag}] ${l}`))
  p.stdout.on('data', out); p.stderr.on('data', out)
  p.on('exit', code => { console.log(`[${tag}] terminato (${code})`); shutdown() })
  return p
})

let stopping = false
function shutdown() {
  if (stopping) return
  stopping = true
  for (const p of procs) if (p.exitCode === null) isWin ? spawn('taskkill', ['/pid', String(p.pid), '/T', '/F']) : p.kill('SIGTERM')
  setTimeout(() => process.exit(0), 500)
}
process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)
