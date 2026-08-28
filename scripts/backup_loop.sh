#!/usr/bin/env sh
set -eu
INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
while true; do
    /scripts/backup_postgres.sh
    sleep "$INTERVAL"
done
