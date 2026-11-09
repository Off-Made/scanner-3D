---
title: Scan3D backend
emoji: 🧊
colorFrom: gray
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Scan3D — backend di ricostruzione

API usata dalla PWA Scan3D (frontend su Vercel). Accesso protetto da PIN.

Segreti da impostare in **Settings → Variables and secrets**:

| Nome | Tipo | Valore |
|---|---|---|
| `ACCESS_PIN` | Secret | il tuo PIN (6+ cifre) |
| `SESSION_SECRET` | Secret | una stringa casuale lunga |
| `CORS_ORIGINS` | Variable | `https://<il-tuo-progetto>.vercel.app` |
| `CORS_ORIGIN_REGEX` | Variable (facoltativa) | `https://<il-tuo-progetto>-.*\.vercel\.app` (anteprime) |
| `HF_TOKEN` | Secret (facoltativo) | token HF per il provider AI |
