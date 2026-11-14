"""Optional camera temperature from OpenIPC JSON or Prometheus metrics."""

from __future__ import annotations

import json
import logging
import re

import requests

from .camera import safe_url

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "campost/1.0"}
SESSION = requests.Session()

# OpenIPC exposes {"soc_temp": "38°C", ...} at /cgi-bin/j/pulse.cgi
JSON_KEYS = ("soc_temp", "temperature", "temp")

# Fallback for /metrics: node_hwmon_temp_celsius 38.5714
METRIC_RE = re.compile(
    r"^node_hwmon_temp_celsius(?:\{[^}]*\})?\s+(-?\d+(?:\.\d+)?)\s*$",
    re.MULTILINE,
)


def fetch_temperature(url: str, *, timeout: float = 5.0) -> str | None:
    """Return a formatted temperature or None.

    Temperature is optional metadata: any failure is logged and ignored so it
    can never block the snapshot post.
    """
    try:
        response = SESSION.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Temperature request failed for %s: %s", safe_url(url), exc)
        return None

    value = _parse(response.text)
    if value is None:
        log.warning("No temperature found at %s", safe_url(url))
    return value


def _parse(text: str) -> str | None:
    try:
        payload = json.loads(text)
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        for key in JSON_KEYS:
            raw = payload.get(key)
            if raw not in (None, ""):
                return _normalize(raw)

    match = METRIC_RE.search(text)
    if match:
        return _normalize(match.group(1))
    return None


def _normalize(value: object) -> str | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return None

    number = float(match.group())
    if number.is_integer():
        return f"{int(number)} °C"
    return f"{number:.1f} °C"
