#!/usr/bin/env sh
set -eu
flask --app app db upgrade
flask --app app check-production
if [ "${STARTUP_INTEGRITY_CHECK:-1}" = "1" ]; then
    flask --app app audit-integrity
    flask --app app validate-integrity
fi
exec gunicorn --config gunicorn.conf.py app:app
