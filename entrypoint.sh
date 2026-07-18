#!/bin/bash
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Creating admin user..."
bash admin-create.sh

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Daphne server..."
exec daphne -b 0.0.0.0 -p 8000 core.asgi:application