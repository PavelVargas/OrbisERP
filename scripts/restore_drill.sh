#!/usr/bin/env sh
set -eu

: "${RESTORE_TEST_DATABASE_URL:?Configura RESTORE_TEST_DATABASE_URL con una base EXCLUSIVA de simulacro}"
: "${1:?Uso: scripts/restore_drill.sh archivo.dump}"
if [ "${CONFIRM_RESTORE_DRILL:-}" != "RESTORE_TEST_ONLY" ]; then
    echo "Operación detenida. Define CONFIRM_RESTORE_DRILL=RESTORE_TEST_ONLY." >&2
    exit 2
fi
if [ -n "${DATABASE_URL:-}" ] && [ "$RESTORE_TEST_DATABASE_URL" = "$DATABASE_URL" ]; then
    echo "ERROR: RESTORE_TEST_DATABASE_URL no puede ser DATABASE_URL de producción." >&2
    exit 3
fi

TEST_URL="$(printf '%s' "$RESTORE_TEST_DATABASE_URL" | sed 's#^postgresql+psycopg://#postgresql://#')"
pg_restore --list "$1" >/dev/null
pg_restore --clean --if-exists --no-owner --no-acl --dbname="$TEST_URL" "$1"
psql "$TEST_URL" -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null
psql "$TEST_URL" -v ON_ERROR_STOP=1 -c 'SELECT version_num FROM alembic_version' >/dev/null
echo "Simulacro de restauración completado en la base exclusiva de pruebas."
