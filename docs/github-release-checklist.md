# GitHub Release Checklist

Use this checklist before publishing the repository. This project can contain LLM keys, X.com cookies, WeCom webhooks, personal research files, and database caches, so treat release hygiene as part of the work.

## 1. Confirm Sensitive Files Are Not Tracked

These must not be tracked by Git:

- `.env`
- `.env.local`
- `frontend/.env.local`
- `.claude/`
- `.agents/`
- `.codex-tmp/`
- database dumps, Redis dumps, and local logs
- annual-report or research-report PDF caches
- personal stock-analysis JSON files and temporary import scripts

Check:

```bash
git status --short
git ls-files .env .env.local frontend/.env.local .claude .agents .codex-tmp
```

If a sensitive path is tracked, remove it from the Git index while keeping the local file:

```bash
git rm --cached <path>
```

## 2. Search for Secrets

```bash
git grep -n -i "api_key\|auth_token\|ct0\|bearer\|webhook\|secret\|password" -- . ':!*.example' ':!docs/*'
```

Field names and placeholders are acceptable. Real keys, cookies, tokens, or webhook URLs must be removed and rotated.

High-risk values:

- OpenRouter, OpenAI, Anthropic, or DeepSeek API keys
- X.com `auth_token` and `ct0`
- WeCom webhook URLs
- database passwords
- `SECRET_KEY`

## 3. Review Ignore Rules

`.gitignore` should cover:

- Python caches, virtual environments, pytest and ruff caches
- Node dependencies and Next.js build output
- environment files
- crawler and runtime data
- local logs and dumps
- personal analysis JSON files
- local assistant or editor state

Check untracked files:

```bash
git status --short --untracked-files=all
```

## 4. Review Documentation

Minimum public docs:

- `README.md`
- `.env.example`
- `docs/deployment.md`
- `docs/development.md`
- `docs/data-sources.md`
- `docs/data-flow.md`
- `docs/github-release-checklist.md`

Make sure README ports and commands match `docker-compose.yml`.

## 5. Smoke Test

```bash
docker compose config
docker compose up -d --build
docker compose exec backend uv run alembic upgrade head
docker compose ps
curl -sf http://localhost:8500/docs >/dev/null
curl -sf http://localhost:3010 >/dev/null
```

Build-only option:

```bash
docker compose config
docker compose build backend frontend x-crawler
```

## 6. Tests and Static Checks

Backend:

```bash
docker compose exec backend uv run pytest
docker compose exec backend uv run ruff check app tests
```

Frontend:

```bash
docker compose exec frontend pnpm type-check
docker compose exec frontend pnpm build
```

If any check is intentionally skipped or currently failing, mention that in the release notes.

## 7. License

Add a `LICENSE` file before making the repository public if you want others to use the code under an open-source license.

Common choices:

- MIT: simple and permissive.
- Apache-2.0: permissive with patent language.
- No license: all rights reserved by default.

## 8. Suggested First Commit

```bash
git add README.md .gitignore .env.example docker-compose.yml backend frontend x-crawler docs scripts
git status --short
git commit -m "Prepare project for GitHub release"
```

Run the secret scan again before committing. If a real secret was ever committed, deleting it is not enough: rotate the secret and rewrite the Git history before publishing.
