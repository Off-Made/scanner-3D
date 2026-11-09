// Controllo pre-commit: blocca segreti, file pesanti e riferimenti personali/aziendali.
// Installato come .git/hooks/pre-commit da `node scripts/install-hooks.mjs`.
// Uso manuale:  node scripts/precommit-check.mjs          (file in stage)
//               node scripts/precommit-check.mjs --all    (tutti i file tracciati + non ignorati)
//
// Termini extra da bloccare (es. ID utente, domini interni) vanno in .git/info/precommit-denylist,
// uno per riga: quel file resta solo sul PC e non viene mai committato.
import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { ROOT } from './lib.mjs'

const MAX_BYTES = 5 * 1024 * 1024
const git = (...a) => execFileSync('git', a, { cwd: ROOT, encoding: 'utf8' })

const files = (process.argv.includes('--all')
  ? git('ls-files', '--cached', '--others', '--exclude-standard')
  : git('diff', '--cached', '--name-only', '--diff-filter=ACMR')
).split('\n').filter(Boolean)

const RULES = [
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----/, 'chiave privata'],
  [/\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b/, 'token GitHub'],
  [/\bhf_[A-Za-z0-9]{30,}\b/, 'token Hugging Face'],
  [/\b(?:vercel|vc)_[A-Za-z0-9]{20,}\b/i, 'token Vercel'],
  [/\bAKIA[0-9A-Z]{16}\b/, 'chiave AWS'],
  [/^[ \t]*(?:ACCESS_PIN|SESSION_SECRET|HF_TOKEN)[ \t]*=[ \t]*\S+/m, 'segreto valorizzato in un file env'],
  [/https?:\/\/[^\s/@:]+:[^\s/@]+@/, 'credenziali dentro un URL'],
  [/[A-Za-z]:\\{1,2}Users\\{1,2}[^\\\s"'`]+/i, 'percorso assoluto della cartella utente di Windows'],
  [/\/(?:c\/)?Users\/[A-Za-z0-9._-]+\/(?:Desktop|Documents|AppData)/i, 'percorso utente assoluto'],
]
// email consentite: noreply GitHub e indirizzi d'esempio
const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g
const EMAIL_OK = /@(users\.noreply\.github\.com|anthropic\.com|example\.(com|org)|localhost)$/i
const BINARY = /\.(png|jpe?g|gif|webp|ico|zip|7z|exe|dll|glb|stl|3mf|ply|woff2?)$/i

const denyFile = join(ROOT, '.git', 'info', 'precommit-denylist')
const deny = existsSync(denyFile)
  ? readFileSync(denyFile, 'utf8').split(/\r?\n/).map(s => s.trim()).filter(s => s && !s.startsWith('#'))
  : []

const problems = []
for (const f of files) {
  const p = join(ROOT, f)
  if (!existsSync(p)) continue
  const size = statSync(p).size
  if (size > MAX_BYTES) { problems.push(`${f}: file troppo grande (${(size / 1e6).toFixed(1)} MB > 5 MB)`); continue }
  if (f.split('/').some(seg => seg === '.env' || /^\.env\.(?!example$)/.test(seg))) problems.push(`${f}: file .env (segreti) non deve essere committato`)
  if (BINARY.test(f)) continue
  const text = readFileSync(p, 'utf8')
  for (const [re, label] of RULES) if (re.test(text)) problems.push(`${f}: ${label}`)
  // i lockfile contengono email pubbliche degli autori dei pacchetti: non sono nostre
  if (!/package-lock\.json$/.test(f)) for (const m of text.match(EMAIL) ?? []) if (!EMAIL_OK.test(m) && !/\.(png|svg|js|ts|tsx|css)$/i.test(m)) problems.push(`${f}: indirizzo email "${m}"`)
  const lower = text.toLowerCase() + '\n' + f.toLowerCase()
  for (const term of deny) if (lower.includes(term.toLowerCase())) problems.push(`${f}: contiene un termine della denylist locale`)
}

if (problems.length) {
  console.error(`\n✗ Pre-commit: ${problems.length} problema/i trovati. Commit bloccato.\n`)
  for (const p of [...new Set(problems)]) console.error('  - ' + p)
  console.error('\nCorreggi i file (o togli dallo stage con `git restore --staged <file>`) e riprova.\n')
  process.exit(1)
}
console.log(`✓ Pre-commit: ${files.length} file controllati, nessun problema.`)
