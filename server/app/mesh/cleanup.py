"""Pulizia della ricostruzione e preparazione di una mesh stampabile.

Da nuvola di punti (fotogrammetria):
  rumore -> piano del tavolo (RANSAC) -> oggetto principale (DBSCAN) -> allineamento Z-up
  -> Poisson -> taglio sul piano e sul riquadro dell'oggetto con chiusura dei tagli
  -> componente principale -> chiusura garantita (manifold3d, fallback voxel) -> normalizzazione

Da mesh (provider AI): componente principale -> chiusura -> normalizzazione.

Convenzione: Z verso l'alto, unità = millimetri (scala arbitraria finché l'utente non
imposta una misura reale), oggetto centrato in XY e appoggiato su z = 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import trimesh

Progress = Callable[[str], None]
DEFAULT_SIZE_MM = 100.0
TARGET_FACES = 150_000


@dataclass
class CleanupInfo:
    steps: list[str] = field(default_factory=list)
    plane_found: bool = False
    repaired_with: str = "nessuna riparazione"

    def log(self, msg: str, progress: Progress | None):
        self.steps.append(msg)
        if progress:
            progress(msg)


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


def points_to_mesh(ply_path: str, progress: Progress | None = None, depth: int = 9) -> tuple[trimesh.Trimesh, CleanupInfo]:
    import open3d as o3d

    info = CleanupInfo()
    pcd = o3d.io.read_point_cloud(str(ply_path))
    if len(pcd.points) < 1000:
        raise ValueError("Nuvola di punti troppo povera: servono foto più nitide e più sovrapposte.")
    diag = float(np.linalg.norm(pcd.get_max_bound() - pcd.get_min_bound()))

    pcd = pcd.voxel_down_sample(diag / 600)
    pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    info.log(f"Rumore rimosso: {len(pcd.points):,} punti", progress)

    # --- piano del tavolo -------------------------------------------------
    T = np.eye(4)
    plane_model, inliers = pcd.segment_plane(distance_threshold=diag * 0.006, ransac_n=3, num_iterations=2000)
    if len(inliers) > 0.12 * len(pcd.points):
        a, b, c, d = plane_model
        normal = np.array([a, b, c])
        rest = pcd.select_by_index(inliers, invert=True)
        dist = (np.asarray(rest.points) @ normal + d) / np.linalg.norm(normal)
        if np.median(dist) < 0:  # l'oggetto deve stare dal lato positivo della normale
            normal, d, dist = -normal, -d, -dist
        keep = np.where(dist > diag * 0.008)[0]  # via il tavolo e tutto ciò che sta sotto
        pcd = rest.select_by_index(keep)
        # dopo la rotazione (normale -> +Z) i punti del piano hanno z = -d/|n|: li porto a z = 0
        T = _rotation_to_z(normal)
        T[2, 3] = d / np.linalg.norm(normal)
        info.plane_found = True
        info.log("Piano di appoggio trovato e rimosso", progress)
    else:
        info.log("Nessun piano di appoggio evidente", progress)

    # --- oggetto principale -------------------------------------------------
    labels = np.array(pcd.cluster_dbscan(eps=diag * 0.02, min_points=12))
    if labels.max() >= 0:
        main = np.bincount(labels[labels >= 0]).argmax()
        pcd = pcd.select_by_index(np.where(labels == main)[0])
    info.log(f"Oggetto isolato: {len(pcd.points):,} punti", progress)
    if len(pcd.points) < 500:
        raise ValueError("Non riesco a isolare l'oggetto dallo sfondo. Prova con uno sfondo più uniforme.")

    pcd.transform(T)
    pts = np.asarray(pcd.points)
    if info.plane_found:
        pts_min_z = 0.0
    else:
        pts_min_z = float(pts[:, 2].min())

    # --- superficie (Poisson) -------------------------------------------------
    pcd.estimate_normals(o3d.geometry.KDTreeSearchParamKNN(30))
    pcd.orient_normals_consistent_tangent_plane(20)
    centroid = pts.mean(axis=0)
    nrm = np.asarray(pcd.normals)
    if np.mean(np.einsum("ij,ij->i", nrm, pts - centroid)) < 0:  # normali verso l'esterno
        pcd.normals = o3d.utility.Vector3dVector(-nrm)
    mesh_o3d, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=depth)
    # Poisson "inventa" superficie lontano dai punti (una bolla chiusa attorno all'oggetto).
    # Tolgo i vertici lontani dal punto reale più vicino. Uso la distanza e non la densità:
    # una zona fotografata poco (pochi punti) è comunque vera e non va eliminata.
    from scipy.spatial import cKDTree

    tree = cKDTree(pts)
    spacing = float(np.percentile(tree.query(pts, k=2)[0][:, 1], 95))
    verts = np.asarray(mesh_o3d.vertices)
    far = tree.query(verts, k=1)[0] > max(spacing * 4, diag * 0.004)
    mesh_o3d.remove_vertices_by_mask(far)
    mesh = trimesh.Trimesh(np.asarray(mesh_o3d.vertices), np.asarray(mesh_o3d.triangles), process=True)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    margin = (hi - lo) * 0.03
    inside = np.all((mesh.vertices >= lo - margin) & (mesh.vertices <= hi + margin), axis=1)
    if info.plane_found:
        inside &= mesh.vertices[:, 2] >= 0
    mesh.update_faces(np.all(inside[mesh.faces], axis=1))
    mesh.remove_unreferenced_vertices()
    info.log(f"Superficie ricostruita: {len(mesh.faces):,} triangoli", progress)

    # Solido chiuso per costruzione: voxel + pavimento temporaneo sul piano del tavolo.
    # le pareti si fermano un po' sopra il tavolo (tavolo rimosso con margine + bordo a bassa
    # densità): la base va ricostruita fino a z = 0
    floor_top = float(mesh.vertices[:, 2].min()) if info.plane_found else None
    mesh = solidify(mesh, floor_top=floor_top)
    info.repaired_with = "solidificata a voxel con base piatta" if info.plane_found else "solidificata a voxel"
    info.log("Volume interno riempito, base piatta", progress)
    return finalize(mesh, info, progress)


def solidify(mesh: trimesh.Trimesh, resolution: int = 200, floor_top: float | None = None) -> trimesh.Trimesh:
    """Superficie (anche aperta sul fondo) -> solido chiuso.

    1. voxelizza la superficie e chiude le piccole fessure (dilatazione)
    2. se c'è il piano: pavimento temporaneo da sotto z = 0 fino a `floor_top` (dove finiscono
       le pareti), così il fondo aperto diventa una cavità chiusa
    3. riempie l'interno, toglie il pavimento e ricostruisce la base estrudendo verso z = 0
       la sezione dell'oggetto appena sopra il pavimento
    4. estrae la superficie (marching cubes), leviga e semplifica
    """
    floor = floor_top is not None
    from scipy import ndimage

    pitch = float(mesh.extents.max()) / resolution
    vox = mesh.voxelized(pitch)
    # in basso servono abbastanza strati da arrivare fino a z = 0 (dove va ricostruita la base)
    below = 4 + (int(np.ceil(max(0.0, vox.translation[2]) / pitch)) + 2 if floor else 0)
    grid = np.pad(vox.matrix, ((4, 4), (4, 4), (below, 4)))
    origin = vox.translation - np.array([4, 4, below]) * pitch  # centro del voxel [0,0,0]
    zi = lambda z: int(np.clip(np.floor((z - origin[2]) / pitch), 0, grid.shape[2] - 2))  # noqa: E731
    if floor:
        z0, k1 = zi(0.0), max(zi(0.0), zi(floor_top) + 3)
    shell = grid
    # Se nella superficie c'è un buco, il riempimento "esce" e l'interno resta vuoto:
    # allora chiudo le fessure in modo via via più deciso finché l'interno si riempie.
    for it in (2, 4, 7, 11):
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
    # tengo solo la parte connessa più grande
    lab, n = ndimage.label(grid)
    if n > 1:
        grid = lab == (np.bincount(lab.ravel())[1:].argmax() + 1)
    grid = np.pad(grid, 1)
    out = trimesh.voxel.ops.matrix_to_marching_cubes(grid, pitch=pitch)
    out.apply_translation(origin - pitch)
    trimesh.smoothing.filter_taubin(out, iterations=12)
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
    """Per mesh già pronte (provider AI, glTF Y-up)."""
    info = CleanupInfo()
    if y_up:  # glTF è Y-up: ruoto per avere Z-up come gli slicer
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    if len(mesh.faces) > TARGET_FACES:
        mesh = _decimate(mesh, TARGET_FACES)
    info.log(f"Mesh ricevuta: {len(mesh.faces):,} triangoli", progress)
    return finalize(mesh, info, progress)


def finalize(mesh: trimesh.Trimesh, info: CleanupInfo, progress: Progress | None) -> tuple[trimesh.Trimesh, CleanupInfo]:
    mesh = largest_component(mesh)
    mesh = make_watertight(mesh, info)
    info.log(f"Mesh chiusa ({info.repaired_with})", progress)
    mesh = normalize(mesh)
    return mesh, info


def largest_component(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    parts = mesh.split(only_watertight=False)
    if len(parts) <= 1:
        return mesh
    return max(parts, key=lambda p: (abs(p.volume) if p.is_watertight else 0, p.area))


def make_watertight(mesh: trimesh.Trimesh, info: CleanupInfo) -> trimesh.Trimesh:
    mesh.merge_vertices()
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(mesh)
    if not mesh.is_watertight:
        trimesh.repair.fill_holes(mesh)
    m = _to_manifold(mesh)
    if m is not None and mesh.is_watertight:
        out = _from_manifold(m)
        if len(out.faces) and out.is_watertight:
            info.repaired_with = "verificata con manifold3d" if info.repaired_with == "nessuna riparazione" else info.repaired_with
            return out
    # fallback robusto: voxelizzazione piena + marching cubes = superficie chiusa per costruzione
    out = voxel_remesh(mesh)
    info.repaired_with = "ricostruita a voxel (fori chiusi)"
    m = _to_manifold(out)
    return _from_manifold(m) if m is not None else out


def voxel_remesh(mesh: trimesh.Trimesh, resolution: int = 160) -> trimesh.Trimesh:
    from scipy import ndimage

    pitch = float(mesh.extents.max()) / resolution
    vox = mesh.voxelized(pitch)
    grid = ndimage.binary_closing(vox.matrix, iterations=2)
    grid = ndimage.binary_fill_holes(grid)
    grid = np.pad(grid, 1)
    out = trimesh.voxel.ops.matrix_to_marching_cubes(grid, pitch=pitch)
    out.apply_translation(vox.translation - pitch)  # compensa il padding
    trimesh.smoothing.filter_taubin(out, iterations=10)
    out = _decimate(out, TARGET_FACES) if len(out.faces) > TARGET_FACES else out
    trimesh.repair.fix_normals(out)
    return out


def normalize(mesh: trimesh.Trimesh, size_mm: float = DEFAULT_SIZE_MM) -> trimesh.Trimesh:
    """Lato più lungo = size_mm, centrata in XY, appoggiata su z = 0."""
    ext = float(mesh.extents.max())
    if ext > 0:
        mesh.apply_scale(size_mm / ext)
    lo, hi = mesh.bounds
    mesh.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    return mesh


def _decimate(mesh: trimesh.Trimesh, faces: int) -> trimesh.Trimesh:
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
