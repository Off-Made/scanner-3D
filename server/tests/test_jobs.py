import json
import io
from pathlib import Path
import time

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.providers.base import Provider, ProviderError
from app.providers.mock import MockProvider


class FailingProvider(Provider):
    id = "fail"
    label = "Fallisce"

    def reconstruct(self, photos, ctx):
        ctx.progress(10, "provo")
        raise ProviderError("Messaggio chiaro per l'utente.")


class MissingLibProvider(Provider):
    """Simula Open3D installato ma senza la sua libreria di sistema (il caso del Codespace)."""
    id = "missing"
    label = "Manca libreria"

    def reconstruct(self, photos, ctx):
        raise ImportError("libusb-1.0.so.0: cannot open shared object file: No such file or directory")


def jpeg(w=800, h=600, seed=0) -> bytes:
    rng = np.random.default_rng(seed)
    buf = io.BytesIO()
    Image.fromarray(rng.integers(0, 255, (h, w, 3), dtype=np.uint8)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def client(tmp_path):
    s = Settings(access_pin="123456", session_secret=b"x", data_dir=tmp_path)
    app = create_app(s, providers={"mock": MockProvider(seconds=0.2), "fail": FailingProvider(),
                                          "missing": MissingLibProvider()})
    c = TestClient(app)
    tok = c.post("/api/auth", json={"pin": "123456"}).json()["token"]
    c.headers.update({"Authorization": f"Bearer {tok}"})
    return c


def wait_done(c, job_id, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "error", "cancelled"):
            return j
        time.sleep(0.1)
    raise AssertionError("timeout")


def test_full_job_flow_returns_printable_glb(client):
    assert any(p["id"] == "mock" for p in client.get("/api/providers").json())
    job = client.post("/api/jobs", json={"provider": "mock", "name": "Tazza"}).json()
    for i in range(3):
        r = client.post(f"/api/jobs/{job['id']}/photos", files={"photo": (f"{i}.jpg", jpeg(seed=i), "image/jpeg")})
        assert r.status_code == 200 and r.json()["photos"] == i + 1
    assert client.get(f"/api/jobs/{job['id']}/model.glb").status_code == 409  # non ancora pronto
    assert client.post(f"/api/jobs/{job['id']}/start").json()["status"] == "queued"
    done = wait_done(client, job["id"])
    assert done["status"] == "done", done
    assert done["report"]["watertight"] and done["report"]["printable"]
    r = client.get(f"/api/jobs/{job['id']}/model.glb")
    assert r.status_code == 200
    mesh = trimesh.load(io.BytesIO(r.content), file_type="glb", force="mesh")
    assert mesh.is_watertight and max(mesh.extents) == pytest.approx(100, abs=0.5)
    # le foto vengono cancellate dopo il successo (spazio disco)
    assert client.post(f"/api/jobs/{job['id']}/photos", files={"photo": ("x.jpg", jpeg(), "image/jpeg")}).status_code == 409
    assert client.delete(f"/api/jobs/{job['id']}").json() == {"ok": True}
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404


def test_provider_error_is_reported_to_user(client):
    job = client.post("/api/jobs", json={"provider": "fail"}).json()
    client.post(f"/api/jobs/{job['id']}/photos", files={"photo": ("a.jpg", jpeg(), "image/jpeg")})
    client.post(f"/api/jobs/{job['id']}/start")
    done = wait_done(client, job["id"])
    assert done["status"] == "error" and done["error"] == "Messaggio chiaro per l'utente."


def test_missing_system_library_is_named_in_the_error(client):
    job = client.post("/api/jobs", json={"provider": "missing"}).json()
    client.post(f"/api/jobs/{job['id']}/photos", files={"photo": ("a.jpg", jpeg(), "image/jpeg")})
    client.post(f"/api/jobs/{job['id']}/start")
    done = wait_done(client, job["id"])
    assert done["status"] == "error"
    assert "libusb-1.0.so.0" in done["error"] and "npm run doctor" in done["error"]


def test_upload_validation(client):
    job = client.post("/api/jobs", json={"provider": "mock"}).json()
    r = client.post(f"/api/jobs/{job['id']}/photos", files={"photo": ("a.txt", b"not an image", "text/plain")})
    assert r.status_code == 400 and "immagine" in r.json()["detail"]
    r = client.post(f"/api/jobs/{job['id']}/photos", files={"photo": ("s.jpg", jpeg(100, 100), "image/jpeg")})
    assert r.status_code == 400 and "piccola" in r.json()["detail"]
    assert client.post(f"/api/jobs/{job['id']}/start").status_code == 400  # zero foto
    assert client.post("/api/jobs", json={"provider": "boh"}).status_code == 400


def test_max_40_photos(client, tmp_path):
    job = client.post("/api/jobs", json={"provider": "mock"}).json()
    small = jpeg(400, 400)
    for _ in range(40):
        assert client.post(f"/api/jobs/{job['id']}/photos", files={"photo": ("a.jpg", small, "image/jpeg")}).status_code == 200
    r = client.post(f"/api/jobs/{job['id']}/photos", files={"photo": ("a.jpg", small, "image/jpeg")})
    assert r.status_code == 400 and "40" in r.json()["detail"]


def test_photos_are_resized_to_2400(client, tmp_path):
    job = client.post("/api/jobs", json={"provider": "mock"}).json()
    client.post(f"/api/jobs/{job['id']}/photos", files={"photo": ("big.jpg", jpeg(4032, 3024), "image/jpeg")})
    saved = next((tmp_path / "jobs" / job["id"] / "photos").glob("*.jpg"))
    assert max(Image.open(saved).size) == 2400


def test_jobs_require_token(tmp_path):
    s = Settings(access_pin="123456", session_secret=b"x", data_dir=tmp_path)
    c = TestClient(create_app(s, providers={"mock": MockProvider(0.1)}))
    assert c.post("/api/jobs", json={"provider": "mock"}).status_code == 401
    assert c.get("/api/providers").status_code == 401


def test_relative_data_dir_is_made_absolute(tmp_path, monkeypatch):
    from app.jobs import JobManager
    monkeypatch.chdir(tmp_path)
    jm = JobManager(Path("rel-data"), {"mock": MockProvider(0.1)})
    assert jm.dir.is_absolute() and jm.dir == (tmp_path / "rel-data" / "jobs").resolve()


def test_photo_view_angles_are_stored_outside_the_photo_folder(client, tmp_path):
    job = client.post("/api/jobs", json={"provider": "mock"}).json()
    client.post(f"/api/jobs/{job['id']}/photos", files={"photo": ("a.jpg", jpeg(800, 600), "image/jpeg")},
                data={"angle": "-90", "ring": "1"})
    client.post(f"/api/jobs/{job['id']}/photos", files={"photo": ("b.jpg", jpeg(800, 600), "image/jpeg")})
    client.post(f"/api/jobs/{job['id']}/photos", files={"photo": ("c.jpg", jpeg(800, 600), "image/jpeg")},
                data={"angle": "nan"})
    d = tmp_path / "jobs" / job["id"]
    views = json.loads((d / "views.json").read_text())
    assert views == {"001.jpg": {"angle": 270.0, "ring": 1}}  # senza angolo o con angolo non valido: nessuna vista
    assert [p.name for p in (d / "photos").iterdir()] == ["001.jpg", "002.jpg", "003.jpg"]


def test_failed_job_log_can_be_downloaded(client):
    job = client.post("/api/jobs", json={"provider": "missing"}).json()
    client.post(f"/api/jobs/{job['id']}/photos", files={"photo": ("a.jpg", jpeg(), "image/jpeg")})
    client.post(f"/api/jobs/{job['id']}/start")
    wait_done(client, job["id"])
    r = client.get(f"/api/jobs/{job['id']}/log")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert "stato error" in r.text and "error.txt" in r.text and "libusb" in r.text
    assert client.get("/api/jobs/nonesiste/log").status_code == 404
