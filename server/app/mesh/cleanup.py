"""Pulizia della ricostruzione e preparazione di una mesh stampabile.

Strada principale (fotogrammetria con mesh di OpenMVS, e provider AI):
  piano del tavolo (RANSAC) -> Z-up, taglio sotto il tavolo -> oggetto principale
  -> base piatta (il bordo inferiore viene estruso fino a z = 0)
  -> fori chiusi con MeshFix (superfici minime: la geometria vera NON viene toccata)
  -> verifica manifold3d -> normalizzazione + report di fedeltà

Fallback (solo se la strada principale non dà un solido chiuso):
  solidificazione a voxel ad alta risoluzione, con chiusura delle fessure più delicata possibile.

Da nuvola di punti (se ReconstructMesh non è disponibile): Poisson con le normali di OpenMVS,
poi la stessa chiusura.

Convenzione: Z verso l'alto, unità = millimetri (scala arbitraria finché l'utente non
imposta una misura reale), oggetto centrato in XY e appoggiato su z = 0.
"""
from __future__ import annotations

import gc
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import trimesh

Progress = Callable[[str], None]
DEFAULT_SIZE_MM = 100.0
TARGET_FACES = 300_000
MAX_INPUT_FACES = 1_500_000  # oltre, la pulizia su 8 GB rischia di esaurire la memoria
MAX_POISSON_POINTS = 80_000


@dataclass
class CleanupInfo:
    steps: list[str] = field(default_factory=list)
    plane_found: bool = False
    repaired_with: str = "nessuna riparazione"
    filled_pct: float = 0.0          # % della superficie finale che è stata "inventata" per chiudere i fori
    base_added: bool = False         # fondo chiuso con una base piatta sul piano del tavolo
    deviation_mm: float | None = None  # distanza media superficie ricostruita -> modello finale

    def log(self, msg: str, progress: Progress | None):
        self.steps.append(msg)
        if progress:
            progress(msg)

    def fidelity(self) -> dict:
        return {"filledPct": round(self.filled_pct, 1), "baseAdded": self.base_added,
                "deviationMm": None if self.deviation_mm is None else round(self.deviation_mm, 2),
                "method": self.repaired_with}


def _rotation_to_z(normal: np.ndarray) -> np.ndarray:
    """Matrice 4x4 che porta `normal` sull'asse +Z."""
    n = normal / np.linalg.norm(normal)
    z = np.array([0.0, 0.0, 1.0])
    v, c = np.cross(n, z), float(np.dot(n, z))
    if np.linalg.norm(v) < 1e-9:
        R = np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    else:
        vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        R = np.eye(3) + vx + vx @ vx * (1 / (1 + c))
    T = np.eye(4)
    T[:3, :3] = R
    return T


def find_table(points: np.ndarray, diag: float) -> tuple[np.ndarray, np.ndarray] | None:
    """RANSAC sul piano dominante. Restituisce (T, inlier_mask): T porta il piano a z = 0 con
    l'oggetto dal lato +Z. None se non c'è un piano evidente (≥ 12% dei punti)."""
    import open3d as o3d

    o3d.utility.random.seed(0)  # risultato ripetibile a parità di foto
    pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    (a, b, c, d), inliers = pcd.segment_plane(distance_threshold=diag * 0.006, ransac_n=3, num_iterations=2000)
    if len(inliers) <= 0.12 * len(points):
        return None
    mask = np.zeros(len(points), bool)
    mask[inliers] = True
    # RANSAC è parallelo (non del tutto ripetibile) e si ferma al primo piano "abbastanza buono":
    # lo rifinisco con i minimi quadrati sui punti più vicini, così base e altezza sono precise.
    normal, d = np.array([a, b, c]) / np.linalg.norm([a, b, c]), d / np.linalg.norm([a, b, c])
    for _ in range(3):
        P = points[mask]
        centroid = P.mean(axis=0)
        n = np.linalg.svd(P - centroid, full_matrices=False)[2][-1]
        normal, d = (n, -float(n @ centroid)) if n @ normal >= 0 else (-n, float(n @ centroid))
        r = np.abs(points @ normal + d)
        mask = r < max(2.5 * float(np.median(r[mask])), diag * 1e-4)
    dist = points[~mask] @ normal + d
    # da che parte sta l'oggetto: conto solo i punti ben lontani dal piano (lo spessore del
    # tavolo, il suo bordo o il rumore appena sotto non devono decidere)
    far = dist[np.abs(dist) > diag * 0.02]
    if np.median(far if len(far) else dist) < 0:  # l'oggetto deve stare dal lato positivo della normale
        normal, d = -normal, -d
    # dopo la rotazione (normale -> +Z) i punti del piano hanno z = -d/|n|: li porto a z = 0
    T = _rotation_to_z(normal)
    T[2, 3] = d / np.linalg.norm(normal)
    return T, mask


# --- strada principale: superficie (mesh) -> solido fedele ------------------------------------

def surface_to_printable(mesh: trimesh.Trimesh, progress: Progress | None = None, y_up: bool = False,
                         find_plane: bool = True, max_input_faces: int | None = None) -> tuple[trimesh.Trimesh, CleanupInfo]:
    """Mesh di superficie (OpenMVS o AI) -> solido chiuso, Z-up, 100 mm, con report di fedeltà."""
    info = CleanupInfo()
    limit = max_input_faces or MAX_INPUT_FACES
    if len(mesh.faces) > limit:
        # una scena intera da foto del telefono, o un modello AI ad alta risoluzione, può avere
        # milioni di triangoli: riduco SUBITO, prima dei passi che occupano memoria in proporzione
        n0 = len(mesh.faces)
        mesh = _decimate(mesh, limit)
        info.log(f"Superficie ridotta da {n0:,} a {len(mesh.faces):,} triangoli per stare nella memoria", progress)
    mesh = trimesh.Trimesh(mesh.vertices, mesh.faces, process=True)
    if y_up:  # glTF è Y-up: ruoto per avere Z-up come gli slicer
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    if len(mesh.faces) < 4:
        raise ValueError("Superficie ricostruita troppo povera: servono foto più nitide e più sovrapposte.")
    info.log(f"Superficie ricevuta: {len(mesh.faces):,} triangoli", progress)
    diag = float(np.linalg.norm(mesh.extents))

    table = find_table(mesh.sample(60_000, seed=0), diag) if find_plane else None
    if table is not None:
        T, _ = table
        mesh.apply_transform(T)
        # via il tavolo e tutto ciò che sta sotto (piccolo margine per lo spessore del rumore)
        mesh = mesh.slice_plane([0, 0, diag * 0.004], [0, 0, 1], cap=False)
        info.plane_found = True
        info.log("Piano di appoggio trovato e rimosso", progress)
    else:
        info.log("Nessun piano di appoggio evidente", progress)

    mesh = largest_component(mesh)
    if len(mesh.faces) < 4:
        raise ValueError("Non riesco a isolare l'oggetto dallo sfondo. Prova con uno sfondo più uniforme.")
    info.log(f"Oggetto isolato: {len(mesh.faces):,} triangoli", progress)
    if len(mesh.faces) > TARGET_FACES:
        mesh = _decimate(mesh, TARGET_FACES)
    surface = mesh.copy()  # la superficie "vera", per misurare quanto il modello finale se ne scosta

    if info.plane_found and cap_bottom(mesh):
        info.base_added = True
        info.log("Base piatta ricostruita sul piano del tavolo", progress)
    area_seen = float(mesh.area)

    closed = close_holes(mesh, info, area_seen=area_seen)
    if closed is None:
        info.log("Chiusura fine non riuscita: uso la solidificazione a voxel", progress)
        floor_top = float(surface.vertices[:, 2].min()) if info.plane_found else None
        closed = solidify(surface, floor_top=floor_top)
        info.repaired_with = "solidificata a voxel (dettagli fini ridotti)"
        info.filled_pct = max(0.0, 100 * (1 - area_seen / float(closed.area))) if closed.area else 0.0
    else:
        info.repaired_with = "fori chiusi con superfici minime (MeshFix)"
    info.log(f"Mesh chiusa: {info.repaired_with}; superficie aggiunta {info.filled_pct:.1f}%", progress)
    return _finish(closed, surface, info, progress)


def _finish(mesh: trimesh.Trimesh, surface: trimesh.Trimesh | None, info: CleanupInfo,
            progress: Progress | None) -> tuple[trimesh.Trimesh, CleanupInfo]:
    mesh = largest_component(mesh)
    if not mesh.is_watertight:
        mesh = make_watertight(mesh, info)
    M = normalize_matrix(mesh)
    mesh.apply_transform(M)
    if surface is not None and len(surface.faces):
        surface = surface.copy()
        surface.apply_transform(M)
        info.deviation_mm = deviation(surface, mesh)
        info.log(f"Scostamento medio dalla superficie ricostruita: {info.deviation_mm:.2f} mm", progress)
    mesh.metadata["fidelity"] = info.fidelity()
    return mesh, info


def deviation(reference: trimesh.Trimesh, mesh: trimesh.Trimesh, n: int = 4000) -> float:
    """Distanza media (unità della mesh) dei punti della superficie vera dal modello finale."""
    pts = reference.sample(n, seed=0)
    _, dist, _ = trimesh.proximity.closest_point(mesh, pts)
    return float(np.mean(dist))


def boundary_loops(mesh: trimesh.Trimesh) -> list[np.ndarray]:
    """Bordi aperti come cicli di vertici, nel verso dei triangoli che li contengono."""
    idx = trimesh.grouping.group_rows(mesh.edges_sorted, require_count=1)
    nxt: dict[int, int] = {}
    for a, b in mesh.edges[idx]:
        nxt.setdefault(int(a), int(b))
    loops, seen = [], set()
    for start in nxt:
        if start in seen:
            continue
        loop, cur = [start], nxt[start]
        seen.add(start)
        while cur != start and cur in nxt and cur not in seen:
            loop.append(cur)
            seen.add(cur)
            cur = nxt[cur]
        if cur == start and len(loop) >= 3:
            loops.append(np.array(loop))
    return loops


def cap_bottom(mesh: trimesh.Trimesh) -> bool:
    """Chiude il fondo aperto (il lato appoggiato al tavolo, mai fotografato) con una base piatta:
    il bordo più basso viene estruso in verticale fino a z = 0 e chiuso da un poligono.
    Modifica `mesh` sul posto. False se non c'è un bordo inferiore riconoscibile."""
    import mapbox_earcut as earcut

    loops = boundary_loops(mesh)
    if not loops:
        return False
    z = mesh.vertices[:, 2]
    zmin, h = float(z.min()), float(np.ptp(z))
    low = [lp for lp in loops if z[lp].max() < zmin + 0.15 * h]
    if not low:
        return False
    loop = max(low, key=len)
    ring = mesh.vertices[loop]
    n = len(loop)
    base = ring.copy()
    base[:, 2] = 0.0
    off = len(mesh.vertices)
    new_idx = np.arange(off, off + n)
    nxt = np.roll(np.arange(n), -1)
    # il bordo va da loop[i] a loop[i+1] nel verso del triangolo esistente: la parete lo percorre al contrario
    walls = np.vstack([np.c_[loop[nxt], loop, new_idx], np.c_[loop[nxt], new_idx, new_idx[nxt]]])
    tri = np.asarray(earcut.triangulate_float64(base[:, :2].astype(np.float64), np.array([n], np.uint32)))
    if len(tri) < 3:
        return False
    cap = new_idx[tri.reshape(-1, 3)]
    # la base deve guardare verso il basso
    p = base[tri.reshape(-1, 3)]
    nz = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])[:, 2]
    cap[nz > 0] = cap[nz > 0][:, ::-1]
    mesh.vertices = np.vstack([mesh.vertices, base])
    mesh.faces = np.vstack([mesh.faces, walls, cap])
    return True


def close_holes(mesh: trimesh.Trimesh, info: CleanupInfo, area_seen: float | None = None) -> trimesh.Trimesh | None:
    """Chiude i fori con MeshFix (triangolazione + raffinamento dei soli fori: il resto della
    superficie resta com'è). None se il risultato non è un solido valido."""
    from pymeshfix import PyTMesh

    area_seen = float(mesh.area) if area_seen is None else area_seen
    t = PyTMesh()
    t.set_quiet(1)
    t.load_array(np.ascontiguousarray(mesh.vertices, dtype=np.float64), np.ascontiguousarray(mesh.faces, dtype=np.int32))
    t.remove_smallest_components()
    t.fill_small_boundaries(0, True)  # 0 = tutti i fori, qualunque dimensione
    t.clean(10, 3)                    # toglie auto-intersezioni e triangoli degeneri (ri-chiude se serve)
    if t.n_boundaries:
        t.fill_small_boundaries(0, True)
    v, f = t.return_arrays()
    if len(f) < 4:
        return None
    out = trimesh.Trimesh(v, f, process=True)
    m = _to_manifold(out) if out.is_watertight else None
    if m is None:
        return None
    out = _from_manifold(m)
    if not out.is_watertight or out.volume <= 0:
        return None
    trimesh.repair.fix_normals(out)
    info.filled_pct = max(0.0, 100 * (1 - area_seen / float(out.area)))
    return out


# --- da nuvola di punti (fallback se ReconstructMesh non c'è o fallisce) ----------------------

def points_to_mesh(ply_path: str, progress: Progress | None = None, depth: int = 9) -> tuple[trimesh.Trimesh, CleanupInfo]:
    import open3d as o3d
    from scipy.spatial import cKDTree

    info = CleanupInfo()
    pcd = o3d.io.read_point_cloud(str(ply_path))
    if len(pcd.points) < 1000:
        raise ValueError("Nuvola di punti troppo povera: servono foto più nitide e più sovrapposte.")
    has_normals = pcd.has_normals()  # OpenMVS (--estimate-normals) le orienta verso le fotocamere
    diag = float(np.linalg.norm(pcd.get_max_bound() - pcd.get_min_bound()))

    pcd = pcd.voxel_down_sample(diag / 800)
    pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    info.log(f"Rumore rimosso: {len(pcd.points):,} punti", progress)

    T = np.eye(4)
    table = find_table(np.asarray(pcd.points), diag)
    if table is not None:
        T, mask = table
        pcd = pcd.select_by_index(np.where(~mask)[0])
        z = (np.asarray(pcd.points) @ T[:3, :3].T + T[:3, 3])[:, 2]
        pcd = pcd.select_by_index(np.where(z > diag * 0.008)[0])  # via il tavolo e ciò che sta sotto
        info.plane_found = True
        info.log("Piano di appoggio trovato e rimosso", progress)
    else:
        info.log("Nessun piano di appoggio evidente", progress)

    labels = np.array(pcd.cluster_dbscan(eps=diag * 0.02, min_points=12))
    if labels.max() >= 0:
        main = np.bincount(labels[labels >= 0]).argmax()
        pcd = pcd.select_by_index(np.where(labels == main)[0])
    info.log(f"Oggetto isolato: {len(pcd.points):,} punti", progress)
    if len(pcd.points) < 500:
        raise ValueError("Non riesco a isolare l'oggetto dallo sfondo. Prova con uno sfondo più uniforme.")
    pcd.transform(T)

    # Memoria: Poisson cresce con il numero di punti; oltre ~80k non si guadagna dettaglio.
    if len(pcd.points) > MAX_POISSON_POINTS:
        voxel = float(np.linalg.norm(pcd.get_max_bound() - pcd.get_min_bound())) / 800
        while len(pcd.points) > MAX_POISSON_POINTS:
            voxel *= 1.25
            pcd = pcd.voxel_down_sample(voxel)
    pts = np.asarray(pcd.points)
    if not has_normals:
        pcd.estimate_normals(o3d.geometry.KDTreeSearchParamKNN(24))
        pcd.orient_normals_consistent_tangent_plane(12)
        nrm = np.asarray(pcd.normals)
        if np.mean(np.einsum("ij,ij->i", nrm, pts - pts.mean(axis=0))) < 0:  # normali verso l'esterno
            pcd.normals = o3d.utility.Vector3dVector(-nrm)
    mesh_o3d, _ = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=depth)
    # Poisson "inventa" superficie lontano dai punti: tolgo i vertici lontani dal punto reale più vicino.
    tree = cKDTree(pts)
    spacing = float(np.percentile(tree.query(pts, k=2)[0][:, 1], 95))
    far = tree.query(np.asarray(mesh_o3d.vertices), k=1)[0] > max(spacing * 4, diag * 0.004)
    mesh_o3d.remove_vertices_by_mask(far)
    mesh = trimesh.Trimesh(np.asarray(mesh_o3d.vertices), np.asarray(mesh_o3d.triangles), process=True)
    del mesh_o3d, tree, pcd
    gc.collect()
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    margin = (hi - lo) * 0.03
    inside = np.all((mesh.vertices >= lo - margin) & (mesh.vertices <= hi + margin), axis=1)
    if info.plane_found:
        inside &= mesh.vertices[:, 2] >= 0
    mesh.update_faces(np.all(inside[mesh.faces], axis=1))
    mesh.remove_unreferenced_vertices()
    mesh = largest_component(mesh)
    info.log(f"Superficie ricostruita: {len(mesh.faces):,} triangoli", progress)

    surface = mesh.copy()
    if info.plane_found and cap_bottom(mesh):
        info.base_added = True
    area_seen = float(mesh.area)
    closed = close_holes(mesh, info, area_seen=area_seen)
    if closed is None:
        floor_top = float(surface.vertices[:, 2].min()) if info.plane_found else None
        closed = solidify(surface, floor_top=floor_top)
        info.repaired_with = "solidificata a voxel con base piatta" if info.plane_found else "solidificata a voxel"
        info.filled_pct = max(0.0, 100 * (1 - area_seen / float(closed.area))) if closed.area else 0.0
    else:
        info.repaired_with = "fori chiusi con superfici minime (MeshFix)"
    info.log(f"Mesh chiusa: {info.repaired_with}", progress)
    return _finish(closed, surface, info, progress)


# --- fallback a voxel ------------------------------------------------------------------------

def _voxelize_surface(mesh: trimesh.Trimesh, pitch: float) -> tuple[np.ndarray, np.ndarray]:
    """Voxel attraversati dalla superficie, vettorizzato (trimesh.voxelized a 384 impiega minuti).
    Campiona la superficie con passo < pitch/2: ogni voxel toccato riceve almeno un punto.
    Restituisce (matrice booleana, centro del voxel [0,0,0])."""
    count = int(min(12_000_000, max(10_000, 6 * mesh.area / pitch**2)))
    pts = np.vstack([mesh.sample(count, seed=0), mesh.vertices])
    lo = pts.min(axis=0)
    idx = np.round((pts - lo) / pitch).astype(np.int64)
    grid = np.zeros(idx.max(axis=0) + 1, dtype=bool)
    grid[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    return grid, lo

def solidify(mesh: trimesh.Trimesh, resolution: int = 384, floor_top: float | None = None) -> trimesh.Trimesh:
    """Superficie (anche aperta sul fondo) -> solido chiuso. Usata solo se MeshFix non riesce.

    1. voxelizza la superficie; se l'interno non si riempie (c'è un buco), chiude le fessure in
       modo via via più deciso, ma al massimo di 7 voxel (≈ 2% della dimensione): oltre la forma
       si deforma troppo
    2. se c'è il piano: pavimento temporaneo fino a `floor_top`, così il fondo aperto diventa una
       cavità chiusa; poi la base viene estrusa fino a z = 0
    3. estrae la superficie (marching cubes), leviga appena e semplifica
    """
    floor = floor_top is not None
    from scipy import ndimage

    pitch = float(mesh.extents.max()) / resolution
    matrix, start = _voxelize_surface(mesh, pitch)
    below = 4 + (int(np.ceil(max(0.0, start[2]) / pitch)) + 2 if floor else 0)
    grid = np.pad(matrix, ((4, 4), (4, 4), (below, 4)))
    origin = start - np.array([4, 4, below]) * pitch  # centro del voxel [0,0,0]
    zi = lambda z: int(np.clip(np.floor((z - origin[2]) / pitch), 0, grid.shape[2] - 2))  # noqa: E731
    if floor:
        z0, k1 = zi(0.0), max(zi(0.0), zi(floor_top) + 3)
    shell = grid
    for it in (1, 2, 4, 7):
        g = ndimage.binary_dilation(shell, iterations=it)
        if floor:
            g[:, :, : k1 + 1] = True
        filled = ndimage.binary_fill_holes(g)
        if filled.sum() > 1.3 * g.sum():
            break
    grid = ndimage.binary_erosion(filled, iterations=it, border_value=1)
    if floor:
        footprint = grid[:, :, k1 + 1]
        grid[:, :, z0 + 1 : k1 + 1] = footprint[:, :, None]
        grid[:, :, : z0 + 1] = False
    lab, n = ndimage.label(grid)
    if n > 1:
        grid = lab == (np.bincount(lab.ravel())[1:].argmax() + 1)
    grid = np.pad(grid, 1)
    out = trimesh.voxel.ops.matrix_to_marching_cubes(grid, pitch=pitch)
    out.apply_translation(origin - pitch)
    trimesh.smoothing.filter_taubin(out, iterations=3)  # solo per togliere la "scalinatura" dei voxel
    if len(out.faces) > TARGET_FACES:
        out = _decimate(out, TARGET_FACES)
    trimesh.repair.fix_normals(out)
    return out


def crop_to_box(mesh: trimesh.Trimesh, lo: np.ndarray, hi: np.ndarray) -> trimesh.Trimesh:
    """Interseca la mesh con un box. Usa manifold3d (booleano esatto) se la mesh è valida,
    altrimenti taglia piano per piano chiudendo i tagli con trimesh."""
    box = trimesh.creation.box(bounds=[lo, hi])
    m = _to_manifold(mesh)
    if m is not None:
        out = _from_manifold(m ^ _to_manifold(box))
        if len(out.faces):
            return out
    for axis in range(3):
        for sign, value in ((1, lo[axis]), (-1, hi[axis])):
            normal = np.zeros(3)
            normal[axis] = sign
            origin = np.zeros(3)
            origin[axis] = value
            try:
                mesh = mesh.slice_plane(origin, normal, cap=True)
            except Exception:  # noqa: BLE001 - il capping può fallire su mesh molto sporche
                mesh = mesh.slice_plane(origin, normal, cap=False)
    return mesh


def mesh_to_printable(mesh: trimesh.Trimesh, progress: Progress | None = None, y_up: bool = True) -> tuple[trimesh.Trimesh, CleanupInfo]:
    """Per mesh già pronte (provider AI, glTF Y-up): niente tavolo da cercare, solo chiusura fedele."""
    return surface_to_printable(mesh, progress, y_up=y_up, find_plane=False)


def largest_component(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    parts = mesh.split(only_watertight=False)
    if len(parts) <= 1:
        return mesh
    return max(parts, key=lambda p: p.area)  # per area: un pezzo aperto grande batte un sassolino chiuso


def make_watertight(mesh: trimesh.Trimesh, info: CleanupInfo) -> trimesh.Trimesh:
    mesh.merge_vertices()
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(mesh)
    if not mesh.is_watertight:
        closed = close_holes(mesh, info)
        if closed is not None:
            info.repaired_with = "fori chiusi con superfici minime (MeshFix)"
            return closed
    m = _to_manifold(mesh)
    if m is not None and mesh.is_watertight:
        out = _from_manifold(m)
        if len(out.faces) and out.is_watertight:
            if info.repaired_with == "nessuna riparazione":
                info.repaired_with = "verificata con manifold3d"
            return out
    out = voxel_remesh(mesh)
    info.repaired_with = "ricostruita a voxel (dettagli fini ridotti)"
    m = _to_manifold(out)
    return _from_manifold(m) if m is not None else out


def voxel_remesh(mesh: trimesh.Trimesh, resolution: int = 320) -> trimesh.Trimesh:
    from scipy import ndimage

    pitch = float(mesh.extents.max()) / resolution
    matrix, start = _voxelize_surface(mesh, pitch)
    grid = ndimage.binary_closing(np.pad(matrix, 3), iterations=2)
    grid = ndimage.binary_fill_holes(grid)
    grid = np.pad(grid, 1)
    out = trimesh.voxel.ops.matrix_to_marching_cubes(grid, pitch=pitch)
    out.apply_translation(start - 4 * pitch)  # compensa il padding
    trimesh.smoothing.filter_taubin(out, iterations=3)
    out = _decimate(out, TARGET_FACES) if len(out.faces) > TARGET_FACES else out
    trimesh.repair.fix_normals(out)
    return out


def normalize_matrix(mesh: trimesh.Trimesh, size_mm: float = DEFAULT_SIZE_MM) -> np.ndarray:
    """Trasformazione che porta il lato più lungo a size_mm, centrata in XY e appoggiata su z = 0."""
    ext = float(mesh.extents.max())
    s = size_mm / ext if ext > 0 else 1.0
    lo, hi = mesh.bounds * s
    M = np.diag([s, s, s, 1.0])
    M[:3, 3] = [-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]]
    return M


def normalize(mesh: trimesh.Trimesh, size_mm: float = DEFAULT_SIZE_MM) -> trimesh.Trimesh:
    mesh.apply_transform(normalize_matrix(mesh, size_mm))
    return mesh


def finalize(mesh: trimesh.Trimesh, info: CleanupInfo, progress: Progress | None) -> tuple[trimesh.Trimesh, CleanupInfo]:
    return _finish(mesh, None, info, progress)


def _decimate(mesh: trimesh.Trimesh, faces: int) -> trimesh.Trimesh:
    """Semplificazione quadrica: toglie triangoli dove la superficie è piatta, li tiene sui dettagli.
    fast_simplification impiega meno di un secondo dove Open3D impiegava minuti (1,5 M triangoli)."""
    try:
        import fast_simplification as fs

        v, f = np.asarray(mesh.vertices, dtype=np.float32), np.asarray(mesh.faces, dtype=np.int32)
        for _ in range(4):  # su mesh "sporche" una passata si ferma prima dell'obiettivo: ripeto
            v, f = fs.simplify(v, f, target_count=int(faces))
            if len(f) <= faces * 1.1:
                break
        return trimesh.Trimesh(v, f, process=True)
    except ImportError:
        import open3d as o3d

        m = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(mesh.vertices), o3d.utility.Vector3iVector(mesh.faces))
        m = m.simplify_quadric_decimation(int(faces))
        return trimesh.Trimesh(np.asarray(m.vertices), np.asarray(m.triangles), process=True)


def _to_manifold(mesh: trimesh.Trimesh):
    import manifold3d as mf

    try:
        m = mf.Manifold(mf.Mesh(vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
                                tri_verts=np.asarray(mesh.faces, dtype=np.uint32)))
    except Exception:  # noqa: BLE001
        return None
    return m if m.status() == mf.Error.NoError and not m.is_empty() else None


def _from_manifold(m) -> trimesh.Trimesh:
    out = m.to_mesh()
    return trimesh.Trimesh(np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts), process=True)
