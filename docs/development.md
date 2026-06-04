# Development Guide

This document describes the main development entry points, directory responsibilities, and common commands.

## Layout

```text
backend/
  app/api/          # FastAPI routes
  app/core/         # settings, database, shared infrastructure
  app/models/       # SQLAlchemy models
  app/schemas/      # Pydantic schemas
  app/services/     # market data, research, news, AI, business services
  app/tasks/        # Celery tasks and schedule configuration
  alembic/          # database migrations
  tests/            # backend tests

frontend/
  app/              # Next.js app router pages
  components/       # UI components
  lib/              # API clients and utilities

x-crawler/
  crawler.py        # X.com timeline crawler
```

## Backend Development

Container-first workflow:

```bash
docker compose exec backend sh
uv run fastapi dev app/main.py --host 0.0.0.0 --port 8000
```

Common commands:

```bash
uv run pytest
uv run ruff check app tests
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

When adding a config value:

1. Update `backend/app/core/config.py`.
2. Update `.env.example`.
3. Update `docs/deployment.md` if deployment changes.

When adding a table:

1. Add or update `backend/app/models/*`.
2. Generate an Alembic migration.
3. Review the migration before committing.
4. Update schemas, services, and APIs as needed.

## Frontend Development

Container workflow:

```bash
docker compose exec frontend sh
pnpm dev
```

Local workflow:

```bash
cd frontend
corepack enable
corepack prepare pnpm@10.33.4 --activate
pnpm install
pnpm dev
```

Common commands:

```bash
pnpm type-check
pnpm build
```

The frontend reads backend data through `SERVER_API_URL`. Docker Compose defaults to `http://host.docker.internal:8500`.

## Celery Jobs

Task files:

- `backend/app/tasks/data_tasks.py`
- `backend/app/tasks/news_tasks.py`
- `backend/app/tasks/analysis_tasks.py`
- `backend/app/tasks/supply_chain_tasks.py`
- `backend/app/tasks/earnings_tasks.py`

Schedule configuration:

- `backend/app/tasks/celery_app.py`

Manual task examples:

```bash
docker compose exec backend uv run celery -A app.tasks.celery_app call app.tasks.data_tasks.refresh_watchlist_data
docker compose exec backend uv run celery -A app.tasks.celery_app call app.tasks.news_tasks.crawl_research_reports
```

Logs:

```bash
docker compose logs -f celery-worker
docker compose logs -f celery-data-worker
docker compose logs -f celery-beat
```

## Data Ingestion Guidelines

- Public data-source fields change often; parse defensively.
- AKShare is synchronous; call it from async code with `asyncio.to_thread`.
- Keep rate limits and retry policies for high-frequency sources.
- Prefer graceful degradation over blocking an entire refresh chain.
- Update `docs/data-sources.md` when adding or removing sources.

## AI Integration Guidelines

- Use cheap and fast models for bulk L1 tasks.
- Reserve stronger models for L2 deep analysis or high-impact events.
- Validate structured LLM outputs before writing to the database.
- Web-search supplements must be optional and must not block core refresh jobs.

## Release Checks

See [GitHub release checklist](github-release-checklist.md).
