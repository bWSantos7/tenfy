#!/bin/bash
set -e

echo "=== Worker iniciando ==="
echo "Python: $(python --version)"
echo "Celery: $(python -m celery --version)"

echo "=== Migrações ==="
python manage.py migrate --noinput

echo "=== Playwright Chromium ==="
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    print('Chromium OK:', b.version)
    b.close()
" && echo "Chromium pronto" || echo "Chromium FALHOU — continuando sem Playwright"

echo "=== Iniciando Celery ==="
exec python -m celery -A config worker --loglevel=info --concurrency=4 --max-tasks-per-child=100
