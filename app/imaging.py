"""Image preparation helpers."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps

ASPECT_WIDTH = 16
ASPECT_HEIGHT = 9


def fit_to_16_9(img: Image.Image, *, mode: str = "crop") -> Image.Image:
    """Fit an image to 16:9 without distorting it.

    mode="crop" fills the frame and cuts the edges.
    mode="pad" keeps the whole frame and adds black bars.
    """
    target = target_size(img.size)

    if mode == "crop":
        return ImageOps.fit(img, target, method=Image.Resampling.LANCZOS)
    if mode == "pad":
        return ImageOps.pad(
            img, target, color="black", method=Image.Resampling.LANCZOS
        )
    raise ValueError(f"Unknown mode: {mode!r} (expected 'crop' or 'pad')")


def target_size(size: tuple[int, int]) -> tuple[int, int]:
    """Return the largest 16:9 size that fits into the source without upscaling."""
    width, height = size
    if width * ASPECT_HEIGHT <= height * ASPECT_WIDTH:
        return width, max(1, round(width * ASPECT_HEIGHT / ASPECT_WIDTH))
    return max(1, round(height * ASPECT_WIDTH / ASPECT_HEIGHT)), height


def to_jpeg_bytes(img: Image.Image, *, quality: int = 95) -> bytes:
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()
