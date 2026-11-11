#!/usr/bin/env bash
# Avvio automatico nel Codespace: lo lancia .devcontainer (postStartCommand) a OGNI accensione.
#   1. ripara gli strumenti se mancano (es. dopo un rebuild)
#   2. avvia app + API sulla porta 8000 (log: .cache/serve.log)
#   3. rende pubblica la porta 8000, così il telefono e Vercel la raggiungono
# Uso manuale:  bash scripts/codespace-start.sh            (avvia se non è già acceso)
#               bash scripts/codespace-start.sh --restart  (riavvia il server, es. dopo aver cambiato .env)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p .cache
PORT=8000
health() { curl -fsS -m 3 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; }
say() { echo "[avvio $(date +%H:%M:%S)] $*"; }

# Un solo avvio per volta (es. postStartCommand + avvio manuale insieme): il secondo si ferma subito.
exec 9> .cache/codespace-start.lock
if ! flock -n 9; then say "Un altro avvio è già in corso: aspetto che finisca lui."; exit 0; fi

if [ "${1:-}" = "--restart" ]; then
  say "Fermo il server in esecuzione"
  pkill -f "uvicorn app.main:app" 2>/dev/null; sleep 2
fi
if health; then say "Il server è già acceso sulla porta $PORT"; else

  # --- PIN: dai Codespaces secrets (consigliato, sopravvivono ai rebuild) o da .env -----------
  env_has() { [ -n "${!1:-}" ] || grep -Eq "^$1=.+" .env 2>/dev/null; }
  if ! env_has ACCESS_PIN || ! env_has SESSION_SECRET; then
    say "ACCESS_PIN e/o SESSION_SECRET non impostati: NON avvio il server (la porta sarà pubblica)."
    say "Impostali in github.com/settings/codespaces → Secrets (vedi README, 'Avvio automatico'), poi:"
    say "  bash scripts/codespace-start.sh"
    exit 1
  fi

  # --- auto-riparazione: dipendenze Python e strumenti di fotogrammetria ------------------------
  # virtualenv mancante o rotto (es. il Python del Codespace è cambiato dopo un rebuild): setup lo ricrea
  server/.venv/bin/python -c "import pip" >/dev/null 2>&1 || { say "Virtualenv mancante o rotto: npm run setup"; npm run setup; }
  # requirements.txt cambiato (es. nuove librerie dopo un git pull): reinstallo i pacchetti Python
  REQ_SUM="$(sha256sum server/requirements.txt | cut -d' ' -f1)"
  if [ "$(cat .cache/requirements.sha 2>/dev/null)" != "$REQ_SUM" ]; then
    say "Pacchetti Python da aggiornare (requirements.txt cambiato): installo"
    server/.venv/bin/python -m pip install -q -r server/requirements.txt >> .cache/pip.log 2>&1 \
      && echo "$REQ_SUM" > .cache/requirements.sha || say "pip con errori: guarda .cache/pip.log"
  fi
  if ! server/.venv/bin/python scripts/doctor.py >/dev/null 2>&1; then
    say "Mancano componenti: rilancio l'installazione (qualche minuto, log in .cache/setup-tools.log)"
    bash scripts/setup-linux-tools.sh >/dev/null 2>&1 || say "Installazione con errori: guarda .cache/setup-tools.log"
    server/.venv/bin/python scripts/doctor.py || true
  fi

  # --- avvio del server in background ---------------------------------------------------------
  say "Avvio app + API sulla porta $PORT (log: .cache/serve.log)"
  HOST=0.0.0.0 PORT=$PORT setsid nohup npm run serve >> .cache/serve.log 2>&1 < /dev/null 9>&- &
  for _ in $(seq 1 90); do health && break; sleep 2; done
  if ! health; then say "Il server non risponde dopo 3 minuti: guarda .cache/serve.log"; exit 1; fi
  say "Server acceso"
fi

# --- porta pubblica (serve il token del Codespace, presente in automatico) ----------------------
if [ -n "${CODESPACE_NAME:-}" ] && command -v gh >/dev/null; then
  for i in 1 2 3 4 5; do
    if out="$(gh codespace ports visibility "$PORT:public" -c "$CODESPACE_NAME" 2>&1)"; then
      say "Porta $PORT pubblica: https://${CODESPACE_NAME}-${PORT}.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
      exit 0
    fi
    sleep $((i * 3))
  done
  say "GitHub ha risposto: ${out:-nessun messaggio}"
  say "Non riesco a rendere pubblica la porta: scheda Ports → porta $PORT → tasto destro → Port Visibility → Public"
fi
