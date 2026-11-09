"""Configurazione letta da variabili d'ambiente (file .env nella radice del progetto)."""
from __future__ import annotations

import ipaddress
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _csv(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _networks(values: list[str]) -> list[ipaddress._BaseNetwork]:
    nets = []
    for v in values:
        try:
            nets.append(ipaddress.ip_network(v, strict=False))
        except ValueError:
            print(f"[config] TRUSTED_PROXIES: valore ignorato, non è un IP/CIDR: {v!r}")
    return nets


@dataclass
class Settings:
    access_pin: str
    session_secret: bytes
    token_ttl_hours: float = 12
    cors_origins: list[str] = field(default_factory=list)
    cors_origin_regex: str | None = None
    trusted_proxies: list = field(default_factory=list)
    trusted_ip_headers: list[str] = field(default_factory=lambda: ["CF-Connecting-IP", "X-Forwarded-For"])
    pin_max_attempts: int = 5
    pin_window_seconds: int = 60
    pin_generated: bool = False
    data_dir: Path = ROOT / "server" / "data"
    job_ttl_hours: float = 48
    serve_web: Path | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        pin = os.getenv("ACCESS_PIN", "").strip()
        generated = not pin
        if generated:
            pin = f"{secrets.randbelow(10**6):06d}"
        secret = os.getenv("SESSION_SECRET", "").encode() or secrets.token_bytes(32)
        return cls(
            access_pin=pin,
            session_secret=secret,
            token_ttl_hours=float(os.getenv("TOKEN_TTL_HOURS", "12") or 12),
            cors_origins=_csv(os.getenv("CORS_ORIGINS")),
            cors_origin_regex=os.getenv("CORS_ORIGIN_REGEX") or None,
            trusted_proxies=_networks(_csv(os.getenv("TRUSTED_PROXIES"))),
            trusted_ip_headers=_csv(os.getenv("TRUSTED_IP_HEADERS")) or ["CF-Connecting-IP", "X-Forwarded-For"],
            pin_generated=generated,
            data_dir=Path(os.getenv("DATA_DIR") or ROOT / "server" / "data"),
            job_ttl_hours=float(os.getenv("JOB_TTL_HOURS", "48") or 48),
            serve_web=Path(os.environ["SERVE_WEB"]) if os.getenv("SERVE_WEB") else None,
        )
