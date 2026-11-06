"""API Scan3D (FastAPI).

Avvio in locale (dalla radice):  npm run dev
oppure:  server\\.venv\\Scripts\\python -m uvicorn app.main:app --app-dir server --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth import PinRateLimiter, check_pin, client_ip, issue_token, verify_token
from .config import Settings
from .imaging import BadImage, save_normalized
from .jobs import JobManager
from .providers import default_providers
from .providers.base import Provider

PUBLIC_PATHS = {"/api/health", "/api/auth"}


class PinIn(BaseModel):
    pin: str


class JobIn(BaseModel):
    provider: str = "photo"
    name: str = Field(default="Scansione", max_length=80)


def create_app(settings: Settings | None = None, providers: dict[str, Provider] | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    limiter = PinRateLimiter(settings.pin_max_attempts, settings.pin_window_seconds)
    jobs = JobManager(settings.data_dir, providers or default_providers(), settings.job_ttl_hours)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if settings.pin_generated:
            print(f"\n  >>> PIN di accesso per questa sessione: {settings.access_pin}  <<<\n", flush=True)
        yield

    app = FastAPI(title="Scan3D API", version="0.1.0", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.settings = settings
    app.state.jobs = jobs

    @app.middleware("http")
    async def require_token(request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or path in PUBLIC_PATHS or not path.startswith("/api/"):
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not (auth.startswith("Bearer ") and verify_token(settings, auth[7:])):
            return JSONResponse({"detail": "Accesso non autorizzato: inserisci il PIN."}, status_code=401)
        return await call_next(request)

    # Aggiunto DOPO il middleware di auth = più esterno: anche le risposte 401 hanno gli header CORS.
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,  # niente cookie: il token viaggia nell'header
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.post("/api/auth")
    def auth(body: PinIn, request: Request):
        ip = client_ip(request, settings)
        wait = limiter.retry_after(ip)
        if wait:
            return JSONResponse({"detail": f"Troppi tentativi. Riprova tra {wait} s."},
                                status_code=429, headers={"Retry-After": str(wait)})
        if not check_pin(settings, body.pin):
            limiter.fail(ip)
            return JSONResponse({"detail": "PIN errato."}, status_code=401)
        limiter.reset(ip)
        token, exp = issue_token(settings)
        return {"token": token, "expiresAt": exp}

    @app.get("/api/me")
    def me():
        return {"ok": True}

    # --- ricostruzione -------------------------------------------------------------
    @app.get("/api/providers")
    def list_providers():
        return [p.info() for p in jobs.providers.values()]

    def _job_or_404(job_id: str):
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Scansione non trovata sul server (forse è scaduta).")
        return job

    @app.post("/api/jobs")
    def create_job(body: JobIn):
        try:
            return jobs.create(body.provider, body.name).public()
        except KeyError:
            raise HTTPException(400, f"Motore di ricostruzione sconosciuto: {body.provider}")

    @app.post("/api/jobs/{job_id}/photos")
    def upload_photo(job_id: str, photo: UploadFile = File(...)):
        job = _job_or_404(job_id)
        if job.status != "uploading":
            raise HTTPException(409, "Elaborazione già avviata: non si possono aggiungere foto.")
        prov = jobs.providers[job.provider]
        if job.photos >= prov.max_photos:
            raise HTTPException(400, f"Massimo {prov.max_photos} foto per scansione.")
        try:
            save_normalized(photo.file.read(), jobs.photos_dir(job.id) / f"{job.photos + 1:03d}.jpg")
        except BadImage as e:
            raise HTTPException(400, str(e))
        return {"photos": jobs.add_photo(job)}

    @app.post("/api/jobs/{job_id}/start")
    def start_job(job_id: str):
        job = _job_or_404(job_id)
        try:
            return jobs.start(job).public()
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        return _job_or_404(job_id).public()

    @app.get("/api/jobs/{job_id}/model.glb")
    def get_model(job_id: str):
        job = _job_or_404(job_id)
        path = jobs.model_path(job.id)
        if job.status != "done" or not path.exists():
            raise HTTPException(409, "Il modello non è ancora pronto.")
        return FileResponse(path, media_type="model/gltf-binary", headers={"Cache-Control": "no-store"})

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str):
        jobs.delete(job_id)
        return {"ok": True}

    # --- frontend statico (opzionale: Codespace / Space con un'unica porta) -----------
    if settings.serve_web and settings.serve_web.exists():
        app.mount("/", SPAStaticFiles(directory=settings.serve_web, html=True), name="web")

    return app


class SPAStaticFiles(StaticFiles):
    """File statici con fallback a index.html per le rotte della PWA."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code == 404 and not path.startswith("api"):
                return await super().get_response("index.html", scope)
            raise


app = create_app()
