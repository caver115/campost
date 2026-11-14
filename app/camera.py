"""Camera snapshot download."""

from __future__ import annotations

import logging
import time
from io import BytesIO

import requests
from PIL import Image

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "campost/1.0"}
SESSION = requests.Session()


class CameraError(RuntimeError):
    """Raised when a snapshot could not be downloaded."""


def get_snapshot(
    url: str,
    *,
    timeout: float = 20.0,
    retries: int = 3,
    retry_delay: float = 5.0,
) -> Image.Image:
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            response = SESSION.get(url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            with Image.open(BytesIO(response.content)) as img:
                img.load()
                return img.copy()
        except Exception as exc:  # noqa: BLE001 - camera errors vary widely
            last_error = exc
            log.warning(
                "Snapshot attempt %d/%d failed for %s: %s",
                attempt,
                retries,
                url,
                exc,
            )
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None and 400 <= status < 500:
                # Client errors (wrong URL, auth) are permanent, do not retry.
                break
            if attempt < retries:
                time.sleep(retry_delay)

    raise CameraError(f"Failed to download snapshot from {url}") from last_error
