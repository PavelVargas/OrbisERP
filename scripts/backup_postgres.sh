#!/usr/bin/env sh
set -eu

if [ -n "${DATABASE_URL:-}" ]; then
    PG_URL="$(printf '%s' "$DATABASE_URL" | sed 's#^postgresql+psycopg://#postgresql://#')"
else
    : "${POSTGRES_PASSWORD:?DATABASE_URL o POSTGRES_PASSWORD es obligatorio}"
    PG_URL="postgresql://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD}@${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-db_inventario}"
fi

BACKUP_DIR="${BACKUP_DIR:-./backups}"
UPLOADS_DIR="${UPLOADS_DIR:-/uploads}"
PRIVATE_STORAGE_DIR="${PRIVATE_STORAGE_DIR:-/private_storage}"
MIRROR_DIR="${BACKUP_MIRROR_DIR:-}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
mkdir -p "$BACKUP_DIR"
BACKUP_DIR="$(cd "$BACKUP_DIR" && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP="$BACKUP_DIR/orbiserp_${STAMP}.dump"
UPLOADS_ARCHIVE="$BACKUP_DIR/orbiserp_uploads_${STAMP}.tar.gz"
PRIVATE_ARCHIVE="$BACKUP_DIR/orbiserp_private_${STAMP}.tar.gz"
MANIFEST="$BACKUP_DIR/orbiserp_${STAMP}.sha256"

cleanup_partial() {
    rm -f "$DUMP.part" "$UPLOADS_ARCHIVE.part" "$PRIVATE_ARCHIVE.part" "$MANIFEST.part"
}
trap cleanup_partial EXIT INT TERM

# Write to temporary names first. A backup only becomes visible as successful
# after pg_restore/tar integrity checks and checksum generation complete.
pg_dump --format=custom --no-owner --no-acl --file="$DUMP.part" "$PG_URL"
pg_restore --list "$DUMP.part" >/dev/null
mv "$DUMP.part" "$DUMP"

FILES="$DUMP"
if [ -d "$UPLOADS_DIR" ]; then
    tar -czf "$UPLOADS_ARCHIVE.part" -C "$UPLOADS_DIR" .
    tar -tzf "$UPLOADS_ARCHIVE.part" >/dev/null
    mv "$UPLOADS_ARCHIVE.part" "$UPLOADS_ARCHIVE"
    FILES="$FILES $UPLOADS_ARCHIVE"
fi
if [ -d "$PRIVATE_STORAGE_DIR" ]; then
    tar -czf "$PRIVATE_ARCHIVE.part" -C "$PRIVATE_STORAGE_DIR" .
    tar -tzf "$PRIVATE_ARCHIVE.part" >/dev/null
    mv "$PRIVATE_ARCHIVE.part" "$PRIVATE_ARCHIVE"
    FILES="$FILES $PRIVATE_ARCHIVE"
fi

: > "$MANIFEST.part"
for file in $FILES; do
    sha256sum "$file" >> "$MANIFEST.part"
done
mv "$MANIFEST.part" "$MANIFEST"

if [ -n "$MIRROR_DIR" ]; then
    mkdir -p "$MIRROR_DIR"
    for file in $FILES "$MANIFEST"; do
        cp "$file" "$MIRROR_DIR/"
    done
fi

find "$BACKUP_DIR" -type f -name 'orbiserp_*.dump' -mtime "+$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -type f -name 'orbiserp_uploads_*.tar.gz' -mtime "+$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -type f -name 'orbiserp_private_*.tar.gz' -mtime "+$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -type f -name 'orbiserp_*.sha256' -mtime "+$RETENTION_DAYS" -delete

printf '%s\n' "$STAMP" > "$BACKUP_DIR/.last-success"
trap - EXIT INT TERM
echo "Backup verificado: $DUMP"
