# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend-builder

WORKDIR /app/frontend

RUN corepack enable

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/ ./agent/
COPY core/ ./core/
COPY delivery/ ./delivery/
COPY infrastructure/ ./infrastructure/
COPY migrations/ ./migrations/
COPY models/ ./models/
COPY scheduler/ ./scheduler/
COPY services/ ./services/
COPY storage/ ./storage/

COPY --from=frontend-builder /app/delivery/static ./delivery/static

RUN mkdir -p data output

EXPOSE 8005

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8005/api/health || exit 1

CMD ["python", "-m", "delivery.server"]
