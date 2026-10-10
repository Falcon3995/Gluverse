# GluVerse Operations Runbook

## Architecture

- Flask/Gunicorn backend serves `/api/*` and the built React frontend.
- PostgreSQL is the production persistence target.
- Docker Compose provides a local production-like stack with persistent `gluverse-postgres-data`.
- One Gunicorn worker with threads is the default until the app is load-tested with PostgreSQL.

## Required Production Environment

- `APP_ENV=production`
- `FLASK_ENV=production`
- `FLASK_DEBUG=0`
- `SECRET_KEY` with at least 32 random characters
- `DATABASE_URL=postgresql://...`
- `CORS_ORIGINS` matching the browser origin exactly
- `DEMO_RESET_ENABLED=false`
- `NVIDIA_API_KEY`
- `NVIDIA_COACH_MODEL`
- `NVIDIA_SAFETY_MODEL`
- `POSTGRES_PASSWORD` when using Compose

Do not log secrets, cookies, tokens, passwords, or unnecessary health details.

## Startup Verification

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs --no-color backend
curl --fail http://127.0.0.1:5000/api/health
curl --fail http://127.0.0.1:5000/api/ready
BASE_URL=http://127.0.0.1:5000 python3 scripts/smoke_test.py
```

`/api/health` is process-level. `/api/ready` validates database usability.

## Persistence Verification

```bash
PERSISTENCE_STATE_FILE=/tmp/gluverse-smoke.json BASE_URL=http://127.0.0.1:5000 python3 scripts/smoke_test.py
docker compose restart backend
BASE_URL=http://127.0.0.1:5000 SMOKE_USERNAME="$(python3 -c 'import json;print(json.load(open("/tmp/gluverse-smoke.json"))["username"])')" SMOKE_PASSWORD="$(python3 -c 'import json;print(json.load(open("/tmp/gluverse-smoke.json"))["password"])')" python3 scripts/smoke_test.py
docker compose down
docker compose up -d
```

After container recreation, log in with the same smoke credentials and confirm the prior records remain.

## Backup

For PostgreSQL:

```bash
DATABASE_URL="postgresql://gluverse:<password>@127.0.0.1:5432/gluverse" scripts/backup_db.sh
```

For a local SQLite development database only:

```bash
scripts/backup_db.sh backend/gluverse.db
```

Store beta backups outside the application host when possible.

## Restore

Stop writes first. Restore is destructive and requires explicit confirmation:

```bash
ALLOW_RESTORE=1 scripts/restore_db.sh backups/gluverse-postgres-YYYYMMDDTHHMMSSZ.sql.gz "postgresql://gluverse:<password>@127.0.0.1:5432/gluverse"
```

After restore:

```bash
curl --fail http://127.0.0.1:5000/api/ready
BASE_URL=http://127.0.0.1:5000 python3 scripts/smoke_test.py
```

## Monitoring And Incident Response

- Watch container health, `/api/ready`, error rates, auth failures, and disk usage.
- Preserve logs with request IDs during incidents.
- If health fails but readiness passes, inspect app process logs.
- If readiness fails, inspect Postgres health, credentials, volume availability, and migrations/startup errors.
- For suspected data exposure, stop the app, preserve logs/backups, rotate secrets, and notify affected beta users according to the beta incident process.

## Integration Policy

CGM, email delivery, and AI/vendor integrations are disabled until real credentials, security review, tests, and browser/API verification are complete. The production UI must not imply these integrations are active.
