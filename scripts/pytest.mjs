import { spawnSync } from 'node:child_process'
import { join } from 'node:path'
import { ROOT, PY } from './lib.mjs'
process.exit(spawnSync(PY, ['-m', 'pytest'], { stdio: 'inherit', cwd: join(ROOT, 'server') }).status ?? 1)
