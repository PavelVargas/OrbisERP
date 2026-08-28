#!/usr/bin/env sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_DIR="$(cd "$BACKUP_DIR" && pwd)"
MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-30}"
LATEST="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'orbiserp_*.dump' -print | sort | tail -n 1)"
if [ -z "$LATEST" ]; then
    echo "ERROR: no hay respaldo PostgreSQL en $BACKUP_DIR" >&2
    exit 2
fi

pg_restore --list "$LATEST" >/dev/null
STAMP="$(basename "$LATEST" .dump | sed 's/^orbiserp_//')"
MANIFEST="$BACKUP_DIR/orbiserp_${STAMP}.sha256"
if [ ! -f "$MANIFEST" ]; then
    echo "ERROR: falta manifiesto SHA-256 para $LATEST" >&2
    exit 3
fi
sha256sum -c "$MANIFEST"

NOW="$(date +%s)"
MOD="$(date -r "$LATEST" +%s)"
AGE="$(( (NOW - MOD) / 3600 ))"
if [ "$AGE" -gt "$MAX_AGE_HOURS" ]; then
    echo "ERROR: respaldo demasiado antiguo (${AGE}h > ${MAX_AGE_HOURS}h)" >&2
    exit 4
fi

echo "Backup OK: $LATEST (${AGE}h)"
