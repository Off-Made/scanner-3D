"""Genera le icone PWA in web/public/icons (cubo isometrico grafite su grigio chiaro)."""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "web" / "public" / "icons"
BG, FG = (245, 245, 244), (42, 42, 42)


def cube(size: int, pad: float) -> Image.Image:
    s = size * 4  # disegno a 4x e poi riduco: bordi morbidi (antialiasing)
    im = Image.new("RGB", (s, s), BG)
    d = ImageDraw.Draw(im)
    r = s * (0.5 - pad)
    cx, cy = s / 2, s / 2
    h = r * 0.5
    top, left, right, bottom = (cx, cy - r), (cx - r * 0.866, cy - h), (cx + r * 0.866, cy - h), (cx, cy + r)
    lb, rb, c = (cx - r * 0.866, cy + h), (cx + r * 0.866, cy + h), (cx, cy)
    w = max(4, int(s * 0.035))
    for a, b in [(top, left), (top, right), (left, c), (right, c), (c, bottom), (left, lb), (right, rb), (lb, bottom), (rb, bottom)]:
        d.line([a, b], fill=FG, width=w, joint="curve")
    for p in (top, left, right, c, lb, rb, bottom):
        d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=FG)
    return im.resize((size, size), Image.LANCZOS)


OUT.mkdir(parents=True, exist_ok=True)
cube(192, 0.22).save(OUT / "icon-192.png")
cube(512, 0.22).save(OUT / "icon-512.png")
cube(512, 0.30).save(OUT / "icon-maskable-512.png")  # margine extra: Android ritaglia a cerchio
cube(180, 0.22).save(OUT / "apple-touch-icon.png")
(OUT / "favicon.svg").write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#f5f5f4"/>'
    '<g fill="none" stroke="#2a2a2a" stroke-width="3" stroke-linejoin="round" stroke-linecap="round">'
    '<path d="M32 12 15 22v20l17 10 17-10V22z"/><path d="M15 22l17 10 17-10M32 32v20"/></g></svg>', encoding="utf-8")
print("icone generate in", OUT.relative_to(OUT.parents[2]))
