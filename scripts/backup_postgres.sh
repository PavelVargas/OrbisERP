#!/usr/bin/env sh
set -eu
: "${DATABASE_URL:?DATABASE_URL es obligatorio}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$BACKUP_DIR/orbiserp_${STAMP}.dump"
PG_URL="$(printf '%s' "$DATABASE_URL" | sed 's#^postgresql+psycopg://#postgresql://#')"
pg_dump --format=custom --no-owner --no-acl --file="$TARGET" "$PG_URL"
find "$BACKUP_DIR" -type f -name 'orbiserp_*.dump' -mtime "+$RETENTION_DAYS" -delete
echo "Backup creado: $TARGET"
