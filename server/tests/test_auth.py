import ipaddress

from fastapi.testclient import TestClient
from starlette.requests import Request

from app.auth import PinRateLimiter, client_ip, issue_token, verify_token
from app.config import Settings
from app.main import create_app


def make_settings(**kw) -> Settings:
    base = dict(access_pin="123456", session_secret=b"test-secret", token_ttl_hours=1)
    base.update(kw)
    return Settings(**base)


def fake_request(peer: str, headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 1234)})


# --- token -------------------------------------------------------------------

def test_token_roundtrip_and_expiry():
    s = make_settings()
    token, exp = issue_token(s, now=1000)
    assert verify_token(s, token, now=1001)
    assert not verify_token(s, token, now=exp + 1)  # scaduto


def test_token_rejects_tampering_and_other_secret():
    s = make_settings()
    token, _ = issue_token(s)
    payload, sig = token.split(".")
    assert not verify_token(s, payload + "x." + sig)
    assert not verify_token(make_settings(session_secret=b"other"), token)
    assert not verify_token(s, "garbage")


# --- API -----------------------------------------------------------------------

def test_health_is_public_and_api_requires_token():
    c = TestClient(create_app(make_settings()))
    assert c.get("/api/health").json() == {"ok": True}
    assert c.get("/api/me").status_code == 401


def test_pin_flow():
    c = TestClient(create_app(make_settings()))
    assert c.post("/api/auth", json={"pin": "000000"}).status_code == 401
    r = c.post("/api/auth", json={"pin": "123456"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert c.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_rate_limit_after_five_failures():
    c = TestClient(create_app(make_settings()))
    for _ in range(5):
        assert c.post("/api/auth", json={"pin": "999999"}).status_code == 401
    r = c.post("/api/auth", json={"pin": "123456"})  # anche il PIN giusto viene bloccato
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_cors_headers_present_even_on_401():
    c = TestClient(create_app(make_settings(cors_origins=["https://scan3d.vercel.app"])))
    r = c.get("/api/me", headers={"Origin": "https://scan3d.vercel.app"})
    assert r.status_code == 401
    assert r.headers.get("access-control-allow-origin") == "https://scan3d.vercel.app"
    r = c.get("/api/me", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


# --- IP reale dietro proxy --------------------------------------------------------

def test_forwarded_headers_trusted_only_from_loopback_or_trusted_proxy():
    s = make_settings()
    # dal tunnel/proxy locale: si usa l'header
    assert client_ip(fake_request("127.0.0.1", {"CF-Connecting-IP": "203.0.113.7"}), s) == "203.0.113.7"
    assert client_ip(fake_request("127.0.0.1", {"X-Forwarded-For": "198.51.100.2, 10.0.0.1"}), s) == "198.51.100.2"
    # da un client qualunque: header ignorato (potrebbe essere falsificato)
    assert client_ip(fake_request("198.51.100.9", {"CF-Connecting-IP": "1.2.3.4"}), s) == "198.51.100.9"
    # da un proxy dichiarato fidato
    s2 = make_settings(trusted_proxies=[ipaddress.ip_network("10.0.0.0/8")])
    assert client_ip(fake_request("10.1.2.3", {"X-Forwarded-For": "203.0.113.50"}), s2) == "203.0.113.50"


def test_rate_limiter_window():
    lim = PinRateLimiter(max_attempts=2, window_seconds=60)
    lim.fail("a", now=0)
    lim.fail("a", now=1)
    assert lim.retry_after("a", now=2) > 0
    assert lim.retry_after("a", now=62) == 0  # finestra scaduta
    assert lim.retry_after("b", now=2) == 0  # IP diversi indipendenti
