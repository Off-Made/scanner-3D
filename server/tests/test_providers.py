from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image

from app.providers.ai_hf import HuggingFaceProvider, build_kwargs, find_mesh_file
from app.providers.base import ProviderError, RunContext
from app.providers.photogrammetry import colmap_gpu_and_thread_options


def ctx(tmp_path):
    return RunContext(work_dir=tmp_path, report_progress=lambda p, s: None, is_cancelled=lambda: False)


def test_colmap_option_names_differ_between_v3_and_v4():
    f4, m4 = colmap_gpu_and_thread_options(4, 4, 8)
    assert "--FeatureExtraction.num_threads" in f4 and "4" in f4 and "--FeatureMatching.use_gpu" in m4
    f3, m3 = colmap_gpu_and_thread_options(3, 4, 8)
    assert "--SiftExtraction.use_gpu" in f3 and "--SiftMatching.num_threads" in m3


API = {"named_endpoints": {"/shape_generation": {"parameters": [
    {"parameter_name": "caption", "component": "Textbox", "parameter_has_default": False},
    {"parameter_name": "image", "component": "Image", "parameter_has_default": False},
    {"parameter_name": "steps", "component": "Slider", "parameter_has_default": True},
]}}}


def test_build_kwargs_puts_photo_in_first_image_param():
    kw = build_kwargs(API, "/shape_generation", "FILE")
    assert kw == {"caption": None, "image": "FILE"}
    with pytest.raises(ProviderError, match="non espone"):
        build_kwargs(API, "/altro", "FILE")


def test_find_mesh_file_in_nested_results(tmp_path):
    glb = tmp_path / "out.glb"
    glb.write_bytes(b"x")
    assert find_mesh_file(({"value": str(glb)}, "html", 3)) == str(glb)
    assert find_mesh_file(["/no/such.glb", 1]) is None


class FakeClient:
    """Simula gradio_client.Client: restituisce un glb generato al volo."""

    def __init__(self, out_dir: Path):
        self.out = out_dir
        self.called = None

    def view_api(self, **_):
        return API

    def predict(self, api_name, **kwargs):
        self.called = (api_name, kwargs)
        path = self.out / "gen.glb"
        trimesh.creation.icosphere(subdivisions=3).export(path)
        return ({"value": str(path)}, "<html>", 123)


def test_hf_provider_with_fake_client(tmp_path):
    photos = []
    for i, blur in enumerate([0, 1]):
        arr = np.random.default_rng(i).integers(0, 255, (400, 400, 3), dtype=np.uint8)
        p = tmp_path / f"{i}.jpg"
        im = Image.fromarray(arr)
        if blur:
            im = im.resize((40, 40)).resize((400, 400))  # foto sfocata
        im.save(p)
        photos.append(p)
    fake = FakeClient(tmp_path)
    prov = HuggingFaceProvider(client_factory=lambda space, token: fake)
    mesh, steps = prov.reconstruct(photos, ctx(tmp_path))
    assert mesh.is_watertight and max(mesh.extents) == pytest.approx(100, abs=1)
    assert steps[0] == "Foto usata: 0.jpg"  # ha scelto la foto nitida
    assert fake.called[0] == "/shape_generation"


def test_hf_provider_translates_quota_errors(tmp_path):
    class Boom(FakeClient):
        def predict(self, **_):
            raise RuntimeError("You have exceeded your ZeroGPU quota")
    p = tmp_path / "a.jpg"
    Image.new("RGB", (400, 400)).save(p)
    prov = HuggingFaceProvider(client_factory=lambda *a: Boom(tmp_path))
    with pytest.raises(ProviderError, match="Quota"):
        prov.reconstruct([p], ctx(tmp_path))


def test_hf_client_kwargs_match_real_gradio_signature(monkeypatch):
    """Il client finto non controlla i nomi dei parametri: verifichiamo quelli veri (senza rete)."""
    import inspect

    import gradio_client

    seen = {}

    def fake_init(self, *args, **kwargs):
        inspect.signature(real_init).bind(self, *args, **kwargs)  # TypeError se un nome non esiste
        seen.update(kwargs)

    real_init = gradio_client.Client.__init__
    monkeypatch.setattr(gradio_client.Client, "__init__", fake_init)
    HuggingFaceProvider()._client()
    assert "token" in seen


def test_describe_import_error_names_missing_system_library():
    from app.deps import describe_import_error
    msg = describe_import_error(ImportError("libusb-1.0.so.0: cannot open shared object file: No such file"))
    assert "libreria di sistema" in msg and "libusb-1.0.so.0" in msg
    assert "«open3d»" in describe_import_error(ModuleNotFoundError("No module named 'open3d'", name="open3d"))


def test_ai_provider_unavailable_when_mesh_libraries_fail(monkeypatch):
    from app import deps
    monkeypatch.setattr(deps, "check_module", lambda m: "manca una libreria di sistema (libGL.so.1)" if m == "open3d" else None)
    ok, why = HuggingFaceProvider().available()
    assert not ok and "open3d" in why and "libGL.so.1" in why


def test_photogrammetry_reports_missing_openmvs_libraries(monkeypatch, tmp_path):
    from app.providers import photogrammetry as ph
    for name in ("colmap", "InterfaceCOLMAP", "DensifyPointCloud"):
        (tmp_path / name).write_text("")
    monkeypatch.setattr(ph, "IS_WIN", False)
    monkeypatch.setattr(ph, "colmap_bin", lambda: tmp_path / "colmap")
    monkeypatch.setattr(ph, "omvs", lambda tool: tmp_path / tool)
    monkeypatch.setattr(ph, "missing_shared_libs", lambda b, d: ("libboost_iostreams.so.1.83.0",))
    ok, why = ph.PhotogrammetryProvider().available()
    assert not ok and "libboost_iostreams" in why and "setup-linux-tools.sh" in why


def test_failed_step_message_includes_log_tail(tmp_path):
    import sys
    c = RunContext(work_dir=tmp_path, report_progress=lambda p, s: None, is_cancelled=lambda: False,
                   log_file=tmp_path / "pipeline.log")
    with pytest.raises(ProviderError) as e:
        c.run([sys.executable, "-c", "print('ERRORE: immagini non valide'); raise SystemExit(2)"],
              band=(0, 10), step="Prova", expected_s=1)
    assert "codice 2" in str(e.value) and "immagini non valide" in str(e.value)


def test_colmap_resolution_and_low_texture_options():
    f4, _ = colmap_gpu_and_thread_options(4, 4, 4, 2000)
    assert f4[f4.index("--FeatureExtraction.max_image_size") + 1] == "2000"
    assert "--SiftExtraction.domain_size_pooling" in f4
    f3, _ = colmap_gpu_and_thread_options(3, 4, 4, 2000)
    assert "--SiftExtraction.max_image_size" in f3


class FakeRun:
    """ctx.run finto: registra i programmi e crea i file che produrrebbero (o fallisce a comando)."""

    def __init__(self, w, fail=()):
        self.w, self.fail, self.calls = w, set(fail), []

    def __call__(self, cmd, band, step, expected_s, cwd=None, env=None):
        tool = Path(str(cmd[0])).stem
        self.calls.append(tool)
        if tool in self.fail:
            raise ProviderError(f"{tool} fallito")
        out = {"ReconstructMesh": "scene_dense_mesh.ply", "RefineMesh": "scene_dense_mesh_refine.ply"}.get(tool)
        if out:
            (self.w / out).write_text("")


@pytest.mark.parametrize("fail, refine_present, expected, note", [
    ((), True, "scene_dense_mesh_refine.ply", "affinata"),
    (("RefineMesh",), True, "scene_dense_mesh.ply", "Affinamento non riuscito"),
    ((), False, "scene_dense_mesh.ply", "manca RefineMesh"),
    (("ReconstructMesh",), True, None, "nuvola di punti"),
])
def test_openmvs_mesh_fallback_chain(monkeypatch, tmp_path, fail, refine_present, expected, note):
    from app.providers import photogrammetry as ph
    for name in ("ReconstructMesh", *(["RefineMesh"] if refine_present else [])):
        (tmp_path / name).write_text("")
    monkeypatch.setattr(ph, "omvs", lambda tool: tmp_path / tool)
    c = ctx(tmp_path)
    fake = FakeRun(tmp_path, fail)
    monkeypatch.setattr(c, "run", fake)
    surface, notes = ph.PhotogrammetryProvider().mesh_from_dense(c, tmp_path, [], None, 30)
    assert (surface.name if surface else None) == expected
    assert any(note in n for n in notes)
    if "ReconstructMesh" in fail:
        assert "RefineMesh" not in fake.calls  # niente affinamento senza superficie


# --- AI multi-vista ---------------------------------------------------------------------------

from app.providers.ai_hf import pick_views  # noqa: E402

API_MV = {"named_endpoints": {"/shape_generation": {"parameters": [
    {"parameter_name": "caption", "component": "Textbox", "parameter_has_default": False},
    {"parameter_name": "image", "component": "Image", "parameter_has_default": True},
    *({"parameter_name": f"mv_image_{v}", "component": "Image", "parameter_has_default": True}
      for v in ("front", "back", "left", "right")),
    {"parameter_name": "steps", "component": "Slider", "parameter_has_default": True},
    {"parameter_name": "octree_resolution", "component": "Slider", "parameter_has_default": True},
]}}}


def test_build_kwargs_maps_views_and_known_overrides():
    kw = build_kwargs(API_MV, "/shape_generation", {"front": "F", "back": "B", "right": "R"},
                      {"octree_resolution": 380, "parametro_inesistente": 1})
    assert kw == {"caption": None, "mv_image_front": "F", "mv_image_back": "B", "mv_image_right": "R",
                  "octree_resolution": 380}
    # endpoint a foto singola: la vista frontale va nel parametro immagine
    assert build_kwargs(API, "/shape_generation", {"front": "F", "back": "B"}) == {"caption": None, "image": "F"}


def fake_photos(n):
    return [Path(f"{i + 1:03d}.jpg") for i in range(n)]


def test_pick_views_from_compass_angles():
    photos = fake_photos(12)
    views = {p.name: {"angle": i * 30.0, "ring": 0} for i, p in enumerate(photos)}
    v = pick_views(photos, views, sharp=lambda p: 1.0)
    assert {k: p.name for k, p in v.items()} == {"front": "001.jpg", "right": "004.jpg", "back": "007.jpg", "left": "010.jpg"}
    v = pick_views(photos, views, sharp=lambda p: 1.0, swap_lr=True)
    assert v["left"].name == "004.jpg" and v["right"].name == "010.jpg"


def test_pick_views_prefers_side_ring_and_sharp_photos():
    photos = fake_photos(4)
    views = {"001.jpg": {"angle": 0, "ring": 0}, "002.jpg": {"angle": 92, "ring": 1},
             "003.jpg": {"angle": 80, "ring": 0}, "004.jpg": {"angle": 100, "ring": 0}}
    sharp = {"003.jpg": 1.0, "004.jpg": 5.0}
    v = pick_views(photos, views, sharp=lambda p: sharp.get(p.name, 1.0))
    assert v["right"].name == "004.jpg"  # stesso anello dell'oggetto, la più nitida entro ±30°
    assert "back" not in v and "left" not in v  # angoli non coperti: meglio niente che una vista sbagliata


def test_pick_views_without_compass_uses_only_front_and_back():
    v = pick_views(fake_photos(12), {}, sharp=lambda p: 1.0)
    assert {k: p.name for k, p in v.items()} == {"front": "001.jpg", "back": "007.jpg"}
    assert set(pick_views(fake_photos(2), {}, sharp=lambda p: 1.0)) == {"front"}


def test_hf_provider_multiview_with_fake_client(tmp_path):
    photos = []
    for i in range(8):
        p = tmp_path / f"{i + 1:03d}.jpg"
        Image.fromarray(np.random.default_rng(i).integers(0, 255, (200, 200, 3), dtype=np.uint8)).save(p)
        photos.append(p)

    class MV(FakeClient):
        def view_api(self, **_):
            return API_MV
    fake = MV(tmp_path)
    c = ctx(tmp_path)
    c.photo_views = {p.name: {"angle": i * 45.0, "ring": 0} for i, p in enumerate(photos)}
    mesh, steps = HuggingFaceProvider(client_factory=lambda *a: fake).reconstruct(photos, c)
    kw = fake.called[1]
    assert {"mv_image_front", "mv_image_back", "mv_image_left", "mv_image_right"} <= set(kw)
    assert "image" not in kw
    assert steps[0].startswith("Viste usate:") and "fronte 001.jpg" in steps[0]
    assert mesh.is_watertight


def write_images_bin(model_dir: Path, count: int):
    import struct
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "images.bin").write_bytes(struct.pack("<Q", count) + b"\0" * 64)


def test_registered_images_read_from_colmap_model(tmp_path):
    from app.providers.photogrammetry import registered_images
    write_images_bin(tmp_path / "0", 27)
    assert registered_images(tmp_path / "0") == 27
    assert registered_images(tmp_path / "manca") == 0


@pytest.mark.parametrize("registered, total, ok", [(40, 40, True), (20, 40, True), (19, 40, False), (3, 30, False), (8, 12, True)])
def test_too_few_registered_photos_stops_with_clear_message(registered, total, ok):
    from app.providers.photogrammetry import check_registration
    if ok:
        check_registration(registered, total)
    else:
        with pytest.raises(ProviderError, match=f"{registered} foto su {total}"):
            check_registration(registered, total)


def test_unreliable_model_is_flagged_in_report():
    from app.mesh.report import printability
    m = trimesh.creation.icosphere(2, radius=50)
    m.metadata["fidelity"] = {"filledPct": 0.0, "baseAdded": False, "deviationMm": 13.4, "method": "x"}
    check = next(c for c in printability(m)["checks"] if c["id"] == "fidelity")
    assert not check["ok"] and "non è affidabile" in check["hint"]
