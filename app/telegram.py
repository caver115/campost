"""Minimal Telegram Bot API client for photo albums."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org/bot"
MAX_ATTEMPTS = 3
SESSION = requests.Session()


class TelegramError(RuntimeError):
    """Raised when the Telegram API rejects a request."""


@dataclass(frozen=True)
class MediaItem:
    filename: str
    caption: str
    data: bytes


def send_photo(
    token: str,
    chat_id: str,
    item: MediaItem,
    *,
    timeout: float = 60.0,
) -> dict:
    data = {"chat_id": chat_id, "caption": item.caption}
    files = {"photo": (item.filename, item.data, "image/jpeg")}
    return _call("sendPhoto", token, data=data, files=files, timeout=timeout)


def send_media_group(
    token: str,
    chat_id: str,
    items: list[MediaItem],
    *,
    timeout: float = 120.0,
) -> list[dict]:
    if not 2 <= len(items) <= 10:
        raise ValueError("sendMediaGroup requires between 2 and 10 items")

    media: list[dict] = []
    files: dict[str, tuple[str, bytes, str]] = {}
    for index, item in enumerate(items):
        key = f"file{index}"
        media.append(
            {
                "type": "photo",
                "media": f"attach://{key}",
                "caption": item.caption,
            }
        )
        files[key] = (item.filename, item.data, "image/jpeg")

    data = {"chat_id": chat_id, "media": json.dumps(media)}
    return _call("sendMediaGroup", token, data=data, files=files, timeout=timeout)


def notify_failure(
    token: str,
    chat_id: str,
    text: str,
    *,
    timeout: float = 30.0,
) -> None:
    try:
        _call(
            "sendMessage",
            token,
            data={"chat_id": chat_id, "text": text},
            timeout=timeout,
        )
    except Exception:  # noqa: BLE001 - notification must never break the run
        log.exception("Failed to send failure notification")


def _call(method: str, token: str, *, timeout: float, **kwargs) -> object:
    url = f"{API_BASE}{token}/{method}"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = SESSION.post(url, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            # Do not retry on network errors: the request may have been
            # delivered already and a retry would post a duplicate message.
            raise TelegramError(f"{method}: network error: {exc}") from exc

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict) and payload.get("ok"):
            return payload.get("result")

        description = ""
        retry_after = None
        if isinstance(payload, dict):
            description = payload.get("description") or ""
            retry_after = (payload.get("parameters") or {}).get("retry_after")

        if response.status_code == 429 and attempt < MAX_ATTEMPTS:
            delay = min(float(retry_after or 5), 60.0)
            log.warning("Telegram rate limit, retrying in %.0fs", delay)
            time.sleep(delay)
            continue

        if response.status_code >= 500 and attempt < MAX_ATTEMPTS:
            delay = 2.0 * attempt
            log.warning(
                "Telegram server error %s, retrying in %.0fs",
                response.status_code,
                delay,
            )
            time.sleep(delay)
            continue

        detail = description or response.text[:300]
        raise TelegramError(f"{method} failed ({response.status_code}): {detail}")

    raise TelegramError(f"{method} failed after {MAX_ATTEMPTS} attempts")
