"""Fotogrammetria su CPU: COLMAP (pose) + OpenMVS (punti densi) + pulizia Open3D/trimesh.

Configurazione dal benchmark (README): foto a 1600 px, matcher exhaustive, 4 thread per
l'estrazione delle feature (con 12 thread la RAM esplodeva a 8 GB), priorità bassa.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from ..config import ROOT
from ..mesh.cleanup import points_to_mesh
from .base import Provider, ProviderError, RunContext

IS_WIN = sys.platform == "win32"


def colmap_bin() -> Path:
    if os.getenv("COLMAP_BIN"):
        return Path(os.environ["COLMAP_BIN"])
    local = ROOT / "tools" / "colmap" / "bin" / ("colmap.exe" if IS_WIN else "colmap")
    return local if local.exists() else Path(shutil.which("colmap") or local)


def openmvs_dir() -> Path:
    if os.getenv("OPENMVS_DIR"):
        return Path(os.environ["OPENMVS_DIR"])
    return ROOT / "tools" / "openmvs" / ("vc17/x64/Release" if IS_WIN else "bin")


def omvs(tool: str) -> Path:
    return openmvs_dir() / (tool + (".exe" if IS_WIN else ""))


@lru_cache(maxsize=4)
def colmap_major(path: str) -> int:
    """COLMAP 4.x ha rinominato le opzioni (SiftExtraction.use_gpu -> FeatureExtraction.use_gpu)."""
    try:
        out = subprocess.run([path, "help"], capture_output=True, text=True, timeout=30).stdout
        m = re.search(r"COLMAP (\d+)\.", out)
        return int(m.group(1)) if m else 4
    except (OSError, subprocess.TimeoutExpired):
        return 4


def colmap_gpu_and_thread_options(major: int, feature_threads: int, match_threads: int) -> tuple[list[str], list[str]]:
    if major >= 4:
        return (["--FeatureExtraction.use_gpu", "0", "--FeatureExtraction.num_threads", str(feature_threads)],
                ["--FeatureMatching.use_gpu", "0", "--FeatureMatching.num_threads", str(match_threads)])
    return (["--SiftExtraction.use_gpu", "0", "--SiftExtraction.num_threads", str(feature_threads)],
            ["--SiftMatching.use_gpu", "0", "--SiftMatching.num_threads", str(match_threads)])


class PhotogrammetryProvider(Provider):
    id = "photo"
    label = "Precisa (foto)"
    description = "Fotogrammetria: forma fedele all'oggetto. 20–40 foto, circa 10 minuti."
    min_photos = 12
    max_photos = 40

    def __init__(self):
        self.feature_threads = int(os.getenv("PHOTO_FEATURE_THREADS", "4"))
        self.match_threads = int(os.getenv("PHOTO_MATCH_THREADS", "4"))
        self.res_level = int(os.getenv("PHOTO_RESOLUTION_LEVEL", "1"))

    def available(self) -> tuple[bool, str]:
        missing = [str(p.relative_to(ROOT)) if ROOT in p.parents else str(p)
                   for p in (colmap_bin(), omvs("InterfaceCOLMAP"), omvs("DensifyPointCloud")) if not p.exists()]
        if missing:
            return False, "Strumenti di fotogrammetria non installati sul server: " + ", ".join(missing)
        return True, ""

    def reconstruct(self, photos: list[Path], ctx: RunContext):
        ok, why = self.available()
        if not ok:
            raise ProviderError(why)
        w = ctx.work_dir
        images = photos[0].parent
        db, sparse, dense = w / "db.db", w / "sparse", w / "dense"
        sparse.mkdir(parents=True, exist_ok=True)
        colmap = colmap_bin()
        feat_opts, match_opts = colmap_gpu_and_thread_options(colmap_major(str(colmap)), self.feature_threads, self.match_threads)
        n = len(photos)

        ctx.run([colmap, "feature_extractor", "--database_path", db, "--image_path", images,
                 "--ImageReader.single_camera", "1", *feat_opts],
                band=(2, 18), step="Analisi dei dettagli nelle foto", expected_s=2.5 * n)
        ctx.run([colmap, "exhaustive_matcher", "--database_path", db, *match_opts],
                band=(18, 36), step="Confronto delle foto tra loro", expected_s=0.12 * n * n)
        ctx.run([colmap, "mapper", "--database_path", db, "--image_path", images, "--output_path", sparse],
                band=(36, 44), step="Calcolo delle posizioni della fotocamera", expected_s=0.8 * n)
        models = sorted(p for p in sparse.iterdir() if p.is_dir())
        if not models:
            raise ProviderError("Le foto non si sovrappongono abbastanza: scattane di più girando lentamente "
                                "attorno all'oggetto, con buona luce.")
        model = max(models, key=lambda p: (p / "images.bin").stat().st_size if (p / "images.bin").exists() else 0)
        ctx.run([colmap, "image_undistorter", "--image_path", images, "--input_path", model,
                 "--output_path", dense, "--output_type", "COLMAP"],
                band=(44, 46), step="Preparazione delle immagini", expected_s=3)
        ctx.run([omvs("InterfaceCOLMAP"), "-i", dense, "-o", w / "scene.mvs", "--image-folder", dense / "images", "-w", w],
                band=(46, 47), step="Preparazione della ricostruzione densa", expected_s=2)
        ctx.run([omvs("DensifyPointCloud"), w / "scene.mvs", "--resolution-level", str(self.res_level),
                 "--process-priority", "-1", "--max-threads", "0", "-w", w],
                band=(47, 85), step="Ricostruzione della superficie (la parte più lunga)", expected_s=8 * n)
        ply = w / "scene_dense.ply"
        if not ply.exists():
            raise ProviderError("La ricostruzione densa non ha prodotto punti. Riprova con più luce e foto più nitide.")

        ctx.progress(86, "Pulizia del modello")
        try:
            mesh, info = points_to_mesh(str(ply), progress=lambda m: ctx.progress(90, m))
        except ValueError as e:
            raise ProviderError(str(e)) from e
        return mesh, info.steps
