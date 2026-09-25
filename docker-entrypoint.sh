#!/bin/sh
# Container entrypoint: apply database migrations, then hand off to the CMD
# (gunicorn). `exec` keeps the server as PID 1 so it receives stop signals.
set -e

python manage.py migrate --noinput

exec "$@"
