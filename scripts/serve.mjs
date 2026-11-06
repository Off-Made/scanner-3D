// npm run serve: compila la PWA e avvia il server che espone app + API su UNA sola porta (8000).
// Utile nel Codespace: basta rendere pubblica la porta 8000 per provare tutto dal telefono.
import { spawn, spawnSync } from 'node:child_process'
import { join } from 'node:path'
import { ROOT, PY, hasVenv, isWin } from './lib.mjs'

if (!hasVenv()) { console.error('Virtualenv mancante: esegui prima  npm run setup'); process.exit(1) }
const build = spawnSync('npm', ['run', 'build'], { cwd: join(ROOT, 'web'), stdio: 'inherit', shell: isWin })
if (build.status !== 0) process.exit(build.status ?? 1)

const host = process.env.HOST ?? '127.0.0.1'
const p = spawn(PY, ['-m', 'uvicorn', 'app.main:app', '--app-dir', join(ROOT, 'server'), '--host', host, '--port', process.env.PORT ?? '8000'],
  { stdio: 'inherit', env: { ...process.env, SERVE_WEB: join(ROOT, 'web', 'dist'), PYTHONUNBUFFERED: '1' } })
p.on('exit', code => process.exit(code ?? 0))
for (const s of ['SIGINT', 'SIGTERM']) process.on(s, () => (isWin ? spawn('taskkill', ['/pid', String(p.pid), '/T', '/F']) : p.kill(s)))
