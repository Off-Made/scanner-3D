#!/usr/bin/env bash
# Installa COLMAP, OpenMVS e le librerie di sistema per Open3D su Linux (Codespace / Ubuntu 24.04).
# Si può rilanciare quante volte vuoi: salta ciò che è già a posto.
# Log completo: .cache/setup-tools.log
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OPENMVS_VERSION="v2.4.0"
mkdir -p "$ROOT/.cache"
exec > >(tee -a "$ROOT/.cache/setup-tools.log") 2>&1
echo "===== $(date -Is) setup-linux-tools"
FAILED=0

apt_install() { sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@"; }

echo "== 1/3 Librerie di sistema per Open3D (servono a entrambi i motori) =="
# Passo separato: se COLMAP o OpenMVS falliscono, la modalità Rapida funziona lo stesso.
sudo apt-get update -y || echo "ATTENZIONE: apt-get update non riuscito, provo comunque"
apt_install unzip curl ca-certificates libgl1 libegl1 libglib2.0-0 libgomp1 libusb-1.0-0 libx11-6 libxext6 \
  || { echo "ERRORE: librerie di sistema non installate"; FAILED=1; }

echo "== 2/3 COLMAP (apt) =="
if command -v colmap >/dev/null; then echo "COLMAP già presente"
else apt_install colmap || { echo "ERRORE: COLMAP non installato"; FAILED=1; }; fi

echo "== 3/3 OpenMVS ${OPENMVS_VERSION} (binari precompilati Ubuntu) =="
BIN="$ROOT/tools/openmvs/bin"
if [ -x "$BIN/DensifyPointCloud" ] && [ -x "$BIN/InterfaceCOLMAP" ]; then echo "OpenMVS già presente"
else
  mkdir -p "$BIN" "$ROOT/tools/_downloads"
  ZIP="$ROOT/tools/_downloads/OpenMVS_Ubuntu_x64.zip"
  if [ ! -s "$ZIP" ]; then
    curl -fsSL -o "$ZIP.part" "https://github.com/cdcseacave/openMVS/releases/download/${OPENMVS_VERSION}/OpenMVS_Ubuntu_x64.zip" \
      && mv "$ZIP.part" "$ZIP" || { echo "ERRORE: download di OpenMVS non riuscito"; rm -f "$ZIP.part"; FAILED=1; }
  fi
  if [ -s "$ZIP" ]; then
    rm -rf "$ROOT/tools/openmvs/_x" && unzip -q -o "$ZIP" -d "$ROOT/tools/openmvs/_x"
    for t in InterfaceCOLMAP DensifyPointCloud ReconstructMesh; do
      f="$(find "$ROOT/tools/openmvs/_x" -type f -name "$t" | head -1 || true)"
      if [ -n "$f" ]; then cp "$f" "$BIN/$t"; chmod +x "$BIN/$t"; else echo "ATTENZIONE: $t non trovato nell'archivio"; fi
    done
    # eventuali librerie condivise incluse nell'archivio
    find "$ROOT/tools/openmvs/_x" -name "*.so*" -exec cp -n {} "$BIN/" \; 2>/dev/null || true
  fi
fi

# Librerie che mancano a OpenMVS: cerco il pacchetto apt che le fornisce e lo installo.
missing_libs() { LD_LIBRARY_PATH="$BIN" ldd "$BIN/DensifyPointCloud" "$BIN/InterfaceCOLMAP" 2>/dev/null | awk '/not found/ {print $1}' | sort -u; }
if [ -x "$BIN/DensifyPointCloud" ] && [ -n "$(missing_libs)" ]; then
  echo "== Librerie mancanti a OpenMVS: provo a installarle =="
  command -v apt-file >/dev/null || apt_install apt-file
  sudo apt-file update >/dev/null 2>&1 || true
  PKGS=""
  for lib in $(missing_libs); do
    pkg="$(apt-file search -l "/$lib" 2>/dev/null | grep -v -- '-dbg' | head -1)"
    if [ -n "$pkg" ]; then PKGS="$PKGS $pkg"; else echo "  nessun pacchetto trovato per $lib"; fi
  done
  # shellcheck disable=SC2086
  [ -n "$PKGS" ] && apt_install $PKGS
fi

echo "== Controllo =="
command -v colmap >/dev/null && colmap help 2>&1 | head -1 || { echo "ATTENZIONE: colmap non funziona"; FAILED=1; }
if [ -x "$BIN/DensifyPointCloud" ]; then
  if [ -n "$(missing_libs)" ]; then echo "ATTENZIONE: a OpenMVS mancano ancora:"; missing_libs; FAILED=1; else echo "OpenMVS ok"; fi
else echo "ATTENZIONE: OpenMVS non installato"; FAILED=1; fi

[ "$FAILED" = 0 ] && echo "== Strumenti pronti ==" || echo "== Completato CON ERRORI: guarda i messaggi sopra (log in .cache/setup-tools.log) =="
exit "$FAILED"
