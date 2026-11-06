"""Provider AI: modello immagine -> 3D ospitato su un Hugging Face Space (via gradio_client).

Lo Space e l'endpoint sono configurabili (HF_SPACE, HF_API_NAME) perché gli Space pubblici
cambiano nel tempo. L'adattatore legge la descrizione dell'API dello Space, passa la foto al
primo parametro di tipo immagine, lascia i valori predefiniti agli altri e cerca nel risultato
un file 3D (.glb/.obj/.ply/.stl).

Limiti onesti: la forma è "immaginata" da una sola foto (il retro è inventato), le quote
gratuite sono limitate e lo Space può cambiare API o sparire.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from PIL import Image

from ..mesh.cleanup import mesh_to_printable
from .base import Provider, ProviderError, RunContext

MESH_EXT = (".glb", ".gltf", ".obj", ".ply", ".stl")


def sharpness(path: Path) -> float:
    """Varianza del Laplaciano su un'immagine ridotta: più alta = più nitida."""
    im = np.asarray(Image.open(path).convert("L").resize((256, 256)), dtype=np.float32)
    lap = im[1:-1, 1:-1] * -4 + im[:-2, 1:-1] + im[2:, 1:-1] + im[1:-1, :-2] + im[1:-1, 2:]
    return float(lap.var())


def find_mesh_file(result: Any) -> str | None:
    """Cerca ricorsivamente un percorso di file 3D nel risultato di gradio (tuple, dict, str)."""
    if isinstance(result, str):
        return result if result.lower().endswith(MESH_EXT) and Path(result).exists() else None
    if isinstance(result, dict):
        for key in ("path", "value", "name", "url"):
            if key in result and (found := find_mesh_file(result[key])):
                return found
        return next((f for v in result.values() if (f := find_mesh_file(v))), None)
    if isinstance(result, (list, tuple)):
        return next((f for v in result if (f := find_mesh_file(v))), None)
    return None


def build_kwargs(api_info: dict, api_name: str, image_handle: Any) -> dict:
    """Prepara gli argomenti: la foto al primo parametro immagine, il resto ai default."""
    endpoints = api_info.get("named_endpoints", {})
    if api_name not in endpoints:
        raise ProviderError(f"Lo Space AI non espone l'endpoint {api_name}. Endpoint disponibili: "
                            + (", ".join(endpoints) or "nessuno"))
    kwargs, image_set = {}, False
    for p in endpoints[api_name].get("parameters", []):
        name = p.get("parameter_name") or p.get("label")
        is_image = "image" in str(p.get("component", "")).lower() or "image" in str(p.get("python_type", {})).lower()
        if is_image and not image_set:
            kwargs[name] = image_handle
            image_set = True
        elif not p.get("parameter_has_default", False):
            kwargs[name] = None  # parametri opzionali senza default (es. caption)
    if not image_set:
        raise ProviderError(f"L'endpoint {api_name} non accetta un'immagine.")
    return kwargs


class HuggingFaceProvider(Provider):
    id = "ai"
    label = "Rapida (AI)"
    description = "Modello AI da una foto: pochi minuti, forma plausibile ma non fedele."
    min_photos = 1
    max_photos = 40

    def __init__(self, client_factory=None):
        self.space = os.getenv("HF_SPACE", "tencent/Hunyuan3D-2")
        self.api_name = os.getenv("HF_API_NAME", "/shape_generation")
        self.token = os.getenv("HF_TOKEN") or None
        self._client_factory = client_factory  # iniettabile nei test

    def available(self) -> tuple[bool, str]:
        try:
            import gradio_client  # noqa: F401
        except ImportError:
            return False, "Pacchetto gradio_client non installato sul server."
        return True, ""

    def _client(self):
        if self._client_factory:
            return self._client_factory(self.space, self.token)
        from gradio_client import Client
        return Client(self.space, hf_token=self.token, verbose=False)

    def reconstruct(self, photos: list[Path], ctx: RunContext):
        from gradio_client import handle_file

        ctx.progress(5, "Scelta della foto più nitida")
        best = max(photos, key=sharpness)
        ctx.progress(10, f"Connessione al servizio AI ({self.space})")
        try:
            client = self._client()
            kwargs = build_kwargs(client.view_api(return_format="dict", print_info=False), self.api_name, handle_file(str(best)))
            ctx.progress(20, "Generazione del modello con l'AI (1–3 minuti)")
            result = client.predict(api_name=self.api_name, **kwargs)
        except ProviderError:
            raise
        except Exception as e:  # noqa: BLE001 - errori di rete/quota/Space li traduco per l'utente
            msg = str(e)
            if "quota" in msg.lower() or "zerogpu" in msg.lower():
                raise ProviderError("Quota gratuita del servizio AI esaurita. Riprova più tardi o imposta HF_TOKEN.") from e
            raise ProviderError(f"Il servizio AI non ha risposto correttamente: {msg[:200]}") from e
        path = find_mesh_file(result)
        if not path:
            raise ProviderError("Il servizio AI non ha restituito un modello 3D.")
        ctx.progress(85, "Pulizia del modello")
        loaded = trimesh.load(path, force="mesh")
        mesh, info = mesh_to_printable(loaded, progress=lambda m: ctx.progress(92, m), y_up=path.lower().endswith((".glb", ".gltf")))
        return mesh, [f"Foto usata: {best.name}", *info.steps]
