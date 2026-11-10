# Scan3D

PWA per telefono: **fotografi un oggetto da tutti i lati → il server ricostruisce un modello 3D →
lo controlli, lo porti alla misura reale e lo esporti in STL / 3MF / OBJ** per Cura, PrusaSlicer,
Bambu Studio e OrcaSlicer.

- Interfaccia mobile-first in scala di grigi, tema chiaro/scuro, installabile sulla schermata Home.
- Due motori intercambiabili: **Precisa (foto)** — fotogrammetria COLMAP + OpenMVS — e **Rapida (AI)** —
  modello immagine→3D su un Hugging Face Space.
- Archivio delle scansioni nel telefono (funziona anche offline).

> Lo stato dettagliato del lavoro è in [PROGRESS.md](PROGRESS.md).

---

## Indice
1. [Come funziona (in breve)](#come-funziona-in-breve)
2. [Avvio in locale](#avvio-in-locale)
3. [Guida passo passo: GitHub → Codespace → Vercel](#guida-passo-passo-github--codespace--vercel)
4. [Collaudo dal telefono](#collaudo-dal-telefono)
5. [Configurazione (variabili d'ambiente)](#configurazione-variabili-dambiente)
6. [Test automatici](#test-automatici)
7. [Benchmark e tempi misurati](#benchmark-e-tempi-misurati)
8. [Limiti onesti](#limiti-onesti)
9. [Struttura del progetto](#struttura-del-progetto)

---

## Come funziona (in breve)

```
 Telefono (PWA)                                   Server (FastAPI)
 ┌───────────────────────────┐   foto (HTTPS)    ┌──────────────────────────────────────┐
 │ scansione guidata         │ ────────────────▶ │ coda job (uno alla volta)            │
 │ anello di copertura       │   Bearer token    │  ├ Precisa: COLMAP → OpenMVS → pulizia│
 │ import dalla galleria     │                   │  └ Rapida: Hugging Face Space → pulizia│
 │                           │ ◀──────────────── │ mesh chiusa (watertight), Z-up, mm   │
 │ viewer 3D, misura in mm   │   modello .glb    └──────────────────────────────────────┘
 │ export STL / 3MF / OBJ    │
 │ archivio (IndexedDB)      │
 └───────────────────────────┘
```

- Il telefono fa solo ciò che sa fare bene: **foto di qualità** (nitidezza, luce, copertura degli angoli) e
  **visualizzazione/export**. Il calcolo pesante è sul server.
- Appena il modello è pronto, il telefono lo scarica nell'archivio e il server lo cancella.
- L'export avviene **nel telefono**: funziona anche senza rete.

---

## Avvio in locale

Requisiti: Node.js 20+ (testato con 24), Python 3.12, Git. Nessun Docker, nessun permesso di amministratore:
tutto si installa **dentro la cartella del progetto** (`web/node_modules`, `server/.venv`, `.cache/`, `tools/`).

```bash
npm run setup     # dipendenze web + virtualenv Python + controllo strumenti
npm run dev       # sviluppo: backend http://127.0.0.1:8000 + frontend http://127.0.0.1:5173
npm run serve     # "come in produzione": app + API su UNA sola porta (http://127.0.0.1:8000)
```

Il **PIN** viene stampato nel terminale all'avvio (oppure impostalo in `.env`, partendo da `.env.example`).
Il PIN serve solo per parlare con il server (scansione/elaborazione); archivio ed export funzionano senza.

### Strumenti di fotogrammetria (Windows)

Non sono nel repository (sono binari pesanti). Scaricali dalle release ufficiali ed estraili così:

| Strumento | Release | Percorso atteso |
|---|---|---|
| COLMAP 4.2.1 (no CUDA) | github.com/colmap/colmap/releases → `colmap-x64-windows-nocuda.zip` | `tools/colmap/bin/colmap.exe` |
| OpenMVS 2.4.0 | github.com/cdcseacave/openMVS/releases → `OpenMVS_Windows_x64.zip` | `tools/openmvs/vc17/x64/Release/*.exe` |

`npm run doctor` verifica che ci siano (e che i pacchetti Python si importino). Su Linux (Codespace) li installa `scripts/setup-linux-tools.sh`.

> Senza strumenti l'app funziona comunque: il motore "Precisa" appare disattivato con il motivo.

---

## Guida passo passo: GitHub → Codespace → Vercel

L'ordine conta: **prima GitHub, poi il backend (Codespace), poi il frontend (Vercel)**, perché Vercel deve
sapere l'indirizzo del backend.

> ⚠️ **Prima di tutto**: verifica che la policy della tua azienda consenta di caricare codice su un account
> GitHub personale da questo PC. Il progetto non contiene nulla di aziendale (l'hook pre-commit lo controlla).

### Passo 1 — Crea la repository su GitHub

1. Vai su github.com → **New repository**.
2. Nome: `scan3d-pwa` · Visibilità: **Private** · **non** aggiungere README, .gitignore o licenza.
3. Crea un **token a scadenza breve** (così non resta nessuna credenziale permanente sul PC):
   Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token
   - Expiration: **1 giorno** · Repository access: **Only select repositories** → `scan3d-pwa`
   - Permissions → Repository → **Contents: Read and write**
4. Dal **tuo terminale** (non incollare il token in chat né in file):
   ```powershell
   cd <cartella del progetto>
   git -c credential.helper= push -u origin main
   ```
   Username: il tuo utente GitHub · Password: **incolla il token**. `-c credential.helper=` evita che
   Windows salvi la credenziale.
5. **Pulizia**: su GitHub elimina il token; poi in PowerShell
   `cmdkey /list | findstr /i github` e, se compare qualcosa, `cmdkey /delete:git:https://github.com`.

### Passo 2 — Backend nel Codespace (per i test)

1. **Una volta sola, prima di creare il Codespace:** su github.com/settings/codespaces → **Secrets** →
   *New secret*, con accesso alla repo `scan3d-pwa`, crea:

   | Secret | Valore |
   |---|---|
   | `ACCESS_PIN` | il tuo PIN (6+ cifre) |
   | `SESSION_SECRET` | una stringa casuale lunga (es. output di `openssl rand -hex 32`) |
   | `CORS_ORIGINS` | `https://scan3d-pwa.vercel.app` (il tuo indirizzo Vercel) |
   | `CORS_ORIGIN_REGEX` | `https://scan3d-pwa-.*\.vercel\.app` (facoltativo, anteprime Vercel) |
   | `HF_TOKEN` | facoltativo, token Hugging Face per la modalità Rapida |

   I secrets sopravvivono ai rebuild (il file `.env` invece va perso se il Codespace viene ricreato).
   Se il Codespace esiste già, dopo aver aggiunto i secrets va **riavviato** (Stop → Start) per leggerli.
2. Sulla pagina della repo: **Code → Codespaces → Create codespace on main**.
   Il primo avvio dura ~10–15 minuti: installa COLMAP, OpenMVS e le dipendenze (`.devcontainer/`).
3. **Avvio automatico** (`scripts/codespace-start.sh`, ad ogni accensione): ripara gli strumenti se mancano,
   avvia app + API sulla porta 8000 e la rende **pubblica**. Non serve più `npm run serve`.
   - Stato: `tail .cache/codespace-start.log` · log del server: `tail -f .cache/serve.log`
   - Diagnosi: `npm run doctor` · riavvio (es. dopo aver cambiato un secret o `.env`):
     `bash scripts/codespace-start.sh --restart`
   - Senza `ACCESS_PIN`/`SESSION_SECRET` il server **non parte**, perché la porta è pubblica.
4. L'indirizzo è `https://<nome-codespace>-8000.app.github.dev` (lo trovi nel log o nella scheda **Ports**) e
   **resta lo stesso** finché non elimini il Codespace: lo imposti su Vercel una volta sola.
5. **Prova subito dal telefono** aprendo quell'indirizzo in Safari: è già l'app completa.
6. Uso quotidiano: apri github.com/codespaces (anche dal telefono) → **⋯ → Open** sul Codespace
   (o "Start"), aspetta 2–3 minuti e usa l'app. In github.com/settings/codespaces puoi alzare l'**idle
   timeout** fino a 240 minuti e la **conservazione** fino a 30 giorni (oltre, un Codespace inutilizzato
   viene cancellato e l'indirizzo cambia).

Cosa **non** fa bene un Codespace gratuito (onestamente):
- quota personale ~120 core-ore/mese e 15 GB; la macchina base ha 2 core / 8 GB → la fotogrammetria
  è circa **2–4 volte più lenta** che sul PC di sviluppo e consuma quota;
- va in sospensione dopo l'inattività e i job in corso si perdono;
- l'indirizzo cambia se ricrei il Codespace. Va bene per **collaudare**, non per un uso continuativo.

### Passo 3 — Frontend su Vercel

1. vercel.com → **Add New… → Project** → importa `scan3d-pwa` da GitHub.
2. **Root Directory: `web`** (importante). Framework: Vite (rilevato da `web/vercel.json`).
3. **Environment Variables** → `VITE_API_URL` = indirizzo del backend del Passo 2
   (es. `https://<nome>-8000.app.github.dev`, senza `/` finale).
4. **Deploy**. Otterrai un indirizzo tipo `https://scan3d-pwa.vercel.app`.
5. Controlla che i secrets `CORS_ORIGINS` (e `CORS_ORIGIN_REGEX`) del Passo 2 contengano questo indirizzo,
   poi `bash scripts/codespace-start.sh --restart`. (Senza questo il browser blocca le chiamate dal dominio Vercel.)
   Se il Codespace è spento, l'app lo dice e mostra il pulsante **Accendi il server** (va su
   github.com/codespaces; per un'altra pagina imposta `VITE_BACKEND_START_URL` su Vercel).
6. Se l'indirizzo del backend cambia, aggiorna `VITE_API_URL` su Vercel e fai **Redeploy**.

### Passo 4 (facoltativo) — Backend stabile su Hugging Face Space

⚠️ Da novembre 2026 gli Space **Docker** richiedono l'abbonamento **PRO** di Hugging Face (gratis restano solo
gli Space statici). Questa strada quindi è a pagamento; la gratuita è il Codespace con avvio automatico.

Per un indirizzo fisso e sempre disponibile (hardware CPU basic: 2 vCPU / 16 GB):

1. `npm run hf-space` → crea la cartella `dist-hf-space/` (Dockerfile + server).
2. huggingface.co → **New Space** → SDK **Docker** → hardware **CPU basic** → visibilità **Public**
   (uno Space privato richiede il login HF e il telefono non potrebbe chiamarlo; la protezione è il PIN).
3. Carica il contenuto di `dist-hf-space/` (Files → Upload files) e imposta i segreti indicati nel suo README
   (`ACCESS_PIN`, `SESSION_SECRET`, `CORS_ORIGINS`).
4. Il build avviene sui server di Hugging Face (nessun Docker sul tuo PC). Indirizzo:
   `https://<utente>-<space>.hf.space` → mettilo in `VITE_API_URL` su Vercel e fai Redeploy.

⚠️ Non verificato da qui: il Dockerfile non è mai stato costruito (niente Docker sul PC di sviluppo).
Con 2 vCPU una scansione da 40 foto richiederà presumibilmente **20–40 minuti**.

---

## Collaudo dal telefono

Apri l'indirizzo HTTPS (Codespace o Vercel) e segui la tabella. Segna ✓ o annota cosa succede.

| # | Controllo | iPhone 13 | iPhone SE 2022 |
|---|---|---|---|
| 1 | La Home si apre, testo leggibile, nessun elemento sotto il notch / la barra in basso | | |
| 2 | Safari → Condividi → **Aggiungi alla schermata Home** → l'app si apre a tutto schermo con l'icona | | |
| 3 | Tema scuro: cambia con l'icona luna/sole e segue il tema di sistema | | |
| 4 | Nuova scansione → PIN errato rifiutato, PIN giusto accettato | | |
| 5 | **Inizia scansione** → Safari chiede fotocamera e sensori di movimento → consenti | | |
| 6 | Il mirino mostra la fotocamera posteriore; otturatore raggiungibile col pollice senza scorrere | | |
| 7 | Girando attorno all'oggetto l'anello si riempie e scatta da solo; suggerimenti "più luce" / "fermo un attimo" | | |
| 8 | Permesso fotocamera negato (Impostazioni → Safari → Fotocamera → Nega): messaggio chiaro con istruzioni | | |
| 9 | **Galleria**: importa 30–40 foto dal Rullino (anche HEIC) | | |
| 10 | Elabora → barra di avanzamento; chiudi e riapri l'app: la scansione continua e la ritrovi in Archivio | | |
| 11 | Viewer: ruota (1 dito), zoom (pizzico), sposta (2 dita) fluidi | | |
| 12 | Misure → imposta l'altezza reale in mm → le altre dimensioni si aggiornano in proporzione | | |
| 13 | Posizione → ruota di 90° e "Appoggia sulla base più ampia" | | |
| 14 | Controllo → mesh chiusa, normali, piatto di stampa | | |
| 15 | Esporta → **Condividi** STL → AirDrop o "Salva su File" | | |
| 16 | Il file STL/3MF si apre in uno slicer (PrusaSlicer, Bambu Studio, Cura, OrcaSlicer) con le misure giuste | | |
| 17 | Archivio: miniatura, rinomina, riesporta, elimina | | |
| 18 | Modalità aereo: l'app installata si apre, l'archivio e i modelli si vedono, l'export funziona | | |
| 19 | Rapida (AI): da 1+ foto produce un modello in pochi minuti (dipende dalla quota HF) | | |

### Android / Samsung — da verificare (non avevo un dispositivo)

Il codice gestisce Chrome e Samsung Internet, ma **non è stato provato su un telefono vero**:
- permessi fotocamera in **Samsung Internet** e messaggi di errore specifici;
- orientamento con `deviceorientationabsolute` (anello di copertura);
- prompt di installazione della PWA (menu ⋮ → Installa app);
- condivisione file con `navigator.share` (foglio di condivisione Android);
- vibrazione allo scatto (solo Android);
- prestazioni del viewer su un telefono di fascia media.

---

## Configurazione (variabili d'ambiente)

Tutte in `.env` (vedi `.env.example`). Non committare mai `.env`.

| Variabile | Default | A cosa serve |
|---|---|---|
| `ACCESS_PIN` | generato all'avvio | PIN di accesso al server |
| `SESSION_SECRET` | generato all'avvio | firma dei token (se cambia, serve rifare il login) |
| `TOKEN_TTL_HOURS` | 12 | durata del login |
| `CORS_ORIGINS` | vuoto | domini autorizzati (es. il dominio Vercel), separati da virgola |
| `CORS_ORIGIN_REGEX` | vuoto | regex per le anteprime Vercel |
| `TRUSTED_PROXIES` | (loopback sempre) | proxy fidati da cui leggere l'IP reale (IP/CIDR) |
| `TRUSTED_IP_HEADERS` | `CF-Connecting-IP,X-Forwarded-For` | header con l'IP reale del client |
| `DATA_DIR` | `server/data` | cartella dei job |
| `JOB_TTL_HOURS` | 48 | dopo quanto i job non scaricati vengono cancellati |
| `PHOTO_FEATURE_THREADS` | 4 | thread di estrazione feature (più thread = più RAM) |
| `PHOTO_MATCH_THREADS` | 4 | thread del confronto tra foto |
| `PHOTO_RESOLUTION_LEVEL` | 1 | OpenMVS: 0 = piena risoluzione, 1 = metà (più veloce) |
| `COLMAP_BIN`, `OPENMVS_DIR` | auto | percorsi degli strumenti |
| `HF_SPACE` | `tencent/Hunyuan3D-2` | Space AI immagine→3D |
| `HF_API_NAME` | `/shape_generation` | endpoint dello Space |
| `HF_TOKEN` | vuoto | token HF facoltativo (quote migliori) |
| `VITE_API_URL` | vuoto | **solo Vercel**: indirizzo del backend |
| `SCAN3D_ENABLE_MOCK` | vuoto | `1` = motore "Demo" per test/sviluppo |

### Sicurezza dell'accesso
- PIN → token firmato (HMAC-SHA256) in `Authorization: Bearer`. **Niente cookie**: Safari blocca i cookie tra
  domini diversi (Vercel ↔ backend), il token nell'header funziona ovunque.
- Max 5 tentativi di PIN al minuto per IP. L'IP reale si legge dagli header **solo** se la richiesta arriva
  da un proxy fidato (altrimenti chiunque potrebbe falsificarli).
- CORS: solo le origini configurate. Foto: max 40 per scansione, max 25 MB l'una, convertite a 1600 px.

---

## Test automatici

```bash
npm test                     # vitest (web) + pytest (server)
npm run serve                # in un altro terminale, con SCAN3D_ENABLE_MOCK=1 e ACCESS_PIN impostati
cd web
PIN=<pin> BASE_URL=http://127.0.0.1:8000 npm run smoke                       # iPhone 13, iPhone SE, Galaxy S9+
PIN=<pin> BASE_URL=http://127.0.0.1:8000 PROVIDER=mock IMAGES=<cartella foto> npm run e2e
PIN=<pin> BASE_URL=http://127.0.0.1:8000 PROVIDER=photo IMAGES=<cartella foto> npm run e2e   # ricostruzione vera
server/.venv/Scripts/python scripts/verify_exports.py web/e2e/out             # verifica STL/3MF/OBJ con trimesh
```

I test e2e usano il **Chrome già installato** (nessun browser scaricato) con emulazione del telefono e
fotocamera finta.

---

## Benchmark e tempi misurati

PC di sviluppo: Intel i5-1245U (10 core / 12 thread), 7,6 GB RAM, GPU integrata (niente CUDA).

**Fotogrammetria, 30 foto a 1600 px** (dataset pubblico AliceVision *monstree*):

| Thread feature | Totale | Memoria allocata (picco) | Foto registrate |
|---|---|---|---|
| 12 (default COLMAP) | 10,0 min | 8,3 GB (paging!) | 26/30 |
| **4** (adottato) | **8,1 min** | **2,8 GB** | 26/30 |

**Prove su dataset 360°** (Middlebury, foto 640×480):

| Dataset | Foto | Esito |
|---|---|---|
| templeRing (tempio in gesso) | 47 | 47/47 registrate, 3,1 min, modello riconoscibile e chiuso |
| dinoRing (dinosauro scuro, liscio) | 30 | **fallisce**: solo 3/30 registrate (troppo poca texture) |
| monstree (rilievo su tronco, solo fronte) | 30 | superficie aperta (non c'è il retro) → guscio sottile |

Il collaudo e2e completo (app → server → modello → export) è riportato in [PROGRESS.md](PROGRESS.md).

---

## Limiti onesti

- **Fotogrammetria**: funziona su oggetti **opachi e con dettagli**; fallisce o dà risultati poveri su vetro,
  metallo lucido, superfici lisce e uniformi (come il dinosauro del test), oggetti sottili (fili, foglie).
- **Scala**: la fotografia non conosce le misure. Il modello arriva con il lato lungo a 100 mm ("scala
  indicativa") finché non inserisci una misura reale presa col righello. Precisione attesa: qualche mm.
- **Dettagli**: per garantire una mesh chiusa e stampabile il modello viene "solidificato" (voxel ~0,5% del
  lato lungo): fessure e dettagli molto fini si riempiono o si arrotondano. La base è sempre piatta.
- **AI (Rapida)**: forma plausibile ma **inventata** (soprattutto il retro), quote gratuite limitate, lo Space
  può cambiare API o sparire. Configurabile con `HF_SPACE` / `HF_API_NAME`.
- **Tempi**: ~8–12 min per 40 foto sul PC di sviluppo; su server gratuiti a 2 core molto di più.
- **Upload**: va tenuta aperta l'app finché le foto non sono state inviate; dopo, la ricostruzione continua sul
  server anche ad app chiusa.
- **Invio diretto alla stampante** (OctoPrint/Moonraker): non incluso. Richiederebbe uno slicer lato server
  perché le stampanti vogliono G-code. Idee future: import da Scaniverse, slicing con PrusaSlicer CLI.

---

## Struttura del progetto

```
web/                 PWA (Vite + React + TypeScript)
  src/scan/          fotocamera, copertura, qualità, import, invio
  src/three/         viewer, geometria (misure, rotazioni, appoggio), export STL/3MF/OBJ
  src/screens/       Home, Scansione, Elaborazione, Modello, Esporta, Archivio
  src/db/            archivio IndexedDB (Dexie)
  e2e/               test Playwright (smoke, flusso completo)
  vercel.json        configurazione Vercel
server/              API (FastAPI)
  app/providers/     photogrammetry (COLMAP+OpenMVS), ai_hf (Hugging Face), mock
  app/mesh/          pulizia e chiusura della mesh, report di stampabilità
  app/jobs.py        coda dei job
  tests/             pytest
bench/               benchmark della fotogrammetria
deploy/hf-space/     Dockerfile + README per un Hugging Face Space
.devcontainer/       configurazione del Codespace
scripts/             setup, dev, serve, hook pre-commit, strumenti Linux, verifica export
```
