"""Optional camera telemetry (temperature, light, uptime) for captions."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import requests

from .camera import safe_url

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "campost/1.0"}
SESSION = requests.Session()

# OpenIPC exposes these at /cgi-bin/j/pulse.cgi
TEMP_KEYS = ("soc_temp", "temperature", "temp")
LIGHT_KEYS = ("daynight_value", "light", "illuminance")
UPTIME_KEYS = ("uptime",)

# Fallback for /metrics: node_hwmon_temp_celsius 38.5714
METRIC_RE = re.compile(
    r"^node_hwmon_temp_celsius(?:\{[^}]*\})?\s+(-?\d+(?:\.\d+)?)\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Telemetry:
    temperature: str | None = None
    light: str | None = None
    uptime: str | None = None

    def caption_parts(self) -> list[str]:
        parts: list[str] = []
        if self.temperature:
            parts.append(f"SoC: {self.temperature}")
        if self.light:
            parts.append(f"Light: {self.light}")
        if self.uptime:
            parts.append(f"Uptime: {self.uptime}")
        return parts


def fetch_telemetry(url: str, *, timeout: float = 5.0) -> Telemetry:
    """Return telemetry or an empty object.

    Telemetry is optional metadata: any failure is logged and ignored so it can
    never block the snapshot post.
    """
    try:
        response = SESSION.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Telemetry request failed for %s: %s", safe_url(url), exc)
        return Telemetry()

    telemetry = _parse(response.text)
    if not telemetry.caption_parts():
        log.warning("No telemetry found at %s", safe_url(url))
    return telemetry


def _parse(text: str) -> Telemetry:
    try:
        payload = json.loads(text)
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        return Telemetry(
            temperature=_normalize_temperature(_first(payload, TEMP_KEYS)),
            light=_clean(_first(payload, LIGHT_KEYS)),
            uptime=_clean(_first(payload, UPTIME_KEYS)),
        )

    match = METRIC_RE.search(text)
    if match:
        return Telemetry(temperature=_normalize_temperature(match.group(1)))
    return Telemetry()


def _first(payload: dict, keys: tuple[str, ...]) -> object | None:
    for key in keys:
        raw = payload.get(key)
        if raw not in (None, ""):
            return raw
    return None


def _normalize_temperature(value: object | None) -> str | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return None

    number = float(match.group())
    if number.is_integer():
        return f"{int(number)} °C"
    return f"{number:.1f} °C"


def _clean(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
