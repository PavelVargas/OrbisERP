#!/usr/bin/env sh
set -eu
flask --app app check-production
flask --app app audit-integrity
flask --app app validate-integrity
flask --app app maintenance-check --strict
if command -v pg_restore >/dev/null 2>&1 && [ -d "${BACKUP_DIR:-./backups}" ]; then
    /scripts/verify_backup.sh 2>/dev/null || scripts/verify_backup.sh
fi
