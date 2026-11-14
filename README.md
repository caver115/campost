# campost

Posts hourly snapshots from several cameras to one Telegram channel as a single
album.

## Layout

| File | Purpose |
| --- | --- |
| `app/__main__.py` | CLI, capture and send orchestration |
| `app/config.py` | env variables and `urls.txt` parsing |
| `app/camera.py` | snapshot download with retries |
| `app/imaging.py` | 16:9 crop/pad and JPEG encoding |
| `app/telegram.py` | `sendPhoto`, `sendMediaGroup`, failure notifications |
| `urls.example.txt` | camera list template |
| `urls.txt` | local camera list (gitignored, created from the template) |
| `docker-compose.yml` | service definition (state, volumes, schedule) |
| `image/` | Dockerfile, entrypoint, build ignore rules |
| `tests/` | unit tests |

## Camera list

Copy the template and fill in real camera addresses:

```bash
cp urls.example.txt urls.txt
```

One camera per line. An optional caption can be given before a `|`:

```text
Entrance | http://192.168.1.10/image.jpg
Yard | rtsp://user:password@192.168.1.11:554/stream1
http://192.168.1.12/webcapture.jpg?command=snap&channel=1
```

HTTP(S) URLs are downloaded directly. RTSP URLs are grabbed with `ffmpeg`
(one frame over TCP), which usually yields the main stream instead of the
low-resolution HTTP snapshot; `ffmpeg` must be installed locally and is already
included in the Docker image.

File names and `name` values are derived from the line order (`camera_1`,
`camera_2`, ...), captions use the text before `|` or `Camera N`.

## Local run

```bash
cp .env.example .env           # fill in BOTPOST_BOT_TOKEN and BOTPOST_CHANNEL_ID
cp urls.example.txt urls.txt   # fill in real camera addresses
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# dry run: save snapshots locally, do not contact Telegram
python -m app --dry-run --out out

# real run
python -m app
```

Telegram credentials are read from environment variables, so either export them
or use a tool like `direnv` / `set -a; . .env; set +a`.

## Docker

```bash
cp .env.example .env
cp urls.example.txt urls.txt
docker compose up -d --build
docker compose logs -f

# one-off run without waiting for the schedule
docker compose run --rm campost python -m app
```

The container runs supercronic with the schedule from
`BOTPOST_INTERVAL_CRON` (default `0 * * * *`). If the container is down at the
scheduled minute, that run is skipped.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Behaviour notes

- Both cameras are fetched independently; a failing camera does not block the
  other one. HTTP(S) sources are downloaded directly, RTSP sources are captured
  with `ffmpeg -rtsp_transport tcp -frames:v 1`.
- Credentials in URLs are masked in logs.
- Two or more photos are sent as one album via `sendMediaGroup`. If only one
  camera responds, the photo is sent with `sendPhoto`.
- If Telegram rejects the album, the photos are sent separately.
- When no snapshot could be captured (or a camera fails while
  `BOTPOST_NOTIFY_FAILURES=true`), a short message is posted to the same channel.
- Images are cropped to 16:9 (edge cut, not stretched). Switch to letterbox
  padding by calling `fit_to_16_9(img, mode="pad")`.
