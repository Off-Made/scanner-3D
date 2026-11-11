"""Pulizia mesh su dati sintetici: un oggetto appoggiato su un tavolo, inclinato a caso
(come esce dalla fotogrammetria, dove gli assi sono arbitrari), con rumore e oggetti di disturbo."""
import numpy as np
import open3d as o3d
import pytest
import trimesh

from app.mesh.cleanup import mesh_to_printable, points_to_mesh
from app.mesh.report import printability


def synthetic_scene(path, seed=0):
    rng = np.random.default_rng(seed)
    # oggetto: cilindro r=1, h=2 (solo la superficie visibile: lati + coperchio, NON il fondo)
    n = 30000
    th = rng.uniform(0, 2 * np.pi, n)
    z = rng.uniform(0, 2, n)
    side = np.c_[np.cos(th), np.sin(th), z]
    r = np.sqrt(rng.uniform(0, 1, 6000))
    a = rng.uniform(0, 2 * np.pi, 6000)
    top = np.c_[r * np.cos(a), r * np.sin(a), np.full(6000, 2.0)]
    # tavolo: quadrato 8x8 a z=0
    table = np.c_[rng.uniform(-4, 4, 40000), rng.uniform(-4, 4, 40000), np.zeros(40000)]
    # disturbo: un piccolo oggetto lontano + rumore sparso
    junk = rng.normal([3, 3, 0.2], 0.1, (800, 3))
    noise = rng.uniform(-4, 4, (300, 3))
    pts = np.vstack([side, top, table, junk, noise]) + rng.normal(0, 0.004, (n + 6000 + 40000 + 800 + 300, 3))
    # rotazione e traslazione arbitrarie
    R = trimesh.transformations.random_rotation_matrix(rng.random(3))
    pts = (pts @ R[:3, :3].T) * 3.7 + [10, -5, 2]
    pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(pts))
    o3d.io.write_point_cloud(str(path), pc)


def test_object_on_table_becomes_closed_upright_solid(tmp_path):
    ply = tmp_path / "scene.ply"
    synthetic_scene(ply)
    mesh, info = points_to_mesh(str(ply), depth=8)
    rep = printability(mesh)
    assert info.plane_found
    assert rep["watertight"] and rep["windingConsistent"] and rep["components"] == 1
    # in piedi (Z-up), appoggiato a z=0, lato lungo normalizzato a 100 mm
    ex, ey, ez = mesh.extents
    assert max(mesh.extents) == pytest.approx(100, abs=0.5)
    # cilindro con altezza = diametro: anche l'altezza deve tornare ~100 mm (base ricostruita)
    assert ez == pytest.approx(100, rel=0.06)
    assert mesh.bounds[0][2] == pytest.approx(0, abs=0.01)
    # proporzioni del cilindro (diametro = altezza) entro il 10%
    assert ex / ez == pytest.approx(1, rel=0.12) and ey / ez == pytest.approx(1, rel=0.12)
    # è pieno: volume vicino a quello di un cilindro di diametro = altezza = 100 (pi*50^2*100)
    assert rep["volumeMm3"] == pytest.approx(np.pi * 50**2 * 100, rel=0.15)
    # la base è piatta: molti vertici a z ~ 0
    assert (mesh.vertices[:, 2] < 1.0).sum() > 50


def test_ai_mesh_y_up_becomes_z_up_and_closed():
    m = trimesh.creation.box(extents=[1, 3, 1])  # alto lungo Y come nei glTF
    m.faces = m.faces[:-2]  # un buco
    out, info = mesh_to_printable(m, y_up=True)
    assert out.is_watertight
    assert out.extents[2] == pytest.approx(100, abs=1)  # l'altezza ora è Z
    assert out.bounds[0][2] == pytest.approx(0, abs=0.01)


def test_too_few_points_gives_clear_error(tmp_path):
    p = tmp_path / "tiny.ply"
    o3d.io.write_point_cloud(str(p), o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.random.rand(50, 3))))
    with pytest.raises(ValueError, match="troppo povera"):
        points_to_mesh(str(p))


# --- Pulizia fedele (mesh OpenMVS): chiude i fori senza "gonfiare" la forma ---------------

from app.mesh.cleanup import close_holes, solidify, surface_to_printable, CleanupInfo  # noqa: E402


def box_with_slot():
    """Cubo 40 mm con una fessura larga 4 mm e profonda 20 mm dall'alto (un dettaglio fine)."""
    import manifold3d as mf

    cube = trimesh.creation.box(extents=[40, 40, 40])
    slot = trimesh.creation.box(extents=[4, 50, 20], transform=trimesh.transformations.translation_matrix([0, 0, 10.01]))
    to_m = lambda m: mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32),  # noqa: E731
                                         tri_verts=np.asarray(m.faces, np.uint32)))
    out = (to_m(cube) - to_m(slot)).to_mesh()
    m = trimesh.Trimesh(np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts))
    # suddivido per avere triangoli piccoli, come in una mesh vera
    v, f = trimesh.remesh.subdivide_to_size(m.vertices, m.faces, max_edge=2.0)
    return trimesh.Trimesh(v, f)


def punch_holes(mesh, centers, radius):
    keep = np.ones(len(mesh.faces), bool)
    for c in centers:
        keep &= np.linalg.norm(mesh.triangles_center - c, axis=1) > radius
    mesh = mesh.copy()
    mesh.update_faces(keep)
    mesh.remove_unreferenced_vertices()
    return mesh


def test_close_holes_keeps_fine_slot():
    m = punch_holes(box_with_slot(), [[20, 10, -10], [-10, 20, 5]], radius=4)
    assert not m.is_watertight
    out = close_holes(m, CleanupInfo())
    assert out is not None and out.is_watertight
    # il centro della fessura deve restare VUOTO (la vecchia chiusura a voxel lo riempiva)
    assert not out.contains([[0, 0, 12]])[0]
    assert out.contains([[10, 0, 12]])[0]  # accanto alla fessura è pieno


def test_close_holes_sphere_volume_preserved():
    s = trimesh.creation.icosphere(subdivisions=4, radius=50)
    m = punch_holes(s, [[50, 0, 0], [0, -50, 0], [0, 0, 50]], radius=8)
    info = CleanupInfo()
    out = close_holes(m, info)
    assert out is not None and out.is_watertight
    assert out.volume == pytest.approx(s.volume, rel=0.02)
    assert 0 < info.filled_pct < 10  # dichiara quanta superficie ha dovuto inventare


def test_voxel_fallback_keeps_slot():
    """Il fallback a voxel (prima: dilatazione fino a 11 voxel a risoluzione 200) chiudeva le fessure."""
    m = punch_holes(box_with_slot(), [[20, 10, -10]], radius=4)
    out = solidify(m, resolution=384)
    assert out.is_watertight
    assert not out.contains([[0, 0, 12]])[0]  # anche il fallback ora non deve chiudere la fessura


def scene_mesh(seed=0):
    """Come esce da ReconstructMesh: oggetto (con fessura) saldato a un tavolo, fondo aperto,
    assi arbitrari, un oggetto di disturbo sul tavolo."""
    rng = np.random.default_rng(seed)
    obj = box_with_slot()
    obj.apply_translation([0, 0, 20])  # appoggiato a z = 0
    obj.update_faces(obj.triangles_center[:, 2] > 0.5)  # tolgo il fondo (mai fotografato)
    obj.remove_unreferenced_vertices()
    obj = punch_holes(obj, [[20, 0, 30]], radius=3)  # un buco sul fianco
    table = trimesh.creation.box(extents=[200, 200, 0.2], transform=trimesh.transformations.translation_matrix([0, 0, -0.1]))
    v, f = trimesh.remesh.subdivide_to_size(table.vertices, table.faces, max_edge=8.0)
    table = trimesh.Trimesh(v, f)
    junk = trimesh.creation.icosphere(2, radius=5)
    junk.apply_translation([70, 70, 5])
    scene = trimesh.util.concatenate([obj, table, junk])
    R = trimesh.transformations.random_rotation_matrix(rng.random(3))
    scene.apply_transform(R)
    scene.apply_scale(0.037)
    scene.apply_translation([3, -2, 1])
    return scene


def test_surface_to_printable_upright_closed_and_faithful():
    mesh, info = surface_to_printable(scene_mesh())
    rep = printability(mesh)
    assert info.plane_found
    assert rep["watertight"] and rep["components"] == 1
    assert max(mesh.extents) == pytest.approx(100, abs=0.5)
    assert mesh.bounds[0][2] == pytest.approx(0, abs=0.01)
    # il cubo può uscire ruotato attorno a Z: la scala la ricavo dall'altezza (40 mm in origine)
    s = mesh.extents[2] / 40
    assert 40 * s * 0.98 <= max(mesh.extents[:2]) <= 40 * s * 1.45  # in pianta tra 40 e 40·√2
    # fessura conservata: larga 4 mm, profonda 20 mm dall'alto, passa per il centro
    assert not mesh.contains([[0, 0, mesh.extents[2] - 8 * s]])[0]
    assert rep["volumeMm3"] == pytest.approx((40**3 - 4 * 40 * 20) * s**3, rel=0.04)
    assert rep["fidelity"]["filledPct"] < 20
