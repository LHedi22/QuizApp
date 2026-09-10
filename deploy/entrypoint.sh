#!/bin/sh
set -e

case "$1" in
  web)
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
    exec gunicorn app.wsgi:application --bind 0.0.0.0:8000 --workers "${WEB_WORKERS:-3}"
    ;;
  worker)
    exec python manage.py qcluster
    ;;
  *)
    exec "$@"
    ;;
esac
