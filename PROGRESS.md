# PROGRESS — Scan3D

Stato di avanzamento, decisioni e come riprendere il lavoro.

## Come riprendere
1. Leggi questo file e `README.md`.
2. `npm run setup` (se è un PC nuovo), poi `npm test`.
3. Riparti dalla prima voce non spuntata in "Da fare".

## Fatto
- [x] Fase 0 — Benchmark, verifica tunnel (bloccato), scaffold, git locale con hook pre-commit
- [x] Fase 1 — Job via API (coda a un posto, stato su disco), fotogrammetria (1600 px, 4 thread,
      BelowNormal, max 40 foto), scansione guidata (anello di copertura, scatto automatico, suggerimenti),
      upload in background, avanzamento con ripresa, viewer 3D, misura reale in mm, export STL + condivisione
- [x] Fase 2 — Pulizia: piano del tavolo (RANSAC), oggetto principale (DBSCAN), Z-up, Poisson tagliata per
      distanza dai punti, solidificazione a voxel con base piatta fino a z=0, verifica manifold3d;
      report di stampabilità; appoggio sulla base più ampia; rotazioni 90°; export 3MF e OBJ
- [x] Fase 3 — Archivio IndexedDB (miniatura, nome, data, rinomina, riesporta, elimina), tema chiaro/scuro,
      guscio offline (service worker), three.js caricato solo nelle schermate 3D
- [x] Fase 4 — Provider AI (Hugging Face via gradio_client) con adattatore generico, selettore
      Precisa/Rapida, mock; testato con client finto
- [x] Import foto da galleria/file (sottocampionamento uniforme a 40, HEIC lato server)
- [x] File di deploy: `.devcontainer`, `scripts/setup-linux-tools.sh`, `web/vercel.json`,
      `deploy/hf-space/Dockerfile`, `npm run hf-space`, `npm run serve` (porta unica)
- [x] README con guida GitHub → Codespace → Vercel → collaudo telefono

## Da fare
- [ ] **Ripartire da qui (dopo il riavvio del PC):** collaudo reale con fotogrammetria, un passo alla volta,
      solo se `psutil.virtual_memory().available` ≥ 2 GB prima di ogni passo:
      1. avviare il server: `SCAN3D_ENABLE_MOCK=1 ACCESS_PIN=<pin> DATA_DIR=.cache/e2e-data SERVE_WEB=web/dist`
         `server/.venv/Scripts/python -m uvicorn app.main:app --app-dir server --port 8000`
      2. ricostruzione via API senza browser (tempio, 40 foto) → misurare tempo e RAM della pulizia
         (ridotta a max 80k punti prima di Poisson, non ancora riprovata)
      3. `PROVIDER=photo IMAGES=../bench/dataset/_templeRing/templeRing npm run e2e` (in `web/`)
      4. `scripts/verify_exports.py web/e2e/out` e `npm run smoke`
      5. compilare "Risultati del collaudo" qui sotto e fare il commit
- [ ] Motore AI reale: NON provare dal PC aziendale (il proxy ispeziona l'HTTPS, Python rifiuta il
      certificato aziendale; l'utente ha scelto di non installare `truststore`). Va provato nel Codespace.
- [ ] (Utente) Verifica policy aziendale → push su GitHub → Codespace → Vercel → collaudo su iPhone 13 / SE
- [ ] (Utente) Collaudo su Android/Samsung (punti elencati nel README)
- [ ] (Futuro) Invio a OctoPrint/Moonraker con slicing lato server; import da Scaniverse

- [x] 2026-11-10 — Codespace: avvio automatico (`postStartCommand` → `scripts/codespace-start.sh`, secrets
      Codespaces, porta pubblica via `gh`), `npm run doctor`, setup Linux idempotente con log, errori
      ImportError leggibili, motori "non disponibili" con motivo visibile anche sul telefono
- [ ] (Utente) Nel Codespace: impostare i secrets, rebuild, `npm run doctor` verde, collaudo Precisa + Rapida
- [x] 2026-11-11 — **Modelli più precisi e senza buchi** (piano: ~/.claude/plans/questo-il-mio-keen-hamming.md):
      foto a 2400 px; OpenMVS a piena risoluzione + ReconstructMesh + RefineMesh (con ripieghi); fori chiusi con
      MeshFix senza gonfiare la forma; base piatta estrusa; report "Fedeltà alla scansione"; AI multi-vista
      Hunyuan3D-2mv con viste scelte dalla bussola; consigli per oggetti lucidi/piccoli/dettagli fini
- [ ] **Nel Codespace (ripartire da qui):**
      1. `bash scripts/setup-linux-tools.sh` (installa RefineMesh) e `server/.venv/bin/pip install -r server/requirements.txt`
         (pymeshfix, fast-simplification), poi `npm run doctor`
      2. `server/.venv/bin/python bench/quality.py --download` e poi
         `server/.venv/bin/python bench/quality.py --variants predefinita veloce` → tabella qui sotto. FERMARSI se
         la predefinita supera 25 min o 7 GB: regolare `PHOTO_MAX_RESOLUTION` / `PHOTO_REFINE` insieme all'utente
      3. collaudo AI multi-vista da iPhone: se il modello esce specchiato → `HF_MV_SWAP_LR=1`
      4. collaudo Precisa da iPhone: un oggetto con dettagli fini e uno lucido opacizzato

## Decisioni
| Data | Decisione |
|---|---|
| 2026-11-11 | Precisa fino a ~25 min (scelta utente): risoluzione piena + RefineMesh; foto a 2400 px (oltre OpenMVS non le usa) |
| 2026-11-11 | Buchi chiusi con MeshFix (solo i fori); la solidificazione a voxel resta come ripiego (384 voxel, max 7 di chiusura) |
| 2026-11-11 | AI: Hunyuan3D-2mv con 4 viste dalla bussola; senza bussola solo fronte+retro |
| 2026-11-10 | HF Space Docker ora a pagamento (PRO): backend resta nel Codespace, con avvio automatico |
| 2026-11-06 | Fotogrammetria: 1600 px, exhaustive, 4 thread, priorità BelowNormal, max 40 foto |
| 2026-11-06 | Nessun tunnel (bloccato dalla rete + policy). Test da telefono via Codespace/Vercel |
| 2026-11-06 | Auth: PIN → token HMAC in `Authorization: Bearer`, niente cookie |
| 2026-11-06 | Push su GitHub e deploy li fa l'utente; prima verifica la policy aziendale |
| 2026-11-06 | Invio a stampanti fuori scope per ora |
| 2026-11-06 | Modello normalizzato a 100 mm sul lato lungo finché l'utente non inserisce una misura reale |
| 2026-11-06 | Archivio solo nel telefono; il server cancella il job appena il modello è scaricato |
| 2026-11-06 | ~~Mesh resa stampabile con solidificazione a voxel~~ (sostituita il 2026-11-11: deformava la forma) |
| 2026-11-06 | `npm` del PC usa un registry aziendale: `.npmrc` con `omit-lockfile-registry-resolved=true` |

## Bug trovati e corretti durante i test
- Timestamp `0` trattato come "assente" nel rate limiter (`now or time.time()`).
- Ricostruzione: Poisson crea una "bolla" chiusa → il ritaglio produceva una scatola. Ora taglio per distanza.
- Base dell'oggetto persa (9% di altezza): griglia voxel che non arrivava a z=0.
- Coperchio bucato nelle zone con pochi punti (taglio per densità) → taglio per distanza + chiusura progressiva.
- `DATA_DIR` relativo + COLMAP con cartella di lavoro diversa → percorsi sbagliati. Ora assoluto.
- Windows: `os.replace` di `job.json` fallisce se l'antivirus tiene aperto il file → nuovi tentativi.
- Mirino troppo alto su iPhone: l'otturatore finiva fuori schermo.
- Bundle iniziale 820 kB → 364 kB (three.js caricato solo dove serve).
- Forma "gonfiata": la solidificazione dilatava fino a 11 voxel (risoluzione 200) e riempiva le fessure ~5% → MeshFix.
- Foto dimezzate due volte (1600 px + `--resolution-level 1`): OpenMVS lavorava a ~800 px.
- `largest_component` preferiva un sassolino chiuso a un oggetto aperto più grande → ora per area.
- Piano del tavolo instabile (RANSAC di Open3D è parallelo) → rifinitura ai minimi quadrati (SVD).
- Semplificazione Open3D: 237 s su 1,5 M triangoli → fast_simplification, < 1 s.

## Collaudo
Vedi la sezione "Risultati del collaudo" in fondo (aggiornata all'ultima esecuzione).

## Non verificabile da qui
- iPhone reali, Android/Samsung, installazione PWA reale (servono HTTPS e telefono).
- Codespace, Vercel, Hugging Face Space (nessun push/deploy fatto, per scelta).
- Dockerfile dello Space e `setup-linux-tools.sh` (niente Docker/Linux sul PC di sviluppo).
- Qualità su oggetti reali fotografati con iPhone (solo dataset pubblici finora).

## Risultati del collaudo
(compilato a fine lavoro)
