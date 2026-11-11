"""Report di stampabilità di una mesh (unità: mm)."""
from __future__ import annotations

import trimesh


def printability(mesh: trimesh.Trimesh) -> dict:
    ext = [round(float(v), 2) for v in mesh.extents]
    watertight = bool(mesh.is_watertight)
    winding = bool(mesh.is_winding_consistent)
    components = len(mesh.split(only_watertight=False)) if len(mesh.faces) < 400_000 else 1
    volume = float(mesh.volume) if watertight else 0.0
    checks = [
        {"id": "closed", "ok": watertight, "label": "Mesh chiusa (watertight)",
         "hint": "" if watertight else "Ci sono fori: lo slicer potrebbe sbagliare il riempimento."},
        {"id": "normals", "ok": winding and volume > 0, "label": "Normali coerenti verso l'esterno",
         "hint": "" if winding else "Alcune facce sono girate al contrario."},
        {"id": "single", "ok": components == 1, "label": "Un solo pezzo",
         "hint": "" if components == 1 else f"Il modello è composto da {components} parti separate."},
    ]
    fidelity = mesh.metadata.get("fidelity")
    if fidelity:
        filled = fidelity["filledPct"]
        ok = filled <= 15
        hint = ("La base piatta è stata aggiunta sul piano del tavolo. " if fidelity.get("baseAdded") else "")
        hint += (f"Il {filled:.0f}% della superficie non era visibile nelle foto ed è stato chiuso a stima"
                 + ("." if ok else ": aggiungi foto da quelle angolazioni per un modello più fedele."))
        if fidelity.get("deviationMm") is not None:
            hint += f" Scostamento medio dalla scansione: {fidelity['deviationMm']:.2f} mm."
        checks.append({"id": "fidelity", "ok": ok, "label": "Fedeltà alla scansione", "hint": hint})
    return {
        "fidelity": fidelity,
        "watertight": watertight,
        "windingConsistent": winding,
        "volumeMm3": round(volume, 1),
        "areaMm2": round(float(mesh.area), 1),
        "extentsMm": ext,
        "triangles": int(len(mesh.faces)),
        "vertices": int(len(mesh.vertices)),
        "components": components,
        "checks": checks,
        "printable": all(c["ok"] for c in checks if c["id"] != "fidelity"),  # la fedeltà informa, non blocca
    }
