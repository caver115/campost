"""Camera snapshot capture over HTTP or RTSP."""

from __future__ import annotations

import logging
import re
import subprocess
import time
from io import BytesIO
from typing import Callable

import requests
from PIL import Image

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "campost/1.0"}
SESSION = requests.Session()
RTSP_PREFIXES = ("rtsp://", "rtsps://")

_CREDENTIALS_RE = re.compile(r"(rts?ps?://)[^/@\s]+@")
_PASSWORD_RE = re.compile(r"(?i)(password=)[^&\s]+")


class CameraError(RuntimeError):
    """Raised when a snapshot could not be captured."""


class PermanentCameraError(CameraError):
    """Raised when retrying cannot help (bad URL, auth failure)."""


def get_snapshot(
    url: str,
    *,
    timeout: float = 20.0,
    ffmpeg_timeout: float = 30.0,
    retries: int = 3,
    retry_delay: float = 5.0,
) -> Image.Image:
    if url.lower().startswith(RTSP_PREFIXES):
        fetch: Callable[[], Image.Image] = lambda: _capture_rtsp(url, ffmpeg_timeout)
    else:
        fetch = lambda: _download_http(url, timeout)

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return fetch()
        except PermanentCameraError as exc:
            log.warning("Snapshot failed for %s: %s", safe_url(url), exc)
            raise
        except Exception as exc:  # noqa: BLE001 - camera errors vary widely
            last_error = exc
            log.warning(
                "Snapshot attempt %d/%d failed for %s: %s",
                attempt,
                retries,
                safe_url(url),
                exc,
            )
            if attempt < retries:
                time.sleep(retry_delay)

    raise CameraError(f"Failed to capture snapshot from {safe_url(url)}") from last_error


def _download_http(url: str, timeout: float) -> Image.Image:
    try:
        response = SESSION.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", None)
        if status is not None and 400 <= status < 500:
            raise PermanentCameraError(f"HTTP {status}") from exc
        raise CameraError(f"HTTP error: {exc}") from exc
    except requests.RequestException as exc:
        raise CameraError(f"HTTP request failed: {exc}") from exc

    return _decode(response.content)


def _capture_rtsp(url: str, ffmpeg_timeout: float) -> Image.Image:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        url,
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "pipe:1",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=ffmpeg_timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PermanentCameraError(
            "ffmpeg is not installed (required for rtsp:// sources)"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CameraError(f"ffmpeg timed out after {ffmpeg_timeout}s") from exc

    if result.returncode != 0 or not result.stdout:
        detail = safe_url(result.stderr.decode("utf-8", "replace").strip()[:300])
        message = f"ffmpeg failed ({result.returncode}): {detail or 'no output'}"
        if "401" in detail or "Unauthorized" in detail:
            raise PermanentCameraError(message)
        raise CameraError(message)

    return _decode(result.stdout)


def _decode(data: bytes) -> Image.Image:
    with Image.open(BytesIO(data)) as img:
        img.load()
        return img.copy()


def safe_url(url: str) -> str:
    """Hide credentials in URLs before logging."""
    masked = _CREDENTIALS_RE.sub(r"\1***@", url)
    return _PASSWORD_RE.sub(r"\1***", masked)
