"""Post snapshots from several cameras to a Telegram channel as one album."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from .camera import get_snapshot
from .config import Camera, Config, ConfigError
from .imaging import fit_to_16_9, to_jpeg_bytes
from .telegram import (
    MediaItem,
    TelegramError,
    notify_failure,
    send_media_group,
    send_photo,
)

log = logging.getLogger("campost")

MAX_PHOTO_BYTES = 10 * 1024 * 1024


def capture(camera: Camera, config: Config, now: datetime) -> MediaItem:
    img = get_snapshot(
        camera.url,
        timeout=config.http_timeout,
        ffmpeg_timeout=config.ffmpeg_timeout,
    )
    img = fit_to_16_9(img)
    data = to_jpeg_bytes(img, quality=config.jpeg_quality)

    if len(data) > MAX_PHOTO_BYTES:
        raise RuntimeError(f"JPEG is too large: {len(data)} bytes")

    filename = now.strftime(f"photo_{camera.name}_%Y-%m-%d_%H-%M-%S.jpg")
    caption = f"{camera.title} — {now:%d.%m.%Y %H:%M}"
    return MediaItem(filename=filename, caption=caption, data=data)


def run_once(
    config: Config,
    *,
    dry_run: bool = False,
    out_dir: Path | None = None,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now()
    items: list[MediaItem] = []
    failed: list[Camera] = []

    for camera in config.cameras:
        try:
            items.append(capture(camera, config, now))
        except Exception:  # noqa: BLE001 - one camera must not break the rest
            log.exception("Camera '%s' failed: %s", camera.name, camera.url)
            failed.append(camera)

    if not items:
        log.error("No snapshots captured")
        if not dry_run and config.notify_failures:
            _notify(config, _failure_text(failed, now))
        return 1

    if dry_run:
        _save_locally(items, out_dir or Path("out"))
        return 0

    if failed and config.notify_failures:
        _notify(config, _failure_text(failed, now))

    try:
        if len(items) == 1:
            log.warning("Only one snapshot available, sending as a single photo")
            send_photo(config.bot_token, config.chat_id, items[0])
        else:
            send_media_group(config.bot_token, config.chat_id, items)
    except TelegramError:
        log.exception("Telegram rejected the album, sending photos separately")
        errors = 0
        for item in items:
            try:
                send_photo(config.bot_token, config.chat_id, item)
            except Exception:  # noqa: BLE001 - keep trying the remaining items
                errors += 1
                log.exception("Failed to send %s", item.filename)
        if errors:
            return 1
        return 0

    log.info("Sent %d photo(s)", len(items))
    return 0


def _save_locally(items: list[MediaItem], target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in items:
        path = target / item.filename
        path.write_bytes(item.data)
        log.info("Saved %s (%d bytes)", path, len(item.data))


def _failure_text(failed: list[Camera], now: datetime) -> str:
    titles = ", ".join(camera.title for camera in failed)
    return f"Не удалось получить кадр: {titles} ({now:%d.%m.%Y %H:%M})"


def _notify(config: Config, text: str) -> None:
    notify_failure(config.bot_token, config.chat_id, text)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Post camera snapshots to a Telegram channel"
    )
    parser.add_argument(
        "--urls",
        type=Path,
        default=None,
        help="path to the camera list (default: $BOTPOST_URLS_FILE or urls.txt)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="save snapshots locally instead of sending them",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("out"),
        help="output directory for --dry-run (default: out)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="logging level (default: INFO)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = Config.from_env(args.urls)
    except ConfigError as exc:
        log.error("%s", exc)
        return 2

    return run_once(config, dry_run=args.dry_run, out_dir=args.out)


if __name__ == "__main__":
    sys.exit(main())
