from __future__ import annotations

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

from PIL import Image

from app import config, imaging, telegram


class ImagingTest(unittest.TestCase):
    def test_target_size_landscape(self) -> None:
        self.assertEqual(imaging.target_size((1600, 1200)), (1600, 900))

    def test_target_size_portrait(self) -> None:
        self.assertEqual(imaging.target_size((1080, 1920)), (1080, 608))

    def test_target_size_already_16_9(self) -> None:
        self.assertEqual(imaging.target_size((1920, 1080)), (1920, 1080))

    def test_fit_crop_keeps_aspect_ratio(self) -> None:
        img = Image.new("RGB", (1600, 1200))
        result = imaging.fit_to_16_9(img, mode="crop")
        self.assertEqual(result.size, (1600, 900))

    def test_fit_pad_keeps_frame_size(self) -> None:
        img = Image.new("RGB", (1000, 1000))
        result = imaging.fit_to_16_9(img, mode="pad")
        self.assertEqual(result.size, (1000, 562))

    def test_jpeg_conversion_from_rgba(self) -> None:
        img = Image.new("RGBA", (160, 90), (10, 20, 30, 128))
        data = imaging.to_jpeg_bytes(img)
        with Image.open(BytesIO(data)) as decoded:
            self.assertEqual(decoded.mode, "RGB")
            self.assertEqual(decoded.size, (160, 90))


class CameraListTest(unittest.TestCase):
    def _write(self, content: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        )
        tmp.write(content)
        tmp.close()
        return Path(tmp.name)

    def test_plain_and_titled_lines(self) -> None:
        path = self._write(
            "# comment\n"
            "\n"
            "Entrance | http://host/a.jpg\n"
            "http://host/b.jpg\n"
        )
        cameras = config.load_cameras(path)
        self.assertEqual([c.name for c in cameras], ["camera_1", "camera_2"])
        self.assertEqual([c.title for c in cameras], ["Entrance", "Camera 2"])
        self.assertEqual(cameras[1].url, "http://host/b.jpg")

    def test_invalid_url_reports_line(self) -> None:
        path = self._write("# header\nnot-a-url\n")
        with self.assertRaises(config.ConfigError) as ctx:
            config.load_cameras(path)
        self.assertIn(":2:", str(ctx.exception))

    def test_empty_file_rejected(self) -> None:
        path = self._write("# only comments\n\n")
        with self.assertRaises(config.ConfigError):
            config.load_cameras(path)


class TelegramPayloadTest(unittest.TestCase):
    def test_media_group_payload(self) -> None:
        items = [
            telegram.MediaItem("one.jpg", "Entrance", b"a"),
            telegram.MediaItem("two.jpg", "Yard", b"b"),
        ]
        with mock.patch.object(telegram, "_call", return_value=[]) as call:
            telegram.send_media_group("TOKEN", "-100", items, timeout=30)

        method, token = call.call_args.args
        kwargs = call.call_args.kwargs
        media = json.loads(kwargs["data"]["media"])

        self.assertEqual(method, "sendMediaGroup")
        self.assertEqual(token, "TOKEN")
        self.assertEqual(kwargs["data"]["chat_id"], "-100")
        self.assertEqual(
            [entry["media"] for entry in media],
            ["attach://file0", "attach://file1"],
        )
        self.assertEqual(set(kwargs["files"]), {"file0", "file1"})

    def test_media_group_rejects_single_item(self) -> None:
        items = [telegram.MediaItem("one.jpg", "Entrance", b"a")]
        with self.assertRaises(ValueError):
            telegram.send_media_group("TOKEN", "-100", items)


if __name__ == "__main__":
    unittest.main()
