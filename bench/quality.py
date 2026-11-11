"""Benchmark di qualità della modalità Precisa: tempo, RAM e fedeltà del modello finale.

Usa lo stesso codice del server (PhotogrammetryProvider + pulizia), su dataset pubblici Middlebury.
Da lanciare nel Codespace (sul PC aziendale la RAM non basta):

    server/.venv/bin/python bench/quality.py --download            # scarica templeRing e dinoRing
    server/.venv/bin/python bench/quality.py --variants predefinita veloce

Varianti:
  predefinita  configurazione attuale (risoluzione piena, ReconstructMesh + RefineMesh)
  veloce       PHOTO_RESOLUTION_LEVEL=1, PHOTO_REFINE=0 (per confronto: quanto costa la qualità)

Scrive bench/out/quality/<dataset>-<variante>/{model.stl, results.json} e stampa una tabella.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

DATASETS = {
    "templeRing": "https://vision.middlebury.edu/mview/data/data/templeRing.zip",
    "dinoRing": "https://vision.middlebury.edu/mview/data/data/dinoRing.zip",
}
VARIANTS = {
    "predefinita": {},
    "veloce": {"PHOTO_RESOLUTION_LEVEL": "1", "PHOTO_REFINE": "0"},
}


IMAGE_EXT = (".png", ".jpg", ".jpeg")


def dataset_images(name: str) -> list[Path]:
    """Immagini del dataset, ovunque si trovino dentro bench/dataset/_<nome> (lo zip può avere sottocartelle)."""
    base = ROOT / "bench" / "dataset" / f"_{name}"
    return sorted(p for p in base.rglob("*") if p.suffix.lower() in IMAGE_EXT) if base.exists() else []


def download(name: str) -> None:
    if dataset_images(name):
        print(f"{name}: già presente ({len(dataset_images(name))} immagini)")
        return
    print(f"{name}: download da {DATASETS[name]} …", flush=True)
    # alcuni server rifiutano (403) il client predefinito "Python-urllib": mi presento come un browser generico
    req = urllib.request.Request(DATASETS[name], headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = r.read()
    except urllib.error.URLError as e:
        dest = ROOT / "bench" / "dataset" / f"_{name}"
        raise SystemExit(
            f"{name}: download non riuscito ({e}).\n"
            f"Alternativa: copia a mano la cartella con le immagini in {dest.relative_to(ROOT)}/\n"
            f"(nel Codespace: trascinala dal PC nell'Explorer di VS Code dentro bench/dataset/_{name}/).")
    zipfile.ZipFile(io.BytesIO(data)).extractall(ROOT / "bench" / "dataset" / f"_{name}")
    n = len(dataset_images(name))
    if not n:
        raise SystemExit(f"{name}: lo zip non contiene immagini PNG/JPG")
    print(f"{name}: {n} immagini")


def run(name: str, variant: str, n: int) -> dict:
    from run_bench import PeakMemory  # campiona la RSS di questo processo e dei programmi figli

    for k in ("PHOTO_RESOLUTION_LEVEL", "PHOTO_REFINE"):
        os.environ.pop(k, None)
    os.environ.update(VARIANTS[variant])
    from app.imaging import save_normalized
    from app.mesh.report import printability
    from app.providers.base import RunContext
    from app.providers.photogrammetry import PhotogrammetryProvider

    out = ROOT / "bench" / "out" / "quality" / f"{name}-{variant}"
    shutil.rmtree(out, ignore_errors=True)
    photos_dir, work = out / "photos", out / "work"
    work.mkdir(parents=True)
    if not dataset_images(name):
        download(name)  # se manca, lo scarico ora
    src = dataset_images(name)
    if len(src) > n:  # selezione uniforme, come l'import dalla galleria
        src = [src[round(i * (len(src) - 1) / (n - 1))] for i in range(n)]
    photos = []
    for i, p in enumerate(src):
        dest = photos_dir / f"{i + 1:03d}.jpg"
        save_normalized(p.read_bytes(), dest)  # stesso trattamento dell'upload dal telefono
        photos.append(dest)

    phases: list[tuple[str, float]] = []

    def report(pct: float, step: str):
        if not phases or phases[-1][0] != step:
            phases.append((step, time.monotonic()))
            print(f"   [{(time.monotonic() - t0) / 60:5.1f} min] {step}", flush=True)

    ctx = RunContext(work_dir=work, report_progress=report, is_cancelled=lambda: False, log_file=work / "pipeline.log")
    mem = PeakMemory(os.getpid())
    t0 = time.monotonic()
    error = None
    try:
        mesh, steps = PhotogrammetryProvider().reconstruct(photos, ctx)
    except Exception as e:  # noqa: BLE001 - nel benchmark registro l'errore e vado avanti
        mesh, steps, error = None, [], str(e)
    total = time.monotonic() - t0
    mem.stop()
    durations = {}
    for (step, t), nxt in zip(phases, [*phases[1:], ("fine", t0 + total)]):
        durations[step] = durations.get(step, 0) + (nxt[1] - t)
    res = {"dataset": name, "variant": variant, "photos": len(photos), "minutes": round(total / 60, 1),
           "peakGB": round(mem.peak / 1e9, 2), "phasesMin": {k: round(v / 60, 2) for k, v in durations.items() if v > 5},
           "error": error, "steps": steps}
    if mesh is not None:
        rep = printability(mesh)
        mesh.export(out / "model.stl")
        res.update({"watertight": rep["watertight"], "triangles": rep["triangles"], "fidelity": rep.get("fidelity")})
    (out / "results.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="scarica i dataset e termina")
    ap.add_argument("--datasets", nargs="+", default=list(DATASETS), choices=list(DATASETS))
    ap.add_argument("--variants", nargs="+", default=["predefinita"], choices=list(VARIANTS))
    ap.add_argument("--n", type=int, default=40, help="numero massimo di foto (come nell'app)")
    a = ap.parse_args()
    if a.download:
        for d in a.datasets:
            download(d)
        return
    rows = []
    for d in a.datasets:
        for v in a.variants:
            print(f"== {d} / {v}", flush=True)
            r = run(d, v, a.n)
            print(json.dumps(r, ensure_ascii=False), flush=True)
            rows.append(r)
    print("\n| Dataset | Variante | Foto | Minuti | RAM picco | Chiusa | Stimata % | Scostamento mm | Triangoli |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        f = r.get("fidelity") or {}
        print(f"| {r['dataset']} | {r['variant']} | {r['photos']} | {r['minutes']} | {r['peakGB']} GB | "
              f"{'sì' if r.get('watertight') else 'no'} | {f.get('filledPct', '–')} | {f.get('deviationMm', '–')} | "
              f"{r.get('triangles', '–')} |" + (f" errore: {r['error'][:80]}" if r["error"] else ""))


if __name__ == "__main__":
    main()
