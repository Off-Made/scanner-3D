"""Fotogrammetria su CPU: COLMAP (pose) + OpenMVS (punti densi, mesh, affinamento) + pulizia.

  COLMAP:  feature (max 2000 px, thread = CPU, al massimo 4: con 12 la RAM esplodeva) -> matching exhaustive -> pose
  OpenMVS: DensifyPointCloud (risoluzione piena, max 2048 px; se fallisce riprova a 1/2 e 1/4) -> ReconstructMesh (graph-cut sulla
           visibilità: segue i punti veri, niente "bolle") -> RefineMesh (affina la superficie
           confrontando le foto: recupera i dettagli fini)
  Pulizia: tavolo, oggetto, base piatta, fori chiusi senza deformare (mesh/cleanup.py)

Ogni passo di qualità ha un ripiego: senza RefineMesh si usa la mesh grezza, senza
ReconstructMesh si torna alla nuvola di punti (Poisson). Priorità bassa per tutti i programmi.
Variabili: PHOTO_FEATURE_THREADS, PHOTO_MATCH_THREADS, PHOTO_FEATURE_MAX_SIZE, PHOTO_MAX_IMAGE,
PHOTO_RESOLUTION_LEVEL, PHOTO_MAX_RESOLUTION, PHOTO_REFINE (0 = niente affinamento), PHOTO_REFINE_LEVEL.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from .. import deps
from ..config import ROOT
from .base import Provider, ProviderError, RunContext, clean_in_subprocess

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


@lru_cache(maxsize=4)
def missing_shared_libs(binary: str, extra_lib_dir: str) -> tuple[str, ...]:
    """Linux: librerie che `ldd` non trova per il binario (vuoto se ldd non c'è o va tutto bene)."""
    if not shutil.which("ldd"):
        return ()
    env = {**os.environ, "LD_LIBRARY_PATH": f"{extra_lib_dir}:{os.environ.get('LD_LIBRARY_PATH', '')}"}
    try:
        out = subprocess.run(["ldd", binary], capture_output=True, text=True, timeout=30, env=env).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ()
    return tuple(line.split("=>")[0].strip() for line in out.splitlines() if "not found" in line)


def colmap_gpu_and_thread_options(major: int, feature_threads: int, match_threads: int,
                                  max_image_size: int | None = None) -> tuple[list[str], list[str]]:
    """Opzioni di estrazione e matching. COLMAP 4.x ha spostato le opzioni generiche in
    FeatureExtraction/FeatureMatching; quelle specifiche di SIFT restano in SiftExtraction."""
    fe = "FeatureExtraction" if major >= 4 else "SiftExtraction"
    fm = "FeatureMatching" if major >= 4 else "SiftMatching"
    feat = [f"--{fe}.use_gpu", "0", f"--{fe}.num_threads", str(feature_threads)]
    if max_image_size:
        # domain size pooling: descrittori più robusti su superfici con poca texture (oggetti in tinta unita)
        feat += [f"--{fe}.max_image_size", str(max_image_size), "--SiftExtraction.domain_size_pooling", "1"]
    return feat, [f"--{fm}.use_gpu", "0", f"--{fm}.num_threads", str(match_threads)]


def registered_images(model_dir: Path) -> int:
    """Foto "agganciate" da COLMAP in un modello sparso: i primi 8 byte di images.bin (uint64)."""
    import struct

    try:
        with open(model_dir / "images.bin", "rb") as f:
            return int(struct.unpack("<Q", f.read(8))[0])
    except (OSError, struct.error):
        return 0


MAX_DEVIATION_MM = 4.0  # oltre (su 100 mm) il modello non rappresenta più la scansione


def check_registration(registered: int, total: int) -> None:
    """Con meno di metà delle foto agganciate il modello è un frammento: meglio fermarsi e dire perché
    (il dinosauro liscio del benchmark: 3 foto su 30, e un "modello" di 3.000 triangoli senza senso)."""
    if registered < max(8, -(-total // 2)):
        raise ProviderError(
            f"Solo {registered} foto su {total} sono state collegate tra loro: l'oggetto ha troppo pochi dettagli "
            "riconoscibili (superficie liscia, lucida o in tinta unita). Opacizzalo con talco, appoggialo su un "
            "giornale e rifai le foto con luce diffusa.")


class PhotogrammetryProvider(Provider):
    id = "photo"
    label = "Precisa (foto)"
    description = ("Fotogrammetria: forma fedele all'oggetto. 20–40 foto, 15–25 minuti. "
                   "Non funziona su oggetti trasparenti; quelli lucidi vanno opacizzati (es. talco).")
    min_photos = 12
    max_photos = 40

    def __init__(self):
        # non più thread delle CPU: nel Codespace (2 CPU) 4 thread raddoppiano la RAM senza andare più veloci
        cpus = str(max(1, min(4, os.cpu_count() or 2)))
        self.feature_threads = int(os.getenv("PHOTO_FEATURE_THREADS", cpus))
        self.match_threads = int(os.getenv("PHOTO_MATCH_THREADS", cpus))
        self.feature_max_size = int(os.getenv("PHOTO_FEATURE_MAX_SIZE", "2000"))
        self.max_image = int(os.getenv("PHOTO_MAX_IMAGE", "2400"))
        self.res_level = int(os.getenv("PHOTO_RESOLUTION_LEVEL", "0"))
        self.max_resolution = int(os.getenv("PHOTO_MAX_RESOLUTION", "2048"))
        self.refine = os.getenv("PHOTO_REFINE", "1") != "0"
        self.refine_level = int(os.getenv("PHOTO_REFINE_LEVEL", "1"))

    def available(self) -> tuple[bool, str]:
        missing = [str(p.relative_to(ROOT)) if ROOT in p.parents else str(p)
                   for p in (colmap_bin(), omvs("InterfaceCOLMAP"), omvs("DensifyPointCloud"))
                   if not p.exists()]
        if missing:
            return False, ("Strumenti di fotogrammetria non installati sul server: " + ", ".join(missing)
                           + (". Nel Codespace esegui: bash scripts/setup-linux-tools.sh" if not IS_WIN else ""))
        if not IS_WIN:
            libs = missing_shared_libs(str(omvs("DensifyPointCloud")), str(openmvs_dir()))
            if libs:
                return False, ("A OpenMVS mancano librerie di sistema: " + ", ".join(libs[:6])
                               + ". Nel Codespace esegui: bash scripts/setup-linux-tools.sh")
        why = deps.missing()
        return (False, why) if why else (True, "")

    def reconstruct(self, photos: list[Path], ctx: RunContext):
        ok, why = self.available()
        if not ok:
            raise ProviderError(why)
        w = ctx.work_dir
        images = photos[0].parent
        db, sparse, dense = w / "db.db", w / "sparse", w / "dense"
        sparse.mkdir(parents=True, exist_ok=True)
        colmap = colmap_bin()
        feat_opts, match_opts = colmap_gpu_and_thread_options(colmap_major(str(colmap)), self.feature_threads,
                                                              self.match_threads, self.feature_max_size)
        n = len(photos)

        ctx.run([colmap, "feature_extractor", "--database_path", db, "--image_path", images,
                 "--ImageReader.single_camera", "1", *feat_opts],
                band=(2, 12), step="Analisi dei dettagli nelle foto", expected_s=3.5 * n)
        ctx.run([colmap, "exhaustive_matcher", "--database_path", db, *match_opts],
                band=(12, 24), step="Confronto delle foto tra loro", expected_s=0.15 * n * n)
        ctx.run([colmap, "mapper", "--database_path", db, "--image_path", images, "--output_path", sparse],
                band=(24, 30), step="Calcolo delle posizioni della fotocamera", expected_s=0.8 * n)
        models = sorted(p for p in sparse.iterdir() if p.is_dir())
        if not models:
            raise ProviderError("Le foto non si sovrappongono abbastanza: scattane di più girando lentamente "
                                "attorno all'oggetto, con buona luce.")
        model = max(models, key=registered_images)
        check_registration(registered_images(model), n)
        ctx.run([colmap, "image_undistorter", "--image_path", images, "--input_path", model,
                 "--output_path", dense, "--output_type", "COLMAP", "--max_image_size", str(self.max_image)],
                band=(30, 32), step="Preparazione delle immagini", expected_s=4)
        # su Linux i binari di OpenMVS usano librerie incluse nella stessa cartella
        omvs_env = None if IS_WIN else {**os.environ, "LD_LIBRARY_PATH": f"{openmvs_dir()}:{os.environ.get('LD_LIBRARY_PATH', '')}"}
        common = ["--process-priority", "-1", "--max-threads", "0", "-w", w]
        ctx.run([omvs("InterfaceCOLMAP"), "-i", dense, "-o", w / "scene.mvs", "--image-folder", dense / "images", "-w", w],
                band=(32, 33), step="Preparazione della ricostruzione densa", expected_s=2, env=omvs_env)
        ply = w / "scene_dense.ply"
        dense_notes = self.densify(ctx, w, common, omvs_env, n)
        if not ply.exists():
            raise ProviderError("La ricostruzione densa non ha prodotto punti. Riprova con più luce e foto più nitide.")

        surface, notes = self.mesh_from_dense(ctx, w, common, omvs_env, n)
        notes = [*dense_notes, *notes]
        mesh, steps, deviation = clean_in_subprocess(ctx, surface or ply, w / "clean.ply", points=surface is None)
        if deviation is not None and deviation > MAX_DEVIATION_MM:
            raise ProviderError(
                f"La ricostruzione è incompleta (il modello si scosta di {deviation:.0f} mm dalla scansione): "
                "servono più foto ben sovrapposte, con più dettagli visibili sull'oggetto e sul piano d'appoggio.")
        return mesh, [f"Foto collegate: {registered_images(model)} su {n}", *notes, *steps]

    def densify(self, ctx: RunContext, w: Path, common: list, env, n: int) -> list[str]:
        """DensifyPointCloud. È il passo che più spesso esaurisce la memoria (8 GB): se fallisce
        riprovo a risoluzione dimezzata, poi a un quarto, invece di fermare tutto."""
        levels = list(dict.fromkeys([self.res_level, self.res_level + 1, self.res_level + 2]))[:3]
        for i, level in enumerate(levels):
            for stale in (w / "scene_dense.ply", w / "scene_dense.mvs"):
                stale.unlink(missing_ok=True)
            step = "Ricostruzione dei punti 3D (la parte più lunga)" if i == 0 else \
                f"Ricostruzione dei punti 3D (riprovo a risoluzione ridotta, livello {level})"
            try:
                ctx.run([omvs("DensifyPointCloud"), w / "scene.mvs", "--resolution-level", str(level),
                         "--max-resolution", str(self.max_resolution), "--min-resolution", "640", *common],
                        band=(33, 60), step=step, expected_s=18 * n / (4 ** i), env=env)
            except ProviderError:
                if i == len(levels) - 1:
                    raise
                continue
            if (w / "scene_dense.ply").exists():
                return [] if i == 0 else [f"Punti 3D calcolati a risoluzione ridotta (livello {level}) per stare nella memoria"]
        return []

    def mesh_from_dense(self, ctx: RunContext, w: Path, common: list, env, n: int) -> tuple[Path | None, list[str]]:
        """Superficie da OpenMVS: ReconstructMesh e, se possibile, RefineMesh.
        Restituisce (file .ply, oppure None per ripiegare sulla nuvola di punti; note per l'utente)."""
        mesh_ply = w / "scene_dense_mesh.ply"
        if omvs("ReconstructMesh").exists():
            try:
                # free-space-support: aiuta le superfici povere di texture; smooth 1 (invece di 2): spigoli più vivi
                ctx.run([omvs("ReconstructMesh"), w / "scene_dense.mvs", "-p", w / "scene_dense.ply",
                         "-o", w / "scene_dense_mesh.mvs", "--free-space-support", "1", "--smooth", "1", *common],
                        band=(60, 68), step="Costruzione della superficie", expected_s=3 * n, env=env)
            except ProviderError:
                pass  # ripiego sulla nuvola di punti, qui sotto
        if not mesh_ply.exists():
            return None, ["Superficie di OpenMVS non riuscita: ricostruita dalla nuvola di punti (meno precisa)"]
        if not self.refine:
            return mesh_ply, ["Affinamento disattivato sul server (PHOTO_REFINE=0)"]
        if not omvs("RefineMesh").exists():
            return mesh_ply, ["Affinamento non disponibile sul server (manca RefineMesh): dettagli fini ridotti"]
        refined = w / "scene_dense_mesh_refine.ply"
        try:
            ctx.run([omvs("RefineMesh"), w / "scene_dense.mvs", "-m", mesh_ply, "-o", w / "scene_dense_mesh_refine.mvs",
                     "--resolution-level", str(self.refine_level), "--scales", "1", "--max-face-area", "16", *common],
                    band=(68, 87), step="Affinamento dei dettagli con le foto", expected_s=12 * n, env=env)
        except ProviderError:
            pass
        if refined.exists():
            return refined, ["Superficie affinata confrontando le foto"]
        return mesh_ply, ["Affinamento non riuscito: uso la superficie senza affinamento"]
