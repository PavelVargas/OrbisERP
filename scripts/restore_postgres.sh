#!/usr/bin/env sh
set -eu
: "${DATABASE_URL:?DATABASE_URL es obligatorio}"
: "${1:?Uso: scripts/restore_postgres.sh archivo.dump}"
if [ "${CONFIRM_RESTORE:-}" != "RESTORE" ]; then
  echo "Operación detenida. Ejecuta con CONFIRM_RESTORE=RESTORE después de verificar el destino."
  exit 2
fi
PG_URL="$(printf '%s' "$DATABASE_URL" | sed 's#^postgresql+psycopg://#postgresql://#')"
pg_restore --clean --if-exists --no-owner --no-acl --dbname="$PG_URL" "$1"
echo "Restauración completada. Ejecuta: flask --app app db upgrade"
