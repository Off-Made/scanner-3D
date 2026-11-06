"""Provider finto per i test e le demo: genera un oggetto noto in pochi secondi.

Attivo solo con SCAN3D_ENABLE_MOCK=1 (mai in produzione).
"""
from __future__ import annotations

import time
from pathlib import Path

import trimesh

from ..mesh.cleanup import CleanupInfo, finalize
from .base import Provider, RunContext


class MockProvider(Provider):
    id = "mock"
    label = "Demo (test)"
    description = "Oggetto di prova generato in pochi secondi (solo sviluppo)."
    min_photos = 1
    max_photos = 40

    def __init__(self, seconds: float = 2.0):
        self.seconds = seconds

    def reconstruct(self, photos: list[Path], ctx: RunContext):
        steps = 8
        for i in range(steps):
            ctx.progress(5 + 80 * i / steps, f"Elaborazione di prova {i + 1}/{steps}")
            time.sleep(self.seconds / steps)
        # una "tazza": cilindro con un foro passante decentrato, utile per testare la chiusura
        body = trimesh.creation.cylinder(radius=30, height=60, sections=64)
        hole = trimesh.creation.cylinder(radius=6, height=80, sections=32)
        hole.apply_translation([12, 0, 0])
        mesh = body.difference(hole, engine="manifold")
        mesh, info = finalize(mesh, CleanupInfo(steps=[f"{len(photos)} foto ricevute"]), None)
        return mesh, info.steps
