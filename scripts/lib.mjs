// Utility comuni agli script: percorsi del progetto e del Python del virtualenv.
import { existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

export const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
export const isWin = process.platform === 'win32'
export const VENV = join(ROOT, 'server', '.venv')
export const PY = isWin ? join(VENV, 'Scripts', 'python.exe') : join(VENV, 'bin', 'python')
export const CACHE = join(ROOT, '.cache')
export const hasVenv = () => existsSync(PY)
