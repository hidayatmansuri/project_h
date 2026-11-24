#!/bin/sh
set -e

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Syncing projectauth protected apps..."
python manage.py projectauth_sync_apps

echo "Starting Gunicorn on 0.0.0.0:${PORT:-8000}..."
exec gunicorn project_h.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout 120 \
    --max-requests 500 \
    --max-requests-jitter 50 \
    --access-logfile - \
    --error-logfile -
