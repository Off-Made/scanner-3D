"""Benchmark della pipeline di fotogrammetria su CPU (COLMAP + OpenMVS + Open3D).

Uso (dalla cartella del progetto):
    server\\.venv\\Scripts\\python.exe bench\\run_bench.py --n 30 --size 1600

Per ogni step misura il tempo e il picco di RAM (processo figlio + suoi figli)
e alla fine scrive bench/out/<tag>/results.json.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import psutil
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
COLMAP = ROOT / "tools" / "colmap" / "bin" / "colmap.exe"
OMVS = ROOT / "tools" / "openmvs" / "vc17" / "x64" / "Release"


class PeakMemory:
    """Campiona ogni 0.25 s la RSS di un processo e di tutti i suoi figli."""

    def __init__(self, pid: int):
        self.pid, self.peak, self.peak_private, self._stop = pid, 0, 0, threading.Event()
        self.min_avail = psutil.virtual_memory().available
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        try:
            root = psutil.Process(self.pid)
        except psutil.NoSuchProcess:
            return
        while not self._stop.is_set():
            try:
                procs = [root] + root.children(recursive=True)
                infos = [p.memory_info() for p in procs if p.is_running()]
                self.peak = max(self.peak, sum(i.rss for i in infos))
                # su Windows 'private' = memoria allocata (anche se finita nel file di paging)
                self.peak_private = max(self.peak_private, sum(getattr(i, "private", i.rss) for i in infos))
                self.min_avail = min(self.min_avail, psutil.virtual_memory().available)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            time.sleep(0.25)

    def stop(self):
        self._stop.set()
        self._t.join(timeout=2)


def run_step(name: str, cmd: list[str], cwd: Path, log: Path, results: list, timeout: int):
    print(f"  > {name} ...", flush=True)
    t0 = time.perf_counter()
    with open(log, "a", encoding="utf-8", errors="replace") as fh:
        fh.write(f"\n===== {name}: {' '.join(map(str, cmd))}\n")
        fh.flush()
        flags = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)  # PC usabile durante il job
        proc = subprocess.Popen([str(c) for c in cmd], cwd=cwd, stdout=fh, stderr=subprocess.STDOUT,
                                creationflags=flags)
        mon = PeakMemory(proc.pid)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = "timeout"
        mon.stop()
    dt = time.perf_counter() - t0
    r = {"step": name, "seconds": round(dt, 1), "peak_rss_gb": round(mon.peak / 1e9, 2),
         "peak_private_gb": round(mon.peak_private / 1e9, 2),
         "min_avail_gb": round(mon.min_avail / 1e9, 2), "exit": code}
    results.append(r)
    print(f"    {dt:7.1f}s  peak {r['peak_rss_gb']} GB, private {r['peak_private_gb']} GB  (RAM libera min {r['min_avail_gb']} GB)  exit={code}", flush=True)
    if code != 0:
        raise RuntimeError(f"step '{name}' fallito (exit={code}), vedi {log}")


def prepare_images(src: Path, dst: Path, n: int, size: int) -> int:
    files = sorted(p for p in src.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if n < len(files):  # selezione uniforme sul giro attorno all'oggetto
        files = [files[round(i * (len(files) - 1) / (n - 1))] for i in range(n)]
    dst.mkdir(parents=True, exist_ok=True)
    for f in files:
        im = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
        im.thumbnail((size, size), Image.LANCZOS)
        im.save(dst / (f.stem + ".jpg"), quality=90)
    return len(files)


def mesh_step(dense_ply: Path, out_dir: Path, results: list, depth: int):
    """Pulizia minima + Poisson con Open3D (misurato sul processo corrente)."""
    import open3d as o3d
    import trimesh

    proc = psutil.Process()
    t0 = time.perf_counter()
    pcd = o3d.io.read_point_cloud(str(dense_ply))
    n_dense = len(pcd.points)
    pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    if not pcd.has_normals():
        pcd.estimate_normals(o3d.geometry.KDTreeSearchParamKNN(30))
    if len(pcd.points) < 300_000:  # l'orientamento coerente è costoso su nuvole grandi
        pcd.orient_normals_consistent_tangent_plane(15)
    mesh, _dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=depth)
    mi = proc.memory_info()
    peak = max(mi.rss, getattr(mi, "peak_wset", 0))
    peak_private = getattr(mi, "private", mi.rss)
    o3d.io.write_triangle_mesh(str(out_dir / "poisson.ply"), mesh)
    tm = trimesh.Trimesh(vertices=np.asarray(mesh.vertices), faces=np.asarray(mesh.triangles), process=True)
    dt = time.perf_counter() - t0
    r = {"step": "open3d_poisson", "seconds": round(dt, 1), "peak_rss_gb": round(peak / 1e9, 2),
         "peak_private_gb": round(peak_private / 1e9, 2),
         "dense_points": n_dense, "points_after_clean": len(pcd.points),
         "triangles": len(tm.faces), "watertight": bool(tm.is_watertight), "exit": 0}
    results.append(r)
    print(f"  > open3d_poisson\n    {dt:7.1f}s  punti densi {n_dense:,}  triangoli {len(tm.faces):,}  watertight={tm.is_watertight}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", default=str(ROOT / "bench" / "dataset" / "monstree_full"))
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--size", type=int, default=1600, help="lato lungo in pixel")
    ap.add_argument("--matcher", choices=["exhaustive", "sequential"], default="exhaustive")
    ap.add_argument("--res-level", type=int, default=1, help="OpenMVS --resolution-level (0=piena)")
    ap.add_argument("--depth", type=int, default=9, help="profondità Poisson")
    ap.add_argument("--threads", type=int, default=-1, help="thread COLMAP feature/matching (-1=tutti)")
    ap.add_argument("--timeout", type=int, default=3600, help="timeout per step in secondi")
    a = ap.parse_args()

    tag = f"n{a.n}_px{a.size}_{a.matcher[:3]}_rl{a.res_level}_t{a.threads}"
    out = ROOT / "bench" / "out" / tag
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    log = out / "pipeline.log"
    res: list = []
    print(f"== Benchmark {tag} ==")
    t_all = time.perf_counter()
    status = "ok"
    try:
        n = prepare_images(Path(a.images), out / "images", a.n, a.size)
        print(f"  immagini preparate: {n}")
        db, sparse = out / "db.db", out / "sparse"
        sparse.mkdir()
        run_step("colmap_features", [COLMAP, "feature_extractor", "--database_path", db,
                 "--image_path", out / "images", "--ImageReader.single_camera", "1",
                 "--FeatureExtraction.use_gpu", "0",
                 "--FeatureExtraction.num_threads", str(a.threads)], out, log, res, a.timeout)
        match = ["exhaustive_matcher"] if a.matcher == "exhaustive" else [
            "sequential_matcher", "--SequentialMatching.overlap", "8"]
        run_step("colmap_matching", [COLMAP, *match, "--database_path", db,
                 "--FeatureMatching.use_gpu", "0", "--FeatureMatching.num_threads", str(a.threads)], out, log, res, a.timeout)
        run_step("colmap_mapper", [COLMAP, "mapper", "--database_path", db,
                 "--image_path", out / "images", "--output_path", sparse], out, log, res, a.timeout)
        models = sorted(p for p in sparse.iterdir() if p.is_dir())
        if not models:
            raise RuntimeError("COLMAP non ha ricostruito nessun modello")
        run_step("colmap_undistort", [COLMAP, "image_undistorter", "--image_path", out / "images",
                 "--input_path", models[0], "--output_path", out / "dense", "--output_type", "COLMAP"],
                 out, log, res, a.timeout)
        run_step("omvs_interface", [OMVS / "InterfaceCOLMAP.exe", "-i", out / "dense", "-o",
                 out / "scene.mvs", "--image-folder", out / "dense" / "images", "-w", out],
                 out, log, res, a.timeout)
        run_step("omvs_densify", [OMVS / "DensifyPointCloud.exe", out / "scene.mvs",
                 "--resolution-level", str(a.res_level), "--process-priority", "-1", "-w", out], out, log, res, a.timeout)
        mesh_step(out / "scene_dense.ply", out, res, a.depth)
        # numero di immagini registrate dal mapper (qualità delle pose)
        txt = out / "model_txt"
        txt.mkdir()
        subprocess.run([str(COLMAP), "model_converter", "--input_path", str(models[0]),
                        "--output_path", str(txt), "--output_type", "TXT"], capture_output=True)
        lines = [l for l in (txt / "images.txt").read_text().splitlines() if l and not l.startswith("#")]
        registered = len(lines) // 2
    except Exception as e:  # noqa: BLE001 - nel benchmark riportiamo qualsiasi errore
        status, registered = f"errore: {e}", None
        print("  !!", status)
    total = round(time.perf_counter() - t_all, 1)
    summary = {"tag": tag, "args": vars(a), "status": status, "total_seconds": total,
               "registered_images": registered,
               "peak_rss_gb": max((r["peak_rss_gb"] for r in res), default=0),
               "peak_private_gb": max((r.get("peak_private_gb", 0) for r in res), default=0), "steps": res}
    (out / "results.json").write_text(json.dumps(summary, indent=2))
    print(f"== Totale {total/60:.1f} min, picco RAM {summary['peak_rss_gb']} GB (private {summary['peak_private_gb']} GB), "
          f"immagini registrate {registered}/{a.n}, stato: {status}")


if __name__ == "__main__":
    sys.exit(main())
