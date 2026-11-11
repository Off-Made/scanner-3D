"""Normalizzazione delle foto caricate: orientamento EXIF, HEIC, ridimensionamento a 2400 px (oltre, OpenMVS non lo userebbe)."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

try:  # foto HEIC caricate dalla galleria iPhone
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

MAX_SIDE = 2400
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MIN_SIDE = 320


class BadImage(ValueError):
    pass


def save_normalized(data: bytes, dest: Path, max_side: int = MAX_SIDE) -> tuple[int, int]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise BadImage("Foto troppo grande (max 25 MB).")
    try:
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im).convert("RGB")
    except (UnidentifiedImageError, OSError) as e:
        raise BadImage("File non riconosciuto come immagine (usa JPEG, PNG o HEIC).") from e
    if min(im.size) < MIN_SIDE:
        raise BadImage(f"Foto troppo piccola ({im.width}×{im.height}): servono almeno {MIN_SIDE} px.")
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "JPEG", quality=93)  # meno artefatti JPEG = meno falsi dettagli per COLMAP
    return im.size
