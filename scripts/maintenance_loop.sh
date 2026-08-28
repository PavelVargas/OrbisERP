#!/usr/bin/env sh
set -u
INTERVAL="${MAINTENANCE_INTERVAL_SECONDS:-86400}"
while true; do
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] OrbisERP maintenance"
    flask --app app maintenance-clean --retention-days "${MAINTENANCE_RETENTION_DAYS:-30}" || true
    flask --app app maintenance-check --no-strict || true
    if [ -x /scripts/verify_backup.sh ]; then
        /scripts/verify_backup.sh || true
    elif [ -x scripts/verify_backup.sh ]; then
        scripts/verify_backup.sh || true
    fi
    sleep "$INTERVAL"
done
