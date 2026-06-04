# Deployment Guide

This guide covers local or private-server deployment with Docker Compose. The compose stack runs PostgreSQL, Redis, FastAPI, Celery workers, Celery beat, the Next.js frontend, and the standalone X.com crawler.

## Prerequisites

- Docker Desktop or Docker Engine
- Docker Compose v2
- At least 4 GB free memory, preferably 8 GB or more
- Network access to the public data sources used by AKShare and related crawlers
- At least one LLM provider key for AI analysis and news scoring

## Environment Variables

Create a local environment file:

```bash
cp .env.example .env
```

Before any public deployment, change at least:

```env
POSTGRES_PASSWORD=replace-me
SECRET_KEY=replace-me-with-a-random-secret
ENVIRONMENT=production
```

Optional integrations:

```env
DEEPSEEK_API_KEY=
OPENROUTER_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
WECHAT_WORK_WEBHOOK_URL=
X_AUTH_TOKEN=
X_CT0_TOKEN=
X_KOL_HANDLES=
```

Never commit `.env`.

## Start the Stack

```bash
docker compose up -d --build
```

Default ports:

| Service | URL |
| --- | --- |
| Frontend | http://localhost:3010 |
| Backend API | http://localhost:8500 |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

## Database Migration

Run migrations after first startup or schema changes:

```bash
docker compose exec backend uv run alembic upgrade head
```

Check current revision:

```bash
docker compose exec backend uv run alembic current
```

## Background Services

| Service | Purpose |
| --- | --- |
| `celery-worker` | Default queue for AI, PDF, and news-processing work. |
| `celery-data-worker` | Dedicated `data` queue for market data and core refresh jobs. |
| `celery-beat` | Scheduler for periodic jobs. |
| `x-crawler` | Playwright crawler for X.com timelines, writing to Redis. |

Useful logs:

```bash
docker compose logs -f celery-worker
docker compose logs -f celery-data-worker
docker compose logs -f celery-beat
docker compose logs -f x-crawler
```

## Operations

```bash
# Show services
docker compose ps

# Restart one service
docker compose restart backend

# Open a backend shell
docker compose exec backend sh

# Trigger watchlist refresh
docker compose exec backend uv run celery -A app.tasks.celery_app call app.tasks.data_tasks.refresh_watchlist_data

# Stop services but keep volumes
docker compose down

# Stop and delete volumes; use with care
docker compose down -v
```

## Proxy Notes

`docker-compose.yml` currently sets proxy variables for backend and worker containers:

```env
HTTP_PROXY=http://host.docker.internal:7897
HTTPS_PROXY=http://host.docker.internal:7897
NO_PROXY=localhost,127.0.0.1,postgres,redis
```

If your host does not expose that proxy port, remove or adjust those variables. Some domestic data-source calls deliberately clear proxy variables inside the fetcher to avoid proxy-related failures.

## X.com Crawler

The `x-crawler` service uses Playwright and login cookies, not the official X API. Configure:

```env
X_AUTH_TOKEN=
X_CT0_TOKEN=
X_KOL_HANDLES=handle1,handle2
X_CRAWL_INTERVAL_MINUTES=30
```

Use a secondary account and keep the interval conservative. Do not commit cookies.

## Smoke Test

```bash
docker compose config
docker compose up -d --build
docker compose exec backend uv run alembic upgrade head
docker compose ps
curl -sf http://localhost:8500/docs >/dev/null
curl -sf http://localhost:3010 >/dev/null
```

If you only want to validate build configuration:

```bash
docker compose config
docker compose build backend frontend x-crawler
```

## Troubleshooting

### Frontend loads but API calls fail

Check backend status and `SERVER_API_URL`:

```bash
docker compose ps backend
docker compose logs -f backend
```

The frontend container defaults to `SERVER_API_URL=http://host.docker.internal:8500`.

### Data refresh fails

Check worker logs first:

```bash
docker compose logs -f celery-data-worker
docker compose logs -f celery-worker
```

Then check network, proxy settings, and whether the upstream data source changed fields or rate-limited requests.

### Scheduled jobs do not run

Check beat and Redis:

```bash
docker compose ps celery-beat redis
docker compose logs -f celery-beat
```
