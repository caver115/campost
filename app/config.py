"""Configuration loading: Telegram credentials from env, cameras from a text file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class Camera:
    name: str
    title: str
    url: str


@dataclass(frozen=True)
class Config:
    bot_token: str
    chat_id: str
    cameras: list[Camera]
    jpeg_quality: int = 95
    http_timeout: float = 20.0
    ffmpeg_timeout: float = 30.0
    notify_failures: bool = True

    @classmethod
    def from_env(cls, urls_file: str | Path | None = None) -> "Config":
        path = Path(urls_file or os.getenv("BOTPOST_URLS_FILE", "urls.txt"))
        return cls(
            bot_token=_required_env("BOTPOST_BOT_TOKEN"),
            chat_id=_required_env("BOTPOST_CHANNEL_ID"),
            cameras=load_cameras(path),
            jpeg_quality=int(os.getenv("BOTPOST_JPEG_QUALITY", "95")),
            http_timeout=float(os.getenv("BOTPOST_HTTP_TIMEOUT", "20")),
            ffmpeg_timeout=float(os.getenv("BOTPOST_FFMPEG_TIMEOUT", "30")),
            notify_failures=_env_bool("BOTPOST_NOTIFY_FAILURES", True),
        )


def load_cameras(path: Path) -> list[Camera]:
    """Parse a camera list.

    Supported lines:
        http://host/image.jpg
        Entrance | http://host/image.jpg
    Empty lines and lines starting with '#' are ignored.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read camera list {path}: {exc}") from exc

    cameras: list[Camera] = []
    for lineno, raw in enumerate(content.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        if "|" in line:
            title, url = (part.strip() for part in line.split("|", 1))
        else:
            title, url = "", line

        if not url.startswith(("http://", "https://", "rtsp://", "rtsps://")):
            raise ConfigError(f"{path}:{lineno}: invalid URL: {url!r}")

        index = len(cameras) + 1
        cameras.append(
            Camera(
                name=f"camera_{index}",
                title=title or f"Camera {index}",
                url=url,
            )
        )

    if not cameras:
        raise ConfigError(f"No camera URLs found in {path}")
    return cameras


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"Environment variable {name} is not set")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")
