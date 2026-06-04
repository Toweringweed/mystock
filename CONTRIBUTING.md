# Contributing

Thanks for improving MyStock. This repository mixes application code, data ingestion, automation, and AI workflows, so small changes can have wide operational effects.

## Development Workflow

1. Read README.md and docs/development.md.
2. Keep changes focused and avoid unrelated refactors.
3. Update docs when changing deployment, data sources, environment variables, or scheduled jobs.
4. Run the relevant checks before committing.

## Recommended Checks

Backend: docker compose exec backend uv run pytest
Backend lint: docker compose exec backend uv run ruff check app tests
Frontend type check: docker compose exec frontend pnpm type-check
Frontend build: docker compose exec frontend pnpm build
Compose config: docker compose config

## Data Source Changes

When adding or removing a data source:

- update docs/data-sources.md
- add defensive parsing for field changes
- preserve retries, rate limits, and useful logs
- make optional sources fail closed without blocking core refresh jobs

## Secrets

Never commit secrets or local state:

- .env files
- API keys
- X.com cookies
- webhook URLs
- database dumps
- local analysis JSON files

Run docs/github-release-checklist.md before opening a public PR or publishing the repository.
