FROM python:3.12-slim

ARG SUPERCRONIC_VERSION=v0.2.33
ARG TARGETARCH=amd64

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl ffmpeg \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN curl -fsSLo /usr/local/bin/supercronic \
      "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH}" \
 && chmod +x /usr/local/bin/supercronic

COPY app ./app
COPY image/docker-entrypoint.sh .

RUN chmod +x docker-entrypoint.sh \
 && useradd --create-home app \
 && chown -R app:app /app

USER app

ENTRYPOINT ["./docker-entrypoint.sh"]
