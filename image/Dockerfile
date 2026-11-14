FROM python:3.12-alpine

ARG SUPERCRONIC_VERSION=v0.2.33
ARG TARGETARCH=amd64

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apk add --no-cache ffmpeg ca-certificates curl tzdata \
 && curl -fsSLo /usr/local/bin/supercronic \
      "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH}" \
 && chmod +x /usr/local/bin/supercronic

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY image/docker-entrypoint.sh .

RUN chmod +x docker-entrypoint.sh \
 && adduser -D -H -u 1000 app \
 && chown -R app:app /app

USER app

ENTRYPOINT ["./docker-entrypoint.sh"]
