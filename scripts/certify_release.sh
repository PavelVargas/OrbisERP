#!/usr/bin/env sh
set -eu

if [ -z "${TEST_DATABASE_URL:-}" ]; then
    echo "ERROR: TEST_DATABASE_URL debe apuntar a PostgreSQL exclusivo de pruebas para certificar un release." >&2
    echo "Usa ALLOW_PARTIAL_CERTIFICATION=1 solo para una revisión estática/local que NO certifica PostgreSQL." >&2
    if [ "${ALLOW_PARTIAL_CERTIFICATION:-0}" != "1" ]; then
        exit 2
    fi
fi

python scripts/release_identity.py
python scripts/static_release_audit.py
python scripts/ui_consistency_audit.py
python scripts/client_ui_audit.py
python scripts/sales_pos_release_audit.py
python scripts/transfer_scanner_release_audit.py

if [ -n "${TEST_DATABASE_URL:-}" ]; then
    # Force every dynamic certification command onto the disposable test DB.
    export DATABASE_URL="$TEST_DATABASE_URL"
    export APP_ENV=testing
    export AUTO_CREATE_SCHEMA=0
    flask --app app db upgrade
    flask --app app audit-integrity
    flask --app app validate-integrity
    pytest -q -rs --ignore=tests/e2e
else
    echo "AVISO: certificación parcial; se omiten DB/HTTP por falta de TEST_DATABASE_URL."
    pytest -q tests/test_retail_platform.py
fi

if [ "${CERTIFY_PRODUCTION_CONFIG:-0}" = "1" ]; then
    flask --app app check-production
fi

mkdir -p dist
VERSION="$(cat VERSION | tr -d '\r\n')"
ARCHIVE="dist/OrbisERP_${VERSION}_commercial.zip"
python scripts/build_release.py --output "$ARCHIVE" --root-name OrbisERP
python scripts/verify_release.py "$ARCHIVE"
echo "Certificación completada: $ARCHIVE"
