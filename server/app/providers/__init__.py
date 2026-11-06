"""Registro dei provider di ricostruzione disponibili."""
from __future__ import annotations

import os

from .ai_hf import HuggingFaceProvider
from .base import Provider
from .mock import MockProvider
from .photogrammetry import PhotogrammetryProvider


def default_providers() -> dict[str, Provider]:
    providers: dict[str, Provider] = {p.id: p for p in (PhotogrammetryProvider(), HuggingFaceProvider())}
    if os.getenv("SCAN3D_ENABLE_MOCK") == "1":
        providers["mock"] = MockProvider(float(os.getenv("SCAN3D_MOCK_SECONDS", "2")))
    return providers
