// Installa l'hook pre-commit in .git/hooks (resta dentro il progetto).
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { ROOT } from './lib.mjs'

const dir = join(ROOT, '.git', 'hooks')
mkdirSync(dir, { recursive: true })
writeFileSync(join(dir, 'pre-commit'), '#!/bin/sh\nexec node scripts/precommit-check.mjs\n', { mode: 0o755 })
console.log('Hook pre-commit installato.')
