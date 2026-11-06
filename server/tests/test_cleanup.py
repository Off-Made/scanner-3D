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
