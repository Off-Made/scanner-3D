"""Verifica con trimesh i file esportati dall'app (STL / 3MF / OBJ).

Uso: server/.venv/Scripts/python scripts/verify_exports.py web/e2e/out
"""
import sys
import zipfile
from pathlib import Path

import trimesh

ok = True
for p in sorted(Path(sys.argv[1]).glob("*")):
    if p.suffix.lower() not in (".stl", ".3mf", ".obj"):
        continue
    m = trimesh.load(p, force="mesh")
    good = m.is_watertight and m.is_winding_consistent and m.volume > 0
    ok &= good
    print(f"{'OK ' if good else 'KO '} {p.name:24} facce {len(m.faces):7,}  watertight {m.is_watertight}  "
          f"normali {m.is_winding_consistent}  {m.extents.round(1)} mm  volume {m.volume / 1000:.1f} cm3")
    if p.suffix.lower() == ".3mf":
        model = zipfile.ZipFile(p).read("3D/3dmodel.model").decode()
        print(f"    3MF: unit=millimeter {'unit=\"millimeter\"' in model}")
sys.exit(0 if ok else 1)
