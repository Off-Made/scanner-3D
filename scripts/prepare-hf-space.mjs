// npm run hf-space: prepara la cartella dist-hf-space/ da caricare su un Hugging Face Space.
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { ROOT } from './lib.mjs'

const out = join(ROOT, 'dist-hf-space')
rmSync(out, { recursive: true, force: true })
mkdirSync(join(out, 'server'), { recursive: true })
cpSync(join(ROOT, 'deploy', 'hf-space', 'Dockerfile'), join(out, 'Dockerfile'))
cpSync(join(ROOT, 'deploy', 'hf-space', 'README.md'), join(out, 'README.md'))
cpSync(join(ROOT, 'server', 'app'), join(out, 'server', 'app'), { recursive: true, filter: p => !p.includes('__pycache__') })
// in produzione non servono gli strumenti di test
const req = readFileSync(join(ROOT, 'server', 'requirements.txt'), 'utf8').split('\n').filter(l => !/^(pytest|httpx)\b/.test(l))
writeFileSync(join(out, 'requirements.txt'), req.join('\n'))
console.log('Cartella pronta:', out, '\nCaricala nel tuo Space (vedi README, sezione "Backend su Hugging Face").')
