#!/bin/sh
set -eu

# Allow one-off commands: docker compose run --rm campost python -m app --dry-run
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

schedule="${BOTPOST_INTERVAL_CRON:-0 * * * *}"
crondir="/tmp/campost-cron"
mkdir -p "$crondir"

cat > "$crondir/crontab" <<EOF
${schedule} /usr/local/bin/python -m app ${CAMPOST_ARGS:-}
EOF

echo "campost: schedule '${schedule}'"
exec /usr/local/bin/supercronic -passthrough-logs "$crondir/crontab"
