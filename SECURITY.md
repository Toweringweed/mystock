# Security Policy

## Supported Use

MyStock is intended for self-hosted or private deployments. Treat it as a research and automation tool, not as a regulated financial-advice system.

## Sensitive Data

Never publish or commit:

- .env files or local environment overrides
- LLM API keys
- X.com auth_token or ct0 cookies
- WeCom webhook URLs
- database or Redis dumps
- local logs and crawler caches
- personal analysis JSON files

If any secret is committed or pushed, rotate it immediately. Removing it from the latest commit is not enough if it entered Git history.

## Reporting Security Issues

For a private repository, report issues through the repository owner directly. For a public repository, open a GitHub security advisory or contact the maintainer privately before disclosing details.

## Deployment Notes

- Change SECRET_KEY and POSTGRES_PASSWORD before production use.
- Keep .env out of version control.
- Avoid exposing PostgreSQL and Redis directly to the public internet.
- Review Docker Compose proxy settings before deployment.
- Use a secondary X.com account for crawler cookies.
- Keep external notification webhooks scoped and revocable.
