"""API Scan3D (FastAPI).

Avvio in locale (dalla radice):  npm run dev
oppure:  server\\.venv\\Scripts\\python -m uvicorn app.main:app --app-dir server --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .auth import PinRateLimiter, check_pin, client_ip, issue_token, verify_token
from .config import Settings

PUBLIC_PATHS = {"/api/health", "/api/auth"}


class PinIn(BaseModel):
    pin: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    limiter = PinRateLimiter(settings.pin_max_attempts, settings.pin_window_seconds)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if settings.pin_generated:
            print(f"\n  >>> PIN di accesso per questa sessione: {settings.access_pin}  <<<\n", flush=True)
        yield

    app = FastAPI(title="Scan3D API", version="0.1.0", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.settings = settings

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

    return app


app = create_app()
