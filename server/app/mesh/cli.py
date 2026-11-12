"""Pulizia del modello in un processo separato (la usa la fotogrammetria, si può lanciare a mano).

Perché separato: è calcolo Python pesante. Dentro il server bloccava le risposte all'app (il
tempo trascorso sembrava fermo) e, se finiva la memoria, Linux uccideva tutto il server.
Così muore al massimo questo processo e l'app riceve un messaggio chiaro.

Uso (dalla cartella server/):
    .venv/bin/python -m app.mesh.cli INPUT.ply OUTPUT.ply            # INPUT = mesh (OpenMVS)
    .venv/bin/python -m app.mesh.cli INPUT.ply OUTPUT.ply --points   # INPUT = nuvola di punti
    .venv/bin/python -m app.mesh.cli MODELLO.glb OUTPUT.ply --y-up --no-plane --max-faces 400000   # AI

Scrive OUTPUT (mesh pulita) e OUTPUT.json ({"steps", "fidelity", "deviationMm"} oppure {"error"});
stampa ogni passo e il picco di RAM (utile per la diagnosi).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def peak_gb() -> float:
    try:
        import resource  # solo Linux/macOS

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6  # Linux: KiB
    except ImportError:  # Windows (sviluppo)
        import psutil

        return getattr(psutil.Process().memory_info(), "peak_wset", 0) / 1e9


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pulizia del modello 3D (Scan3D)")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--points", action="store_true", help="l'ingresso è una nuvola di punti, non una mesh")
    ap.add_argument("--y-up", action="store_true", help="mesh glTF (Y verso l'alto), come quelle dell'AI")
    ap.add_argument("--no-plane", action="store_true", help="non cercare il tavolo (mesh AI: c'è solo l'oggetto)")
    ap.add_argument("--max-faces", type=int, default=None, help="riduci subito la mesh a questi triangoli")
    a = ap.parse_args(argv)
    out, meta = Path(a.output), Path(a.output + ".json")

    def say(msg: str):
        print(msg, flush=True)

    from .cleanup import UserError, points_to_mesh, surface_to_printable

    if a.max_faces:
        say(f"Limite di triangoli: {a.max_faces:,}")
    try:
        if a.points:
            mesh, info = points_to_mesh(a.input, progress=say)
        else:
            import trimesh

            loaded = trimesh.load(a.input, force="mesh")
            say(f"Mesh letta: {len(loaded.faces):,} triangoli (RAM {peak_gb():.1f} GB)")
            mesh, info = surface_to_printable(loaded, progress=say, y_up=a.y_up, find_plane=not a.no_plane,
                                              max_input_faces=a.max_faces)
    except UserError as e:  # messaggi pensati per l'utente (es. "non riesco a isolare l'oggetto")
        meta.write_text(json.dumps({"error": str(e)}, ensure_ascii=False), encoding="utf-8")
        say(f"Errore: {e}")
        return 0
    except Exception as e:  # noqa: BLE001 - guasto interno: dettagli nel log, il server può riprovare
        import traceback

        traceback.print_exc(file=sys.stdout)
        say(f"Errore interno ({type(e).__name__}): {e}")
        return 1
    mesh.export(out)
    meta.write_text(json.dumps({"steps": info.steps, "fidelity": info.fidelity(), "deviationMm": info.deviation_mm},
                               ensure_ascii=False), encoding="utf-8")
    say(f"Fatto: {len(mesh.faces):,} triangoli. RAM di picco {peak_gb():.1f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
