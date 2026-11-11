"""Provider AI: modello immagini -> 3D ospitato su un Hugging Face Space (via gradio_client).

Predefinito: Hunyuan3D-2mv, che accetta più viste (fronte/retro/sinistra/destra). Con più viste
il retro e i fianchi non sono più "immaginati" da una sola foto: la forma è molto più fedele.
Le viste si scelgono in automatico dagli angoli della bussola registrati durante la scansione;
per le foto importate (niente bussola) si usano solo fronte e retro, che non dipendono dal
verso in cui si è girato attorno all'oggetto.

Lo Space e l'endpoint sono configurabili (HF_SPACE, HF_API_NAME) perché gli Space pubblici
cambiano nel tempo: l'adattatore legge la descrizione dell'API e associa le foto ai parametri
per nome (mv_image_front, ...), oppure al primo parametro immagine se lo Space ne ha uno solo.
HF_MV_SWAP_LR=1 scambia sinistra/destra se il modello esce "specchiato".
HF_OCTREE_RESOLUTION (predefinito 380, 0 = lascia il valore dello Space): più alto = più dettagli.

Limiti onesti: le zone che nessuna foto vede sono comunque stimate, le quote gratuite sono
limitate e lo Space può cambiare API o sparire.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import numpy as np
import trimesh
from PIL import Image

from .. import deps
from ..mesh.cleanup import mesh_to_printable
from .base import Provider, ProviderError, RunContext

MESH_EXT = (".glb", ".gltf", ".obj", ".ply", ".stl")
VIEW_ANGLES = {"front": 0.0, "right": 90.0, "back": 180.0, "left": 270.0}
VIEW_LABELS = {"front": "fronte", "right": "destra", "back": "retro", "left": "sinistra"}
MAX_ANGLE_GAP = 30.0  # oltre, la foto non rappresenta quella vista: meglio non usarla


def sharpness(path: Path) -> float:
    """Varianza del Laplaciano su un'immagine ridotta: più alta = più nitida."""
    im = np.asarray(Image.open(path).convert("L").resize((256, 256)), dtype=np.float32)
    lap = im[1:-1, 1:-1] * -4 + im[:-2, 1:-1] + im[2:, 1:-1] + im[1:-1, :-2] + im[1:-1, 2:]
    return float(lap.var())


def _angle_gap(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def pick_views(photos: list[Path], views: dict, sharp: Callable[[Path], float] = sharpness,
               swap_lr: bool = False) -> dict[str, Path]:
    """Sceglie le foto per fronte/destra/retro/sinistra.

    Con la bussola: la bussola cresce in senso orario, quindi girando di +90° si vede il fianco
    destro dell'oggetto (guardandolo dal fronte = prima foto). Per ogni vista prendo la foto più
    nitida entro ±30°, preferendo quelle all'altezza dell'oggetto (anello basso).
    Senza bussola: fronte = prima foto, retro = foto a metà giro (indipendenti dal verso)."""
    if not photos:
        return {}
    known = [(p, views[p.name]) for p in photos if p.name in views and views[p.name].get("angle") is not None]
    if len(known) < 2:
        out = {"front": photos[0]}
        if len(photos) >= 4:
            out["back"] = photos[len(photos) // 2]
        return out
    out: dict[str, Path] = {}
    for role, target in VIEW_ANGLES.items():
        near = [(p, v) for p, v in known if _angle_gap(float(v["angle"]), target) <= MAX_ANGLE_GAP]
        if not near:
            continue
        low = [pv for pv in near if pv[1].get("ring", 0) == 0] or near
        # la più nitida, a parità la più vicina all'angolo giusto
        out[role] = max(low, key=lambda pv: (sharp(pv[0]), -_angle_gap(float(pv[1]["angle"]), target)))[0]
    if "front" not in out:
        out["front"] = photos[0]
    if swap_lr and ("left" in out or "right" in out):
        out["left"], out["right"] = out.get("right"), out.get("left")
        out = {k: v for k, v in out.items() if v is not None}
    return out


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


def _view_of_param(name: str) -> str | None:
    n = name.lower()
    return next((v for v in VIEW_ANGLES if v in n), None)


def build_kwargs(api_info: dict, api_name: str, images: Any, overrides: dict | None = None) -> dict:
    """Prepara gli argomenti dell'endpoint.

    `images`: un handle (foto singola) oppure {"front": h, "back": h, ...}. Se l'endpoint ha
    parametri immagine per vista (mv_image_front, ...) li riempio per nome; altrimenti la vista
    frontale va nel primo parametro immagine. `overrides` vale solo per i parametri che esistono."""
    endpoints = api_info.get("named_endpoints", {})
    if api_name not in endpoints:
        raise ProviderError(f"Lo Space AI non espone l'endpoint {api_name}. Endpoint disponibili: "
                            + (", ".join(endpoints) or "nessuno"))
    images = images if isinstance(images, dict) else {"front": images}
    params = endpoints[api_name].get("parameters", [])

    def is_image(p: dict) -> bool:
        return "image" in str(p.get("component", "")).lower() or "image" in str(p.get("python_type", {})).lower()

    names = [(p.get("parameter_name") or p.get("label"), p) for p in params]
    multiview = any(is_image(p) and _view_of_param(n) for n, p in names)
    kwargs, image_set = {}, False
    for name, p in names:
        view = _view_of_param(name) if is_image(p) else None
        if multiview and view:
            if view in images:
                kwargs[name] = images[view]
                image_set = True
        elif is_image(p) and not multiview and not image_set:
            kwargs[name] = images.get("front", next(iter(images.values()), None))
            image_set = True
        elif overrides and name in overrides:
            kwargs[name] = overrides[name]
        elif not p.get("parameter_has_default", False):
            kwargs[name] = None  # parametri opzionali senza default (es. caption)
    if not image_set:
        raise ProviderError(f"L'endpoint {api_name} non accetta un'immagine.")
    return kwargs


class HuggingFaceProvider(Provider):
    id = "ai"
    label = "Rapida (AI)"
    description = ("Modello AI da 4 viste (fronte, retro, fianchi): pochi minuti, forma vicina all'oggetto "
                   "ma meno precisa della fotogrammetria nei dettagli.")
    min_photos = 1
    max_photos = 40

    def __init__(self, client_factory=None):
        self.space = os.getenv("HF_SPACE", "tencent/Hunyuan3D-2mv")
        self.api_name = os.getenv("HF_API_NAME", "/shape_generation")
        self.token = os.getenv("HF_TOKEN") or None
        self.swap_lr = os.getenv("HF_MV_SWAP_LR", "0") == "1"
        octree = int(os.getenv("HF_OCTREE_RESOLUTION", "380") or 0)
        self.overrides = {"octree_resolution": octree, "check_box_rembg": True} if octree else {"check_box_rembg": True}
        self._client_factory = client_factory  # iniettabile nei test

    def available(self) -> tuple[bool, str]:
        why = deps.missing(("gradio_client", *deps.MESH_MODULES))
        return (False, why) if why else (True, "")

    def _client(self):
        if self._client_factory:
            return self._client_factory(self.space, self.token)
        from gradio_client import Client
        # `token` (gradio_client >= 1.0): il vecchio `hf_token` è stato rimosso nella 2.x.
        return Client(self.space, token=self.token, verbose=False)

    def reconstruct(self, photos: list[Path], ctx: RunContext):
        from gradio_client import handle_file

        ctx.progress(5, "Scelta delle foto (fronte, retro, fianchi)")
        views = pick_views(photos, ctx.photo_views, swap_lr=self.swap_lr)
        ctx.progress(10, f"Connessione al servizio AI ({self.space})")
        try:
            client = self._client()
            api = client.view_api(return_format="dict", print_info=False)
            params = api.get("named_endpoints", {}).get(self.api_name, {}).get("parameters", [])
            if not any(_view_of_param(str(p.get("parameter_name") or "")) for p in params):
                # Space a foto singola: uso la vista frontale, scelta tra le prime foto la più nitida
                views = {"front": max(photos[: max(3, len(photos) // 8)], key=sharpness)}
            kwargs = build_kwargs(api, self.api_name, {k: handle_file(str(p)) for k, p in views.items()}, self.overrides)
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
        try:
            mesh, info = mesh_to_printable(loaded, progress=lambda m: ctx.progress(92, m),
                                           y_up=path.lower().endswith((".glb", ".gltf")))
        except ValueError as e:
            raise ProviderError(str(e)) from e
        if len(views) == 1:
            used = f"Foto usata: {views['front'].name}"
        else:
            used = "Viste usate: " + ", ".join(f"{VIEW_LABELS[k]} {p.name}" for k, p in views.items())
        return mesh, [used, *info.steps]
