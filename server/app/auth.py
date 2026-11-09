"""Accesso con PIN -> token firmato (HMAC-SHA256) inviato in `Authorization: Bearer`.

Niente cookie: funziona uguale in locale, dietro un proxy e da un dominio diverso
(es. frontend su Vercel), dove Safari bloccherebbe i cookie di terze parti.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
import time
from collections import defaultdict, deque

from starlette.requests import Request

from .config import Settings


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(settings: Settings, now: float | None = None) -> tuple[str, int]:
    exp = int((time.time() if now is None else now) + settings.token_ttl_hours * 3600)
    payload = _b64(json.dumps({"exp": exp, "n": secrets.token_hex(8)}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(settings.session_secret, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}", exp


def verify_token(settings: Settings, token: str, now: float | None = None) -> bool:
    try:
        payload, sig = token.split(".", 1)
        expected = _b64(hmac.new(settings.session_secret, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):  # confronto a tempo costante
            return False
        return json.loads(_unb64(payload))["exp"] > (time.time() if now is None else now)
    except (ValueError, KeyError, json.JSONDecodeError):
        return False


def check_pin(settings: Settings, pin: str) -> bool:
    return hmac.compare_digest(pin.strip().encode(), settings.access_pin.encode())


def client_ip(request: Request, settings: Settings) -> str:
    """IP reale del client.

    Gli header CF-Connecting-IP / X-Forwarded-For li può scrivere chiunque, quindi
    li accettiamo SOLO se la connessione arriva da un proxy fidato (loopback o
    TRUSTED_PROXIES). Altrimenti usiamo l'IP della connessione.
    """
    peer = request.client.host if request.client else ""
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return peer or "unknown"
    trusted = addr.is_loopback or any(addr in net for net in settings.trusted_proxies)
    if trusted:
        for header in settings.trusted_ip_headers:
            value = request.headers.get(header)
            if value:
                # X-Forwarded-For: "client, proxy1, proxy2" -> il primo è il client
                return value.split(",")[0].strip()
    return peer


class PinRateLimiter:
    """Max N tentativi falliti per IP in una finestra scorrevole di T secondi."""

    def __init__(self, max_attempts: int, window_seconds: int):
        self.max, self.window = max_attempts, window_seconds
        self._fails: dict[str, deque] = defaultdict(deque)

    def _prune(self, ip: str, now: float) -> deque:
        q = self._fails[ip]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def retry_after(self, ip: str, now: float | None = None) -> int:
        """0 se il client può riprovare, altrimenti i secondi da attendere."""
        now = time.time() if now is None else now
        q = self._prune(ip, now)
        return 0 if len(q) < self.max else int(self.window - (now - q[0])) + 1

    def fail(self, ip: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self._prune(ip, now).append(now)

    def reset(self, ip: str) -> None:
        self._fails.pop(ip, None)
