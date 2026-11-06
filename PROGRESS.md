# PROGRESS — Scan3D

Stato di avanzamento, decisioni e come riprendere il lavoro.

## Come riprendere
1. Leggi questo file e `README.md`.
2. `npm run setup` (se è un PC nuovo), poi `npm test`.
3. Riparti dalla prima voce non spuntata in "Da fare".

## Fatto
- [x] Fase 0.1 — Benchmark fotogrammetria su CPU (vedi README).
- [x] Fase 0.2 — Tunnel: cloudflared bloccato dalla rete aziendale (porta 7844). Niente tunnel.
- [x] Fase 0.3 — Scaffold: FastAPI + PIN/token, PWA React, test, script.
- [x] Fase 0.4 (parte locale) — git locale, identità noreply, hook pre-commit, primo commit.

## Da fare
- [ ] Fase 1 — Job di fotogrammetria via API, scansione guidata, upload, avanzamento, viewer, scala mm, STL + condivisione
- [ ] Fase 2 — Pulizia mesh, watertight (manifold3d), report stampabilità, appoggia sul piatto, rotazioni, 3MF/OBJ
- [ ] Fase 3 — Archivio (IndexedDB), rifiniture UI, guscio offline
- [ ] Fase 4 — Provider AI (Hugging Face) + selettore Precisa/Rapida + mock
- [ ] Import foto da galleria/file
- [ ] File di deploy: .devcontainer, script tool Linux, vercel.json, Dockerfile HF Space
- [ ] README: guida passo passo GitHub → Codespace → Vercel → collaudo telefono
- [ ] Collaudo e2e completo con il dataset (foto → STL verificato con trimesh)

## Decisioni
| Data | Decisione |
|---|---|
| 2026-11-06 | Fotogrammetria: 1600 px, exhaustive, 4 thread, priorità BelowNormal, max 40 foto |
| 2026-11-06 | Nessun tunnel (bloccato + policy). Test da telefono via Vercel + backend in cloud |
| 2026-11-06 | Auth: PIN → token HMAC in `Authorization: Bearer`, niente cookie |
| 2026-11-06 | Push su GitHub e deploy li fa l'utente; prima verifica la policy aziendale |
| 2026-11-06 | Invio a stampanti (OctoPrint/Moonraker) rimandato: fuori scope |

## Non verificabile da qui
- iPhone reali, Android/Samsung, installazione PWA reale (servono HTTPS e telefono).
