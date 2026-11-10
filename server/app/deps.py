"""Controllo delle dipendenze Python con librerie native (Open3D, manifold3d, ...).

Un pacchetto può essere installato ma non importabile, se manca una libreria di sistema
(es. `libusb-1.0.so.0` per Open3D su Linux): l'errore arriva come ImportError/OSError
solo al primo import. Qui lo intercettiamo una volta, all'avvio, con un messaggio chiaro.
"""
from __future__ import annotations

import importlib
from functools import lru_cache

# moduli usati dalla pulizia della mesh, comune a tutti i motori
MESH_MODULES = ("numpy", "scipy", "trimesh", "open3d", "manifold3d")


def describe_import_error(e: BaseException) -> str:
    """Riassunto leggibile: libreria di sistema mancante oppure pacchetto Python mancante."""
    msg = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
    if ".so" in msg or "shared object" in msg or "DLL" in msg:
        return f"manca una libreria di sistema ({msg[:160]})"
    if isinstance(e, ModuleNotFoundError) and e.name:
        return f"manca il pacchetto Python «{e.name}»"
    return msg[:200]


@lru_cache(maxsize=None)
def check_module(name: str) -> str | None:
    """None se il modulo si importa, altrimenti il motivo (in cache: l'import di Open3D è lento)."""
    try:
        importlib.import_module(name)
    except (ImportError, OSError) as e:
        return describe_import_error(e)
    return None


def missing(modules: tuple[str, ...] = MESH_MODULES) -> str:
    """Stringa vuota se è tutto a posto, altrimenti l'elenco dei problemi."""
    problems = [f"{m}: {why}" for m in modules if (why := check_module(m))]
    if not problems:
        return ""
    return "Componenti mancanti sul server — " + "; ".join(problems) + ". Nel Codespace esegui: npm run doctor"
