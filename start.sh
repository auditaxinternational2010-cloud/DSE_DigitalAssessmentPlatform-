#!/bin/sh
set -e
python manage.py migrate --noinput
exec gunicorn eya_questionnaire.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --threads 4 \
    --worker-class gthread \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
