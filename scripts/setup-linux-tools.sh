#!/usr/bin/env bash
# Installa COLMAP e OpenMVS su Linux (Codespace / Ubuntu 24.04).
# NOTA: verificato solo nella sintassi; il primo collaudo reale avviene nel tuo Codespace.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OPENMVS_VERSION="v2.4.0"

echo "== Dipendenze di sistema (COLMAP da apt, librerie per Open3D) =="
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  colmap unzip curl ca-certificates libgl1 libglib2.0-0 libgomp1

echo "== OpenMVS ${OPENMVS_VERSION} (binari precompilati Ubuntu) =="
mkdir -p "$ROOT/tools/openmvs" "$ROOT/tools/_downloads"
ZIP="$ROOT/tools/_downloads/OpenMVS_Ubuntu_x64.zip"
[ -f "$ZIP" ] || curl -fsSL -o "$ZIP" "https://github.com/cdcseacave/openMVS/releases/download/${OPENMVS_VERSION}/OpenMVS_Ubuntu_x64.zip"
rm -rf "$ROOT/tools/openmvs/_x" && unzip -q -o "$ZIP" -d "$ROOT/tools/openmvs/_x"
mkdir -p "$ROOT/tools/openmvs/bin"
for t in InterfaceCOLMAP DensifyPointCloud ReconstructMesh; do
  f="$(find "$ROOT/tools/openmvs/_x" -type f -name "$t" | head -1 || true)"
  if [ -n "$f" ]; then cp "$f" "$ROOT/tools/openmvs/bin/$t"; chmod +x "$ROOT/tools/openmvs/bin/$t"; fi
done
# eventuali librerie condivise incluse nell'archivio
find "$ROOT/tools/openmvs/_x" -name "*.so*" -exec cp -n {} "$ROOT/tools/openmvs/bin/" \; 2>/dev/null || true

echo "== Controllo =="
colmap help | head -1 || echo "ATTENZIONE: colmap non funziona"
MISSING="$(LD_LIBRARY_PATH="$ROOT/tools/openmvs/bin" ldd "$ROOT/tools/openmvs/bin/DensifyPointCloud" 2>/dev/null | grep 'not found' || true)"
if [ -n "$MISSING" ]; then
  echo "ATTENZIONE: a OpenMVS mancano librerie di sistema:"; echo "$MISSING"
  echo "Installa i pacchetti corrispondenti con apt (es. libboost-*, libopencv-*) e riprova."
else
  echo "OpenMVS ok"
fi
