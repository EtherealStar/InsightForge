api:      python -m delivery.server
worker:   celery -A scheduler.celery_app worker -l info -P threads
beat:     celery -A scheduler.celery_app beat -l info
frontend: cd frontend && pnpm dev
