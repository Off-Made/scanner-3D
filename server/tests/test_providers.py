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
