# MyStock

MyStock is a self-hosted stock research workspace for A-share, Hong Kong, and selected global supply-chain signals. It combines market data, fundamentals, research reports, disclosures, news, social feeds, and AI-assisted analysis into a local-first dashboard for watchlist monitoring, event detection, target-price research, and daily review.

> This project is still evolving. Before publishing or deploying it, carefully review `.env`, database dumps, analysis JSON files, X/Twitter cookies, LLM API keys, and webhook URLs.

## Features

- Watchlist management for A-share and Hong Kong stocks.
- Daily K-line history, realtime quote cache, and technical indicators.
- TTM fundamentals, quarterly financials, forecasts, and research metadata.
- Sell-side research metadata, PDF processing, explicit target-price extraction, and web-search supplements.
- CNInfo and EastMoney disclosure ingestion, earnings calendar, restricted-share release events, insider-trade extraction, and event detection.
- News pipeline with entity matching, deduplication, rule scoring, LLM scoring, urgency classification, and optional WeCom notifications.
- X.com timeline crawler for configured KOL accounts using Playwright and a Redis queue.
- AI-generated daily summaries, event reports, supply-chain extraction, segment extraction, and industry metrics.

## Tech Stack

- Backend: FastAPI, SQLAlchemy 2, Alembic, Celery, Redis, PostgreSQL, uv
- Frontend: Next.js 14, React 18, TypeScript, Tailwind CSS, ECharts, lightweight-charts
- Data/crawling: AKShare, yfinance, httpx, Playwright, PyMuPDF
- AI providers: DeepSeek, OpenRouter, OpenAI, Anthropic
- Runtime: Docker Compose

## Repository Layout

```text
.
|-- backend/          # FastAPI API, Celery tasks, data ingestion, AI services, database models
|-- frontend/         # Next.js frontend
|-- x-crawler/        # Standalone X.com timeline crawler
|-- docs/             # Architecture, data sources, deployment, and release notes
|-- scripts/          # Operational helper scripts
|-- docker-compose.yml
`-- .env.example
```

## Quick Start

### 1. Prerequisites

Install:

- Docker Desktop or Docker Engine
- Docker Compose v2
- Optional for non-container development: Node.js 22, pnpm 10, Python 3.12, uv

### 2. Configure environment variables

```bash
cp .env.example .env
```

At minimum, review or change:

- `SECRET_KEY`
- `POSTGRES_PASSWORD`
- One LLM provider key, such as `DEEPSEEK_API_KEY` or `OPENROUTER_API_KEY`
- Optional notification webhook: `WECHAT_WORK_WEBHOOK_URL`
- Optional X.com crawler settings: `X_AUTH_TOKEN`, `X_CT0_TOKEN`, `X_KOL_HANDLES`

### 3. Start services

```bash
docker compose up -d --build
```

Default ports:

- Frontend: http://localhost:3010
- Backend API: http://localhost:8500
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### 4. Run migrations

```bash
docker compose exec backend uv run alembic upgrade head
```

### 5. Common commands

```bash
# Show services
docker compose ps

# Backend logs
docker compose logs -f backend

# Data worker logs
docker compose logs -f celery-data-worker

# Beat scheduler logs
docker compose logs -f celery-beat

# Stop services
docker compose down
```

## Documentation

- [Deployment guide](docs/deployment.md)
- [Development guide](docs/development.md)
- [Data sources](docs/data-sources.md)
- [Data flow](docs/data-flow.md)
- [MCP data dictionary](docs/mcp-data-dictionary.md)
- [GitHub release checklist](docs/github-release-checklist.md)

## Security Notes

Never commit:

- `.env`, `.env.local`, or real API keys/cookies
- X.com `auth_token` or `ct0`
- WeCom webhook URLs
- Database dumps, Redis dumps, local logs, report caches, or PDF caches
- Personal stock-analysis JSON files, temporary import scripts, or AI output caches

Recommended pre-release checks:

```bash
git status --short
git diff -- .env.example .gitignore README.md docs
git grep -n -i "api_key\|auth_token\|ct0\|webhook\|secret\|password" -- . ':!*.example' ':!docs/*'
```

## License

No license is declared yet. Add a `LICENSE` file before making the repository public if you want others to use the code under an open-source license.
