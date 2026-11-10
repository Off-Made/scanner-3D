"""npm run doctor: dice se i motori di ricostruzione possono funzionare su questa macchina, e cosa fare se no.

Usa gli stessi controlli del server (available() dei provider), così il risultato coincide con l'app.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:  # la console di Windows (cp1252) non sa stampare ✓/✗
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("ACCESS_PIN", "000000")  # non serve un PIN vero: non avviamo il server

from app import deps  # noqa: E402
from app.providers import default_providers  # noqa: E402
from app.providers.photogrammetry import colmap_bin, omvs  # noqa: E402

ok_all = True


def line(ok: bool, name: str, detail: str = "") -> None:
    global ok_all
    ok_all &= ok
    print(f"  {'✓' if ok else '✗'} {name:<27} {detail}")


print("Pacchetti Python")
for m in ("gradio_client", *deps.MESH_MODULES):
    why = deps.check_module(m)
    line(why is None, m, why or "")

print("\nStrumenti di fotogrammetria")
for name, p in (("COLMAP", colmap_bin()), ("OpenMVS InterfaceCOLMAP", omvs("InterfaceCOLMAP")),
                ("OpenMVS DensifyPointCloud", omvs("DensifyPointCloud"))):
    line(p.exists(), name, str(p) if p.exists() else f"non trovato ({p})")

print("\nMotori (come li vede l'app)")
for p in default_providers().values():
    ok, why = p.available()
    line(ok, p.label, why)

if ok_all:
    print("\nTutto pronto.")
else:
    fix = "bash scripts/setup-linux-tools.sh" if sys.platform != "win32" else "vedi README, sezione Strumenti"
    print(f"\nQualcosa manca. Per riparare: {fix}\n(poi riavvia il server; dettagli dell'installazione in .cache/setup-tools.log)")
sys.exit(0 if ok_all else 1)
