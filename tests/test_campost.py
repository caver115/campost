from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from io import BytesIO
from pathlib import Path
from unittest import mock

from PIL import Image

from app import camera, config, imaging, telegram, temperature
from app import __main__ as entry


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

    def test_rtsp_url_accepted(self) -> None:
        path = self._write("Yard | rtsp://user:pass@host:554/stream1\n")
        cameras = config.load_cameras(path)
        self.assertEqual(cameras[0].url, "rtsp://user:pass@host:554/stream1")

    def test_temperature_url_parsed(self) -> None:
        path = self._write(
            "Yard | rtsp://host:554/stream1 | http://host/cgi-bin/j/pulse.cgi\n"
        )
        cameras = config.load_cameras(path)
        self.assertEqual(cameras[0].temp_url, "http://host/cgi-bin/j/pulse.cgi")

    def test_temperature_url_optional(self) -> None:
        path = self._write("Yard | rtsp://host:554/stream1\n")
        cameras = config.load_cameras(path)
        self.assertIsNone(cameras[0].temp_url)

    def test_invalid_temperature_url_rejected(self) -> None:
        path = self._write("Yard | http://host/a.jpg | rtsp://host/pulse\n")
        with self.assertRaises(config.ConfigError) as ctx:
            config.load_cameras(path)
        self.assertIn(":1:", str(ctx.exception))

    def test_too_many_separators_rejected(self) -> None:
        path = self._write("A | http://host/a.jpg | http://host/t | extra\n")
        with self.assertRaises(config.ConfigError):
            config.load_cameras(path)


class CameraSourceTest(unittest.TestCase):
    def _png_bytes(self) -> bytes:
        buffer = BytesIO()
        Image.new("RGB", (64, 36), (1, 2, 3)).save(buffer, format="PNG")
        return buffer.getvalue()

    def test_rtsp_uses_ffmpeg(self) -> None:
        result = mock.Mock(returncode=0, stdout=self._png_bytes(), stderr=b"")
        with mock.patch.object(camera.subprocess, "run", return_value=result) as run:
            img = camera.get_snapshot("rtsp://host:554/stream", retries=1)

        self.assertEqual(img.size, (64, 36))
        command = run.call_args.args[0]
        self.assertEqual(command[0], "ffmpeg")
        self.assertIn("-rtsp_transport", command)

    def test_http_does_not_call_ffmpeg(self) -> None:
        response = mock.Mock(content=self._png_bytes())
        response.raise_for_status.return_value = None
        with mock.patch.object(
            camera.SESSION, "get", return_value=response
        ), mock.patch.object(camera.subprocess, "run") as run:
            camera.get_snapshot("http://host/a.jpg", retries=1)

        run.assert_not_called()

    def test_http_4xx_is_permanent(self) -> None:
        response = mock.Mock(status_code=404)
        error = camera.requests.HTTPError(response=response)
        response.raise_for_status.side_effect = error
        with mock.patch.object(
            camera.SESSION, "get", return_value=response
        ), mock.patch.object(camera.time, "sleep") as sleep:
            with self.assertRaises(camera.PermanentCameraError):
                camera.get_snapshot("http://host/missing.jpg", retries=3)

        sleep.assert_not_called()

    def test_rtsp_auth_error_is_permanent(self) -> None:
        result = mock.Mock(returncode=1, stdout=b"", stderr=b"401 Unauthorized")
        with mock.patch.object(
            camera.subprocess, "run", return_value=result
        ), mock.patch.object(camera.time, "sleep") as sleep:
            with self.assertRaises(camera.PermanentCameraError):
                camera.get_snapshot("rtsp://host/stream", retries=3)

        sleep.assert_not_called()

    def test_safe_url_masks_credentials(self) -> None:
        self.assertEqual(
            camera.safe_url("rtsp://user:pass@host:554/stream"),
            "rtsp://***@host:554/stream",
        )
        self.assertEqual(
            camera.safe_url("http://host/image.jpg"), "http://host/image.jpg"
        )
        self.assertEqual(
            camera.safe_url("rtsp://host:554/user=admin&password=secret&channel=1"),
            "rtsp://host:554/user=admin&password=***&channel=1",
        )


class TemperatureTest(unittest.TestCase):
    def _response(self, text: str) -> mock.Mock:
        response = mock.Mock(text=text)
        response.raise_for_status.return_value = None
        return response

    def test_openipc_json(self) -> None:
        payload = '{"soc_temp":"38°C","timezone":"Asia/Krasnoyarsk"}'
        with mock.patch.object(
            temperature.SESSION, "get", return_value=self._response(payload)
        ):
            value = temperature.fetch_temperature("http://host/pulse.cgi", timeout=1)
        self.assertEqual(value, "38 °C")

    def test_prometheus_fallback(self) -> None:
        text = (
            "# HELP node_hwmon_temp_celsius\n"
            "# TYPE node_hwmon_temp_celsius gauge\n"
            "node_hwmon_temp_celsius 38.5714\n"
        )
        with mock.patch.object(
            temperature.SESSION, "get", return_value=self._response(text)
        ):
            value = temperature.fetch_temperature("http://host/metrics", timeout=1)
        self.assertEqual(value, "38.6 °C")

    def test_negative_temperature(self) -> None:
        text = "node_hwmon_temp_celsius -5\n"
        with mock.patch.object(
            temperature.SESSION, "get", return_value=self._response(text)
        ):
            value = temperature.fetch_temperature("http://host/metrics", timeout=1)
        self.assertEqual(value, "-5 °C")

    def test_request_error_returns_none(self) -> None:
        error = temperature.requests.RequestException("boom")
        with mock.patch.object(temperature.SESSION, "get", side_effect=error):
            value = temperature.fetch_temperature("http://host/pulse.cgi", timeout=1)
        self.assertIsNone(value)

    def test_unknown_payload_returns_none(self) -> None:
        with mock.patch.object(
            temperature.SESSION, "get", return_value=self._response("<html></html>")
        ):
            value = temperature.fetch_temperature("http://host/pulse.cgi", timeout=1)
        self.assertIsNone(value)

    def test_capture_appends_temperature(self) -> None:
        camera_config = config.Camera(
            name="camera_1",
            title="Entrance",
            url="http://host/a.jpg",
            temp_url="http://host/pulse.cgi",
        )
        settings = config.Config(
            bot_token="T", chat_id="-100", cameras=[camera_config]
        )
        now = datetime(2026, 11, 14, 12, 30)
        img = Image.new("RGB", (192, 108))

        with mock.patch.object(entry, "get_snapshot", return_value=img), mock.patch.object(
            entry, "fetch_temperature", return_value="38 °C"
        ):
            item = entry.capture(camera_config, settings, now)

        self.assertEqual(item.caption, "Entrance — 14.11.2026 12:30 · 38 °C")

    def test_capture_without_temperature(self) -> None:
        camera_config = config.Camera(
            name="camera_1", title="Entrance", url="http://host/a.jpg"
        )
        settings = config.Config(
            bot_token="T", chat_id="-100", cameras=[camera_config]
        )
        now = datetime(2026, 11, 14, 12, 30)
        img = Image.new("RGB", (192, 108))

        with mock.patch.object(entry, "get_snapshot", return_value=img), mock.patch.object(
            entry, "fetch_temperature"
        ) as fetch:
            item = entry.capture(camera_config, settings, now)

        fetch.assert_not_called()
        self.assertEqual(item.caption, "Entrance — 14.11.2026 12:30")


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
