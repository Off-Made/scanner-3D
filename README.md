# Scan3D

PWA per telefono: fotografi un oggetto da tutti i lati, il server ricostruisce un modello 3D
(fotogrammetria), lo controlli e lo esporti in STL / 3MF / OBJ per la stampa 3D.

> Stato: **Fase 0** (fondamenta). Funzionano accesso con PIN, test della fotocamera e struttura PWA.
> La scansione guidata e la ricostruzione dall'app arrivano nella Fase 1.

## Requisiti

- Node.js 20+ (testato con 24) e Python 3.12
- Nessun permesso di amministratore, nessun Docker: tutto si installa **dentro la cartella del progetto**
  (`web/node_modules`, `server/.venv`, `.cache/`, `tools/`).

## Avvio in locale

```bash
npm run setup     # dipendenze web + virtualenv Python + controllo strumenti
npm run dev       # backend http://127.0.0.1:8000 + frontend http://127.0.0.1:5173
```

Apri http://127.0.0.1:5173. Il **PIN** viene stampato nel terminale all'avvio
(oppure impostalo tu in `.env`, partendo da `.env.example`).

```bash
npm test                                  # test unitari web (vitest) + backend (pytest)
cd web && PIN=<pin> npm run e2e           # smoke test con emulazione iPhone 13 e fotocamera finta
```

Lo smoke test usa il Chrome già installato sul PC (nessun browser scaricato) e salva
screenshot in `web/e2e/screens/`.

## Strumenti di fotogrammetria (`tools/`, non nel repository)

Scaricali dalle release ufficiali ed estraili così:

| Strumento | Release | Percorso atteso |
|---|---|---|
| COLMAP 4.2.1 (no CUDA) | github.com/colmap/colmap/releases → `colmap-x64-windows-nocuda.zip` | `tools/colmap/bin/colmap.exe` |
| OpenMVS 2.4.0 | github.com/cdcseacave/openMVS/releases → `OpenMVS_Windows_x64.zip` | `tools/openmvs/vc17/x64/Release/*.exe` |

`npm run check:tools` verifica che ci siano.

## Provarlo dal telefono

La fotocamera nel browser richiede **HTTPS**. Su una rete aziendale i tunnel verso il PC
(cloudflared, ngrok…) sono spesso bloccati e comunque esporrebbero il PC a internet: **non usarli**.
Il percorso previsto è:

1. **Frontend su Vercel** (HTTPS vero, installabile come PWA) — Fase 0.4.
2. **Backend nel cloud** (GitHub Codespace per i test, poi un hosting dedicato).
   Nel Codespace la porta 8000 va resa *Public* solo durante i test, con PIN attivo,
   e il Codespace va fermato quando hai finito.

Su iPhone: apri l'URL in **Safari** › Condividi › **Aggiungi alla schermata Home**.

## Sicurezza dell'accesso

- PIN → token firmato (HMAC-SHA256, 12 h) inviato in `Authorization: Bearer`. Niente cookie
  (Safari blocca i cookie tra domini diversi, es. Vercel ↔ backend).
- Max 5 tentativi di PIN al minuto per IP. L'IP reale si legge da `CF-Connecting-IP` /
  `X-Forwarded-For` **solo** se la richiesta arriva da un proxy fidato (loopback o `TRUSTED_PROXIES`).
- CORS: solo le origini in `CORS_ORIGINS`.

## Benchmark della fotogrammetria

```bash
server/.venv/Scripts/python bench/run_bench.py --n 30 --size 1600 --threads 4
```

Risultati su un portatile i5-1245U / 8 GB (30 foto del dataset pubblico AliceVision *monstree*):

| Thread feature | Totale | Memoria allocata (picco) | Foto registrate |
|---|---|---|---|
| 12 (default) | 10,0 min | 8,3 GB (paging!) | 26/30 |
| **4** (adottato) | **8,1 min** | **2,8 GB** | 26/30 |

Configurazione usata dall'app: 1600 px, matcher exhaustive, 4 thread, priorità *BelowNormal*,
massimo 40 foto per scansione.

## Limiti onesti

- La fotogrammetria funziona male su oggetti lucidi, trasparenti, scuri o senza texture.
- La scala reale non è nota: dovrai inserire una misura (es. altezza in mm).
- Una ricostruzione richiede ~8–11 minuti su questo PC; su un server cloud gratuito a 2 core molto di più.

## Android / Samsung — da verificare su un dispositivo reale

Il codice gestisce Chrome e Samsung Internet, ma questi punti **non sono stati testati** su un telefono vero:
permessi fotocamera di Samsung Internet, `deviceorientationabsolute`, prompt di installazione PWA,
condivisione file con `navigator.share`.
