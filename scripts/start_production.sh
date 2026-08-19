#!/usr/bin/env sh
set -eu
flask --app app db upgrade
exec gunicorn --config gunicorn.conf.py app:app

